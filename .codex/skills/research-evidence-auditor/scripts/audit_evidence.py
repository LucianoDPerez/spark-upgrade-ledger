"""Build a deterministic evidence-audit report from a JSON payload."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from collections.abc import Mapping
from typing import Any, Sequence, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.evidence import build_evidence_report, report_to_dict  # noqa: E402


MAX_INPUT_BYTES = 10 * 1024 * 1024


class AuditInputError(ValueError):
    """Raised for invalid or unsafe CLI input."""


def build_report_from_payload(payload: object) -> dict[str, Any]:
    """Validate a JSON payload and return the public report contract."""

    if not isinstance(payload, Mapping):
        raise AuditInputError("input JSON must be an object")

    answer = payload.get("answer")
    if not isinstance(answer, str):
        raise AuditInputError("answer must be a string")

    retrieval_sources = payload.get(
        "retrieval_sources",
        payload.get("sources", []),
    )
    if retrieval_sources is None:
        retrieval_sources = []
    if not isinstance(retrieval_sources, list):
        raise AuditInputError("sources must be an array")

    duration_ms = payload.get("duration_ms", 0)
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or duration_ms < 0
    ):
        raise AuditInputError("duration_ms must be a non-negative integer")

    degraded_services = payload.get("degraded_services", [])
    if degraded_services is None:
        degraded_services = []
    if not isinstance(degraded_services, list) or any(
        not isinstance(item, str) for item in degraded_services
    ):
        raise AuditInputError("degraded_services must be an array of strings")

    report = build_evidence_report(
        answer=answer,
        retrieval_sources=retrieval_sources,
        retrieval_strategy=_optional_label(
            payload.get("retrieval_strategy"),
            "hybrid_rerank",
        ),
        answer_mode=_optional_label(
            payload.get("answer_mode", payload.get("mode")),
            "unknown",
        ),
        duration_ms=duration_ms,
        degraded_services=degraded_services,
    )
    return report_to_dict(report)


def _optional_label(value: object, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise AuditInputError("runtime labels must be strings")
    return value.strip() or default


def read_json_payload(path_value: str, stdin: TextIO = sys.stdin) -> object:
    """Read bounded UTF-8 JSON from a file or ``-`` for standard input."""

    if path_value == "-":
        raw_bytes = stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        input_path = Path(path_value)
        if input_path.stat().st_size > MAX_INPUT_BYTES:
            raise AuditInputError(
                f"input exceeds the {MAX_INPUT_BYTES}-byte safety limit"
            )
        raw_bytes = input_path.read_bytes()

    if len(raw_bytes) > MAX_INPUT_BYTES:
        raise AuditInputError(
            f"input exceeds the {MAX_INPUT_BYTES}-byte safety limit"
        )
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AuditInputError("input must be UTF-8 encoded") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuditInputError(
            f"input is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc


def write_json_result(
    payload: Mapping[str, Any],
    output_path: str | None,
    *,
    pretty: bool,
    stdout: TextIO = sys.stdout,
) -> None:
    """Write UTF-8 JSON to stdout or atomically replace the requested file."""

    indent = 2 if pretty else None
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=indent,
        separators=None if pretty else (",", ":"),
    )
    serialized += "\n"
    if output_path is None or output_path == "-":
        stdout.write(serialized)
        return

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit an answer against retrieved source excerpts.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="UTF-8 JSON input path; use - or omit for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="JSON output path; omit or use - for stdout",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="indent the JSON output for human review",
    )
    return parser


def configure_utf8_output() -> None:
    """Keep redirected JSON and diagnostics portable on Windows terminals."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        input_payload = read_json_payload(args.input)
        report = build_report_from_payload(input_payload)
        write_json_result(report, args.output, pretty=args.pretty)
    except (AuditInputError, OSError) as exc:
        print(f"evidence audit input error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
