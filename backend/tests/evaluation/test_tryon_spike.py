from __future__ import annotations

import base64
from collections import Counter
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import httpx
from PIL import Image
import pytest

from tests.evaluation.tryon_spike import (
    ALL_PROVIDERS,
    FASHN_MODEL_ID,
    FLUX_MODEL_ID,
    FalClient,
    GarmentRef,
    SpikeGarment,
    blind_labels,
    build_flux_prompt,
    build_garment_composite,
    estimate_flux_cost_usd,
    fit_within_pixels,
    percentile,
    run_fashn_case,
    run_flux_case,
    select_tryon_garments,
    summarize_ratings,
    summarize_runs,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend" / "scripts" / "spike_tryon_providers.py"
SECRET = "fal-secret-key-123"
CDN = "https://cdn.example.test"


def _image(size: tuple[int, int], color: tuple[int, ...] = (200, 30, 30), mode: str = "RGB", fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def _garment(category: str, item_id: str | None = None, **attrs: str) -> SpikeGarment:
    ref = GarmentRef(item_id=item_id or f"id-{category}", category=category, **attrs)
    return SpikeGarment(ref=ref, image_bytes=_image((120, 160)))


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("spike_tryon_providers", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeFal:
    """Records requests; answers model calls with CDN URLs and serves CDN images."""

    def __init__(self, fail_on_call: int | None = None, status: int = 429) -> None:
        self.requests: list[httpx.Request] = []
        self.fail_on_call = fail_on_call
        self.status = status
        self.model_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "cdn.example.test":
            return httpx.Response(200, content=_image((64, 96), fmt="JPEG"))
        self.model_calls += 1
        if self.fail_on_call == self.model_calls:
            return httpx.Response(self.status, text=f"quota exceeded for key {SECRET}")
        return httpx.Response(200, json={"images": [{"url": f"{CDN}/out_{self.model_calls}.jpg"}], "seed": 7})

    def model_payloads(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests if r.url.host != "cdn.example.test"]


def _client(fake: FakeFal) -> FalClient:
    return FalClient(SECRET, transport=httpx.MockTransport(fake))


def test_select_garments_matches_tryon_service_rule() -> None:
    top, outer, bottom = GarmentRef("t", "top"), GarmentRef("o", "outerwear"), GarmentRef("b", "bottom")
    shoes, bag = GarmentRef("s", "footwear"), GarmentRef("a", "accessory")
    assert select_tryon_garments([top, outer, bottom, shoes, bag]) == [outer, bottom]
    assert select_tryon_garments([outer, top, bottom]) == [outer, bottom]
    assert select_tryon_garments([top, GarmentRef("t2", "top"), bottom]) == [top, bottom]
    dress = GarmentRef("d", "dress")
    assert select_tryon_garments([outer, dress, shoes]) == [dress]
    assert select_tryon_garments([shoes, bag]) == []


def test_prompts_name_garments_from_recorded_attributes_only() -> None:
    upper = GarmentRef("t", "top", sub_category="button_down_shirt", primary_color="white", pattern="solid")
    lower = GarmentRef("b", "bottom", sub_category="chinos", primary_color="navy", pattern="striped")
    flux = build_flux_prompt([upper, lower])
    assert "the white button down shirt (left) on the upper body" in flux
    assert "the navy striped chinos (right) on the lower body" in flux
    dress = GarmentRef("d", "dress", sub_category="midi_dress", primary_color="unknown")
    assert "Dress the person in the midi dress shown" in build_flux_prompt([dress])
    with pytest.raises(ValueError):
        build_flux_prompt([])


def test_composite_is_left_to_right_on_white_and_within_pixel_budget() -> None:
    red = _image((300, 400), (255, 0, 0))
    transparent_blue = _image((200, 400), (0, 0, 255, 0), mode="RGBA")
    composite = Image.open(BytesIO(build_garment_composite([red, transparent_blue], max_pixels=120_000)))
    width, height = composite.size
    assert width * height <= 120_000
    left = composite.getpixel((int(width * 0.25), height // 2))
    right = composite.getpixel((int(width * 0.8), height // 2))
    assert left[0] > 200 and left[2] < 60  # red garment on the left
    assert min(right) > 230  # transparent pixels flattened to white, not black


def test_person_image_is_reduced_below_one_megapixel() -> None:
    fitted = Image.open(BytesIO(fit_within_pixels(_image((896, 1200)), 1_000_000)))
    assert fitted.size[0] * fitted.size[1] <= 1_000_000
    assert fitted.format == "JPEG"
    assert abs(fitted.size[0] / fitted.size[1] - 896 / 1200) < 0.01


def test_flux_cost_matches_fal_worked_example() -> None:
    assert estimate_flux_cost_usd([(1024, 1024), (1024, 1024)], (1024, 1024)) == 0.0475
    # The 896x1200 preset is slightly above one billed megapixel, hence the downscale.
    assert estimate_flux_cost_usd([(896, 1200), (500, 500)], (896, 1200)) == 0.0575


def test_fashn_chains_passes_and_never_sends_the_key_to_the_cdn() -> None:
    fake = FakeFal()
    run = run_fashn_case(_client(fake), "male-01", _image((80, 120), fmt="JPEG"), [_garment("outerwear"), _garment("bottom")])
    assert run.success and run.output_size == (64, 96)
    payloads = fake.model_payloads()
    assert [p["category"] for p in payloads] == ["tops", "bottoms"]
    assert payloads[0]["model_image"].startswith("data:image/jpeg;base64,")
    assert payloads[1]["model_image"] == f"{CDN}/out_1.jpg"  # pass 2 wears pass 1's output
    assert all(r.url.path == f"/{FASHN_MODEL_ID}" for r in fake.requests if r.url.host == "fal.run")
    for request in fake.requests:
        assert ("authorization" in request.headers) == (request.url.host == "fal.run")
    assert run.estimated_cost_usd == 0.15
    assert [c.stage for c in run.calls] == ["pass1:tops", "pass2:bottoms", "download"]


def test_fashn_failure_is_recorded_without_the_key_and_charges_only_successes() -> None:
    fake = FakeFal(fail_on_call=2)
    run = run_fashn_case(_client(fake), "male-02", _image((80, 120), fmt="JPEG"), [_garment("top"), _garment("bottom")])
    assert not run.success and run.output_bytes is None
    failed = run.calls[-1]
    assert failed.http_status == 429 and failed.error_type == "HTTPStatusError"
    assert SECRET not in (failed.error_message or "") and "***" in (failed.error_message or "")
    assert run.estimated_cost_usd == 0.075
    assert SECRET not in json.dumps(run.to_dict(None))


def test_flux_makes_one_call_with_composite_and_prompt() -> None:
    fake = FakeFal()
    garments = [_garment("top", sub_category="tee", primary_color="grey"), _garment("bottom", sub_category="jeans")]
    run = run_flux_case(_client(fake), "female-04", fit_within_pixels(_image((896, 1200))), garments)
    assert run.success
    (payload,) = fake.model_payloads()
    assert payload["human_image_url"].startswith("data:image/jpeg;base64,")
    composite = Image.open(BytesIO(base64.b64decode(payload["garment_image_url"].split(",", 1)[1])))
    assert composite.size[0] > composite.size[1]  # two garments side by side
    assert "grey tee (left)" in payload["prompt"] and payload["prompt"] == run.prompt
    assert run.model_id == FLUX_MODEL_ID and run.estimated_cost_usd == 0.0475


def test_transport_error_is_recorded_as_a_failed_run() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = FalClient(SECRET, transport=httpx.MockTransport(boom))
    run = run_flux_case(client, "male-03", _image((80, 120), fmt="JPEG"), [_garment("dress")])
    assert not run.success and run.calls[0].error_type == "ConnectTimeout" and run.estimated_cost_usd == 0.0


def test_response_without_an_image_is_one_failed_model_call() -> None:
    def no_image(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"images": [], "has_nsfw_concepts": [True]})

    run = run_flux_case(FalClient(SECRET, transport=httpx.MockTransport(no_image)), "female-02",
                        _image((80, 120), fmt="JPEG"), [_garment("dress")])
    assert not run.success and run.estimated_cost_usd == 0.0
    assert [c.stage for c in run.calls] == ["vto", "vto:parse"]
    assert summarize_runs([run.to_dict(None)])["flux"]["mean_model_calls"] == 1


def test_summaries_use_successful_outfits_for_latency_and_count_failures() -> None:
    def row(provider: str, ok: bool, ms: int, cost: float, status: int | None = None) -> dict[str, Any]:
        calls = [{"stage": "pass1:tops", "error_type": None if ok else "HTTPStatusError", "http_status": status}]
        return {"provider": provider, "success": ok, "total_latency_ms": ms, "estimated_cost_usd": cost, "calls": calls}

    runs = [row("flux", True, 4000, 0.05), row("flux", True, 6000, 0.05), row("flux", False, 900, 0.0, 429)]
    summary = summarize_runs(runs)["flux"]
    assert summary["succeeded"] == 2 and summary["success_rate"] == 0.6667
    assert summary["latency_ms_p50"] == 4000 and summary["latency_ms_p95"] == 6000
    assert summary["failures"] == {"HTTPStatusError:429": 1}
    assert summary["estimated_cost_usd_per_success"] == 0.05
    assert percentile([], 50) is None


def test_blind_labels_are_a_deterministic_balanced_permutation() -> None:
    mappings = [blind_labels(f"case-{i}", "salt", ALL_PROVIDERS) for i in range(300)]
    assert mappings == [blind_labels(f"case-{i}", "salt", ALL_PROVIDERS) for i in range(300)]
    for mapping in mappings:
        assert sorted(mapping) == ["A", "B"] and sorted(mapping.values()) == sorted(ALL_PROVIDERS)
    flux_on_a = sum(1 for mapping in mappings if mapping["A"] == "flux")
    assert 110 < flux_on_a < 190
    # The permutation is generic, so a later arm only needs another provider name.
    three = [blind_labels(f"case-{i}", "salt", ["x", "y", "z"]) for i in range(300)]
    for provider in "xyz":
        counts = Counter(label for mapping in three for label, value in mapping.items() if value == provider)
        assert all(70 < counts[label] < 130 for label in "ABC")


def test_ratings_unblind_with_the_same_provider_set() -> None:
    case, providers = "female-01", list(ALL_PROVIDERS)
    labels = {provider: label for label, provider in blind_labels(case, "s", providers).items()}
    ratings = [{"rater": "r1", "ratings": [
        {"case_id": case, "label": labels["flux"], "garment_fidelity": 4, "person_preservation": 5, "realism": 3},
        {"case_id": case, "label": labels["fashn"], "garment_fidelity": 2, "realism": 2, "unacceptable": True},
    ]}]
    result = summarize_ratings(ratings, "s", providers)
    assert result["flux"]["mean_garment_fidelity"] == 4 and result["flux"]["unacceptable_rate"] == 0
    assert result["fashn"]["mean_garment_fidelity"] == 2 and result["fashn"]["unacceptable_rate"] == 1
    assert "mean_person_preservation" not in result["fashn"]
    with pytest.raises(ValueError):
        summarize_ratings([{"ratings": [{"case_id": case, "label": "A", "realism": 6}]}], "s", providers)
    with pytest.raises(ValueError):
        summarize_ratings([{"ratings": [{"case_id": case, "label": "C", "realism": 3}]}], "s", providers)


def test_provider_order_rotates_and_provider_list_is_validated() -> None:
    script = _load_script()
    providers = ["fashn", "flux"]
    assert [script.provider_order(providers, index, 0)[0] for index in range(4)] == ["fashn", "flux"] * 2
    assert script.provider_order(providers, 0, 1) == ["flux", "fashn"]
    assert script.parse_providers("flux, fashn,flux") == ["flux", "fashn"]
    for bad in ("flux,gemini", ""):
        with pytest.raises(SystemExit):
            script.parse_providers(bad)


def test_review_page_hides_provider_identity_and_score_renders(tmp_path: Path) -> None:
    script = _load_script()
    cases = {"salt": "s", "cases": [{
        "case_id": "female-01", "garments": [{"item_id": "x", "category": "dress", "sub_category": "midi_dress",
                                              "primary_color": "red", "pattern": "solid"}],
    }]}
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    # Real run files are named after the provider; the bundle must not leak that.
    runs = [
        {"case_id": "female-01", "provider": provider, "success": True, "repeat": 0, "total_latency_ms": ms,
         "estimated_cost_usd": cost, "output_file": f"outputs/female-01_{provider}_r0.{ext}", "calls": [{"stage": "vto"}]}
        for provider, ms, cost, ext in [("fashn", 9000, 0.075, "png"), ("flux", 5000, 0.0475, "jpg")]
    ]
    for folder in ("outputs", "inputs"):
        (tmp_path / folder).mkdir()
    # As in the live run, the models return different formats, sizes and colors.
    native = {"fashn": ((864, 1157), (255, 0, 0), "PNG"), "flux": ((736, 1024), (0, 0, 255), "JPEG")}
    for run in runs:
        size, color, fmt = native[run["provider"]]
        (tmp_path / run["output_file"]).write_bytes(_image(size, color, fmt=fmt))
    (tmp_path / "inputs" / "female-01_person.jpg").write_bytes(b"p")
    (tmp_path / "inputs" / "female-01_garment1.jpg").write_bytes(b"g")
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"salt": "s", "runs": runs}), encoding="utf-8")

    script.main(["review", "--raw", str(raw), "--out-dir", str(tmp_path)])
    bundle = tmp_path / "review"
    page = (bundle / "index.html").read_text(encoding="utf-8").lower()
    shared_names = " ".join(path.name.lower() for path in bundle.rglob("*"))
    for revealing in ("fashn", "flux", "fal.ai", "bfl"):
        assert revealing not in page and revealing not in shared_names
    assert page.count("<fieldset data-rating") == 2
    mapping = blind_labels("female-01", "s", ["fashn", "flux"])
    assert sorted(p.name for p in (bundle / "images").iterdir()) == ["female-01_A.jpg", "female-01_B.jpg"]
    for label, provider in mapping.items():
        shown = Image.open(bundle / "images" / f"female-01_{label}.jpg")
        assert shown.format == "JPEG" and shown.height == 1024
        red, _, blue = shown.convert("RGB").getpixel((shown.width // 2, shown.height // 2))
        assert (red > blue) == (provider == "fashn")  # each label shows its own provider's image
    assert sorted(p.name for p in (bundle / "inputs").iterdir()) == ["female-01_garment1.jpg", "female-01_person.jpg"]

    summary = script.render_markdown(summarize_runs(runs), {})
    assert "| flux | 1/1 | 5.0 s |" in summary and "| fashn | 1/1 | 9.0 s |" in summary
