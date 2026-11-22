"""Verify common derived quantities with deterministic decimal arithmetic."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import json
import sys
from typing import Mapping


OPERATIONS = {"ratio", "difference", "relative_change", "convert", "implied_rate"}


class CalculationInputError(ValueError):
    """Raised when a calculation request is invalid."""


def verify(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise CalculationInputError("input must be a JSON object")
    operation = payload.get("operation")
    if operation not in OPERATIONS:
        raise CalculationInputError("unsupported operation")
    values = payload.get("values")
    if not isinstance(values, Mapping):
        raise CalculationInputError("values must be an object")
    precision = payload.get("precision", 2)
    if isinstance(precision, bool) or not isinstance(precision, int) or not 0 <= precision <= 12:
        raise CalculationInputError("precision must be an integer from 0 to 12")

    with localcontext() as context:
        context.prec = 40
        raw_result, formula, normalized_inputs = _calculate(operation, values, payload)
        quantum = Decimal(1).scaleb(-precision)
        rounded = raw_result.quantize(quantum, rounding=ROUND_HALF_UP)
    return {
        "operation": operation,
        "inputs": normalized_inputs,
        "formula": formula,
        "raw_result": _decimal_text(raw_result),
        "precision": precision,
        "rounding": "ROUND_HALF_UP",
        "rounded_result": _decimal_text(rounded),
    }


def _calculate(
    operation: str,
    values: Mapping[object, object],
    payload: Mapping[object, object],
) -> tuple[Decimal, str, dict[str, str]]:
    if operation == "ratio":
        numerator = _decimal(values, "numerator")
        denominator = _nonzero_decimal(values, "denominator")
        scale = _payload_decimal(payload, "scale", Decimal(100))
        return (
            numerator / denominator * scale,
            "numerator / denominator * scale",
            _inputs(numerator=numerator, denominator=denominator, scale=scale),
        )
    if operation == "difference":
        left = _decimal(values, "left")
        right = _decimal(values, "right")
        return left - right, "left - right", _inputs(left=left, right=right)
    if operation == "relative_change":
        current = _decimal(values, "current")
        baseline = _nonzero_decimal(values, "baseline")
        scale = _payload_decimal(payload, "scale", Decimal(100))
        return (
            (current - baseline) / baseline * scale,
            "(current - baseline) / baseline * scale",
            _inputs(current=current, baseline=baseline, scale=scale),
        )
    if operation == "convert":
        amount = _decimal(values, "amount")
        rate = _decimal(values, "rate")
        return amount * rate, "amount * rate", _inputs(amount=amount, rate=rate)
    converted = _decimal(values, "converted")
    amount = _nonzero_decimal(values, "amount")
    return converted / amount, "converted / amount", _inputs(converted=converted, amount=amount)


def _decimal(values: Mapping[object, object], key: str) -> Decimal:
    if key not in values or isinstance(values[key], bool):
        raise CalculationInputError(f"{key} must be a decimal value")
    try:
        value = Decimal(str(values[key]))
    except (InvalidOperation, ValueError) as exc:
        raise CalculationInputError(f"{key} must be a decimal value") from exc
    if not value.is_finite():
        raise CalculationInputError(f"{key} must be finite")
    return value


def _nonzero_decimal(values: Mapping[object, object], key: str) -> Decimal:
    value = _decimal(values, key)
    if value == 0:
        raise CalculationInputError(f"{key} must not be zero")
    return value


def _payload_decimal(
    payload: Mapping[object, object],
    key: str,
    default: Decimal,
) -> Decimal:
    if key not in payload:
        return default
    return _decimal(payload, key)


def _inputs(**values: Decimal) -> dict[str, str]:
    return {key: _decimal_text(value) for key, value in values.items()}


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def main() -> int:
    try:
        payload = json.loads(sys.argv[1]) if len(sys.argv) == 2 else json.load(sys.stdin)
        result = verify(payload)
    except (CalculationInputError, json.JSONDecodeError) as exc:
        print(f"calculation input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
