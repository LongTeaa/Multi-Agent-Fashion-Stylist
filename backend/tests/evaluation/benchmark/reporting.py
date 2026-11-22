"""JSON and human-readable Markdown report generation for the 2-layer stylist benchmark."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.1f}%"


def _fmt_ci(ci: list[float] | tuple[float, float] | None, *, is_pct: bool = False) -> str:
    if not ci or len(ci) != 2:
        return "N/A"
    if is_pct:
        return f"[{ci[0] * 100:.1f}%, {ci[1] * 100:.1f}%]"
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def _fmt_num(val: float | None, digits: int = 3) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{digits}f}"


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a transparent Markdown report separated by Layer A, Layer B, Ablations, Stress, and Failures."""
    meta = report.get("metadata", {})
    lines: list[str] = []
    lines.append("# Báo Cáo Benchmark Chất Lượng Tư Vấn Multi-Agent Chatbot")
    lines.append("")
    lines.append("## 1. Thông Tin Đợt Chạy (Execution Metadata)")
    lines.append("")
    lines.append(f"- **Dataset version:** `{meta.get('dataset_version')}` (Wardrobes: `{meta.get('wardrobes_version')}`)")
    lines.append(f"- **Split:** `{meta.get('split')}` ({meta.get('representative_case_count')} representative cases; Stress cases: {meta.get('stress_case_count')})")
    lines.append(f"- **Execution mode:** `{meta.get('execution_mode')}` | **Live LLM:** `{meta.get('live_llm')}` | **Judge enabled:** `{meta.get('judge_enabled')}`")
    lines.append(f"- **Chatbot model:** `{meta.get('chatbot_model') or 'offline-rules'}`")
    lines.append(f"- **Judge model:** `{meta.get('judge_model') or 'disabled'}` (`{meta.get('judge_provider') or 'none'}`)")
    if meta.get("same_family_judge_bias"):
        lines.append("- **CẢNH BÁO THIÊN LỆCH (`SAME_FAMILY_JUDGE_BIAS`):** Giám khảo đang sử dụng cùng họ model Gemini với chatbot.")
    lines.append(f"- **Git commit:** `{meta.get('git_commit')}` | **Timestamp:** `{meta.get('executed_at')}`")
    lines.append(f"- **Run complete:** `{meta.get('run_complete')}`")
    lines.append("")

    # Calibration section
    cal = report.get("judge_calibration")
    if cal:
        lines.append("## 2. Kết Quả Hiệu Chuẩn Giám Khảo (Judge Calibration)")
        lines.append("")
        lines.append(
            f"- **Pointwise Accuracy:** `{_fmt_pct(cal.get('pointwise_accuracy'))}` ({cal.get('pointwise_hits')})"
        )
        lines.append(
            f"- **Pairwise Bidirectional Accuracy:** `{_fmt_pct(cal.get('pairwise_accuracy'))}` ({cal.get('pairwise_hits')})"
        )
        lines.append(
            f"- **Position Consistency Rate:** `{_fmt_pct(cal.get('position_consistency_rate'))}`"
        )
        if cal.get("human_vs_judge_spearman") is not None:
            lines.append(f"- **Human vs Judge Spearman rho:** `{cal.get('human_vs_judge_spearman')}`")
        lines.append("")

    # Layer A Table
    lines.append("## 3. Lớp A — Kiểm Định Kỹ Thuật Bắt Buộc (Technical Gate)")
    lines.append("")
    lines.append("| Hệ thống | Case Pass Lớp A | Grounding ID | Cấu trúc bộ đồ | Tuân thủ Must-Avoid | Giải thích trung thực | Cú pháp [Ngoặc] | Bounded & Persist |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    rep_systems = report.get("representative_summary", {})
    for sys_id, summary in rep_systems.items():
        la = summary.get("layer_a", {})
        lines.append(
            f"| **{sys_id}** | {la.get('case_pass_ratio')} ({_fmt_pct(la.get('case_pass_rate'))}) "
            f"| {_fmt_pct(la.get('valid_item_grounding_rate'))} "
            f"| {_fmt_pct(la.get('outfit_structure_validity_rate'))} "
            f"| {_fmt_pct(la.get('must_avoid_compliance_rate'))} "
            f"| {_fmt_pct(la.get('explanation_factuality_rate'))} "
            f"| {_fmt_pct(la.get('canonical_bracket_rate'))} "
            f"| {_fmt_pct(la.get('bounded_and_persist_rate'))} |"
        )
    lines.append("")

    # Layer B Main Comparison Table
    lines.append("## 4. Lớp B — Benchmark Chất Lượng Tư Vấn (5 Trục B1–B5)")
    lines.append("")
    lines.append("| Hệ thống | Functional Pass (95% CI) | Context Acc (B1) | NDCG@3 (95% CI) | Hit@1 (>=4/5) | Unacceptable (<=2/5) | Diversity (B3) | Profile Diff (B3) | Contrastive (B3) | LLM Explain Acc (B4) | Explain Useful (1-5) | Latency P50/P95 (ms) | Avg LLM Calls |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for sys_id, summary in rep_systems.items():
        lb = summary.get("layer_b", {})
        b1 = lb.get("b1_context", {})
        b2 = lb.get("b2_quality", {})
        b3 = lb.get("b3_personalization", {})
        b4 = lb.get("b4_explanation", {})
        b5 = lb.get("b5_cost", {})
        lat = b5.get("latency_ms", {})
        func_pass = summary.get("functional", {})
        ndcg_str = (
            f"{_fmt_num(b2.get('ndcg_at_3'))} {_fmt_ci(b2.get('ndcg_at_3_ci95'))}"
            if b2.get("ndcg_at_3") is not None
            else "N/A"
        )
        prof_diff_str = (
            f"{_fmt_pct(b3.get('profile_differentiation_rate'))} ({b3.get('profile_differentiation_ratio')})"
            if b3.get("profile_differentiation_rate") is not None
            else "N/A"
        )
        contrast_str = (
            f"{_fmt_pct(b3.get('contrastive_pair_diff_rate'))} ({b3.get('contrastive_pair_diff_ratio')})"
            if b3.get("contrastive_pair_diff_rate") is not None
            else "N/A"
        )
        lines.append(
            f"| **{sys_id}** | {func_pass.get('pass_ratio')} ({_fmt_pct(func_pass.get('pass_rate'))}) {_fmt_ci(func_pass.get('pass_rate_ci95'), is_pct=True)} "
            f"| {_fmt_pct(b1.get('micro_field_accuracy'))} "
            f"| {ndcg_str} "
            f"| {_fmt_pct(b2.get('hit_at_1'))} "
            f"| {_fmt_pct(b2.get('unacceptable_rate'))} "
            f"| {_fmt_num(b3.get('top3_core_diversity'))} "
            f"| {prof_diff_str} "
            f"| {contrast_str} "
            f"| {_fmt_pct(b4.get('explanation_llm_accepted_rate'))} "
            f"| {_fmt_num(b4.get('explanation_usefulness_mean'), 2)} "
            f"| {lat.get('p50_ms', 0)} / {lat.get('p95_ms', 0)} "
            f"| {_fmt_num(b5.get('avg_llm_calls'), 2)} |"
        )
    lines.append("")

    # Split Dev vs Holdout
    lines.append("### 4.1. Đối chiếu Tập Dev vs Holdout (Chống Quá Khớp)")
    lines.append("")
    lines.append("| Hệ thống | Dev Pass | Holdout Pass | Dev NDCG@3 | Holdout NDCG@3 |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for sys_id, summary in rep_systems.items():
        splits = summary.get("split_breakdown", {})
        dev_s = splits.get("dev", {})
        hold_s = splits.get("holdout", {})
        lines.append(
            f"| **{sys_id}** | {dev_s.get('pass_ratio', 'N/A')} ({_fmt_pct(dev_s.get('pass_rate'))}) "
            f"| {hold_s.get('pass_ratio', 'N/A')} ({_fmt_pct(hold_s.get('pass_rate'))}) "
            f"| {_fmt_num(dev_s.get('ndcg_at_3'))} "
            f"| {_fmt_num(hold_s.get('ndcg_at_3'))} |"
        )
    lines.append("")

    # Pairwise Bidirectional Comparisons
    pairwise = report.get("pairwise_comparisons", {})
    if pairwise:
        lines.append("### 4.2. So Sánh Cặp Mù 2 Chiều (M-Full vs Đối Chứng)")
        lines.append("")
        lines.append("| Đối thủ | Số cặp | M-Full Thắng | Hòa / Bất nhất | M-Full Thua | Position Consistency |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for opp, pstat in pairwise.items():
            lines.append(
                f"| **vs {opp}** | {pstat.get('total_pairs')} | {pstat.get('wins')} ({_fmt_pct(pstat.get('win_rate'))}) "
                f"| {pstat.get('ties')} | {pstat.get('losses')} | {_fmt_pct(pstat.get('position_consistency_rate'))} |"
            )
        lines.append("")

    # Net Loop Impact (Ablations)
    ablation = report.get("ablation_impact", {})
    if ablation:
        lines.append("## 5. Đánh Giá Giá Trị Thực Của Multi-Agent Loops (B5 — Net Loop Impact)")
        lines.append("")
        lines.append("| Phép so sánh | Tổng case | Cải thiện (Improved) | Không đổi | Giảm chất lượng (Degraded) | Net Gain | Case cải thiện | Case tụt |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |")
        for label, imp in ablation.items():
            lines.append(
                f"| **{label}** | {imp.get('total_compared')} | {imp.get('improved_count')} | {imp.get('unchanged_count')} "
                f"| {imp.get('degraded_count')} | {imp.get('net_gain'):+d} "
                f"| {', '.join(imp.get('improved_case_ids', [])[:5]) or '-'} "
                f"| {', '.join(imp.get('degraded_case_ids', [])[:5]) or '-'} |"
            )
        lines.append("")

    # Noise Robustness
    noise_cmp = report.get("noise_robustness", {})
    if noise_cmp:
        lines.append("## 6. Độ Bền Trước Nhiễu Nhãn Số Hóa (Noise Robustness)")
        lines.append("")
        lines.append("| Hệ thống | Lớp A Sạch -> Nhiễu | Functional Pass Sạch -> Nhiễu | Chênh lệch | Top-1 Ổn Định (Flip Rate) | Top-1 Core Jaccard |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for sys_id, nstat in noise_cmp.items():
            stab_str = (
                f"{_fmt_pct(nstat.get('top1_exact_stability_rate'))} (flip {_fmt_pct(nstat.get('top1_flip_rate'))})"
                if nstat.get("top1_exact_stability_rate") is not None
                else "N/A"
            )
            lines.append(
                f"| **{sys_id}** | {_fmt_pct(nstat.get('clean_layer_a_rate'))} -> {_fmt_pct(nstat.get('noisy_layer_a_rate'))} "
                f"| {_fmt_pct(nstat.get('clean_func_rate'))} -> {_fmt_pct(nstat.get('noisy_func_rate'))} "
                f"| {_fmt_pct(nstat.get('delta_func_rate'))} "
                f"| {stab_str} "
                f"| {_fmt_num(nstat.get('top1_mean_core_jaccard'))} |"
            )
        lines.append("")

    # Stress Diagnostic Suite (Strictly separate)
    stress = report.get("stress_summary", {})
    if stress:
        lines.append("## 7. Tập Chẩn Đoán Kỹ Thuật Tách Biệt (Diagnostic Stress Suite — 12 Cases)")
        lines.append("")
        lines.append(f"> Lưu ý: Bảng này tách riêng khỏi {meta.get('representative_case_count')} kịch bản đại diện ở trên, dùng để xác nhận các cơ chế Loop 1, Loop 2, Score-Drop Guard và Early Exit hoạt động đúng đặc tả.")
        lines.append("")
        lines.append("| Hệ thống | Lớp A Pass | Stress Case Pass | Loop 1 Triggered | Loop 2 Triggered |")
        lines.append("| :--- | :---: | :---: | :---: | :---: |")
        for sys_id, st in stress.items():
            lines.append(
                f"| **{sys_id}** | {st.get('layer_a_ratio')} | {st.get('pass_ratio')} ({_fmt_pct(st.get('pass_rate'))}) "
                f"| {st.get('loop1_count', 0)} | {st.get('loop2_count', 0)} |"
            )
        lines.append("")

    # Failure Breakdown & Silent Fallback Audit
    failures = report.get("failure_breakdown", [])
    lines.append("## 8. Chi Tiết Các Trường Hợp Lỗi / Fallback (Failure Breakdown)")
    lines.append("")
    if not failures:
        lines.append("- Không ghi nhận trường hợp trượt Lớp A hay functional assertion nào ở các hệ thống chính.")
    else:
        for fail in failures[:30]:
            lines.append(f"### `{fail.get('system_id')}` — Case `{fail.get('case_id')}` ({fail.get('suite')})")
            lines.append(f"- **Query:** {fail.get('query')}")
            lines.append(f"- **Status:** `{fail.get('status')}` | **Error:** `{fail.get('error_code')}` | **Context used:** `{fail.get('context_used')}`")
            if fail.get("layer_a_violations"):
                lines.append(f"- **Vi phạm Lớp A:** {'; '.join(fail['layer_a_violations'])}")
            if fail.get("functional_failures"):
                lines.append(f"- **Chưa đạt assertion:** {'; '.join(fail['functional_failures'])}")
            if fail.get("agent_trace"):
                trace_str = " -> ".join(
                    f"{ev.get('sender')}({ev.get('event_type')})" for ev in fail["agent_trace"]
                )
                lines.append(f"- **Agent Trace:** `{trace_str}`")
            lines.append("")

    # Threats to Validity
    lines.append("## 9. Giới Hạn Phương Pháp (Threats to Validity)")
    lines.append("")
    for threat in report.get("threats_to_validity", []):
        lines.append(f"- {threat}")
    lines.append("")
    return "\n".join(lines)


def save_report_files(
    report: dict[str, Any],
    *,
    report_json: Path | None = None,
    report_md: Path | None = None,
) -> None:
    if report_json is not None:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if report_md is not None:
        report_md.parent.mkdir(parents=True, exist_ok=True)
        report_md.write_text(render_markdown_report(report), encoding="utf-8")
