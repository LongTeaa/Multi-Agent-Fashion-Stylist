from app.agents.fashion_agent import generate_outfit_combinations
from app.agents.personalization_agent import rerank_evaluated_outfits
from app.models.entities import OutfitSlotRole as Role, UserPreference
from tests.unit.test_personalization import _make_slot, _make_evaluated_outfit


def test_combination_budget_visits_later_garments_in_each_role() -> None:
    pool = {"tops": [_make_slot(f"t{i}", Role.TOP) for i in range(3)],
            "bottoms": [_make_slot(f"b{i}", Role.BOTTOM) for i in range(15)],
            "footwear": [_make_slot(f"f{i}", Role.FOOTWEAR) for i in range(15)],
            "outerwear": [_make_slot("outer", Role.OUTERWEAR)]}
    combinations = generate_outfit_combinations(pool)
    assert len(combinations) == 500
    assert len({tuple(item.item_id for item in items) for items in combinations}) == 500
    ids = {item.item_id for items in combinations for item in items}
    assert all(item.item_id in ids for items in pool.values() for item in items)


def test_saved_fit_changes_ranking_without_affecting_neutral_default() -> None:
    common = [_make_slot("b", Role.BOTTOM, fit="regular"), _make_slot("f", Role.FOOTWEAR)]
    slim = _make_evaluated_outfit("a", [_make_slot("slim", Role.TOP, fit="slim"), *common])
    oversized = _make_evaluated_outfit("b", [_make_slot("wide", Role.TOP, fit="oversized"), *common])
    for fit, expected in (("slim", "slim"), ("oversized", "wide")):
        ranked, _ = rerank_evaluated_outfits([slim, oversized],
            preferences=UserPreference(user_id="test", fit_preferences=[fit]))
        assert ranked[0].items[0].item_id == expected
    neutral, _ = rerank_evaluated_outfits([slim, oversized])
    assert neutral[0].personalization_score == neutral[1].personalization_score
