"""Opt-in check: does FLUX VTO render footwear, headwear and layered tops well?

Renders six demo outfits twice with the application's FLUX adapter:
* `current`: today's rule (one upper garment, outerwear over top, plus the bottom;
  or a dress alone; no footwear or headwear);
* `extended`: inner top under outerwear, the dress under its jacket, footwear and
  headwear, laid out as a grid and named in one prompt.

Reads demo wardrobes only and writes images, a raw JSON file and a side-by-side
page to the git-ignored `data/private-tryon-spike/extras/`. The fal key is read
from the application settings (`FAL_KEY` in `.env` or the environment).

Usage (from the repository root, about $0.60 for twelve renders):
    python backend/scripts/spike_tryon_extras.py --live --user female=<uuid> --user male=<uuid>
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from sqlmodel import Session, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402
from app.core.dependencies import get_object_storage  # noqa: E402
from app.models.entities import MediaAsset, WardrobeItem  # noqa: E402
from app.services.flux_vto_provider import (  # noqa: E402
    FluxVtoTryOnProvider,
    build_extended_prompt,
    build_prompt,
    order_extended,
    uses_extended_layout,
)
from app.services.item_media import primary_media_ids  # noqa: E402
from app.services.providers import OutfitGarment, OutfitTryOnRequest  # noqa: E402
from app.services.tryon_service import get_preset_avatar_bytes  # noqa: E402

OUT = ROOT / "data" / "private-tryon-spike" / "extras"
PRICE_PER_RENDER_USD = 0.0475  # fal.ai FLUX VTO, about 1 MP in and out (2026-11-20)

# (case id, avatar, [(role, category, sub_category, color or None)])
CASES: list[tuple[str, str, list[tuple[str, str, str, str | None]]]] = [
    ("x1-shoes", "male", [("upper", "top", "sweater", "grey"), ("lower", "bottom", "trousers", "black"),
                          ("footwear", "footwear", "sneakers", "black")]),
    ("x2-layers-boots", "male", [("outer", "outerwear", "vest", "black"), ("upper", "top", "sweater", "grey"),
                                 ("lower", "bottom", "jeans", "blue"), ("footwear", "footwear", "boots", "black")]),
    ("x3-layers-sneakers", "male", [("outer", "outerwear", "vest", "black"), ("upper", "top", "shirt", "beige"),
                                    ("lower", "bottom", "jeans", "blue"), ("footwear", "footwear", "sneakers", "black")]),
    ("x4-beanie", "male", [("upper", "top", "sweater", "grey"), ("lower", "bottom", "trousers", "black"),
                           ("footwear", "footwear", "sneakers", "black"), ("headwear", "accessory", "beanie", "grey")]),
    ("x5-dress-jacket-flats", "female", [("one_piece", "dress", "cocktail dress", "magenta"),
                                         ("outer", "outerwear", "jacket", "teal"), ("footwear", "footwear", "flats", "beige")]),
    ("x6-sandals-hat", "female", [("upper", "top", "blouse", None), ("lower", "bottom", "skirt", None),
                                  ("footwear", "footwear", "sandals", "brown"), ("headwear", "accessory", "hat", "pink")]),
]
CATEGORY = {"top": "tops", "outerwear": "tops", "bottom": "bottoms", "dress": "one-pieces",
            "footwear": "footwear", "accessory": "headwear"}


@dataclass(frozen=True)
class Resolved:
    role: str
    item: WardrobeItem
    image: bytes


def resolve(session: Session, storage: Any, user_id: str, spec: tuple[str, str, str, str | None]) -> Resolved:
    role, category, sub_category, color = spec
    query = select(WardrobeItem).where(
        WardrobeItem.user_id == user_id,
        WardrobeItem.is_active.is_(True),
        WardrobeItem.is_user_confirmed.is_(True),
        WardrobeItem.deleted_at.is_(None),
        WardrobeItem.category == category,
        WardrobeItem.sub_category == sub_category,
    )
    if color:
        query = query.where(WardrobeItem.primary_color == color)
    item = session.exec(query.order_by(WardrobeItem.id)).first()
    if item is None:
        raise SystemExit(f"No {color or ''} {sub_category} ({category}) in this wardrobe.")
    asset = session.get(MediaAsset, primary_media_ids(session, user_id, [item.id]).get(item.id))
    if asset is None or asset.user_id != user_id:
        raise SystemExit(f"Item {item.id} has no readable image.")
    return Resolved(role, item, storage.get_object(user_id=user_id, bucket=asset.bucket, object_key=asset.object_key))


def garment(resolved: Resolved, *, with_role: bool) -> OutfitGarment:
    item = resolved.item
    category = item.category.value if hasattr(item.category, "value") else str(item.category)
    return OutfitGarment(
        image_bytes=resolved.image,
        mime_type="image/png",
        category=CATEGORY[category],  # type: ignore[arg-type]
        sub_category=item.sub_category or "",
        primary_color=item.primary_color or "",
        pattern=item.pattern or "",
        role=resolved.role if with_role else None,  # type: ignore[arg-type]
    )


def current_rule(items: list[Resolved]) -> list[OutfitGarment]:
    """Today's application rule: dress alone, else outerwear over top, plus the bottom."""
    roles = {r.role: r for r in items}
    if "one_piece" in roles:
        return [garment(roles["one_piece"], with_role=False)]
    upper = roles.get("outer") or roles.get("upper")
    return [garment(r, with_role=False) for r in (upper, roles.get("lower")) if r is not None]


def render(provider: FluxVtoTryOnProvider, person: bytes, garments: list[OutfitGarment]) -> dict[str, Any]:
    started = perf_counter()
    try:
        result = provider.try_on_outfit(OutfitTryOnRequest(person_image_bytes=person, person_mime_type="image/webp",
                                                           garments=tuple(garments)))
    except Exception as exc:  # recorded, never dropped
        return {"success": False, "error_type": type(exc).__name__, "latency_ms": round((perf_counter() - started) * 1000)}
    return {"success": True, "latency_ms": round((perf_counter() - started) * 1000), "image": result.image_bytes}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="Required: confirms paid API calls.")
    parser.add_argument("--user", action="append", required=True, help="female=<uuid> or male=<uuid>")
    args = parser.parse_args(argv)
    if not args.live:
        raise SystemExit("Live runs call a paid API. Re-run with --live to confirm.")
    users = dict(value.split("=", 1) for value in args.user)
    settings = get_settings()
    key = settings.fal_key.get_secret_value() if settings.fal_key else ""
    if not key.strip():
        raise SystemExit("Set FAL_KEY in .env or the environment.")
    provider = FluxVtoTryOnProvider(api_key=key, model=settings.flux_vto_model,
                                    timeout_seconds=float(settings.tryon_timeout_seconds))
    OUT.mkdir(parents=True, exist_ok=True)
    storage = get_object_storage()
    records: list[dict[str, Any]] = []
    with Session(create_database_engine(settings.database_url)) as session:
        for index, (case_id, avatar, specs) in enumerate(CASES):
            items = [resolve(session, storage, users[avatar], spec) for spec in specs]
            person = get_preset_avatar_bytes(avatar)
            arms = {"current": current_rule(items), "extended": [garment(r, with_role=True) for r in items]}
            assert uses_extended_layout(arms["extended"])
            order = ["current", "extended"] if index % 2 == 0 else ["extended", "current"]
            for arm in order:
                result = render(provider, person, arms[arm])
                image = result.pop("image", None)
                if image:
                    (OUT / f"{case_id}_{arm}.webp").write_bytes(image)
                prompt = build_extended_prompt(arms[arm]) if arm == "extended" else build_prompt(arms[arm])
                sent = order_extended(arms[arm]) if arm == "extended" else arms[arm]
                records.append({"case_id": case_id, "arm": arm, "prompt": prompt,
                                "garments": [f"{g.role or g.category}:{g.primary_color} {g.sub_category}".strip() for g in sent],
                                **result})
                status = "ok" if result["success"] else f"FAILED {result.get('error_type')}"
                print(f"  {case_id:<22} {arm:<8} {status:<8} {result['latency_ms'] / 1000:5.1f}s")
            for number, r in enumerate(items, start=1):
                (OUT / f"{case_id}_input{number}.png").write_bytes(r.image)
            (OUT / f"{case_id}_person.webp").write_bytes(person)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = {"check": "tryon-extras-v1", "run_at": stamp, "model": settings.flux_vto_model,
           "estimated_cost_usd": round(PRICE_PER_RENDER_USD * sum(r["success"] for r in records), 4), "renders": records}
    (OUT / f"raw_{stamp}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    write_page(records)
    print(f"Raw: {OUT / f'raw_{stamp}.json'}\nPage: {OUT / 'compare.html'}")


def write_page(records: list[dict[str, Any]]) -> None:
    sections = []
    for case_id, _avatar, specs in CASES:
        inputs = "".join(
            f'<figure><img src="{case_id}_input{n}.png" alt=""><figcaption>{html.escape(spec[0])}: '
            f'{html.escape((spec[3] or "") + " " + spec[2])}</figcaption></figure>'
            for n, spec in enumerate(specs, start=1)
        )
        cells = []
        for arm, title in (("current", "Hiện tại (không giày/mũ, một lớp áo)"), ("extended", "Mở rộng (giày, mũ, nhiều lớp)")):
            row = next(r for r in records if r["case_id"] == case_id and r["arm"] == arm)
            body = (f'<img src="{case_id}_{arm}.webp" alt="{html.escape(title)}">' if row["success"]
                    else f'<div class="missing">Lỗi: {html.escape(str(row.get("error_type")))}</div>')
            cells.append(f'<figure>{body}<figcaption><b>{title}</b> · {row["latency_ms"] / 1000:.1f} s<br>'
                         f'{html.escape(row["prompt"])}</figcaption></figure>')
        sections.append(f'<section><h2>{html.escape(case_id)}</h2><div class="inputs">'
                        f'<figure><img src="{case_id}_person.webp" alt=""><figcaption>Người mẫu</figcaption></figure>'
                        f'{inputs}</div><div class="pair">{"".join(cells)}</div></section>')
    style = ("body{margin:0;font:14px/1.5 system-ui,sans-serif;background:#f7f5f2;color:#1f1d1a}"
             "@media (prefers-color-scheme:dark){body{background:#171513;color:#eee9e2}}"
             "main{max-width:1100px;margin:0 auto;padding:16px}section{margin:0 0 28px}h2{font-size:16px}"
             ".inputs{display:flex;flex-wrap:wrap;gap:8px}.inputs img{height:120px;width:auto;background:#fff;border-radius:6px}"
             ".pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:10px}"
             ".pair img{width:100%;border-radius:8px;background:#fff}figure{margin:0}figcaption{font-size:12px;opacity:.8}"
             ".missing{padding:40px;text-align:center;border:1px dashed #999;border-radius:8px}")
    page = (f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>So sánh giày, mũ, nhiều lớp</title><style>{style}</style>'
            f'</head><body><main><h1>So sánh: cách hiện tại và cách mở rộng</h1>{"".join(sections)}</main></body></html>')
    (OUT / "compare.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
