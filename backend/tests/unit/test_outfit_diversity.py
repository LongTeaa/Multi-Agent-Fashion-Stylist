from app.agents.coordinator import generate_grounded_explanation_vi
from app.agents.personalization_agent import rerank_evaluated_outfits
from app.agents.state import EvaluatedOutfit, StylistContext
from app.models.entities import OutfitSlotRole as Role
from tests.unit.test_personalization import _make_evaluated_outfit, _make_slot


def test_close_alternatives_prefer_different_core_and_preserve_best() -> None:
    top = _make_slot("top", Role.TOP, name="polo")
    bottom = _make_slot("bottom", Role.BOTTOM, name="jeans")
    shoe = _make_slot("shoe", Role.FOOTWEAR, name="sneakers")
    best = _make_evaluated_outfit("a", [top, bottom, shoe], .90)
    near = _make_evaluated_outfit("b", [top, _make_slot("bottom2", Role.BOTTOM), shoe], .89)
    distinct = _make_evaluated_outfit("c", [_make_slot("top2", Role.TOP),
                                        _make_slot("bottom3", Role.BOTTOM), shoe], .88)
    ranked, _ = rerank_evaluated_outfits([near, distinct, best], max_output=2)
    assert [i.item_id for i in ranked[0].items] == ["top", "bottom", "shoe"]
    assert [i.item_id for i in ranked[1].items] == ["top2", "bottom3", "shoe"]
    # Input permutation cannot alter deterministic selection.
    again, _ = rerank_evaluated_outfits([best, distinct, near], max_output=2)
    assert ranked == again


def test_optional_accessory_does_not_create_another_core() -> None:
    core = [_make_slot("top", Role.TOP), _make_slot("bottom", Role.BOTTOM), _make_slot("shoe", Role.FOOTWEAR)]
    ranked, _ = rerank_evaluated_outfits([
        _make_evaluated_outfit("a", core),
        _make_evaluated_outfit("b", core + [_make_slot("bag", Role.ACCESSORY)]),
    ])
    assert len(ranked) == 1


def test_diversity_does_not_replace_a_much_better_alternative() -> None:
    shoe = _make_slot("shoe", Role.FOOTWEAR)
    top = _make_slot("top", Role.TOP)
    candidates = [
        _make_evaluated_outfit("a", [top, _make_slot("bottom", Role.BOTTOM), shoe], .95),
        _make_evaluated_outfit("b", [top, _make_slot("bottom2", Role.BOTTOM), shoe], .94),
        _make_evaluated_outfit("c", [_make_slot("dress", Role.DRESS), shoe], .50),
    ]
    ranked, _ = rerank_evaluated_outfits(candidates, max_output=2)
    assert all(not any(item.slot_role == Role.DRESS for item in outfit.items) for outfit in ranked)


def test_explanation_uses_metadata_instead_of_rank_or_weather_claims() -> None:
    def make(color: str) -> EvaluatedOutfit:
        return _make_evaluated_outfit(color, [
            _make_slot("top" + color, Role.TOP, name="polo", color=color),
            _make_slot("bottom", Role.BOTTOM, name="jeans"),
            _make_slot("shoe", Role.FOOTWEAR, name="sneakers"),
        ])
    ranked, _ = rerank_evaluated_outfits([make("white"), make("black")])
    context = StylistContext(occasion="work", time_of_day="morning", weather_condition="hot")
    explanations = [generate_grounded_explanation_vi(outfit, context) for outfit in ranked]
    assert len(set(explanations)) == 2
    assert all("Áo Polo" in text and "Quần jeans" in text for text in explanations)
    assert all("thoáng mát" not in text and "mềm mại" not in text for text in explanations)
    assert generate_grounded_explanation_vi(ranked[0].model_copy(update={"rank": 3}), context) == explanations[0]
