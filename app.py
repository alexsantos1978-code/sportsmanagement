from dotenv import load_dotenv
load_dotenv()

import json
import re
from pathlib import Path
import streamlit as st

from src.graph.workflow import run_workflow
from src.agents.legal import extract_contract_obligations
from src.tools.parsers import extract_text_from_file
from src.tools.audit_records import (
    list_audit_records,
    save_audit_record,
    verify_auditor_challenge,
)
from src.models.schemas import WorkflowInput
from src.tools.llm_provider import get_provider, is_enabled

# ────────────────────────────────────────────────────────────────────────────
# Page config & styling
# ────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sponsorship Audit",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1200px; }
      h1 { font-weight: 700; letter-spacing: -0.02em; }
      [data-testid="stMetricLabel"] { color: #6b7280; font-size: 0.85rem; font-weight: 500; }
      [data-testid="stMetricValue"] { font-weight: 700; }
      .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; }
      .stTabs [data-baseweb="tab"] { padding: 0.5rem 1rem; }
      div[data-testid="stForm"] { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; background: #fafbfc; }
      .pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
      .pill-ok  { background: #dcfce7; color: #15803d; }
      .pill-warn{ background: #fef3c7; color: #b45309; }
      .pill-info{ background: #dbeafe; color: #1e40af; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
header_col, badge_col = st.columns([4, 1])
with header_col:
    st.title("⚽ Sponsorship Audit")
    st.caption("Multi-agent KPI verification & billing for player sponsorship contracts")
with badge_col:
    provider_label = f"AI: {get_provider()}" if is_enabled() else "AI: off"
    pill_class = "pill-ok" if is_enabled() else "pill-info"
    st.markdown(
        f'<div style="text-align:right; margin-top:1.5rem;"><span class="pill {pill_class}">{provider_label}</span></div>',
        unsafe_allow_html=True,
    )

st.write("")

# ────────────────────────────────────────────────────────────────────────────
# Top-level tabs
# ────────────────────────────────────────────────────────────────────────────
tab_new, tab_challenge = st.tabs(["▶ New Audit", "🔍 Review Challenge"])


# ────────────────────────────────────────────────────────────────────────────
# New Audit flow
# ────────────────────────────────────────────────────────────────────────────
def render_new_audit() -> None:
    with st.form("audit_form", clear_on_submit=False):
        st.markdown("##### 1. Upload contract & data")
        col1, col2 = st.columns(2)
        with col1:
            contract = st.file_uploader("Contract (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])
        with col2:
            csv_file = st.file_uploader("KPI data (optional CSV)", type=["csv"])

        st.markdown("##### 2. Parties")
        col3, col4 = st.columns(2)
        with col3:
            player_name = st.text_input(
                "Player name",
                value="",
                placeholder="e.g. Raphael Dias Belloli",
            )
        with col4:
            sponsor_name = st.text_input(
                "Sponsor name",
                value="",
                placeholder="e.g. AcmeSport",
            )

        submitted = st.form_submit_button("▶ Run Audit", type="primary", use_container_width=True)

    if not submitted:
        return

    if not contract:
        st.error("Please upload a contract file.")
        return
    if not player_name.strip():
        st.error("Please enter the player name.")
        return
    if not sponsor_name.strip():
        st.error("Please enter the sponsor name.")
        return

    player_name = player_name.strip()
    sponsor_name = sponsor_name.strip()

    contracts_dir = Path("data/contracts")
    reports_dir = Path("data/reports")
    contracts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    contract_path = contracts_dir / contract.name
    contract_path.write_bytes(contract.getvalue())

    csv_path = None
    if csv_file:
        csv_path = contracts_dir / csv_file.name
        csv_path.write_bytes(csv_file.getvalue())

    contract_text = extract_text_from_file(str(contract_path))
    wf_input = WorkflowInput(
        player_name=player_name,
        sponsor_name=sponsor_name,
        contract_text=contract_text,
        csv_path=str(csv_path) if csv_path else None,
    )

    with st.spinner("Running multi-agent audit…"):
        result = run_workflow(wf_input)

    revisor = result.revisor_output
    research = result.research_output
    legal = result.legal_output

    approved = revisor.decision == "approved"
    total_due = revisor.audited_total_due if approved else research.total_variable_due
    n_total = len(research.payable_items)
    n_met = sum(1 for it in research.payable_items if it.get("met"))
    avg_conf = (
        sum(o.confidence for o in research.observations) / len(research.observations)
        if research.observations else 0.0
    )

    st.markdown("---")
    if approved:
        st.success(
            f"### ✅ Approved — €{total_due:,.2f} payable to {legal.player_name}\n"
            f"Audit complete. No issues flagged."
        )
    else:
        st.warning(
            f"### ⚠️ Needs Revision — {len(revisor.issues)} issue(s) flagged\n"
            f"Pending settlement: €{total_due:,.2f} (held until issues are resolved)."
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Decision", "Approved" if approved else "Needs Revision")
    m2.metric("Variable Due", f"€{total_due:,.0f}")
    m3.metric("KPIs Met", f"{n_met} / {n_total}")
    m4.metric("Avg. Confidence", f"{avg_conf * 100:.0f}%")

    st.markdown("#### Audit Decision")
    if approved:
        st.info("✓ All KPI observations passed validation. No issues raised by the Revisor agent.")
    else:
        with st.container(border=True):
            st.markdown(f"**The Revisor agent flagged {len(revisor.issues)} issue(s):**")
            for i, issue in enumerate(revisor.issues, 1):
                st.markdown(f"**{i}.** {issue}")

    tab_settle, tab_letter, tab_contract, tab_raw = st.tabs([
        "📊 KPI Settlement",
        "✉️ Billing Letter",
        "📋 Contract KPIs",
        "🧾 Raw Data",
    ])

    kpi_by_id = {k.id: k for k in legal.kpis}
    obs_by_kpi = {o.kpi_id: o for o in research.observations}

    rows = []
    for item in research.payable_items:
        kpi_id = item["kpi_id"]
        kpi = kpi_by_id.get(kpi_id)
        obs = obs_by_kpi.get(kpi_id)
        rows.append({
            "KPI": (kpi.description if kpi else kpi_id),
            "Threshold": item["threshold"],
            "Source A": obs.value_1 if obs else None,
            "Source B": obs.value_2 if obs else None,
            "Actual (reconciled)": item["actual"],
            "Status": "✅ Met" if item.get("met") else "❌ Not met",
            "Variable Due (EUR)": item["amount_due"],
            "Confidence": (obs.confidence if obs else 0.0),
        })

    settlement_column_config = {
        "Threshold": st.column_config.NumberColumn(format="%.2f"),
        "Source A": st.column_config.NumberColumn(format="%.2f"),
        "Source B": st.column_config.NumberColumn(format="%.2f"),
        "Actual (reconciled)": st.column_config.NumberColumn(format="%.2f"),
        "Variable Due (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
        "Confidence": st.column_config.ProgressColumn(
            "Confidence", format="%.0f%%", min_value=0.0, max_value=1.0
        ),
    }

    with tab_settle:
        st.caption("Each contractual KPI reconciled against two data sources, with payout status.")
        st.dataframe(rows, use_container_width=True, hide_index=True, column_config=settlement_column_config)

        if research.comments:
            with st.expander("Analyst commentary", expanded=False):
                for c in research.comments:
                    st.markdown(f"- {c}")

    with tab_letter:
        st.caption("Formal settlement statement for the finance team.")

        with st.container(border=True):
            st.markdown("**Subject:** Sponsorship KPI Settlement Statement")
            st.markdown(f"**To:** Finance Team — {legal.sponsor_name}")
            st.markdown(f"**Re:** {legal.player_name}")
            st.write("")
            st.markdown(
                f"Following the KPI performance audit for **{legal.player_name}**, "
                f"please find the settlement overview below."
            )
            st.write("")
            st.dataframe(rows, use_container_width=True, hide_index=True, column_config=settlement_column_config)
            st.markdown(f"### Total Variable Amount Due: € {total_due:,.2f}")
            st.write("")
            st.markdown("Kind regards,  \n**Account Management**")

        safe_name = re.sub(r"[^\w\-]", "_", player_name)[:80] or "audit"
        report_file = reports_dir / f"{safe_name}_report.txt"
        report_file.write_text(result.billing_letter, encoding="utf-8")

        st.download_button(
            "⬇ Download Billing Letter (Markdown)",
            data=result.billing_letter.encode("utf-8"),
            file_name=report_file.name,
            mime="text/markdown",
            use_container_width=True,
        )

    with tab_contract:
        st.caption("KPIs parsed from the contract by the Legal agent.")
        if legal.kpis:
            st.dataframe(
                [{
                    "KPI": kpi.description,
                    "Threshold": kpi.threshold,
                    "Unit": kpi.unit,
                    "Payout (EUR)": kpi.payout_amount,
                } for kpi in legal.kpis],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Threshold": st.column_config.NumberColumn(format="%.2f"),
                    "Payout (EUR)": st.column_config.NumberColumn(format="€ %.2f"),
                },
            )
        else:
            st.info("No KPIs were extracted from the contract.")

        if legal.notes:
            with st.expander("Parser notes", expanded=False):
                for n in legal.notes:
                    st.markdown(f"- {n}")

    with tab_raw:
        st.caption("Full structured workflow output for debugging or integration.")
        st.code(json.dumps(result.model_dump(), indent=2, ensure_ascii=False), language="json")

    audit_id = save_audit_record(
        wf_input=wf_input,
        result=result,
        report_file_name=report_file.name,
    )
    st.toast(f"Audit saved · ID {audit_id[:8]}…", icon="💾")


# ────────────────────────────────────────────────────────────────────────────
# Review Challenge flow
# ────────────────────────────────────────────────────────────────────────────
def render_review_challenge() -> None:
    st.markdown("##### Verify a third-party challenge against a stored audit record")
    st.caption(
        "Paste an auditor's claim (e.g. *'club_starting_appearances should be 28, not 31'*) "
        "and the Legal, Research, and Revisor agents will re-check it against the original audit."
    )

    audit_records = list_audit_records()
    if not audit_records:
        st.info("No stored audit records yet. Run at least one audit in the **New Audit** tab first.")
        return

    with st.container(border=True):
        options = {
            f"{row.get('player_name', 'n/a')} · {row.get('created_at', 'n/a')} · {row['audit_id'][:8]}": row["audit_id"]
            for row in audit_records
        }
        selected_label = st.selectbox("Audit record", options=list(options.keys()))
        selected_audit_id = options[selected_label]

        challenge_text = st.text_area(
            "Challenge message",
            height=140,
            placeholder=(
                "Example:\n"
                "club_starting_appearances should be 28, not 31.\n"
                "national_team_starting_appearance_pct is 70% based on federation records."
            ),
        )

        review_clicked = st.button("Review Challenge", type="primary", use_container_width=True)

    if not review_clicked:
        return

    if not challenge_text.strip():
        st.error("Please provide challenge text.")
        return

    with st.spinner("Running challenge verification across agents…"):
        review = verify_auditor_challenge(
            audit_id=selected_audit_id,
            challenge_text=challenge_text,
        )

    decision = (review.revisor_decision or "").lower()
    if "approve" in decision or "accept" in decision:
        st.success(f"**Decision:** {review.revisor_decision}")
    elif "reject" in decision or "deny" in decision:
        st.error(f"**Decision:** {review.revisor_decision}")
    else:
        st.warning(f"**Decision:** {review.revisor_decision}")

    if review.revisor_notes:
        st.markdown("**Revisor notes:**")
        for note in review.revisor_notes:
            st.markdown(f"- {note}")

    if review.legal_checks:
        st.markdown("**Legal scope verification:**")
        st.dataframe(
            [{
                "KPI": c.claim.kpi_id or "—",
                "Asserted Value": c.claim.asserted_value,
                "Expected Threshold": c.expected_threshold,
                "In Contract Scope": "✅" if c.in_contract_scope else "❌",
                "Rationale": c.claim.rationale,
            } for c in review.legal_checks],
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Full challenge review payload", expanded=False):
        st.code(json.dumps(review.model_dump(), indent=2, ensure_ascii=False), language="json")


# ────────────────────────────────────────────────────────────────────────────
# Render
# ────────────────────────────────────────────────────────────────────────────
with tab_new:
    render_new_audit()

with tab_challenge:
    render_review_challenge()