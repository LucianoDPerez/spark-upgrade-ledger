"""The only path from validated input to the local model."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from .audit import SkillAuditor
from .cache import TTLCache
from .config import MODEL_REVISION, SKILL_VERSION
from .domain import ChecklistResult, ValidationError, cache_key
from .languages import get_profile
from .llm_client import LLMPort, LlamaServerClient
from .prompts import build_user_prompt
from .ratelimit import MinIntervalLimiter
from .source import parse_source
from .validator import parse_draft, validate_draft


@dataclass(frozen=True)
class ChecklistRequest:
    source_text: str
    source_name: str = "release_notes.txt"
    lang: str = "es"


class BuildChecklistUseCase:
    def __init__(
        self,
        llm: LLMPort | None = None,
        cache: TTLCache | None = None,
        limiter: MinIntervalLimiter | None = None,
        auditor: SkillAuditor | None = None,
    ) -> None:
        self.llm: LLMPort = llm if llm is not None else LlamaServerClient()
        self.cache = cache if cache is not None else TTLCache()
        self.limiter = limiter if limiter is not None else MinIntervalLimiter()
        self.auditor = auditor

    def execute(self, request: ChecklistRequest) -> ChecklistResult:
        if not isinstance(request, ChecklistRequest):
            raise ValidationError("Invalid request.")
        profile = get_profile(request.lang)
        source = parse_source(request.source_text, request.source_name)
        key = cache_key(source.normalized_text(), MODEL_REVISION, SKILL_VERSION, profile.code)

        cached = self.cache.get(key)
        if isinstance(cached, ChecklistResult):
            return cached

        self.limiter.check()
        started = time.monotonic()
        raw = self.llm.complete(profile.system_prompt, build_user_prompt(source.as_prompt()))
        duration_ms = int((time.monotonic() - started) * 1000)
        outcome = validate_draft(parse_draft(raw), source.normalized_text())
        items = tuple(
            replace(item, line_start=source.find_lines(item.source_quote)[0],
                    line_end=source.find_lines(item.source_quote)[1])
            for item in outcome.items
        )

        result = ChecklistResult(
            source_name=source.name,
            items=items,
            raw_output=raw,
            lang=profile.code,
            warnings=outcome.warnings,
            duration_ms=duration_ms,
        )
        if self.auditor is not None:
            result = replace(result, audit=self.auditor.run(result, source))

        self.cache.set(key, result)
        return result
