"""Conservative deterministic conflict signals for claim/evidence pairs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from rag.evidence.models import EvidenceRelation


NUMBER_TOKEN = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
VERSION_TOKEN = re.compile(
    r"(?<![\w])(?:v(?:ersion)?\s*)?\d+(?:\.\d+){1,3}(?![\w])|"
    r"(?<!\d)(?:19|20)\d{2}(?:[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?)?(?!\d)",
    re.IGNORECASE,
)
NEGATION_MARKERS = (
    "并非", "不是", "不会", "不能", "无法", "没有", "未能", "未通过",
    "不支持", "不得", "无证据",
)
ENGLISH_NEGATION = re.compile(
    r"\b(?:no|not|never|cannot|can't|doesn't|didn't)\b|"
    r"\b(?:does|did)\s+not\b",
    re.IGNORECASE,
)
UPWARD_MARKERS = (
    "提高", "增加", "上升", "改善", "通过", "支持", "允许",
    "improve", "increase", "rise", "pass", "support", "allow",
)
DOWNWARD_MARKERS = (
    "降低", "减少", "下降", "恶化", "失败", "反对", "禁止",
    "decrease", "decline", "drop", "fail", "oppose", "prohibit",
)
CHINESE_ATTRIBUTE = re.compile(
    r"(?P<entity>[\u4e00-\u9fffA-Za-z0-9_.+-]{1,32})\s*(?:的)?\s*"
    r"(?P<attribute>版本|许可证|许可协议|状态|颜色|语言|框架|数据库|端口|作者|负责人|"
    r"准确率|召回率)"
    r"(?:为|是|采用|使用|等于|：|:)\s*(?P<value>[^，。；;\n]{1,64})"
)
ENGLISH_ATTRIBUTE = re.compile(
    r"(?P<entity>[A-Za-z0-9_.+-]{1,32})(?:'s)?\s+"
    r"(?P<attribute>version|licen[cs]e|status|color|language|framework|database|"
    r"port|author|owner|accuracy|recall)\s+"
    r"(?:is|was|uses?|equals?|=|:)\s*(?P<value>[^,.;\n]{1,64})",
    re.IGNORECASE,
)


class ConflictKind(str, Enum):
    NUMERIC = "numeric"
    TEMPORAL_VERSION = "temporal_version"
    POLARITY = "polarity"
    DIRECTION = "direction"
    ATTRIBUTE = "attribute"


@dataclass(frozen=True)
class ConflictSignal:
    kind: ConflictKind
    relation: EvidenceRelation
    confidence_floor: float
    rationale: str
    suspected: bool = False


def detect_conflict_signal(
    left: str,
    right: str,
    *,
    alignment_score: float,
    has_shared_context: bool,
) -> ConflictSignal | None:
    """Return a strong or suspected conflict without guessing beyond the text."""

    if not has_shared_context:
        return None

    if opposite_direction(left, right):
        return ConflictSignal(
            kind=ConflictKind.DIRECTION,
            relation=EvidenceRelation.CONTRADICTS,
            confidence_floor=0.65,
            rationale="结论与证据包含方向相反的变化或结论词",
        )

    if has_negation(left) != has_negation(right):
        return ConflictSignal(
            kind=ConflictKind.POLARITY,
            relation=EvidenceRelation.CONTRADICTS,
            confidence_floor=0.65,
            rationale="结论与证据的明确否定表达不一致",
        )

    left_attribute = extract_attribute(left)
    right_attribute = extract_attribute(right)
    if _same_attribute(left_attribute, right_attribute):
        if left_attribute[2] != right_attribute[2]:
            if _different_temporal_versions(left, right):
                return _suspected_temporal_signal()
            return ConflictSignal(
                kind=ConflictKind.ATTRIBUTE,
                relation=EvidenceRelation.CONTRADICTS,
                confidence_floor=0.7,
                rationale="同一实体的同一属性取值不一致",
            )

    if _different_temporal_versions(left, right):
        return _suspected_temporal_signal()

    left_numbers = numbers(left)
    right_numbers = numbers(right)
    if (
        alignment_score >= 0
        and len(left_numbers) == 1
        and len(right_numbers) == 1
        and left_numbers.isdisjoint(right_numbers)
    ):
        return ConflictSignal(
            kind=ConflictKind.NUMERIC,
            relation=EvidenceRelation.CONTRADICTS,
            confidence_floor=0.7,
            rationale="同一候选语境中的单一数值不一致",
        )
    return None


def extract_attribute(text: str) -> tuple[str, str, str] | None:
    for pattern in (CHINESE_ATTRIBUTE, ENGLISH_ATTRIBUTE):
        match = pattern.search(text.strip())
        if match:
            return tuple(_normalize_part(match.group(name)) for name in ("entity", "attribute", "value"))
    return None


def numbers(text: str) -> set[str]:
    return {token.casefold() for token in NUMBER_TOKEN.findall(text)}


def has_negation(text: str) -> bool:
    normalized = f" {text.casefold()} "
    return any(marker in normalized for marker in NEGATION_MARKERS) or bool(
        ENGLISH_NEGATION.search(normalized)
    )


def opposite_direction(left: str, right: str) -> bool:
    left_direction = _direction(left)
    right_direction = _direction(right)
    return bool(left_direction and right_direction and left_direction != right_direction)


def _suspected_temporal_signal() -> ConflictSignal:
    return ConflictSignal(
        kind=ConflictKind.TEMPORAL_VERSION,
        relation=EvidenceRelation.INSUFFICIENT,
        confidence_floor=0.0,
        rationale="疑似冲突：材料的时间或版本不同，不能直接判定事实互相反驳",
        suspected=True,
    )


def _different_temporal_versions(left: str, right: str) -> bool:
    left_versions = {_normalize_part(item) for item in VERSION_TOKEN.findall(left)}
    right_versions = {_normalize_part(item) for item in VERSION_TOKEN.findall(right)}
    return bool(left_versions and right_versions and left_versions.isdisjoint(right_versions))


def _same_attribute(
    left: tuple[str, str, str] | None,
    right: tuple[str, str, str] | None,
) -> bool:
    return bool(left and right and left[:2] == right[:2])


def _normalize_part(value: str) -> str:
    return " ".join(value.casefold().strip().split()).rstrip("。.")


def _direction(text: str) -> str:
    normalized = text.casefold()
    has_upward = any(marker in normalized for marker in UPWARD_MARKERS)
    has_downward = any(marker in normalized for marker in DOWNWARD_MARKERS)
    if has_upward == has_downward:
        return ""
    return "upward" if has_upward else "downward"
