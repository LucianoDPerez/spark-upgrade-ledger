# AGENTS.md — spark-upgrade-ledger

## What this is

HER Hack-Astron #8 entry. Turns public Spark-X2.6 release notes into an upgrade checklist where every item must be traceable to a source line and reviewable by a human. The only generation step runs locally on Spark-X2.6-4B via llama-server (`http://localhost:8080/v1`). SkillHub skill `global/research-evidence-auditor` v20260820.034025 provides the claim-audit contract and deterministic report builder. No cloud inference. No diagnosis, no legal or safety claims.

## How to run

1. Verify the model: `curl http://localhost:8080/health` -> `{"status":"ok"}`. Model id `spark2.6-4B`. If down, start llama-server (command in README.md). NEVER fabricate outputs.
2. CLI: `python3 run.py --input data/release_notes.txt`.
3. UI: `python3 -m streamlit run app.py` (port 8501).
4. Tests (no model needed): `python3 -m unittest discover -s tests -v` — must stay green.
5. Skill: installed at `.codex/skills/research-evidence-auditor`. Reinstall with `npx @astron-team/skillhub@latest install research-evidence-auditor --namespace global --agent codex --scope project`.

## Architecture (do not break)

- `src/config.py` — single source of truth. No magic numbers elsewhere.
- `src/domain.py` — pure entities, no framework imports. `normalize()` + `cache_key` implement deduplication.
- `src/source.py` — parses release notes into numbered lines with provenance. Deterministic, no model.
- `src/prompts.py` — Spanish system prompt. Output is strict JSON with `source_quote` per item. No invented numbers, no diagnoses.
- `src/llm_client.py` — `LLMPort` protocol + `LlamaServerClient`. Fixed URL only (no SSRF). Always send `chat_template_kwargs: {enable_thinking: False}` — Spark-X2.6 fills the token budget with reasoning otherwise and returns empty content.
- `src/validator.py` — deterministic fail-closed gates: exact schema, no invented numbers, exact quote grounding, basic negation guard. Reject before cache and before screen.
- `src/audit.py` — adapter to the installed SkillHub skill. Builds the documented JSON contract and runs the skill's `scripts/audit_evidence.py`. Fail closed on bad input or bad output.
- `src/usecase.py` — `BuildChecklistUseCase.execute()` is the ONLY path to the LLM. Validate -> cache -> rate-limit -> LLM -> validate -> cache -> audit. Idempotent by content hash.
- `src/cache.py`, `src/ratelimit.py` — thread-safe, TTL / min-interval. Fail closed.
- UI (`app.py`, `run.py`) — thin layers. No business logic, no direct `requests` to the LLM. Human accepts, corrects or rejects each item.

## Rules

- SOLID / Clean / KISS / DRY. One responsibility per file. Inject fakes for tests (see `tests/test_usecase.py`), never call the real model in unit tests.
- Validate inputs: 20–8000 chars. Reject with `ValidationError`, never traceback internals.
- Never log full user texts or PII. Never commit secrets, tokens or personal data. `data/` contains short attributed public excerpts only.
- Record model revision, skill version and inference settings in `docs/DISCUSSION.md`. Keep it in sync with code.
- Report failures honestly. Do not invent model outputs.
