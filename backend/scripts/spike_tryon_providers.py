"""Opt-in spike: compare FASHN Try-On v1.6 and FLUX VTO on real demo outfits.

Both models are called through fal.ai with one key (`FAL_KEY`). The spike never
writes to the application database or object storage; it only reads demo
wardrobes. All images and run files go to a git-ignored output directory.

Steps (from the repository root):
    # 1. Offline: pick the cases and print the estimated cost.
    python backend/scripts/spike_tryon_providers.py plan --user female=<uuid> --user male=<uuid>
    # 2. Live (paid): render every case with both providers.
    $env:FAL_KEY = "<key>"
    python backend/scripts/spike_tryon_providers.py run --live --provider both
    # 3. Offline: build the blind rating page for fashion raters.
    python backend/scripts/spike_tryon_providers.py review --raw <raw.json>
    # 4. Offline: latency, success and cost, plus un-blinded ratings.
    python backend/scripts/spike_tryon_providers.py score --raw <raw.json> --ratings <ratings.json>
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import html
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from PIL import Image  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402
from app.core.dependencies import get_object_storage  # noqa: E402
from app.models.entities import MediaAsset, OutfitItem, OutfitRecommendation, WardrobeItem  # noqa: E402
from app.services.item_media import primary_media_ids  # noqa: E402
from app.services.tryon_service import get_preset_avatar_bytes  # noqa: E402
from app.services.tryon_spike import (  # noqa: E402
    FAL_BASE_URL,
    FASHN_MODEL_ID,
    FASHN_PRICE_PER_IMAGE_USD,
    FLUX_FIRST_INPUT_MEGAPIXEL_USD,
    FLUX_MODEL_ID,
    FLUX_OUTPUT_MEGAPIXEL_USD,
    FLUX_EXTRA_INPUT_MEGAPIXEL_USD,
    PERSON_MAX_PIXELS,
    CaseRun,
    FalClient,
    GarmentRef,
    SpikeGarment,
    blind_labels,
    build_garment_composite,
    fit_within_pixels,
    run_fashn_case,
    run_flux_case,
    select_tryon_garments,
    summarize_ratings,
    summarize_runs,
)

SPIKE_VERSION = "tryon-provider-spike-v1"
DEFAULT_OUT = ROOT / "data" / "private-tryon-spike"
FLUX_ESTIMATE_PER_CASE_USD = FLUX_FIRST_INPUT_MEGAPIXEL_USD + FLUX_EXTRA_INPUT_MEGAPIXEL_USD + FLUX_OUTPUT_MEGAPIXEL_USD
PROVIDERS = ("fashn", "flux")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ref(item: WardrobeItem) -> GarmentRef:
    category = item.category.value if hasattr(item.category, "value") else str(item.category)
    return GarmentRef(
        item_id=item.id,
        category=category,
        sub_category=item.sub_category or "",
        primary_color=item.primary_color or "",
        pattern=item.pattern or "",
    )


def _active(item: WardrobeItem | None) -> bool:
    return item is not None and item.is_active and item.is_user_confirmed and item.deleted_at is None


def select_cases(session: Session, users: dict[str, str], min_per_branch: int) -> list[dict[str, Any]]:
    """Persisted outfits first; then deterministic fills so each user has `min_per_branch`
    upper + bottom cases and, when the wardrobe has dresses, `min_per_branch` dress cases."""
    cases: list[dict[str, Any]] = []
    for gender, user_id in users.items():
        user_cases: list[dict[str, Any]] = []
        outfits = session.exec(
            select(OutfitRecommendation)
            .where(OutfitRecommendation.user_id == user_id)
            .order_by(OutfitRecommendation.created_at, OutfitRecommendation.id)
        ).all()
        seen: set[tuple[str, ...]] = set()
        for outfit in outfits:
            item_ids = session.exec(
                select(OutfitItem.wardrobe_item_id).where(OutfitItem.outfit_id == outfit.id, OutfitItem.user_id == user_id)
            ).all()
            items = [session.get(WardrobeItem, item_id) for item_id in item_ids]
            refs = [_ref(item) for item in items if _active(item) and item is not None]
            garments = select_tryon_garments(refs)
            key = tuple(garment.item_id for garment in garments)
            if not garments or key in seen:
                continue
            seen.add(key)
            user_cases.append({"source": "persisted_outfit", "outfit_id": outfit.id, "garments": garments})

        wardrobe = [
            _ref(item)
            for item in session.exec(
                select(WardrobeItem).where(
                    WardrobeItem.user_id == user_id,
                    WardrobeItem.is_active.is_(True),
                    WardrobeItem.is_user_confirmed.is_(True),
                    WardrobeItem.deleted_at.is_(None),
                )
            ).all()
        ]

        def by_category(category: str) -> list[GarmentRef]:
            return sorted((ref for ref in wardrobe if ref.category == category), key=lambda ref: ref.item_id)

        top_bottom = sum(1 for case in user_cases if len(case["garments"]) == 2)
        for top, bottom in zip(by_category("top"), by_category("bottom")):
            if top_bottom >= min_per_branch:
                break
            if (top.item_id, bottom.item_id) in seen:
                continue
            seen.add((top.item_id, bottom.item_id))
            user_cases.append({"source": "constructed_pair", "outfit_id": None, "garments": [top, bottom]})
            top_bottom += 1

        dresses = sum(1 for case in user_cases if case["garments"][0].category == "dress")
        for dress in by_category("dress"):
            if dresses >= min_per_branch:
                break
            if (dress.item_id,) in seen:
                continue
            seen.add((dress.item_id,))
            user_cases.append({"source": "constructed_dress", "outfit_id": None, "garments": [dress]})
            dresses += 1

        for index, case in enumerate(user_cases, start=1):
            cases.append(
                {
                    "case_id": f"{gender}-{index:02d}",
                    "avatar_gender": gender,
                    "user_id": user_id,
                    "source": case["source"],
                    "outfit_id": case["outfit_id"],
                    "garments": [garment.__dict__ for garment in case["garments"]],
                }
            )
    return cases


def _session() -> Session:
    return Session(create_database_engine(get_settings().database_url))


def _parse_users(values: list[str]) -> dict[str, str]:
    users: dict[str, str] = {}
    for value in values:
        gender, _, user_id = value.partition("=")
        gender = gender.strip().lower()
        if gender not in {"female", "male"} or not user_id.strip():
            raise SystemExit(f"--user must look like female=<uuid> or male=<uuid>, got '{value}'")
        users[gender] = user_id.strip()
    return users


def command_plan(args: argparse.Namespace) -> None:
    users = _parse_users(args.user)
    with _session() as session:
        cases = select_cases(session, users, args.min_per_branch)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    document = {"spike": SPIKE_VERSION, "created_at": _now(), "salt": uuid4().hex, "cases": cases}
    cases_path = out_dir / "cases.json"
    cases_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    fashn_calls = sum(len(case["garments"]) for case in cases)
    print(f"{len(cases)} cases written to {cases_path}")
    for case in cases:
        names = " + ".join(f"{g['category']}:{g['sub_category']}" for g in case["garments"])
        print(f"  {case['case_id']:<10} {case['source']:<17} {names}")
    print(
        f"Estimated cost per repeat: FASHN {fashn_calls} calls x ${FASHN_PRICE_PER_IMAGE_USD} = "
        f"${fashn_calls * FASHN_PRICE_PER_IMAGE_USD:.2f}; FLUX {len(cases)} calls x ~${FLUX_ESTIMATE_PER_CASE_USD:.4f} = "
        f"${len(cases) * FLUX_ESTIMATE_PER_CASE_USD:.2f}"
    )


def _load_garments(session: Session, storage: Any, case: dict[str, Any]) -> list[SpikeGarment]:
    user_id = case["user_id"]
    refs = [GarmentRef(**garment) for garment in case["garments"]]
    media = primary_media_ids(session, user_id, [ref.item_id for ref in refs])
    garments: list[SpikeGarment] = []
    for ref in refs:
        asset_id = media.get(ref.item_id)
        asset = session.get(MediaAsset, asset_id) if asset_id else None
        if asset is None or asset.user_id != user_id:
            raise SystemExit(f"Case {case['case_id']}: item {ref.item_id} has no readable image.")
        data = storage.get_object(user_id=user_id, bucket=asset.bucket, object_key=asset.object_key)
        garments.append(SpikeGarment(ref=ref, image_bytes=data))
    return garments


def _extension(image_bytes: bytes) -> str:
    with Image.open(BytesIO(image_bytes)) as image:
        return {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(image.format or "", "bin")


def _write_raw(path: Path, header: dict[str, Any], runs: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({**header, "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")


def command_run(args: argparse.Namespace) -> None:
    if not args.live:
        raise SystemExit("Live runs call paid APIs. Re-run with --live to confirm.")
    api_key = os.environ.get("FAL_KEY", "")
    if not api_key.strip():
        raise SystemExit("Set FAL_KEY in the environment (never commit it).")
    out_dir: Path = args.out_dir
    cases_path = args.cases or out_dir / "cases.json"
    cases_doc = json.loads(cases_path.read_text(encoding="utf-8"))
    providers = list(PROVIDERS) if args.provider == "both" else [args.provider]
    for folder in ("inputs", "outputs", "runs"):
        (out_dir / folder).mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / "runs" / f"raw_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    header = {
        "spike": SPIKE_VERSION,
        "started_at": _now(),
        "cases_sha256": sha256(cases_path.read_bytes()).hexdigest(),
        "salt": cases_doc["salt"],
        "host": FAL_BASE_URL,
        "models": {"fashn": FASHN_MODEL_ID, "flux": FLUX_MODEL_ID},
        "fashn_mode": args.fashn_mode,
        "repeats": args.repeats,
        "price_source": "fal.ai model pages, read 2026-11-20",
    }
    runs: list[dict[str, Any]] = []
    consecutive_failures = {provider: 0 for provider in providers}
    client = FalClient(api_key, timeout_seconds=args.timeout)
    storage = get_object_storage()
    try:
        with _session() as session:
            for repeat in range(args.repeats):
                for index, case in enumerate(cases_doc["cases"]):
                    case_id = case["case_id"]
                    garments = _load_garments(session, storage, case)
                    person = fit_within_pixels(get_preset_avatar_bytes(case["avatar_gender"]), PERSON_MAX_PIXELS)
                    if repeat == 0:
                        (out_dir / "inputs" / f"{case_id}_person.jpg").write_bytes(person)
                        for number, garment in enumerate(garments, start=1):
                            (out_dir / "inputs" / f"{case_id}_garment{number}.jpg").write_bytes(
                                fit_within_pixels(garment.image_bytes, PERSON_MAX_PIXELS)
                            )
                        (out_dir / "inputs" / f"{case_id}_composite.jpg").write_bytes(
                            build_garment_composite([garment.image_bytes for garment in garments])
                        )
                    # Alternate the provider order so neither always runs first.
                    order = providers if (index + repeat) % 2 == 0 else list(reversed(providers))
                    for provider in order:
                        if consecutive_failures[provider] >= args.max_consecutive_failures:
                            print(f"  {case_id} {provider}: skipped after repeated failures")
                            continue
                        run: CaseRun = (
                            run_fashn_case(client, case_id, person, garments, mode=args.fashn_mode)
                            if provider == "fashn"
                            else run_flux_case(client, case_id, person, garments)
                        )
                        output_file = None
                        if run.output_bytes:
                            output_file = f"outputs/{case_id}_{provider}_r{repeat}.{_extension(run.output_bytes)}"
                            (out_dir / output_file).write_bytes(run.output_bytes)
                        consecutive_failures[provider] = 0 if run.success else consecutive_failures[provider] + 1
                        record = run.to_dict(output_file)
                        record["repeat"] = repeat
                        runs.append(record)
                        _write_raw(raw_path, header, runs)
                        status = "ok" if run.success else "FAILED"
                        print(f"  {case_id} r{repeat} {provider:<5} {status:<6} {run.total_latency_ms / 1000:6.1f}s ${run.estimated_cost_usd:.4f}")
    finally:
        client.close()
        header["finished_at"] = _now()
        _write_raw(raw_path, header, runs)
    print(f"Raw results: {raw_path}")


def _load_raw(paths: list[Path]) -> tuple[str, list[dict[str, Any]]]:
    salts: set[str] = set()
    runs: list[dict[str, Any]] = []
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        salts.add(document["salt"])
        runs.extend(document["runs"])
    if len(salts) != 1:
        raise SystemExit("Raw files come from different case plans (salts differ).")
    return salts.pop(), runs


REVIEW_STYLE = """
:root{--bg:#f7f5f2;--card:#fff;--ink:#1f1d1a;--muted:#6b665e;--line:#e3ded6;--accent:#8a4b2a}
@media (prefers-color-scheme:dark){:root{--bg:#171513;--card:#211e1b;--ink:#eee9e2;--muted:#a9a196;--line:#3a352f;--accent:#e0a070}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}p{color:var(--muted);margin:0 0 16px}
.case{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 20px}
.case h2{font-size:16px;margin:0 0 12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
figure{margin:0}img{width:100%;height:auto;border-radius:8px;border:1px solid var(--line);background:#fff}
figcaption{font-size:13px;color:var(--muted);margin-top:4px}.inputs img{max-height:240px;object-fit:contain}
fieldset{border:1px solid var(--line);border-radius:8px;margin:8px 0 0;padding:8px 10px}legend{font-weight:600}
label{display:flex;justify-content:space-between;gap:8px;margin:4px 0}select{min-width:64px}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;display:flex;gap:10px;flex-wrap:wrap;align-items:center;z-index:1}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:8px 14px;font-weight:600;cursor:pointer}
input[type=text]{padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.missing{padding:24px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:8px}
"""

REVIEW_SCRIPT = """
const KEY='tryon-spike-ratings';
function collect(){const rows=[];document.querySelectorAll('[data-rating]').forEach(f=>{const r={case_id:f.dataset.case,label:f.dataset.label};
f.querySelectorAll('select').forEach(s=>{r[s.name]=s.value?Number(s.value):null});r.unacceptable=f.querySelector('input[type=checkbox]').checked;rows.push(r)});return rows}
function save(){try{localStorage.setItem(KEY,JSON.stringify({rater:document.getElementById('rater').value,ratings:collect()}))}catch(e){}}
function restore(){let d=null;try{d=JSON.parse(localStorage.getItem(KEY)||'null')}catch(e){}if(!d)return;document.getElementById('rater').value=d.rater||'';
(d.ratings||[]).forEach(r=>{const f=document.querySelector(`[data-case="${r.case_id}"][data-label="${r.label}"]`);if(!f)return;
f.querySelectorAll('select').forEach(s=>{if(r[s.name])s.value=String(r[s.name])});f.querySelector('input[type=checkbox]').checked=!!r.unacceptable})}
function exportJson(){const rater=document.getElementById('rater').value.trim();if(!rater){alert('Nhập tên người chấm trước khi xuất.');return}
const rows=collect();const missing=rows.filter(r=>!r.garment_fidelity||!r.person_preservation||!r.realism).length;
if(missing&&!confirm(missing+' ảnh chưa chấm đủ 3 tiêu chí. Vẫn xuất?'))return;
const blob=new Blob([JSON.stringify({rater,exported_at:new Date().toISOString(),ratings:rows},null,2)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='ratings_'+rater.replace(/\\W+/g,'_')+'.json';a.click()}
document.addEventListener('change',save);document.addEventListener('input',save);restore();
"""


def _score_select(name: str, label: str) -> str:
    options = "".join(f'<option value="{value}">{value}</option>' for value in range(1, 6))
    return f'<label>{label}<select name="{name}"><option value="">–</option>{options}</select></label>'


def command_review(args: argparse.Namespace) -> None:
    salt, runs = _load_raw(args.raw)
    out_dir: Path = args.out_dir
    cases_doc = json.loads((args.cases or out_dir / "cases.json").read_text(encoding="utf-8"))
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for run in sorted(runs, key=lambda row: row.get("repeat", 0)):
        if run["success"]:
            by_case.setdefault(run["case_id"], {}).setdefault(run["provider"], run)
    sections: list[str] = []
    for case in cases_doc["cases"]:
        case_id = case["case_id"]
        garments = "".join(
            f'<figure><img src="inputs/{case_id}_garment{n}.jpg" alt="Món {n}: {html.escape(g["sub_category"])}">'
            f'<figcaption>Món {n}: {html.escape(g["category"])} · {html.escape(g["sub_category"])} · {html.escape(g["primary_color"])}</figcaption></figure>'
            for n, g in enumerate(case["garments"], start=1)
        )
        results: list[str] = []
        for label, provider in sorted(blind_labels(case_id, salt).items()):
            run = by_case.get(case_id, {}).get(provider)
            if run is None:
                results.append(f'<figure><div class="missing">Ảnh {label}: không tạo được</div></figure>')
                continue
            results.append(
                f'<figure><img src="{html.escape(run["output_file"])}" alt="Kết quả {label}">'
                f'<fieldset data-rating data-case="{case_id}" data-label="{label}"><legend>Ảnh {label}</legend>'
                f'{_score_select("garment_fidelity", "Giống món đồ thật (màu, họa tiết, kiểu)")}'
                f'{_score_select("person_preservation", "Giữ nguyên người mẫu (mặt, dáng, nền)")}'
                f'{_score_select("realism", "Tự nhiên, không méo")}'
                f'<label>Không chấp nhận được<input type="checkbox" name="unacceptable"></label></fieldset></figure>'
            )
        sections.append(
            f'<section class="case"><h2>Bộ {html.escape(case_id)}</h2>'
            f'<div class="grid inputs"><figure><img src="inputs/{case_id}_person.jpg" alt="Người mẫu gốc"><figcaption>Người mẫu gốc</figcaption></figure>{garments}</div>'
            f'<div class="grid" style="margin-top:14px">{"".join(results)}</div></section>'
        )
    page = (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Chấm ảnh thử đồ</title><style>{REVIEW_STYLE}</style></head><body><main>"
        "<h1>Chấm ảnh thử đồ</h1><p>Mỗi bộ có hai ảnh A và B từ hai cách tạo khác nhau, thứ tự được xáo ngẫu nhiên. "
        "Chấm 1 (rất kém) đến 5 (rất tốt) cho từng tiêu chí, so với ảnh người mẫu gốc và ảnh món đồ.</p>"
        '<div class="bar"><input type="text" id="rater" placeholder="Tên người chấm" aria-label="Tên người chấm">'
        '<button type="button" onclick="exportJson()">Xuất kết quả</button></div>'
        f"{''.join(sections)}</main><script>{REVIEW_SCRIPT}</script></body></html>"
    )
    page_path = out_dir / "review.html"
    page_path.write_text(page, encoding="utf-8")
    print(f"Blind review page: {page_path}")


def _fmt_seconds(value: float | None) -> str:
    return "–" if value is None else f"{value / 1000:.1f} s"


def render_markdown(run_summary: dict[str, dict[str, Any]], rating_summary: dict[str, dict[str, Any]]) -> str:
    lines = [
        "| Provider | Succeeded | p50 | p95 | Max | Model calls / outfit | Cost / successful outfit | Failures |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]
    for provider, row in run_summary.items():
        failures = ", ".join(f"{key} x{count}" for key, count in row["failures"].items()) or "none"
        cost = row["estimated_cost_usd_per_success"]
        lines.append(
            f"| {provider} | {row['succeeded']}/{row['attempted']} | {_fmt_seconds(row['latency_ms_p50'])} | "
            f"{_fmt_seconds(row['latency_ms_p95'])} | {_fmt_seconds(row['latency_ms_max'])} | {row['mean_model_calls']} | "
            f"{'–' if cost is None else f'${cost:.4f}'} | {failures} |"
        )
    if rating_summary:
        lines += [
            "",
            "| Provider | Raters | Ratings | Garment fidelity | Person preservation | Realism | Unacceptable |",
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for provider, row in rating_summary.items():
            rate = row["unacceptable_rate"]
            lines.append(
                f"| {provider} | {row['raters']} | {row['ratings']} | {row.get('mean_garment_fidelity', '–')} | "
                f"{row.get('mean_person_preservation', '–')} | {row.get('mean_realism', '–')} | "
                f"{'–' if rate is None else f'{rate:.0%}'} |"
            )
    return "\n".join(lines)


def command_score(args: argparse.Namespace) -> None:
    salt, runs = _load_raw(args.raw)
    run_summary = summarize_runs(runs)
    ratings = [json.loads(path.read_text(encoding="utf-8")) for path in args.ratings or []]
    rating_summary = summarize_ratings(ratings, salt) if ratings else {}
    print(render_markdown(run_summary, rating_summary))
    if args.json_out:
        args.json_out.write_text(
            json.dumps({"runs": run_summary, "ratings": rating_summary}, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Select cases offline and print the estimated cost.")
    plan.add_argument("--user", action="append", required=True, help="female=<uuid> or male=<uuid>")
    plan.add_argument("--min-per-branch", type=int, default=3, help="Upper + bottom and dress cases per user (default 3).")
    plan.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    plan.set_defaults(handler=command_plan)

    run = sub.add_parser("run", help="Render every case through fal.ai (paid).")
    run.add_argument("--live", action="store_true", help="Required: confirms paid API calls.")
    run.add_argument("--provider", choices=["fashn", "flux", "both"], default="both")
    run.add_argument("--repeats", type=int, default=1)
    run.add_argument("--fashn-mode", choices=["performance", "balanced", "quality"], default="balanced")
    run.add_argument("--timeout", type=float, default=180.0)
    run.add_argument("--max-consecutive-failures", type=int, default=3)
    run.add_argument("--cases", type=Path)
    run.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    run.set_defaults(handler=command_run)

    review = sub.add_parser("review", help="Write the blind rating page.")
    review.add_argument("--raw", type=Path, nargs="+", required=True)
    review.add_argument("--cases", type=Path)
    review.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    review.set_defaults(handler=command_review)

    score = sub.add_parser("score", help="Summarize latency, success, cost and ratings offline.")
    score.add_argument("--raw", type=Path, nargs="+", required=True)
    score.add_argument("--ratings", type=Path, nargs="*")
    score.add_argument("--json-out", type=Path)
    score.set_defaults(handler=command_score)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
