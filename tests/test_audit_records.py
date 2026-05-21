from __future__ import annotations

from pathlib import Path

from src.models.schemas import (
    ContractExtraction,
    KPI,
    KPIObservation,
    ResearchOutput,
    RevisorOutput,
    WorkflowInput,
    WorkflowResult,
)
from src.tools.audit_records import (
    load_audit_record,
    parse_auditor_challenge_text,
    save_audit_record,
    verify_auditor_challenge,
)


def _sample_result() -> WorkflowResult:
    legal = ContractExtraction(
        player_name="Tester",
        sponsor_name="BrandX",
        language_detected="en",
        contract_period="2025",
        kpis=[
            KPI(
                id="goals_scored",
                description="Goals",
                threshold=15.0,
                unit="goals",
                payout_amount=50000.0,
                currency="EUR",
            )
        ],
    )
    research = ResearchOutput(
        observations=[
            KPIObservation(
                kpi_id="goals_scored",
                source_1="sourceA",
                value_1=22.0,
                source_2="sourceB",
                value_2=20.0,
                reconciled_value=21.0,
                confidence=0.9,
            )
        ],
        payable_items=[
            {
                "kpi_id": "goals_scored",
                "actual": 21.0,
                "threshold": 15.0,
                "met": True,
                "amount_due": 50000.0,
                "currency": "EUR",
            }
        ],
        total_variable_due=50000.0,
    )
    rev = RevisorOutput(decision="approved", audited_total_due=50000.0)

    return WorkflowResult(
        legal_output=legal,
        research_output=research,
        revisor_output=rev,
        final_summary="ok",
        billing_letter="letter",
    )


def test_save_and_load_audit_record(tmp_path: Path):
    wf_input = WorkflowInput(
        player_name="Tester",
        sponsor_name="BrandX",
        contract_text="goals: 15",
        csv_path=None,
    )
    result = _sample_result()

    audit_id = save_audit_record(
        wf_input=wf_input,
        result=result,
        report_file_name="Tester_report.txt",
        base_dir=tmp_path,
    )

    record = load_audit_record(audit_id=audit_id, base_dir=tmp_path)
    assert record is not None
    assert record["audit_id"] == audit_id
    assert record["workflow_result"]["revisor_output"]["decision"] == "approved"


def test_parse_challenge_and_verify(tmp_path: Path):
    wf_input = WorkflowInput(
        player_name="Tester",
        sponsor_name="BrandX",
        contract_text="goals: 15",
        csv_path=None,
    )
    result = _sample_result()

    audit_id = save_audit_record(
        wf_input=wf_input,
        result=result,
        report_file_name="Tester_report.txt",
        base_dir=tmp_path,
    )

    claims = parse_auditor_challenge_text(
        challenge_text="goals_scored should be 18 based on federation data",
        known_kpi_ids=["goals_scored"],
    )
    assert len(claims) == 1
    assert claims[0].kpi_id == "goals_scored"
    assert claims[0].asserted_value == 18.0

    review = verify_auditor_challenge(
        audit_id=audit_id,
        challenge_text="goals_scored should be 18 based on federation data",
        base_dir=tmp_path,
    )

    assert review.audit_id == audit_id
    assert len(review.legal_checks) == 1
    assert review.legal_checks[0].in_contract_scope is True
    assert review.revisor_decision == "needs_revision"


def test_parse_challenge_uses_human_aliases():
    claims = parse_auditor_challenge_text(
        challenge_text=(
            "Club appearances should be 28 based on league logs\n"
            "National team starts are only 70% according to federation records"
        ),
        known_kpi_ids=["club_starting_appearances", "national_team_starting_appearance_pct"],
    )

    assert len(claims) == 2
    assert claims[0].kpi_id == "club_starting_appearances"
    assert claims[0].asserted_value == 28.0
    assert claims[1].kpi_id == "national_team_starting_appearance_pct"
    assert claims[1].asserted_value == 70.0
    assert claims[1].asserted_unit == "%"


def test_parse_challenge_uses_portuguese_aliases():
    claims = parse_auditor_challenge_text(
        challenge_text=(
            "As aparicoes iniciais do clube devem ser 26\n"
            "O percentual de titularidade da selecao e de 72%"
        ),
        known_kpi_ids=["club_starting_appearances", "national_team_starting_appearance_pct"],
    )

    assert len(claims) == 2
    assert claims[0].kpi_id == "club_starting_appearances"
    assert claims[0].asserted_value == 26.0
    assert claims[1].kpi_id == "national_team_starting_appearance_pct"
    assert claims[1].asserted_value == 72.0
    assert claims[1].asserted_unit == "%"


def test_parse_challenge_uses_spanish_aliases():
    claims = parse_auditor_challenge_text(
        challenge_text=(
            "Las apariciones iniciales del club son 24\n"
            "El porcentaje de titularidad de la seleccion es 68%"
        ),
        known_kpi_ids=["club_starting_appearances", "national_team_starting_appearance_pct"],
    )

    assert len(claims) == 2
    assert claims[0].kpi_id == "club_starting_appearances"
    assert claims[0].asserted_value == 24.0
    assert claims[1].kpi_id == "national_team_starting_appearance_pct"
    assert claims[1].asserted_value == 68.0
    assert claims[1].asserted_unit == "%"


def test_parse_challenge_handles_accents_in_aliases():
    claims = parse_auditor_challenge_text(
        challenge_text=(
            "As aparições iniciais do clube devem ser 23\n"
            "El porcentaje de titularidad de la selección es 66%"
        ),
        known_kpi_ids=["club_starting_appearances", "national_team_starting_appearance_pct"],
    )

    assert len(claims) == 2
    assert claims[0].kpi_id == "club_starting_appearances"
    assert claims[0].asserted_value == 23.0
    assert claims[1].kpi_id == "national_team_starting_appearance_pct"
    assert claims[1].asserted_value == 66.0
    assert claims[1].asserted_unit == "%"
