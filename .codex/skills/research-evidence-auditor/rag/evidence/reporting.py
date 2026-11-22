"""Stable JSON and Markdown rendering for evidence reports."""

from __future__ import annotations

from html import escape
import json

from rag.evidence.models import EvidenceReport, SourceLocator


def report_to_dict(report: EvidenceReport) -> dict[str, object]:
    """Validate and serialize a report through one public boundary."""

    report.validate()
    return report.to_dict()


def render_evidence_report_markdown(
    report: EvidenceReport,
    *,
    question: str = "",
) -> str:
    """Render a compact, deterministic and audit-friendly Markdown report."""

    report.validate()
    lines = [
        "# 证据审计报告",
        "",
        f"- 问题：{_markdown_text(question) or '-'}",
        f"- 审计状态：{_code_span(report.status.value)}",
        "",
        "## 结论",
        "",
        _markdown_text(report.answer),
        "",
        "## 主张审计",
        "",
        "| 主张 ID | 原子主张 | 状态 | 置信度 | 证据 | 冲突 |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for claim in report.claims:
        lines.append(
            f"| {_code_span(claim.claim_id)} | {_markdown_text(claim.text)} | "
            f"{_code_span(claim.status.value)} | "
            f"{claim.confidence:.3f} | {_ids(claim.evidence_ids)} | {_ids(claim.conflict_ids)} |"
        )
    if not report.claims:
        lines.append("| - | - | - | - | - | - |")

    source_by_id = {source.source_id: source for source in report.sources}
    lines.extend([
        "", "## 证据明细", "",
        "| 证据 ID | 来源 | 定位 | 质量分 | 摘录 |",
        "| --- | --- | --- | ---: | --- |",
    ])
    for evidence in report.evidence:
        source = source_by_id[evidence.source_id]
        lines.append(
            f"| {_code_span(evidence.evidence_id)} | {_markdown_text(source.title)} | "
            f"{_markdown_text(_locator(evidence.locator, source.path or source.url))} | "
            f"{evidence.quality_score:.3f} | {_markdown_text(evidence.excerpt)} |"
        )
    if not report.evidence:
        lines.append("| - | - | - | - | - |")

    lines.extend(["", "## 冲突与缺口", ""])
    if report.conflicts:
        for conflict in report.conflicts:
            lines.append(
                f"- {_code_span(conflict.conflict_id)}（{conflict.severity:.3f}）："
                f"{_markdown_text(conflict.summary)}；核验建议："
                f"{_markdown_text(conflict.resolution)}"
            )
    else:
        lines.append("- 未发现明确冲突。")
    lines.extend(f"- {_markdown_text(gap)}" for gap in report.gaps)
    if not report.gaps:
        lines.append("- 未发现关键缺口。")

    run_meta = json.dumps(
        report.to_dict()["run_meta"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    lines.extend(["", "## 运行信息", "", _code_span(run_meta), ""])
    return "\n".join(lines)


def _locator(locator: SourceLocator, fallback: str) -> str:
    parts: list[str] = []
    if locator.page_start:
        end = locator.page_end or locator.page_start
        parts.append(f"第 {locator.page_start} 页" if end == locator.page_start else f"第 {locator.page_start}-{end} 页")
    if locator.line_start:
        end = locator.line_end or locator.line_start
        parts.append(f"第 {locator.line_start} 行" if end == locator.line_start else f"第 {locator.line_start}-{end} 行")
    if locator.symbol:
        parts.append(f"符号 {locator.symbol}")
    if locator.url:
        parts.append(locator.url)
    return " / ".join(parts) or fallback or "未标注位置"


def _ids(values: tuple[str, ...]) -> str:
    return ", ".join(_code_span(value) for value in values) or "-"


def _code_span(value: object) -> str:
    return f"`{_markdown_text(value).replace('`', '&#96;')}`"


def _markdown_text(value: object) -> str:
    """Neutralize dynamic text before inserting it into Markdown."""

    normalized = " ".join(str(value).split())
    if normalized.startswith(("=", "+", "-", "@")):
        normalized = "'" + normalized
    return escape(normalized, quote=True).replace("|", "\\|")
