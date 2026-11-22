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

- Model: `spark2.6-4B`, revision `fe31f8d64890302cc3a1d365d700357b4b75ba77`, GGUF Q4_K_M, ctx 16384.
- Skill: `global/research-evidence-auditor` v`20260820.034025`, [detail page](https://skill.xfyun.cn/space/global/research-evidence-auditor), installed with SkillHub CLI 0.3.1.
- Unit tests: **18/18 pass**, no model needed.
- Real local run (`outputs/run-03.json`): 3 items, all quotes are exact substrings of numbered source lines, generation **21,578 ms**, audit `status=partial` with 5 claims (2 supported, 3 insufficient).
- Submission deadline: 2026-11-30 23:59 UTC. Issue: https://github.com/XHToken/Spark-X2.6/issues/32

## Repository access

`main` is protected: changes require a pull request with 1 approving review from the code owner (`.github/CODEOWNERS` -> `@LucianoDPerez`), stale approvals are dismissed, the last push must be approved, conversations must be resolved, force pushes and branch deletions are blocked. Only the owner has write access to the repository. Only the owner can bypass the rule.

## Limitations

- One real run on one hand-written short excerpt; no blind benchmark, no user study.
- The skill's claim splitter fragments Spanish text (e.g. `breaking=False)`), so some claims are `insufficient` even when our exact-substring gate accepted the quote. Reported, not hidden.
- The `breaking` flag is only checked for type, not for semantic correctness against the source.
- The negation guard is a small keyword heuristic, not a semantic entailment check.
- Inputs over 8000 chars and lists over 12 items are rejected by design.
- AI-assisted development was used; all model outputs in `outputs/` are verbatim local runs.
