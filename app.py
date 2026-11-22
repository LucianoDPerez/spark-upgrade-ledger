"""Thin multilingual Streamlit UI. No business logic, no direct LLM calls."""

from __future__ import annotations

import json

import streamlit as st

from src.audit import SkillAuditor
from src.config import DEFAULT_INPUT
from src.domain import Review
from src.languages import PROFILES, get_profile, t
from src.usecase import BuildChecklistUseCase, ChecklistRequest

st.set_page_config(page_title="Upgrade Ledger", page_icon="✅")

_LABELS = [p.label for p in PROFILES.values()]
selected_label = st.selectbox("Language / Idioma / 语言", _LABELS)
code = next(c for c, p in PROFILES.items() if p.label == selected_label)

if st.session_state.get("lang") != code:
    st.session_state["lang"] = code
    st.session_state.pop("result", None)
    st.session_state.pop("reviews", None)

profile = get_profile(code)

st.title(t(profile, "title"))
st.caption(t(profile, "subtitle"))


@st.cache_resource(show_spinner=False)
def get_usecase() -> BuildChecklistUseCase:
    return BuildChecklistUseCase(auditor=SkillAuditor())


example_text = DEFAULT_INPUT.read_text(encoding="utf-8")

st.text(t(profile, "step1"))
pasted = st.text_area(t(profile, "notes"), value=example_text, height=180)
st.caption(t(profile, "step2"))
uploaded = st.file_uploader(t(profile, "upload"), type=["txt"])

if uploaded is not None:
    source_text = uploaded.getvalue().decode("utf-8")
    source_name = uploaded.name
elif pasted.strip():
    source_text = pasted
    source_name = "notas.txt"
else:
    source_text = example_text
    source_name = DEFAULT_INPUT.name

if st.button(t(profile, "generate"), type="primary"):
    try:
        result = get_usecase().execute(
            ChecklistRequest(source_text=source_text, source_name=source_name, lang=code)
        )
        st.session_state["result"] = result
        st.session_state["reviews"] = {}
    except Exception as exc:
        st.error(t(profile, "error", error=exc))

result = st.session_state.get("result")
if result is None:
    st.info(t(profile, "empty"))
else:
    st.subheader(t(profile, "raw"))
    with st.expander(t(profile, "raw_expander")):
        st.code(result.raw_output, language="json")

    st.caption(t(profile, "duration", ms=result.duration_ms))
    for warning in result.warnings:
        st.warning(warning)

    audit = result.audit
    if audit:
        st.caption(
            t(
                profile,
                "audit",
                status=audit.get("status"),
                claims=len(audit.get("claims", [])),
                gaps=len(audit.get("gaps", [])),
            )
        )

    st.subheader(t(profile, "review"))
    canonical = ("accept", "correct", "reject")
    labels = [t(profile, d) for d in canonical]
    for item in result.items:
        with st.container(border=True):
            marker = t(profile, "breaking") if item.breaking else t(profile, "info")
            st.markdown(f"**[{item.id}]** {marker} — {item.title}")
            st.write(t(profile, "affects", value=item.affects))
            st.caption(t(profile, "line", number=item.line_start, quote=item.source_quote))
            current = st.session_state["reviews"].get(item.id, Review("accept")).decision
            chosen_label = st.radio(
                t(profile, "decision", id=item.id),
                labels,
                index=canonical.index(current),
                key=f"decision-{code}-{item.id}",
                horizontal=True,
            )
            decision = canonical[labels.index(chosen_label)]
            correction = ""
            if decision == "correct":
                correction = st.text_input(
                    t(profile, "correction", id=item.id), key=f"corr-{code}-{item.id}"
                )
            st.session_state["reviews"][item.id] = Review(decision=decision, corrected_text=correction)

    approved = tuple(
        item for item in result.items
        if st.session_state["reviews"].get(item.id, Review("accept")).decision != "reject"
    )
    st.caption(t(profile, "approved", n=len(approved), total=len(result.items)))

    artifact = {
        "source": result.source_name,
        "lang": result.lang,
        "approved": [
            {
                **item.__dict__,
                "decision": st.session_state["reviews"].get(item.id, Review("accept")).decision,
                "corrected_text": st.session_state["reviews"].get(item.id, Review("accept")).corrected_text,
            }
            for item in approved
        ],
        "audit_status": audit.get("status", ""),
    }
    st.download_button(
        t(profile, "download"),
        data=json.dumps(artifact, ensure_ascii=False, indent=2),
        file_name="upgrade-ledger.json",
        mime="application/json",
    )
