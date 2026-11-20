"""Clients and pure helpers for the try-on provider comparison spike.

Evaluation code only: the application never imports this module. Two arms,
both served by fal.ai under one API key:

* FASHN Try-On v1.6 via fal.ai (`fal-ai/fashn/tryon/v1.6`): a dedicated try-on
  model, one garment per call, so an upper + lower outfit is two chained calls
  (the second wears the first output), mirroring `tryon_service`.
* FLUX VTO via fal.ai (`fal-ai/flux-pro/v1/vto`): a try-on variant of a general
  image model; one garment reference image plus a prompt, so the garments are
  merged into one left-to-right composite and an outfit is one call. fal serves
  the first VTO version; Black Forest Labs recommends `vto-v2` (2026-07-17),
  which is only on its own API, so FLUX may score below its latest version.

Prices are the figures published by fal.ai on 2026-11-20 and are estimates only.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import math
from time import perf_counter
from typing import Any, Literal

import httpx
from PIL import Image

FAL_BASE_URL = "https://fal.run"
FASHN_MODEL_ID = "fal-ai/fashn/tryon/v1.6"
FLUX_MODEL_ID = "fal-ai/flux-pro/v1/vto"

FASHN_PRICE_PER_IMAGE_USD = 0.075
FLUX_FIRST_INPUT_MEGAPIXEL_USD = 0.0375
FLUX_EXTRA_INPUT_MEGAPIXEL_USD = 0.005
FLUX_OUTPUT_MEGAPIXEL_USD = 0.005
# fal's worked example (two 1024x1024 inputs + one 1024x1024 output = $0.0475)
# only holds when one billed megapixel is 2**20 pixels.
BILLED_MEGAPIXEL = 1_048_576

PERSON_MAX_PIXELS = 1_000_000  # FLUX recommends < 1 MP; both arms get the same image
COMPOSITE_MAX_PIXELS = 520_000  # FLUX recommends about 0.5 MP for the garment reference
COMPOSITE_PADDING = 24
ERROR_MESSAGE_LIMIT = 200

Provider = Literal["fashn", "flux"]
ALL_PROVIDERS: tuple[Provider, ...] = ("fashn", "flux")
FashnCategory = Literal["tops", "bottoms", "one-pieces"]

_FASHN_CATEGORY: dict[str, FashnCategory] = {
    "top": "tops",
    "outerwear": "tops",
    "bottom": "bottoms",
    "dress": "one-pieces",
}
_PRESERVE = (
    "Keep the person's face, hair, pose, body shape, footwear and background unchanged. "
)


@dataclass(frozen=True)
class GarmentRef:
    """A wardrobe item reduced to what the spike needs to choose and describe it."""

    item_id: str
    category: str
    sub_category: str = ""
    primary_color: str = ""
    pattern: str = ""


@dataclass(frozen=True)
class SpikeGarment:
    ref: GarmentRef
    image_bytes: bytes


def select_tryon_garments(items: Sequence[GarmentRef]) -> list[GarmentRef]:
    """Choose the garments a render wears, with the same rule as `tryon_service`.

    A dress is rendered alone. Otherwise outerwear takes precedence over a top for
    the upper body, followed by the bottom. Footwear and accessories are never sent.
    """
    dress: GarmentRef | None = None
    upper: GarmentRef | None = None
    bottom: GarmentRef | None = None
    for item in items:
        if item.category == "dress":
            dress = item
        elif item.category == "bottom":
            bottom = item
        elif item.category == "outerwear":
            upper = item
        elif item.category == "top" and upper is None:
            upper = item
    if dress is not None:
        return [dress]
    return [garment for garment in (upper, bottom) if garment is not None]


def fashn_category(category: str) -> FashnCategory:
    try:
        return _FASHN_CATEGORY[category]
    except KeyError as exc:
        raise ValueError(f"Category '{category}' cannot be rendered by try-on.") from exc


def describe_garment(ref: GarmentRef) -> str:
    """Short English description built only from recorded attributes."""
    words: list[str] = []
    if ref.primary_color and ref.primary_color.lower() != "unknown":
        words.append(ref.primary_color.replace("_", " ").lower())
    if ref.pattern and ref.pattern.lower() not in {"solid", "unknown", "plain"}:
        words.append(ref.pattern.replace("_", " ").lower())
    words.append((ref.sub_category or ref.category).replace("_", " ").lower())
    return " ".join(words)


def build_flux_prompt(garments: Sequence[GarmentRef]) -> str:
    """Prompt that names each garment in the composite's left-to-right order."""
    if not garments:
        raise ValueError("A try-on needs at least one garment.")
    if len(garments) == 1:
        wear = f"Dress the person in the {describe_garment(garments[0])} shown in the reference image."
    else:
        upper, lower = garments[0], garments[1]
        wear = (
            "Dress the person in the garments shown in the reference image: "
            f"the {describe_garment(upper)} (left) on the upper body and "
            f"the {describe_garment(lower)} (right) on the lower body."
        )
    return f"{wear} {_PRESERVE}A natural front-facing full-body studio photo."


def _flatten_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return image.convert("RGB")


def _scale_to_pixels(image: Image.Image, max_pixels: int) -> Image.Image:
    width, height = image.size
    if width * height <= max_pixels:
        return image
    factor = math.sqrt(max_pixels / (width * height))
    size = (max(1, int(width * factor)), max(1, int(height * factor)))
    while size[0] * size[1] > max_pixels:
        size = (size[0] - 1, size[1] - 1)
    return image.resize(size, Image.Resampling.LANCZOS)


def _encode_jpeg(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def fit_within_pixels(image_bytes: bytes, max_pixels: int = PERSON_MAX_PIXELS) -> bytes:
    """Flatten transparency onto white and downscale to at most `max_pixels` (JPEG)."""
    with Image.open(BytesIO(image_bytes)) as source:
        image = _flatten_rgb(source)
    return _encode_jpeg(_scale_to_pixels(image, max_pixels))


def build_garment_composite(images: Sequence[bytes], max_pixels: int = COMPOSITE_MAX_PIXELS) -> bytes:
    """Place garment crops side by side, left to right, on a white canvas (JPEG)."""
    if not images:
        raise ValueError("A composite needs at least one garment image.")
    flattened: list[Image.Image] = []
    for data in images:
        with Image.open(BytesIO(data)) as source:
            flattened.append(_flatten_rgb(source))
    target_height = max(image.height for image in flattened)
    scaled = [
        image.resize((max(1, round(image.width * target_height / image.height)), target_height), Image.Resampling.LANCZOS)
        if image.height != target_height
        else image
        for image in flattened
    ]
    width = sum(image.width for image in scaled) + COMPOSITE_PADDING * (len(scaled) + 1)
    height = target_height + 2 * COMPOSITE_PADDING
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    x = COMPOSITE_PADDING
    for image in scaled:
        canvas.paste(image, (x, COMPOSITE_PADDING))
        x += image.width + COMPOSITE_PADDING
    return _encode_jpeg(_scale_to_pixels(canvas, max_pixels))


REVIEW_IMAGE_HEIGHT = 1024


def normalize_for_review(image_bytes: bytes, height: int = REVIEW_IMAGE_HEIGHT) -> bytes:
    """Re-encode a result as metadata-free JPEG at a fixed height for the blind bundle."""
    with Image.open(BytesIO(image_bytes)) as source:
        image = _flatten_rgb(source)
    width = max(1, round(image.width * height / image.height))
    return _encode_jpeg(image.resize((width, height), Image.Resampling.LANCZOS))


def image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(image_bytes)) as image:
        return image.size


def data_uri(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    return f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def billed_megapixels(width: int, height: int) -> int:
    return max(1, math.ceil(width * height / BILLED_MEGAPIXEL))


def estimate_flux_cost_usd(input_sizes: Sequence[tuple[int, int]], output_size: tuple[int, int]) -> float:
    """fal's published FLUX VTO formula, each image rounded up to whole megapixels."""
    input_mp = sum(billed_megapixels(w, h) for w, h in input_sizes)
    cost = (
        FLUX_FIRST_INPUT_MEGAPIXEL_USD
        + FLUX_EXTRA_INPUT_MEGAPIXEL_USD * max(0, input_mp - 1)
        + FLUX_OUTPUT_MEGAPIXEL_USD * billed_megapixels(*output_size)
    )
    return round(cost, 4)


def estimate_fashn_cost_usd(successful_calls: int) -> float:
    return round(FASHN_PRICE_PER_IMAGE_USD * successful_calls, 4)


@dataclass
class CallRecord:
    """One HTTP call, recorded without payloads, image URLs or credentials."""

    model_id: str
    stage: str
    http_status: int | None
    latency_ms: int
    error_type: str | None = None
    error_message: str | None = None
    seed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "stage": self.stage,
            "http_status": self.http_status,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "seed": self.seed,
        }


@dataclass
class CaseRun:
    case_id: str
    provider: Provider
    model_id: str
    success: bool = False
    calls: list[CallRecord] = field(default_factory=list)
    total_latency_ms: int = 0
    estimated_cost_usd: float = 0.0
    output_bytes: bytes | None = None
    output_size: tuple[int, int] | None = None
    prompt: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, output_file: str | None) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "provider": self.provider,
            "model_id": self.model_id,
            "success": self.success,
            "calls": [call.to_dict() for call in self.calls],
            "total_latency_ms": self.total_latency_ms,
            "estimated_cost_usd": self.estimated_cost_usd,
            "output_file": output_file,
            "output_sha256": sha256(self.output_bytes).hexdigest() if self.output_bytes else None,
            "output_size": list(self.output_size) if self.output_size else None,
            "prompt": self.prompt,
            "settings": self.settings,
        }


class ProviderCallError(Exception):
    def __init__(self, record: CallRecord) -> None:
        super().__init__(record.error_message or record.error_type or "provider call failed")
        self.record = record


def _sanitize(message: str, secret: str) -> str:
    cleaned = message.replace(secret, "***") if secret else message
    return " ".join(cleaned.split())[:ERROR_MESSAGE_LIMIT]


class _JsonApiClient:
    """Shared POST/download logic; subclasses set the auth header and base URL."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        auth_headers: Mapping[str, str],
        timeout_seconds: float,
        transport: httpx.BaseTransport | None,
        clock: Callable[[], float],
    ) -> None:
        self._api_key = api_key
        self._clock = clock
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            headers=dict(auth_headers),
        )
        # Output images live on third-party CDNs; never send the API key there.
        self._download_http = httpx.Client(timeout=httpx.Timeout(timeout_seconds), transport=transport)

    def close(self) -> None:
        self._http.close()
        self._download_http.close()

    def _post(self, path: str, model_id: str, stage: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], CallRecord]:
        started = self._clock()
        try:
            response = self._http.post(path, json=dict(payload))
        except httpx.HTTPError as exc:
            raise ProviderCallError(
                CallRecord(model_id, stage, None, self._elapsed_ms(started), type(exc).__name__, _sanitize(str(exc), self._api_key))
            ) from exc
        latency_ms = self._elapsed_ms(started)
        if response.status_code >= 400:
            raise ProviderCallError(
                CallRecord(model_id, stage, response.status_code, latency_ms, "HTTPStatusError", _sanitize(response.text, self._api_key))
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderCallError(
                CallRecord(model_id, stage, response.status_code, latency_ms, "InvalidJSON", "response body is not JSON")
            ) from exc
        seed = body.get("seed") if isinstance(body, dict) else None
        return body, CallRecord(model_id, stage, response.status_code, latency_ms, seed=seed if isinstance(seed, int) else None)

    def download(self, url: str, stage: str, model_id: str) -> tuple[bytes, CallRecord]:
        started = self._clock()
        try:
            if url.startswith("data:"):
                content = base64.b64decode(url.split(",", 1)[1])
                status: int | None = None
            else:
                response = self._download_http.get(url)
                response.raise_for_status()
                content, status = response.content, response.status_code
        except (httpx.HTTPError, ValueError, IndexError) as exc:
            raise ProviderCallError(
                CallRecord(
                    model_id,
                    stage,
                    getattr(getattr(exc, "response", None), "status_code", None),
                    self._elapsed_ms(started),
                    type(exc).__name__,
                    _sanitize(str(exc), self._api_key),
                )
            ) from exc
        return content, CallRecord(model_id, stage, status, self._elapsed_ms(started))

    def _elapsed_ms(self, started: float) -> int:
        return max(0, round((self._clock() - started) * 1000))


class FalClient(_JsonApiClient):
    """Synchronous client for `https://fal.run/<model_id>`."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = FAL_BASE_URL,
        timeout_seconds: float = 180.0,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A fal.ai API key is required for live runs.")
        key = api_key.strip()
        super().__init__(
            key,
            base_url=base_url,
            auth_headers={"Authorization": f"Key {key}"},
            timeout_seconds=timeout_seconds,
            transport=transport,
            clock=clock,
        )

    def run(self, model_id: str, stage: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], CallRecord]:
        return self._post(f"/{model_id}", model_id, stage, payload)


def _first_image_url(body: Mapping[str, Any]) -> str:
    images = body.get("images")
    if not isinstance(images, list) or not images or not isinstance(images[0], dict) or not images[0].get("url"):
        raise ValueError("Response has no images[0].url")
    return str(images[0]["url"])


PARSE_STAGE_SUFFIX = ":parse"


def _record_invalid_body(run: CaseRun, model_id: str, stage: str, exc: Exception) -> None:
    """Record an unusable response body as its own entry; it is not another model call."""
    run.calls.append(
        CallRecord(model_id, f"{stage}{PARSE_STAGE_SUFFIX}", None, 0, type(exc).__name__, str(exc)[:ERROR_MESSAGE_LIMIT])
    )


def _is_model_call(call: Mapping[str, Any]) -> bool:
    stage = str(call.get("stage", ""))
    return stage != "download" and not stage.endswith(PARSE_STAGE_SUFFIX)


def run_fashn_case(
    client: FalClient,
    case_id: str,
    person_jpeg: bytes,
    garments: Sequence[SpikeGarment],
    *,
    mode: str = "balanced",
) -> CaseRun:
    """Chain one FASHN call per garment; later passes wear the previous output URL."""
    run = CaseRun(case_id=case_id, provider="fashn", model_id=FASHN_MODEL_ID, settings={"mode": mode})
    current_person = data_uri(person_jpeg)
    output_url: str | None = None
    successes = 0
    for index, garment in enumerate(garments, start=1):
        category = fashn_category(garment.ref.category)
        stage = f"pass{index}:{category}"
        payload = {
            "model_image": current_person,
            "garment_image": data_uri(fit_within_pixels(garment.image_bytes, PERSON_MAX_PIXELS)),
            "category": category,
            "mode": mode,
            "garment_photo_type": "auto",
            "num_samples": 1,
            "output_format": "png",
        }
        try:
            body, record = client.run(FASHN_MODEL_ID, stage, payload)
        except ProviderCallError as exc:
            run.calls.append(exc.record)
            break
        run.calls.append(record)
        try:
            output_url = _first_image_url(body)
        except ValueError as exc:
            _record_invalid_body(run, FASHN_MODEL_ID, stage, exc)
            break
        successes += 1
        current_person = output_url
    run.estimated_cost_usd = estimate_fashn_cost_usd(successes)
    if successes == len(garments) and output_url is not None:
        try:
            content, record = client.download(output_url, "download", FASHN_MODEL_ID)
        except ProviderCallError as exc:
            run.calls.append(exc.record)
        else:
            run.calls.append(record)
            run.output_bytes = content
            run.output_size = image_size(content)
            run.success = True
    run.total_latency_ms = sum(call.latency_ms for call in run.calls)
    return run


def run_flux_case(
    client: FalClient,
    case_id: str,
    person_jpeg: bytes,
    garments: Sequence[SpikeGarment],
) -> CaseRun:
    """Merge the garments into one composite, then make a single FLUX VTO call."""
    run = CaseRun(case_id=case_id, provider="flux", model_id=FLUX_MODEL_ID)
    started = perf_counter()
    composite = build_garment_composite([garment.image_bytes for garment in garments])
    composite_ms = max(0, round((perf_counter() - started) * 1000))
    run.prompt = build_flux_prompt([garment.ref for garment in garments])
    run.settings = {"composite_ms": composite_ms, "composite_size": list(image_size(composite))}
    payload = {
        "prompt": run.prompt,
        "human_image_url": data_uri(person_jpeg),
        "garment_image_url": data_uri(composite),
        "output_format": "jpeg",
    }
    try:
        body, record = client.run(FLUX_MODEL_ID, "vto", payload)
    except ProviderCallError as exc:
        run.calls.append(exc.record)
        run.total_latency_ms = composite_ms + exc.record.latency_ms
        return run
    run.calls.append(record)
    try:
        url = _first_image_url(body)
        content, download_record = client.download(url, "download", FLUX_MODEL_ID)
    except ProviderCallError as exc:
        run.calls.append(exc.record)
    except ValueError as exc:
        _record_invalid_body(run, FLUX_MODEL_ID, "vto", exc)
    else:
        run.calls.append(download_record)
        run.output_bytes = content
        run.output_size = image_size(content)
        run.success = True
        run.estimated_cost_usd = estimate_flux_cost_usd([image_size(person_jpeg), image_size(composite)], run.output_size)
    run.total_latency_ms = composite_ms + sum(call.latency_ms for call in run.calls)
    return run


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile; `None` for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return float(ordered[min(rank, len(ordered)) - 1])


def summarize_runs(runs: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-provider success, end-to-end latency (successful outfits only) and cost."""
    summary: dict[str, dict[str, Any]] = {}
    for provider in sorted({str(run["provider"]) for run in runs}):
        rows = [run for run in runs if run["provider"] == provider]
        ok = [run for run in rows if run["success"]]
        latencies = [float(run["total_latency_ms"]) for run in ok]
        failures: dict[str, int] = {}
        for run in rows:
            if run["success"]:
                continue
            failed = [call for call in run["calls"] if call.get("error_type")]
            key = failed[-1]["error_type"] if failed else "unknown"
            status = failed[-1].get("http_status") if failed else None
            label = f"{key}:{status}" if status else key
            failures[label] = failures.get(label, 0) + 1
        total_cost = round(sum(float(run["estimated_cost_usd"]) for run in rows), 4)
        model_calls = [sum(1 for call in run["calls"] if _is_model_call(call)) for run in rows]
        summary[provider] = {
            "attempted": len(rows),
            "succeeded": len(ok),
            "success_rate": round(len(ok) / len(rows), 4) if rows else None,
            "latency_ms_p50": percentile(latencies, 50),
            "latency_ms_p95": percentile(latencies, 95),
            "latency_ms_max": max(latencies) if latencies else None,
            "mean_model_calls": round(sum(model_calls) / len(rows), 3) if rows else None,
            "estimated_cost_usd_total": total_cost,
            "estimated_cost_usd_per_success": round(total_cost / len(ok), 4) if ok else None,
            "failures": failures,
        }
    return summary


def blind_labels(case_id: str, salt: str, providers: Sequence[str]) -> dict[str, str]:
    """Deterministic per-case permutation of providers onto labels A, B, C, ..."""
    ordered = sorted(set(providers), key=lambda provider: sha256(f"{salt}:{case_id}:{provider}".encode()).hexdigest())
    return {chr(ord("A") + index): provider for index, provider in enumerate(ordered)}


RATING_CRITERIA = ("garment_fidelity", "person_preservation", "realism")


def summarize_ratings(
    rating_files: Sequence[Mapping[str, Any]],
    salt: str,
    providers: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Un-blind rater scores (1-5 per criterion) and average them per provider.

    `providers` MUST be the provider set the review page was built from.
    """
    scores: dict[str, dict[str, list[int]]] = {}
    unacceptable: dict[str, list[bool]] = {}
    raters: set[str] = set()
    for document in rating_files:
        raters.add(str(document.get("rater", "")))
        for row in document.get("ratings", []):
            label = str(row["label"])
            provider = blind_labels(str(row["case_id"]), salt, providers).get(label)
            if provider is None:
                raise ValueError(f"Unknown blind label '{label}'")
            for criterion in RATING_CRITERIA:
                value = row.get(criterion)
                if value is None:
                    continue
                if not isinstance(value, int) or not 1 <= value <= 5:
                    raise ValueError(f"{criterion} must be an integer from 1 to 5, got {value!r}")
                scores.setdefault(provider, {}).setdefault(criterion, []).append(value)
            unacceptable.setdefault(provider, []).append(bool(row.get("unacceptable", False)))
    result: dict[str, dict[str, Any]] = {}
    for provider in sorted(set(scores) | set(unacceptable)):
        flags = unacceptable.get(provider, [])
        result[provider] = {
            "raters": len(raters),
            "ratings": len(flags),
            "unacceptable_rate": round(sum(flags) / len(flags), 4) if flags else None,
            **{
                f"mean_{criterion}": round(sum(values) / len(values), 3)
                for criterion, values in scores.get(provider, {}).items()
                if values
            },
        }
    return result
