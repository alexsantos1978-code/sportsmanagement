from __future__ import annotations
from src.models.schemas import ContractExtraction, ResearchOutput, RevisorOutput
from src.tools.llm_provider import call_json, get_provider, is_enabled


def audit_outputs(legal_output: ContractExtraction, research_output: ResearchOutput) -> RevisorOutput:
    issues = []

    legal_kpis = {k.id for k in legal_output.kpis}
    observed_kpis = {o.kpi_id for o in research_output.observations}
    missing = legal_kpis - observed_kpis
    if missing:
        issues.append(f"Missing observations for KPIs: {sorted(missing)}")

    for obs in research_output.observations:
        if obs.confidence < 0.6:
            issues.append(f"Low confidence for KPI {obs.kpi_id}: {obs.confidence}")

    if is_enabled():
        llm_payload = call_json(
            system_prompt=(
                "You are a senior audit reviewer. Return only valid JSON. "
                "Focus on consistency risks between contract KPIs and observed evidence."
            ),
            user_prompt=(
                "Review this audit package and suggest additional issues if needed.\n"
                "Return JSON object with key 'issues' as an array of strings.\n"
                f"Legal KPIs: {[k.model_dump() for k in legal_output.kpis]}\n"
                f"Observations: {[o.model_dump() for o in research_output.observations]}\n"
                f"Payable items: {research_output.payable_items}"
            ),
            temperature=0.0,
        )
        if llm_payload:
            llm_issues = llm_payload.get("issues", [])
            if isinstance(llm_issues, list):
                for item in llm_issues:
                    text = str(item).strip()
                    if text and text not in issues:
                        issues.append(text)
            if llm_issues:
                issues.append(f"LLM-assisted review enabled via provider: {get_provider()}.")

    decision = "approved" if not issues else "needs_revision"
    audited_total = research_output.total_variable_due if decision == "approved" else 0.0

    return RevisorOutput(
        decision=decision,
        issues=issues,
        audited_total_due=audited_total,
    )