"""Adapter to the installed SkillHub skill research-evidence-auditor."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import SKILL_AUDIT_SCRIPT
from .domain import ChecklistResult, GenerationError, SourceDocument


def build_payload(result: ChecklistResult, source: SourceDocument) -> dict:
    """Build the documented JSON input contract of the installed skill."""
    sources = []
    for index, item in enumerate(result.items, start=1):
        line_start, line_end = source.find_lines(item.source_quote)
        sources.append(
            {
                "title": f"{source.name} line {line_start or 'unknown'}",
                "source": source.url or source.name,
                "doc_type": "text",
                "chunk_id": index,
                "content": item.source_quote,
                "score": 1.0,
                "metadata": {"line_start": line_start, "line_end": line_end},
            }
        )
    answer = "\n".join(
        f"{item.id}: {item.title} (affects {item.affects}; breaking={item.breaking})"
        for item in result.items
    )
    return {
        "answer": answer,
        "sources": sources,
        "mode": "local",
        "retrieval_strategy": "exact_line",
        "answer_mode": "generated_checklist",
        "duration_ms": result.duration_ms,
        "degraded_services": [],
    }


def run_audit(payload: dict, script: Path = SKILL_AUDIT_SCRIPT) -> dict:
    """Run the skill's deterministic report builder. Fail closed."""
    if not script.is_file():
        raise GenerationError("SkillHub audit script is not installed.")
    if not isinstance(payload, dict) or not payload.get("sources"):
        raise GenerationError("Audit input has no evidence sources.")

    with tempfile.TemporaryDirectory(prefix="upgrade-ledger-audit-") as tmp:
        in_path = Path(tmp) / "input.json"
        out_path = Path(tmp) / "report.json"
        in_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, str(script), str(in_path), "--pretty", "--output", str(out_path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GenerationError(f"SkillHub audit could not run: {type(exc).__name__}") from exc
        if completed.returncode != 0 or not out_path.is_file():
            raise GenerationError("SkillHub audit rejected the input.")
        try:
            report = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GenerationError("SkillHub audit produced unreadable output.") from exc

    if not isinstance(report, dict) or report.get("status") not in {"complete", "partial", "refused"}:
        raise GenerationError("SkillHub audit produced an invalid report.")
    return report


class SkillAuditor:
    def run(self, result: ChecklistResult, source: SourceDocument) -> dict:
        return run_audit(build_payload(result, source))
