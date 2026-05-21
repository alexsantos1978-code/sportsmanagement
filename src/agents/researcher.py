from __future__ import annotations
from typing import Optional
import pandas as pd

from src.models.schemas import ContractExtraction, ResearchOutput, KPIObservation
from src.tools.data_sources import get_mock_kpi_values
from src.tools.llm_provider import call_json, get_provider, is_enabled


def _read_csv_value(csv_path: Optional[str], kpi_id: str) -> Optional[float]:
    """
    Expected CSV columns (minimum):
      - kpi_id
      - value
    Example:
      kpi_id,value
      goals_scored,22
      club_starting_appearances,31
      national_team_starting_appearance_pct,78
    """
    if not csv_path:
        return None
    try:
        df = pd.read_csv(csv_path)
        if "kpi_id" not in df.columns or "value" not in df.columns:
            return None
        row = df[df["kpi_id"] == kpi_id]
        if row.empty:
            return None
        return float(row.iloc[0]["value"])
    except Exception:
        return None


def _default_value_for_kpi(kpi_id: str) -> tuple[float, float]:
    """
    Returns fallback twin-source values for KPI IDs not covered by get_mock_kpi_values().
    """
    # Existing mock function should handle goals/assists.
    if kpi_id in {"goals_scored", "assists"}:
        return get_mock_kpi_values(kpi_id)

    # New contract KPIs (heuristic mock defaults)
    if kpi_id == "club_starting_appearances":
        return 32.0, 30.0
    if kpi_id == "national_team_starting_appearance_pct":
        return 78.0, 74.0
    if kpi_id == "club_retainer_eur":
        return 800000.0, 800000.0
    if kpi_id == "national_team_retainer_eur":
        return 500000.0, 500000.0
    if kpi_id == "total_annual_retainer_eur":
        return 1300000.0, 1300000.0

    # Generic fallback
    return 0.0, 0.0


def _is_variable_payout_kpi(kpi_id: str) -> bool:
    """
    Fixed retainer KPIs are informational and should not add variable bonus payout.
    """
    fixed_ids = {
        "club_retainer_eur",
        "national_team_retainer_eur",
        "total_annual_retainer_eur",
    }
    return kpi_id not in fixed_ids


def gather_and_compute(legal_output: ContractExtraction, csv_path: Optional[str] = None) -> ResearchOutput:
    observations: list[KPIObservation] = []
    payable_items: list[dict] = []
    total_due = 0.0

    for kpi in legal_output.kpis:
        v1, v2 = _default_value_for_kpi(kpi.id)

        # CSV overrides source 2 when provided
        csv_val = _read_csv_value(csv_path, kpi.id)
        if csv_val is not None:
            v2 = csv_val

        reconciled = (v1 + v2) / 2.0
        confidence = 0.85 if csv_val is not None else 0.70

        observations.append(
            KPIObservation(
                kpi_id=kpi.id,
                source_1="mock_source_A",
                value_1=v1,
                source_2="csv_or_mock_source_B",
                value_2=v2,
                reconciled_value=reconciled,
                confidence=confidence,
            )
        )

        # Variable payout only for performance KPIs
        if _is_variable_payout_kpi(kpi.id):
            amount_due = kpi.payout_amount if reconciled >= kpi.threshold else 0.0
            total_due += amount_due
        else:
            amount_due = 0.0  # fixed/informational KPI

        payable_items.append(
            {
                "kpi_id": kpi.id,
                "actual": reconciled,
                "threshold": kpi.threshold,
                "met": reconciled >= kpi.threshold,
                "amount_due": amount_due,
                "currency": kpi.currency,
                "kpi_type": "variable" if _is_variable_payout_kpi(kpi.id) else "fixed_or_informational",
            }
        )

    result = ResearchOutput(
        observations=observations,
        payable_items=payable_items,
        total_variable_due=total_due,
        comments=[
            "Enhanced KPI handling includes appearance and retainer-style clauses.",
            "CSV value overrides source_2 when provided.",
        ],
    )

    if not is_enabled():
        return result

    llm_payload = call_json(
        system_prompt=(
            "You are a research analyst assistant for sports sponsorship KPI reconciliation. "
            "Return only valid JSON."
        ),
        user_prompt=(
            "Given the reconciled KPI observations and payable items, provide concise analyst comments.\n"
            "Return JSON object with key 'comments' as an array of short strings.\n"
            f"Observations: {[o.model_dump() for o in observations]}\n"
            f"Payable items: {payable_items}\n"
            f"Total variable due: {total_due}"
        ),
        temperature=0.1,
    )

    if not llm_payload:
        return result

    comments = llm_payload.get("comments", [])
    if isinstance(comments, list):
        for comment in comments:
            text = str(comment).strip()
            if text:
                result.comments.append(text)
    result.comments.append(f"LLM-assisted commentary enabled via provider: {get_provider()}.")

    return result