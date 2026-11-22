"""Thin Streamlit UI. No business logic, no direct LLM calls."""

from __future__ import annotations

import json

import streamlit as st

from src.audit import SkillAuditor
from src.config import DEFAULT_INPUT
from src.domain import Review
from src.usecase import BuildChecklistUseCase, ChecklistRequest

st.set_page_config(page_title="Upgrade Ledger", page_icon="✅")
st.title("Upgrade Ledger")
st.caption("Notas de lanzamiento publicas -> checklist verificable con revision humana.")


@st.cache_resource(show_spinner=False)
def get_usecase() -> BuildChecklistUseCase:
    return BuildChecklistUseCase(auditor=SkillAuditor())


uploaded = st.file_uploader("Notas de lanzamiento (.txt)", type=["txt"])
if uploaded is not None:
    source_text = uploaded.getvalue().decode("utf-8")
    source_name = uploaded.name
else:
    source_text = DEFAULT_INPUT.read_text(encoding="utf-8")
    source_name = DEFAULT_INPUT.name

if st.button("Generar checklist", type="primary"):
    try:
        result = get_usecase().execute(ChecklistRequest(source_text=source_text, source_name=source_name))
        st.session_state["result"] = result
        st.session_state["reviews"] = {}
    except Exception as exc:
        st.error(f"No se pudo generar el checklist: {exc}")

result = st.session_state.get("result")
if result is None:
    st.info("Cargá un archivo o usá el ejemplo incluido y presioná Generar checklist.")
else:
    st.subheader("Salida cruda de Spark")
    with st.expander("Ver JSON generado por el modelo"):
        st.code(result.raw_output, language="json")

    st.caption(f"Generacion local: {result.duration_ms} ms")
    for warning in result.warnings:
        st.warning(warning)

    audit = result.audit
    if audit:
        st.caption(
            f"SkillHub research-evidence-auditor: status={audit.get('status')}, "
            f"claims={len(audit.get('claims', []))}, gaps={len(audit.get('gaps', []))}"
        )

    st.subheader("Revision humana")
    for item in result.items:
        with st.container(border=True):
            st.markdown(f"**[{item.id}]** {'BREAKING' if item.breaking else 'info'} — {item.title}")
            st.write(f"Afecta: {item.affects}")
            st.caption(f"Linea {item.line_start}: {item.source_quote}")
            key = f"decision-{item.id}"
            decision = st.radio(
                f"Decision para {item.id}",
                ["accept", "correct", "reject"],
                index=["accept", "correct", "reject"].index(
                    st.session_state["reviews"].get(item.id, Review("accept")).decision
                ),
                key=key,
                horizontal=True,
            )
            correction = ""
            if decision == "correct":
                correction = st.text_input(f"Correccion para {item.id}", key=f"corr-{item.id}")
            st.session_state["reviews"][item.id] = Review(decision=decision, corrected_text=correction)

    approved = tuple(
        item for item in result.items
        if st.session_state["reviews"].get(item.id, Review("accept")).decision != "reject"
    )
    st.caption(f"Aprobados: {len(approved)} de {len(result.items)}")

    artifact = {
        "source": result.source_name,
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
        "Descargar artefacto final (JSON)",
        data=json.dumps(artifact, ensure_ascii=False, indent=2),
        file_name="upgrade-ledger.json",
        mime="application/json",
    )
