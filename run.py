#!/usr/bin/env python3
"""CLI demo: input -> Spark draft -> deterministic gates -> skill audit -> review."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.audit import SkillAuditor
from src.config import DEFAULT_INPUT
from src.domain import ChecklistResult
from src.source import load_source
from src.usecase import BuildChecklistUseCase, ChecklistRequest


def render(result: ChecklistResult) -> str:
    lines = [f"Source: {result.source_name}", ""]
    audit = result.audit
    lines.append(f"Spark generation: {result.duration_ms} ms")
    for warning in result.warnings:
        lines.append(f"Warning: {warning}")
    if audit:
        lines.append(f"SkillHub audit: status={audit.get('status')}, claims={len(audit.get('claims', []))}")
        lines.append("")
    for item in result.items:
        marker = "BREAKING" if item.breaking else "info"
        lines.append(f"[{item.id}] ({marker}) {item.title}")
        lines.append(f"      affects: {item.affects}")
        lines.append(f"      source line {item.line_start}: {item.source_quote}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    source = load_source(args.input)
    usecase = BuildChecklistUseCase(auditor=SkillAuditor())
    result = usecase.execute(
        ChecklistRequest(source_text=args.input.read_text(encoding="utf-8"), source_name=source.name)
    )

    print(render(result))
    if args.output is not None:
        payload = {
            "source": {"name": source.name, "url": source.url},
            "items": [asdict(item) for item in result.items],
            "raw_output": result.raw_output,
            "warnings": list(result.warnings),
            "duration_ms": result.duration_ms,
            "audit": result.audit,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nArtifact written to {args.output}")


if __name__ == "__main__":
    main()
