from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.agents.legal import assess_challenge_claims
from src.models.schemas import (
    ChallengeClaim,
    ChallengeReviewResult,
    ContractExtraction,
    ResearchOutput,
    RevisorOutput,
    WorkflowInput,
    WorkflowResult,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reports_root(base_dir: Path | None = None) -> Path:
    root = base_dir or Path("data/reports")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _append_jsonl(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def save_audit_record(
    wf_input: WorkflowInput,
    result: WorkflowResult,
    report_file_name: str,
    base_dir: Path | None = None,
) -> str:
    root = _reports_root(base_dir)
    records_dir = root / "records"
    records_dir.mkdir(parents=True, exist_ok=True)

    audit_id = str(uuid4())
    created_at = _utc_now_iso()

    record = {
        "audit_id": audit_id,
        "created_at": created_at,
        "player_name": wf_input.player_name,
        "sponsor_name": wf_input.sponsor_name,
        "contract_text": wf_input.contract_text,
        "csv_path": wf_input.csv_path,
        "report_file": report_file_name,
        "workflow_result": result.model_dump(),
    }

    (records_dir / f"{audit_id}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _append_jsonl(
        root / "audit_log.jsonl",
        {
            "audit_id": audit_id,
            "created_at": created_at,
            "player_name": wf_input.player_name,
            "sponsor_name": wf_input.sponsor_name,
            "decision": result.revisor_output.decision,
            "audited_total_due": result.revisor_output.audited_total_due,
            "report_file": report_file_name,
        },
    )

    return audit_id


def list_audit_records(base_dir: Path | None = None) -> list[dict]:
    root = _reports_root(base_dir)
    log_path = root / "audit_log.jsonl"
    if not log_path.exists():
        return []

    rows: list[dict] = []
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return rows


def load_audit_record(audit_id: str, base_dir: Path | None = None) -> dict | None:
    root = _reports_root(base_dir)
    record_path = root / "records" / f"{audit_id}.json"
    if not record_path.exists():
        return None
    try:
        return json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _extract_first_value(text: str) -> tuple[float | None, str | None]:
    eur_match = re.search(r"(?:EUR|€)\s*([\d,]+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if eur_match:
        return float(eur_match.group(1).replace(",", "")), "EUR"

    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if pct_match:
        return float(pct_match.group(1)), "%"

    num_match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if num_match:
        return float(num_match.group(1)), None

    return None, None


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).strip()


def _default_kpi_aliases() -> dict[str, list[str]]:
    return {
        "goals_scored": [
            "goals",
            "goal",
            "goals scored",
            "golos",
            "golo",
            "goles",
            "gol",
        ],
        "assists": ["assist", "assists", "assistencias", "asistencias", "asistencia"],
        "club_starting_appearances": [
            "club starting appearances",
            "club appearances",
            "starting appearances",
            "starts for club",
            "aparicoes iniciais do clube",
            "titularidades no clube",
            "apariciones iniciales del club",
            "titularidades en el club",
        ],
        "national_team_starting_appearance_pct": [
            "national team starting appearances",
            "national team starts",
            "national team appearance percentage",
            "national team pct",
            "selecao nacional aparicoes iniciais",
            "percentual de titularidade da selecao",
            "seleccion nacional apariciones iniciales",
            "porcentaje de titularidad de la seleccion",
        ],
        "club_retainer_eur": [
            "club retainer",
            "club value",
            "club fee",
            "valor do clube",
            "retentor do clube",
            "valor del club",
            "retainer del club",
        ],
        "national_team_retainer_eur": [
            "national team retainer",
            "national team value",
            "national team fee",
            "valor da selecao nacional",
            "retentor da selecao",
            "valor de la seleccion nacional",
            "retainer de la seleccion",
        ],
        "total_annual_retainer_eur": [
            "total annual retainer",
            "annual retainer",
            "total retainer",
            "retentor anual total",
            "valor anual total",
            "retainer anual total",
            "valor anual total",
        ],
    }


def _match_kpi_id(line: str, known_kpi_ids: list[str]) -> str | None:
    normalized_line = _normalize_text(line)

    for kpi_id in known_kpi_ids:
        if _normalize_text(kpi_id) in normalized_line:
            return kpi_id

    aliases = _default_kpi_aliases()
    for kpi_id in known_kpi_ids:
        for alias in aliases.get(kpi_id, []):
            if _normalize_text(alias) in normalized_line:
                return kpi_id

    return None


def parse_auditor_challenge_text(challenge_text: str, known_kpi_ids: list[str]) -> list[ChallengeClaim]:
    lines = [line.strip() for line in challenge_text.splitlines() if line.strip()]
    if not lines:
        return []

    claims: list[ChallengeClaim] = []
    for line in lines:
        matched_kpi = _match_kpi_id(line=line, known_kpi_ids=known_kpi_ids)

        value, unit = _extract_first_value(line)
        claims.append(
            ChallengeClaim(
                kpi_id=matched_kpi,
                asserted_value=value,
                asserted_unit=unit,
                rationale=line,
            )
        )

    return claims


def _extract_research_checks(
    legal_output: ContractExtraction,
    research_output: ResearchOutput,
    claims: list[ChallengeClaim],
) -> list[dict]:
    threshold_by_kpi = {kpi.id: kpi.threshold for kpi in legal_output.kpis}
    obs_by_kpi = {obs.kpi_id: obs for obs in research_output.observations}

    checks: list[dict] = []
    for claim in claims:
        if not claim.kpi_id:
            checks.append(
                {
                    "kpi_id": None,
                    "supported": False,
                    "notes": ["No KPI id was extracted from this challenge line."],
                }
            )
            continue

        obs = obs_by_kpi.get(claim.kpi_id)
        threshold = threshold_by_kpi.get(claim.kpi_id)
        if obs is None or threshold is None:
            checks.append(
                {
                    "kpi_id": claim.kpi_id,
                    "supported": False,
                    "notes": ["No observation or threshold available for this KPI."],
                }
            )
            continue

        notes = [
            f"Observed reconciled value: {obs.reconciled_value}",
            f"Contract threshold: {threshold}",
        ]
        supported = False

        if claim.asserted_value is not None:
            delta = abs(claim.asserted_value - obs.reconciled_value)
            notes.append(f"Difference between claim and observed value: {delta}")
            supported = delta > 0.01
        else:
            notes.append("Claim contains no numeric asserted value; cannot compare numerically.")

        checks.append(
            {
                "kpi_id": claim.kpi_id,
                "supported": supported,
                "notes": notes,
                "observation_confidence": obs.confidence,
            }
        )

    return checks


def _decide_challenge_outcome(legal_scope_ok: bool, research_supported: bool) -> tuple[str, list[str]]:
    notes: list[str] = []

    if not legal_scope_ok:
        notes.append("Challenge references KPI(s) outside the current contract scope.")
        return "rejected", notes

    if research_supported:
        notes.append("At least one claim differs from recorded observations and requires revision.")
        return "needs_revision", notes

    notes.append("Challenge is in scope, but recorded observations do not support the asserted discrepancy.")
    return "rejected", notes


def verify_auditor_challenge(
    audit_id: str,
    challenge_text: str,
    base_dir: Path | None = None,
) -> ChallengeReviewResult:
    record = load_audit_record(audit_id=audit_id, base_dir=base_dir)
    if record is None:
        raise ValueError(f"Audit record not found for id: {audit_id}")

    wf_dump = record.get("workflow_result", {})
    legal_output = ContractExtraction(**wf_dump.get("legal_output", {}))
    research_output = ResearchOutput(**wf_dump.get("research_output", {}))
    _ = RevisorOutput(**wf_dump.get("revisor_output", {}))

    claims = parse_auditor_challenge_text(
        challenge_text=challenge_text,
        known_kpi_ids=[kpi.id for kpi in legal_output.kpis],
    )
    legal_checks = assess_challenge_claims(legal_output=legal_output, claims=claims)
    research_checks = _extract_research_checks(
        legal_output=legal_output,
        research_output=research_output,
        claims=claims,
    )

    legal_scope_ok = all(check.in_contract_scope for check in legal_checks) if legal_checks else False
    research_supported = any(bool(item.get("supported")) for item in research_checks)
    revisor_decision, revisor_notes = _decide_challenge_outcome(legal_scope_ok, research_supported)

    outcome = ChallengeReviewResult(
        audit_id=audit_id,
        parsed_claims=claims,
        legal_checks=legal_checks,
        research_checks=research_checks,
        revisor_decision=revisor_decision,
        revisor_notes=revisor_notes,
    )

    root = _reports_root(base_dir)
    challenges_dir = root / "challenges"
    challenges_dir.mkdir(parents=True, exist_ok=True)

    challenge_id = str(uuid4())
    created_at = _utc_now_iso()
    payload = {
        "challenge_id": challenge_id,
        "created_at": created_at,
        "audit_id": audit_id,
        "challenge_text": challenge_text,
        "review": outcome.model_dump(),
    }

    (challenges_dir / f"{challenge_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _append_jsonl(
        root / "challenge_log.jsonl",
        {
            "challenge_id": challenge_id,
            "created_at": created_at,
            "audit_id": audit_id,
            "revisor_decision": outcome.revisor_decision,
        },
    )

    return outcome
