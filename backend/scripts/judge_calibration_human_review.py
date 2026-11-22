"""Build an offline blind human review UI for judge calibration samples and score human-vs-judge agreement."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.evaluation.benchmark.metrics import compute_spearman_rho

DEFAULT_CALIBRATION_PATH = REPOSITORY_ROOT / "data" / "fixtures" / "judge_calibration_v1.json"
DEFAULT_OUT_DIR = REPOSITORY_ROOT / "data" / "private-judge-calibration-review"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Chấm Điểm Mù Hiệu Chuẩn Giám Khảo Thời Trang (20 Mẫu)</title>
  <style>
    :root {
      --bg: #f8fafc;
      --card: #ffffff;
      --border: #cbd5e1;
      --text: #0f172a;
      --muted: #475569;
      --accent: #0f766e;
      --accent-soft: #ccfbf1;
      --warn: #b45309;
      --warn-bg: #fef3c7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 20px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    .container { max-width: 980px; margin: 0 auto; }
    .header-card, .sample-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 18px;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }
    h1 { margin: 0 0 8px; font-size: 22px; }
    .rubric {
      background: #f1f5f9;
      border-left: 4px solid var(--accent);
      padding: 12px 14px;
      border-radius: 6px;
      font-size: 14px;
      margin: 12px 0;
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      margin-top: 14px;
    }
    input[type="text"] {
      padding: 9px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 14px;
      min-width: 240px;
    }
    button {
      cursor: pointer;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 9px 14px;
      font-size: 14px;
      font-weight: 600;
      background: #fff;
      color: var(--text);
    }
    button.primary {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    button.filter-active {
      background: #e2e8f0;
      border-color: #64748b;
    }
    .progress-bar {
      height: 10px;
      background: #e2e8f0;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 12px;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      background: var(--accent);
      transition: width 0.2s ease;
    }
    .sample-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 10px;
      margin-bottom: 12px;
    }
    .badge {
      display: inline-block;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      background: #e2e8f0;
      color: #334155;
    }
    .badge.done { background: var(--accent-soft); color: #115e59; }
    .meta-line { margin: 6px 0; font-size: 14px; }
    .items-table {
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0 12px;
      font-size: 13px;
    }
    .items-table th, .items-table td {
      border: 1px solid #e2e8f0;
      padding: 6px 8px;
      text-align: left;
    }
    .items-table th { background: #f8fafc; font-weight: 600; }
    .explanation-box {
      background: #f8fafc;
      border: 1px dashed var(--border);
      padding: 10px 12px;
      border-radius: 8px;
      font-size: 14px;
      margin-bottom: 14px;
    }
    .criterion-row {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
      border-top: 1px solid #f1f5f9;
      gap: 10px;
    }
    .criterion-label { font-size: 14px; font-weight: 500; min-width: 260px; }
    .score-group { display: flex; gap: 6px; }
    .score-btn {
      width: 40px;
      height: 36px;
      padding: 0;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: #fff;
      font-weight: 700;
    }
    .score-btn.selected {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .error-banner {
      display: none;
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 8px;
      background: var(--warn-bg);
      color: var(--warn);
      font-size: 14px;
      font-weight: 500;
    }
    .hidden { display: none; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header-card">
      <h1>Chấm Điểm Mù Chất Lượng Phối Đồ (20 Mẫu)</h1>
      <p style="margin:0;color:var(--muted);font-size:14px;">
        Mỗi mẫu hiển thị ngẫu nhiên một gợi ý phối đồ và lời giải thích. Đánh giá độc lập theo thang <strong>1–5</strong>; dữ liệu tự lưu trên trình duyệt cho tới khi xuất file JSON.
      </p>
      <div class="rubric">
        <strong>Thang điểm tham chiếu:</strong><br />
        <strong>1</strong> = Không chấp nhận được / sai nghiêm trọng ngữ cảnh hoặc thời tiết &nbsp;|&nbsp;
        <strong>2</strong> = Kém / lệch hoàn cảnh hoặc trang trọng &nbsp;|&nbsp;
        <strong>3</strong> = Chấp nhận được nhưng chưa tối ưu &nbsp;|&nbsp;
        <strong>4</strong> = Tốt / gọn gàng hợp lý &nbsp;|&nbsp;
        <strong>5</strong> = Rất tốt / mặc ngay không cần chỉnh.
      </div>
      <div class="controls">
        <input id="raterName" type="text" placeholder="Nhập họ tên người chấm (vd: Nguyen Van A)" />
        <button id="filterAll" class="filter-active" type="button">Tất cả (<span id="totalCount">0</span>)</button>
        <button id="filterPending" type="button">Chưa chấm (<span id="pendingCount">0</span>)</button>
        <button id="exportBtn" class="primary" type="button">Xuất kết quả JSON</button>
        <button id="resetBtn" type="button">Xóa nháp</button>
      </div>
      <div style="margin-top:10px;font-size:13px;color:var(--muted);">
        Tiến độ: <strong id="progressText">0/0</strong> mẫu hoàn tất.
      </div>
      <div class="progress-bar"><div id="progressFill" class="progress-fill"></div></div>
      <div id="errorBanner" class="error-banner"></div>
    </div>
    <div id="samplesRoot"></div>
  </div>

  <script>
    const BENCH_DATASET_VERSION = __DATASET_VERSION_JSON__;
    const SAMPLES = __SAMPLES_JSON__;
    const STORAGE_KEY = "fashion_blind_review_" + BENCH_DATASET_VERSION;
    const CRITERIA = [
      { key: "occasion_formality", label: "1. Hợp hoàn cảnh & độ trang trọng (occasion_formality)" },
      { key: "weather_comfort_function", label: "2. Hợp thời tiết, thoải mái & công năng (weather_comfort_function)" },
      { key: "aesthetic_harmony", label: "3. Hài hòa màu sắc, phom dáng & phong cách (aesthetic_harmony)" },
      { key: "explanation_usefulness", label: "4. Lời giải thích trung thực, rõ ràng & hữu ích (explanation_usefulness)" }
    ];
    const WEATHER_LABELS = {
      hot: "Nóng (hot)",
      warm: "Ấm (warm)",
      cool: "Mát (cool)",
      cold: "Lạnh (cold)",
      rainy: "Mưa (rainy)"
    };

    let state = { rater_name: "", ratings: {} };
    let filterMode = "all";

    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (saved && typeof saved === "object") {
        state.rater_name = String(saved.rater_name || "");
        state.ratings = saved.ratings && typeof saved.ratings === "object" ? saved.ratings : {};
      }
    } catch (_) {}

    function saveState() {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (_) {}
    }

    function isSampleDone(blindId) {
      const entry = state.ratings[blindId];
      if (!entry) return false;
      return CRITERIA.every(c => Number.isInteger(entry[c.key]) && entry[c.key] >= 1 && entry[c.key] <= 5);
    }

    function computeFashionMean(entry) {
      if (!entry) return null;
      const a = entry.occasion_formality, b = entry.weather_comfort_function, c = entry.aesthetic_harmony;
      if ([a, b, c].every(v => Number.isInteger(v) && v >= 1 && v <= 5)) {
        return ((a + b + c) / 3).toFixed(2);
      }
      return null;
    }

    function escapeHtml(str) {
      return String(str ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function updateProgress() {
      const total = SAMPLES.length;
      const done = SAMPLES.filter(s => isSampleDone(s.blind_id)).length;
      document.getElementById("totalCount").textContent = String(total);
      document.getElementById("pendingCount").textContent = String(total - done);
      document.getElementById("progressText").textContent = `${done}/${total}`;
      document.getElementById("progressFill").style.width = total ? `${(done / total) * 100}%` : "0%";
    }

    function render() {
      const root = document.getElementById("samplesRoot");
      root.innerHTML = "";
      for (const sample of SAMPLES) {
        const done = isSampleDone(sample.blind_id);
        if (filterMode === "pending" && done) continue;
        const entry = state.ratings[sample.blind_id] || {};
        const meanFashion = computeFashionMean(entry);

        const card = document.createElement("div");
        card.className = "sample-card";
        card.id = "card-" + sample.blind_id;

        const itemsRows = (sample.items || []).map(it => {
          const flags = Array.isArray(it.functional_flags) && it.functional_flags.length
            ? it.functional_flags.join(", ")
            : "—";
          return `<tr>
            <td>${escapeHtml(it.category || "")}</td>
            <td><strong>${escapeHtml(it.name || it.sub_category || "")}</strong></td>
            <td>${escapeHtml(it.primary_color || "")}</td>
            <td>${escapeHtml(it.material || "")}</td>
            <td>${escapeHtml(it.style || "")} (${escapeHtml(it.fit || "")})</td>
            <td>${escapeHtml(it.formality_level ?? "")}/5</td>
            <td>${escapeHtml(flags)}</td>
          </tr>`;
        }).join("");

        const weatherText = WEATHER_LABELS[sample.weather_condition] || sample.weather_condition || "Không nêu rõ";
        let criteriaHtml = "";
        for (const crit of CRITERIA) {
          const current = entry[crit.key];
          let btns = "";
          for (let score = 1; score <= 5; score++) {
            const cls = current === score ? "score-btn selected" : "score-btn";
            btns += `<button type="button" class="${cls}" data-bid="${sample.blind_id}" data-crit="${crit.key}" data-score="${score}">${score}</button>`;
          }
          criteriaHtml += `<div class="criterion-row">
            <div class="criterion-label">${escapeHtml(crit.label)}</div>
            <div class="score-group">${btns}</div>
          </div>`;
        }

        card.innerHTML = `
          <div class="sample-top">
            <div>
              <strong>Mẫu ${escapeHtml(sample.blind_id)}</strong>
              ${meanFashion ? `<span style="margin-left:10px;font-size:13px;color:var(--accent);">Điểm phối đồ TB: <strong>${meanFashion}/5</strong></span>` : ""}
            </div>
            <span class="badge ${done ? "done" : ""}">${done ? "Đã chấm đủ" : "Chưa xong"}</span>
          </div>
          <div class="meta-line"><strong>Yêu cầu người dùng:</strong> ${escapeHtml(sample.query)}</div>
          <div class="meta-line"><strong>Thời tiết bối cảnh:</strong> ${escapeHtml(weatherText)} &nbsp;|&nbsp; <strong>Hồ sơ sở thích:</strong> ${escapeHtml(sample.profile_summary || "không có")}</div>
          <table class="items-table">
            <thead>
              <tr><th>Nhóm</th><th>Tên món đồ</th><th>Màu</th><th>Chất liệu</th><th>Phong cách / Dáng</th><th>Trang trọng</th><th>Cờ chức năng</th></tr>
            </thead>
            <tbody>${itemsRows}</tbody>
          </table>
          <div class="explanation-box">
            <strong>Lời giải thích của hệ thống:</strong> ${escapeHtml(sample.explanation_vi)}
          </div>
          ${criteriaHtml}
        `;
        root.appendChild(card);
      }

      root.querySelectorAll(".score-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const bid = btn.getAttribute("data-bid");
          const crit = btn.getAttribute("data-crit");
          const score = Number(btn.getAttribute("data-score"));
          if (!state.ratings[bid]) state.ratings[bid] = {};
          state.ratings[bid][crit] = score;
          saveState();
          document.getElementById("errorBanner").style.display = "none";
          render();
          updateProgress();
        });
      });
      updateProgress();
    }

    const raterInput = document.getElementById("raterName");
    raterInput.value = state.rater_name;
    raterInput.addEventListener("input", () => {
      state.rater_name = raterInput.value;
      saveState();
      document.getElementById("errorBanner").style.display = "none";
    });

    document.getElementById("filterAll").addEventListener("click", () => {
      filterMode = "all";
      document.getElementById("filterAll").classList.add("filter-active");
      document.getElementById("filterPending").classList.remove("filter-active");
      render();
    });
    document.getElementById("filterPending").addEventListener("click", () => {
      filterMode = "pending";
      document.getElementById("filterPending").classList.add("filter-active");
      document.getElementById("filterAll").classList.remove("filter-active");
      render();
    });

    document.getElementById("resetBtn").addEventListener("click", () => {
      if (!confirm("Xóa toàn bộ điểm đang lưu nháp trên trình duyệt?")) return;
      state = { rater_name: "", ratings: {} };
      raterInput.value = "";
      saveState();
      render();
    });

    document.getElementById("exportBtn").addEventListener("click", () => {
      const err = document.getElementById("errorBanner");
      const rater = (state.rater_name || "").trim();
      if (!rater) {
        err.textContent = "Vui lòng nhập họ tên người chấm trước khi xuất file JSON.";
        err.style.display = "block";
        raterInput.focus();
        return;
      }
      const missing = SAMPLES.filter(s => !isSampleDone(s.blind_id));
      if (missing.length > 0) {
        err.textContent = `Còn ${missing.length} mẫu chưa chấm đủ 4 tiêu chí (bắt đầu từ ${missing[0].blind_id}).`;
        err.style.display = "block";
        filterMode = "all";
        render();
        const el = document.getElementById("card-" + missing[0].blind_id);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }

      const payload = {
        schema_version: "blind-calibration-rating-v1",
        dataset_version: BENCH_DATASET_VERSION,
        rater_name: rater,
        submitted_at: new Date().toISOString(),
        ratings: SAMPLES.map(s => {
          const r = state.ratings[s.blind_id];
          const mean = (r.occasion_formality + r.weather_comfort_function + r.aesthetic_harmony) / 3;
          return {
            blind_id: s.blind_id,
            occasion_formality: r.occasion_formality,
            weather_comfort_function: r.weather_comfort_function,
            aesthetic_harmony: r.aesthetic_harmony,
            explanation_usefulness: r.explanation_usefulness,
            fashion_quality_score: Number(mean.toFixed(4))
          };
        })
      };

      const slug = rater.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_|_$/g, "") || "rater";
      const blob = new Blob([JSON.stringify(payload, null, 2) + "\\n"], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `calibration_ratings_${slug}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });

    render();
  </script>
</body>
</html>
"""


def build_blind_calibration_package(
    *,
    calibration_path: Path = DEFAULT_CALIBRATION_PATH,
    out_dir: Path = DEFAULT_OUT_DIR,
    seed: int = 20261122,
) -> dict[str, Any]:
    """Generate a shuffled, label-free HTML review folder plus private blind_manifest.json."""
    cal_data = json.loads(calibration_path.read_text(encoding="utf-8"))
    raw_samples = list(cal_data.get("pointwise_samples", []))
    if not raw_samples:
        raise ValueError(f"No pointwise_samples found in {calibration_path}")

    rng = random.Random(seed)
    indices = list(range(len(raw_samples)))
    rng.shuffle(indices)

    blind_samples: list[dict[str, Any]] = []
    manifest_entries: list[dict[str, Any]] = []
    for pos, orig_idx in enumerate(indices, start=1):
        src = raw_samples[orig_idx]
        blind_id = f"S{pos:02d}"
        blind_samples.append(
            {
                "blind_id": blind_id,
                "query": str(src["query"]),
                "weather_condition": str(src.get("weather_condition") or ""),
                "profile_summary": str(src.get("profile_summary") or "không có"),
                "items": list(src.get("items", [])),
                "explanation_vi": str(src["explanation_vi"]),
            }
        )
        manifest_entries.append(
            {
                "blind_id": blind_id,
                "sample_id": str(src["id"]),
            }
        )

    dataset_version = str(cal_data.get("dataset_version") or "judge-calibration-v2")
    review_dir = out_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    html_path = review_dir / "index.html"
    html_content = _HTML_TEMPLATE.replace(
        "__DATASET_VERSION_JSON__",
        json.dumps(dataset_version, ensure_ascii=False),
    ).replace(
        "__SAMPLES_JSON__",
        json.dumps(blind_samples, ensure_ascii=False),
    )
    html_path.write_text(html_content, encoding="utf-8")

    manifest_path = out_dir / "blind_manifest.json"
    manifest_payload = {
        "dataset_version": dataset_version,
        "seed": seed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blind_to_sample": {e["blind_id"]: e["sample_id"] for e in manifest_entries},
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "dataset_version": dataset_version,
        "sample_count": len(blind_samples),
        "review_html": str(html_path),
        "manifest_path": str(manifest_path),
    }


def _validate_rating_score(value: Any, *, field: str, rater: str, blind_id: str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Rater '{rater}' has non-numeric {field} for {blind_id}") from exc
    if not (1.0 <= score <= 5.0):
        raise ValueError(f"Rater '{rater}' has out-of-range {field}={score} for {blind_id} (must be 1..5)")
    return score


def load_human_ratings(
    *,
    ratings_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Load, validate, and unblind all calibration_ratings_*.json files under ratings_dir."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    blind_to_sample: dict[str, str] = dict(manifest["blind_to_sample"])
    expected_blinds = set(blind_to_sample.keys())

    files = sorted(ratings_dir.glob("calibration_ratings_*.json"))
    if not files:
        raise ValueError(f"No calibration_ratings_*.json files found in {ratings_dir}")

    rater_scores: dict[str, dict[str, float]] = {}
    rater_usefulness: dict[str, dict[str, float]] = {}
    human_ratings_by_id: dict[str, list[float]] = {sid: [] for sid in blind_to_sample.values()}
    usefulness_by_id: dict[str, list[float]] = {sid: [] for sid in blind_to_sample.values()}

    for file_path in files:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        rater = str(payload.get("rater_name") or file_path.stem).strip()
        if rater in rater_scores:
            raise ValueError(f"Duplicate rater_name '{rater}' in {file_path}")
        entries = list(payload.get("ratings") or [])
        seen_blinds: set[str] = set()
        r_fashion: dict[str, float] = {}
        r_useful: dict[str, float] = {}
        for item in entries:
            bid = str(item.get("blind_id") or "").strip()
            if bid not in blind_to_sample:
                raise ValueError(f"Unknown blind_id '{bid}' in {file_path}")
            if bid in seen_blinds:
                raise ValueError(f"Duplicate blind_id '{bid}' in {file_path}")
            seen_blinds.add(bid)

            occ = _validate_rating_score(item.get("occasion_formality"), field="occasion_formality", rater=rater, blind_id=bid)
            wea = _validate_rating_score(item.get("weather_comfort_function"), field="weather_comfort_function", rater=rater, blind_id=bid)
            aes = _validate_rating_score(item.get("aesthetic_harmony"), field="aesthetic_harmony", rater=rater, blind_id=bid)
            exp = _validate_rating_score(item.get("explanation_usefulness"), field="explanation_usefulness", rater=rater, blind_id=bid)
            fashion = round((occ + wea + aes) / 3.0, 4)

            sid = blind_to_sample[bid]
            r_fashion[sid] = fashion
            r_useful[sid] = exp
            human_ratings_by_id[sid].append(fashion)
            usefulness_by_id[sid].append(exp)

        if seen_blinds != expected_blinds:
            missing = sorted(expected_blinds - seen_blinds)
            raise ValueError(f"Rater '{rater}' missing ratings for blind IDs: {missing}")

        rater_scores[rater] = r_fashion
        rater_usefulness[rater] = r_useful

    sample_ids = sorted(blind_to_sample.values())
    rater_names = sorted(rater_scores.keys())
    inter_rater_spearmans: list[float] = []
    inter_rater_maes: list[float] = []
    for i in range(len(rater_names)):
        for j in range(i + 1, len(rater_names)):
            r1 = [rater_scores[rater_names[i]][sid] for sid in sample_ids]
            r2 = [rater_scores[rater_names[j]][sid] for sid in sample_ids]
            rho = compute_spearman_rho(r1, r2)
            if rho is not None:
                inter_rater_spearmans.append(rho)
            mae = sum(abs(a - b) for a, b in zip(r1, r2)) / len(r1)
            inter_rater_maes.append(round(mae, 4))

    mean_human_by_id = {
        sid: round(sum(human_ratings_by_id[sid]) / len(human_ratings_by_id[sid]), 4)
        for sid in sample_ids
    }
    mean_usefulness_by_id = {
        sid: round(sum(usefulness_by_id[sid]) / len(usefulness_by_id[sid]), 4)
        for sid in sample_ids
    }

    return {
        "rater_count": len(rater_names),
        "raters": rater_names,
        "sample_count": len(sample_ids),
        "inter_rater_spearman_mean": (
            round(sum(inter_rater_spearmans) / len(inter_rater_spearmans), 4)
            if inter_rater_spearmans
            else None
        ),
        "inter_rater_mae_mean": (
            round(sum(inter_rater_maes) / len(inter_rater_maes), 4)
            if inter_rater_maes
            else None
        ),
        "human_ratings_by_id": human_ratings_by_id,
        "mean_human_by_id": mean_human_by_id,
        "mean_usefulness_by_id": mean_usefulness_by_id,
    }


def _render_human_vs_judge_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Báo Cáo Đối Chiếu Người Chấm Mù vs LLM Judge")
    lines.append("")
    lines.append(f"- **Số người chấm mù:** `{summary['rater_count']}` ({', '.join(summary['raters'])})")
    lines.append(f"- **Số mẫu hiệu chuẩn:** `{summary['sample_count']}`")
    lines.append(f"- **Độ đồng thuận liên người chấm (Pairwise Spearman rho TB):** `{summary['inter_rater_spearman_mean']}`")
    lines.append(f"- **Sai số tuyệt đối trung bình giữa người chấm (Inter-Rater MAE):** `{summary['inter_rater_mae_mean']}`")
    if summary.get("judge_model"):
        lines.append(f"- **LLM Judge:** `{summary['judge_model']}` (`{summary.get('judge_provider')}`)")
        lines.append(f"- **Human vs Judge Spearman rho (thực tế):** `{summary.get('human_vs_judge_spearman')}`")
        lines.append(f"- **Human vs Judge MAE:** `{summary.get('human_vs_judge_mae')}`")
    lines.append("")
    lines.append("| Sample ID | Nhãn | TB Người chấm (1-5) | Điểm LLM Judge | Chênh lệch |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for row in summary.get("per_sample", []):
        j_str = f"{row['judge_score']:.2f}" if row.get("judge_score") is not None else "N/A"
        diff_str = f"{row['abs_diff']:.2f}" if row.get("abs_diff") is not None else "N/A"
        lines.append(
            f"| `{row['sample_id']}` | `{row.get('label') or '-'}` | {row['human_mean']:.2f} | {j_str} | {diff_str} |"
        )
    lines.append("")
    return "\n".join(lines)


def score_human_vs_judge(
    *,
    ratings_dir: Path,
    manifest_path: Path,
    judge_calibration_json: Path | None = None,
    out_json: Path | None = None,
    out_md: Path | None = None,
) -> dict[str, Any]:
    """Compute real inter-rater agreement and human-vs-judge Spearman correlation (0 API calls)."""
    loaded = load_human_ratings(ratings_dir=ratings_dir, manifest_path=manifest_path)
    mean_human = loaded["mean_human_by_id"]

    judge_by_id: dict[str, dict[str, Any]] = {}
    judge_model: str | None = None
    judge_provider: str | None = None
    if judge_calibration_json is not None:
        j_data = json.loads(judge_calibration_json.read_text(encoding="utf-8"))
        judge_model = j_data.get("judge_model")
        judge_provider = j_data.get("judge_provider")
        for detail in j_data.get("details", []):
            judge_by_id[str(detail["id"])] = detail

    per_sample: list[dict[str, Any]] = []
    aligned_h: list[float] = []
    aligned_j: list[float] = []
    abs_diffs: list[float] = []
    for sid in sorted(mean_human.keys()):
        h_val = mean_human[sid]
        detail = judge_by_id.get(sid)
        j_val = float(detail["fashion_quality_score"]) if detail is not None else None
        diff = round(abs(h_val - j_val), 4) if j_val is not None else None
        if j_val is not None and diff is not None:
            aligned_h.append(h_val)
            aligned_j.append(j_val)
            abs_diffs.append(diff)
        per_sample.append(
            {
                "sample_id": sid,
                "label": detail.get("label") if detail else None,
                "human_mean": h_val,
                "human_scores": loaded["human_ratings_by_id"][sid],
                "judge_score": j_val,
                "abs_diff": diff,
            }
        )

    summary = {
        "rater_count": loaded["rater_count"],
        "raters": loaded["raters"],
        "sample_count": loaded["sample_count"],
        "inter_rater_spearman_mean": loaded["inter_rater_spearman_mean"],
        "inter_rater_mae_mean": loaded["inter_rater_mae_mean"],
        "judge_model": judge_model,
        "judge_provider": judge_provider,
        "human_vs_judge_spearman": compute_spearman_rho(aligned_h, aligned_j),
        "human_vs_judge_mae": round(sum(abs_diffs) / len(abs_diffs), 4) if abs_diffs else None,
        "per_sample": per_sample,
    }

    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if out_md is not None:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_render_human_vs_judge_markdown(summary), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Generate offline blind review HTML and private manifest.")
    p_build.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    p_build.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p_build.add_argument("--seed", type=int, default=20261122)

    p_score = sub.add_parser("score", help="Validate rater JSON files and score agreement against Judge.")
    p_score.add_argument("--ratings-dir", type=Path, required=True)
    p_score.add_argument("--manifest", type=Path, required=True)
    p_score.add_argument("--judge-calibration-json", type=Path, default=None)
    p_score.add_argument("--out-json", type=Path, default=None)
    p_score.add_argument("--out-md", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "build":
        res = build_blind_calibration_package(
            calibration_path=args.calibration,
            out_dir=args.out_dir,
            seed=args.seed,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    res = score_human_vs_judge(
        ratings_dir=args.ratings_dir,
        manifest_path=args.manifest,
        judge_calibration_json=args.judge_calibration_json,
        out_json=args.out_json,
        out_md=args.out_md,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
