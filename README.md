# Upgrade Ledger

HER Hack-Astron #8 entry. Turns public Spark-X2.6 release notes into an **upgrade checklist where every item is traceable to a source line and can be accepted, corrected or rejected by a human**.

The only generation step runs locally on Spark-X2.6-4B through llama-server. A SkillHub skill (`global/research-evidence-auditor`) audits the generated claims. No cloud inference.

## Run

```bash
# 1. Model must be up
curl http://localhost:8080/health          # {"status":"ok"}
llama-server -m ~/.cache/huggingface/hub/models--XHToken--Spark-X2.6-4B-GGUF/snapshots/fe31f8d64890302cc3a1d365d700357b4b75ba77/Spark-X2.6-4B-Q4_K_M.gguf \
  -c 16384 -ngl 99 --port 8080 --alias spark2.6-4B \
  --temp 0.2 --top-p 0.95 --top-k 20 --repeat-penalty 1.05 --jinja

# 2. Local environment
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 3. Tests (no model needed)
.venv/bin/python -m unittest discover -s tests -v

# 4. CLI
.venv/bin/python run.py --output outputs/run.json

# 5. UI
.venv/bin/python -m streamlit run app.py
```

Skill reinstall (already committed in `.codex/skills/`):

```bash
npx @astron-team/skillhub@latest install research-evidence-auditor \
  --namespace global --agent codex --scope project
```

## Flow

```
public release notes (numbered lines)
  -> agent loads SkillHub skill
  -> Spark-X2.6-4B drafts strict JSON (ONE identifiable step)
  -> deterministic gates: schema / invented numbers / exact quote grounding / negation
  -> skill's audit_evidence.py produces a claim-level report
  -> human accepts, corrects or rejects each item
  -> final artifact JSON
```

`src/usecase.py` is the only path to the model: validate -> cache -> rate-limit -> LLM -> validate -> cache -> audit.

## Verified evidence

- Model: `spark2.6-4B`, revision `fe31f8d64890302cc3a1d365d700357b4b75ba77`, GGUF Q4_K_M, ctx 16384, file SHA256 `91cb2811aebb47ac916aa619d27d4cdd7f4143106b7917accb8ead4cd7f5cbd9`.
- Skill: `global/research-evidence-auditor` v`20260820.034025`, [detail page](https://skill.xfyun.cn/space/global/research-evidence-auditor), installed with SkillHub CLI 0.3.1. All 22 files match the hashes in `.skillhub/metadata.json`.
- Hardware/runtime: Apple M1, 16 GB RAM, macOS 15.5, llama.cpp `0.9.0` build `12110` commit `cd959bae9`.
- Unit tests: **31/31 pass**, no model needed, including explicit-approval cases (pending, empty correction, accept, reject) and the final-vs-review-log split.
- Three real local runs (`evidence/run-en.json`, `run-es.json`, `run-zh.json`): 3 items each, every quote grounded in exactly one numbered source line (source text verbatim from HF discussion #34), generation 21,669 / 24,958 / 23,960 ms. The audit receives **all source lines** as evidence, never only the model's own quotes, and no artificial `score=1.0`; status `partial` with 8 / 8 / 7 claims.
- Submission deadline: 2026-11-30 23:59 UTC. Issue: https://github.com/XHToken/Spark-X2.6/issues/32

## Languages

UI copy, generation prompt and review controls are localized in **English**, **Español** and **中文**. Select the language in the app or run `python3 run.py --lang en|es|zh`. `src/languages.py` holds all profiles; `source_quote` stays verbatim in every language because the validator requires an exact substring of the source. The model card declares en and zh; Spanish is a transfer observation, not a declared capability.

Three real CLI runs and three UI screenshots are committed under `evidence/` and `docs/`.

## Repository access

`main` is protected: changes require a pull request with 1 approving review from the code owner (`.github/CODEOWNERS` -> `@LucianoDPerez`), stale approvals are dismissed, the last push must be approved, conversations must be resolved, force pushes and branch deletions are blocked. Only the owner has write access to the repository. Only the owner can bypass the rule.

## Limitations

- Three runs on one short excerpt of a public community discussion (not official release notes); no blind benchmark, no user study.
- The skill's claim splitter fragments Spanish text (e.g. `breaking=False)`), so some claims are `insufficient` even when the exact-substring gate accepted the quote. Reported, not hidden.
- The `breaking` flag is only checked for type, not for semantic correctness against the source.
- The negation guard is a small keyword heuristic, not a semantic entailment check.
- Inputs over 8000 chars and lists over 12 items are rejected by design.
- AI-assisted development was used; all model outputs in `evidence/` are verbatim local runs.
- The auditor receives every source line, not only the quotes selected by the model; see `src/audit.py`.
