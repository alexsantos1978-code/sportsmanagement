from __future__ import annotations
from src.models.schemas import ContractExtraction, ResearchOutput, RevisorOutput

KPI_LABELS = {
    "goals_scored": "Goals Scored",
    "assists": "Assists",
    "club_starting_appearances": "Club Starting Appearances",
    "national_team_starting_appearance_pct": "National Team Starting Appearances (%)",
    "club_retainer_eur": "Club Retainer (EUR)",
    "national_team_retainer_eur": "National Team Retainer (EUR)",
    "total_annual_retainer_eur": "Total Annual Retainer (EUR)",
}

KPI_UNITS = {
    "goals_scored": "",
    "assists": "",
    "club_starting_appearances": "",
    "national_team_starting_appearance_pct": "%",
    "club_retainer_eur": "EUR",
    "national_team_retainer_eur": "EUR",
    "total_annual_retainer_eur": "EUR",
}

def build_summary(
    legal_output: ContractExtraction,
    research_output: ResearchOutput,
    revisor_output: RevisorOutput,
) -> str:
    return (
        f"Player: {legal_output.player_name}\n"
        f"Sponsor: {legal_output.sponsor_name}\n"
        f"Decision: {revisor_output.decision}\n"
        f"Audited Variable Amount Due: {revisor_output.audited_total_due:,.2f} EUR"
    )

def build_billing_letter(
    legal_output: ContractExtraction,
    research_output: ResearchOutput,
    revisor_output: RevisorOutput,
) -> str:
    def fmt_num(v: float) -> str:
        return f"{v:,.2f}"

    def fmt_currency(v: float, ccy: str = "EUR") -> str:
        return f"{fmt_num(v)} {ccy}"

    def label(kpi_id: str) -> str:
        return KPI_LABELS.get(kpi_id, kpi_id.replace("_", " ").title())

    def unit_for(kpi_id: str) -> str:
        return KPI_UNITS.get(kpi_id, "")

    obs_by_kpi = {obs.kpi_id: obs for obs in research_output.observations}

    # Build a lookup from KPI id → payable item
    payable_by_kpi = {item["kpi_id"]: item for item in research_output.payable_items}

    lines = []
    lines.append("Subject: Sponsorship KPI Settlement Statement")
    lines.append("")
    lines.append("Dear Finance Team,")
    lines.append("")
    lines.append(
        f"Following the KPI performance audit for **{legal_output.player_name}**, "
        "please find the settlement overview below."
    )
    lines.append("")
    lines.append("### KPI Settlement")
    lines.append("")
    lines.append("| KPI | Contract Threshold | Source A | Source B | Reconciled Actual | Status | Variable Due | Data Confidence |")
    lines.append("|---|---:|---|---|---:|:---:|---:|:---:|")

    for kpi in legal_output.kpis:
        unit = unit_for(kpi.id)
        obs = obs_by_kpi.get(kpi.id)
        item = payable_by_kpi.get(kpi.id, {})

        # Format threshold
        if unit == "%":
            threshold_txt = f"{fmt_num(kpi.threshold)}%"
        elif unit == "EUR":
            threshold_txt = fmt_currency(kpi.threshold, "EUR")
        else:
            threshold_txt = fmt_num(kpi.threshold)

        if obs is None:
            lines.append(
                f"| {label(kpi.id)} | {threshold_txt} | n/a | n/a | n/a | — | — | — |"
            )
            continue

        # Format source and reconciled values
        if unit == "%":
            src_a_txt = f"{obs.source_1}: {fmt_num(obs.value_1)}%"
            src_b_txt = f"{obs.source_2}: {fmt_num(obs.value_2)}%"
            reconciled_txt = f"{fmt_num(obs.reconciled_value)}%"
        elif unit == "EUR":
            src_a_txt = f"{obs.source_1}: {fmt_currency(obs.value_1)}"
            src_b_txt = f"{obs.source_2}: {fmt_currency(obs.value_2)}"
            reconciled_txt = fmt_currency(obs.reconciled_value)
        else:
            src_a_txt = f"{obs.source_1}: {fmt_num(obs.value_1)}"
            src_b_txt = f"{obs.source_2}: {fmt_num(obs.value_2)}"
            reconciled_txt = fmt_num(obs.reconciled_value)

        met = bool(item.get("met", obs.reconciled_value >= kpi.threshold))
        amount_due = float(item.get("amount_due", 0.0))
        ccy = item.get("currency", kpi.currency)
        status = "✅ Met" if met else "❌ Not met"
        due_txt = fmt_currency(amount_due, ccy)
        confidence_txt = f"{obs.confidence * 100:.1f}%"

        lines.append(
            f"| {label(kpi.id)} | {threshold_txt} | {src_a_txt} | {src_b_txt} | {reconciled_txt} | {status} | {due_txt} | {confidence_txt} |"
        )

    lines.append("")
    lines.append(f"**Total Variable Amount Due: {fmt_currency(revisor_output.audited_total_due, 'EUR')}**")
    lines.append("")
    lines.append("Kind regards,  ")
    lines.append("**Account Management**")

    return "\n".join(lines)