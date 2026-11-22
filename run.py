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
from src.languages import PROFILES, get_profile, t
from src.source import load_source
from src.usecase import BuildChecklistUseCase, ChecklistRequest


def render(result: ChecklistResult, profile) -> str:
    lines = [f"{t(profile, 'title')} — {profile.label}", f"Source: {result.source_name}", ""]
    lines.append(t(profile, "duration", ms=result.duration_ms))
    for warning in result.warnings:
        lines.append(f"Warning: {warning}")
    audit = result.audit
    if audit:
        lines.append(
            t(
                profile,
                "audit",
                status=audit.get("status"),
                claims=len(audit.get("claims", [])),
                gaps=len(audit.get("gaps", [])),
            )
        )
        lines.append("")
    for item in result.items:
        marker = t(profile, "breaking") if item.breaking else t(profile, "info")
        lines.append(f"[{item.id}] ({marker}) {item.title}")
        lines.append(f"      {t(profile, 'affects', value=item.affects)}")
        lines.append(f"      {t(profile, 'line', number=item.line_start, quote=item.source_quote)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--lang", choices=sorted(PROFILES), default="es")
    args = parser.parse_args()

    profile = get_profile(args.lang)
    source = load_source(args.input)
    usecase = BuildChecklistUseCase(auditor=SkillAuditor())
    result = usecase.execute(
        ChecklistRequest(
            source_text=args.input.read_text(encoding="utf-8"),
            source_name=source.name,
            lang=args.lang,
        )
    )

    print(render(result, profile))
    if args.output is not None:
        payload = {
            "source": {"name": source.name, "url": source.url},
            "lang": result.lang,
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
