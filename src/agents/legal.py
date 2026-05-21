from __future__ import annotations
import re
from src.models.schemas import (
    ContractExtraction,
    KPI,
    ChallengeClaim,
    LegalChallengeCheck,
)
from src.tools.llm_provider import call_json, get_provider, is_enabled

SUPPORTED_LANGS = ["en", "es", "pt", "it", "fr", "de", "nl"]


def detect_language_hint(text: str) -> str:
    lowered = text.lower()
    if any(w in lowered for w in ["jogador", "aparições", "seleção", "valor"]):
        return "pt"
    if any(w in lowered for w in ["el jugador", "patrocinador"]):
        return "es"
    return "en"


def _extract_currency_amounts(text: str):
    # matches like "EUR 800,000" or "EUR 15,000,000"
    return [float(x.replace(",", "")) for x in re.findall(r"EUR\s*([\d,]+)", text, flags=re.IGNORECASE)]


def _extract_percentages(text: str):
    # matches like "75%"
    return [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]


def _extract_integers(text: str):
    return [int(x) for x in re.findall(r"\b\d+\b", text)]


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def extract_contract_obligations(contract_text: str, player_name: str, sponsor_name: str) -> ContractExtraction:
    lang = detect_language_hint(contract_text)
    lower = contract_text.lower()

    kpis: list[KPI] = []

    # Backward compatible goals/assists
    goals_threshold = 15
    assists_threshold = 10
    g = re.search(r"goals?\s*[:=]?\s*(\d+)", lower)
    a = re.search(r"assists?\s*[:=]?\s*(\d+)", lower)
    if g:
        goals_threshold = int(g.group(1))
    if a:
        assists_threshold = int(a.group(1))

    kpis.append(KPI(
        id="goals_scored",
        description="Total official goals scored in season",
        threshold=float(goals_threshold),
        unit="goals",
        payout_amount=50000.0,
        currency="EUR",
    ))
    kpis.append(KPI(
        id="assists",
        description="Total official assists in season",
        threshold=float(assists_threshold),
        unit="assists",
        payout_amount=30000.0,
        currency="EUR",
    ))

    # New: detect appearance/table clauses
    numbers = _extract_integers(contract_text)
    eur_amounts = _extract_currency_amounts(contract_text)
    pcts = _extract_percentages(contract_text)

    # Heuristics for your sample table
    if ("club starting appearances" in lower) or ("iniciais do clube" in lower):
        # sample has yearly thresholds 20..40; use min threshold as contractual floor
        appearance_candidates = [n for n in numbers if 10 <= n <= 60]
        club_app_threshold = float(min(appearance_candidates)) if appearance_candidates else 20.0
        kpis.append(KPI(
            id="club_starting_appearances",
            description="Minimum club starting appearances",
            threshold=club_app_threshold,
            unit="appearances",
            payout_amount=100000.0,
            currency="EUR",
        ))

    if ("national team starting appearances" in lower) or ("seleção nacional iniciais" in lower):
        nt_pct = pcts[0] if pcts else 75.0
        kpis.append(KPI(
            id="national_team_starting_appearance_pct",
            description="Minimum national team starting appearance percentage",
            threshold=float(nt_pct),
            unit="percent",
            payout_amount=120000.0,
            currency="EUR",
        ))

    if ("club retainer" in lower) or ("valor do clube" in lower):
        # first EUR in row often club retainer
        club_retainer = eur_amounts[0] if eur_amounts else 800000.0
        kpis.append(KPI(
            id="club_retainer_eur",
            description="Annual club retainer value",
            threshold=float(club_retainer),
            unit="EUR",
            payout_amount=0.0,  # informational / fixed component
            currency="EUR",
        ))

    if ("national team retainer" in lower) or ("valor da" in lower and "national team" in lower):
        nt_retainer = eur_amounts[1] if len(eur_amounts) > 1 else 500000.0
        kpis.append(KPI(
            id="national_team_retainer_eur",
            description="Annual national team retainer value",
            threshold=float(nt_retainer),
            unit="EUR",
            payout_amount=0.0,  # informational / fixed component
            currency="EUR",
        ))

    # Base fee and period heuristic
    base_fee = 200000.0
    if eur_amounts:
        # from sample totals: 15,000,000 is contract total; keep base fee simple for now
        base_fee = min(eur_amounts)

    result = ContractExtraction(
        player_name=player_name,
        sponsor_name=sponsor_name,
        language_detected=lang if lang in SUPPORTED_LANGS else "en",
        contract_period="multi-year",
        base_fee=float(base_fee),
        base_currency="EUR",
        kpis=kpis,
        notes=[
            "Enhanced parser: includes club/national-team appearance and retainer clauses when detected.",
            "Uses heuristic extraction from table text; recommend structured table parser for production accuracy.",
        ],
    )

    if not is_enabled():
        return result

    llm_payload = call_json(
        system_prompt=(
            "You are a legal contract extraction assistant. "
            "Return only valid JSON with concise values."
        ),
        user_prompt=(
            "Extract contract obligations from the text below.\n"
            "Expected JSON object keys: language_detected (string), contract_period (string), "
            "base_fee (number), notes (array of strings), kpis (array).\n"
            "Each KPI must include: id, description, threshold, unit, payout_amount, currency.\n"
            f"Known player: {player_name}\n"
            f"Known sponsor: {sponsor_name}\n"
            "Contract text:\n"
            f"{contract_text}"
        ),
        temperature=0.0,
    )

    if not llm_payload:
        return result

    llm_lang = str(llm_payload.get("language_detected", "")).strip().lower()
    if llm_lang in SUPPORTED_LANGS:
        result.language_detected = llm_lang

    llm_period = str(llm_payload.get("contract_period", "")).strip()
    if llm_period:
        result.contract_period = llm_period

    llm_base_fee = _to_float(llm_payload.get("base_fee"), result.base_fee)
    if llm_base_fee > 0:
        result.base_fee = llm_base_fee

    kpis_by_id = {k.id: k for k in result.kpis}
    llm_kpis = llm_payload.get("kpis", [])
    if isinstance(llm_kpis, list):
        for item in llm_kpis:
            if not isinstance(item, dict):
                continue
            kpi_id = str(item.get("id", "")).strip()
            if not kpi_id:
                continue

            description = str(item.get("description", "")).strip() or kpi_id
            threshold = _to_float(item.get("threshold"), 0.0)
            unit = str(item.get("unit", "")).strip() or "count"
            payout_amount = _to_float(item.get("payout_amount"), 0.0)
            currency = str(item.get("currency", "EUR")).strip() or "EUR"

            if kpi_id in kpis_by_id:
                existing = kpis_by_id[kpi_id]
                if threshold > 0:
                    existing.threshold = threshold
                if description:
                    existing.description = description
                if unit:
                    existing.unit = unit
                if payout_amount >= 0:
                    existing.payout_amount = payout_amount
                if currency:
                    existing.currency = currency
            elif threshold > 0:
                result.kpis.append(
                    KPI(
                        id=kpi_id,
                        description=description,
                        threshold=threshold,
                        unit=unit,
                        payout_amount=payout_amount,
                        currency=currency,
                    )
                )

    llm_notes = llm_payload.get("notes", [])
    if isinstance(llm_notes, list):
        for note in llm_notes:
            text = str(note).strip()
            if text:
                result.notes.append(text)
    result.notes.append(f"LLM-assisted extraction enabled via provider: {get_provider()}.")

    return result


def assess_challenge_claims(
    legal_output: ContractExtraction,
    claims: list[ChallengeClaim],
) -> list[LegalChallengeCheck]:
    kpis_by_id = {kpi.id: kpi for kpi in legal_output.kpis}
    checks: list[LegalChallengeCheck] = []

    for claim in claims:
        notes: list[str] = []
        in_scope = False
        threshold = None
        unit = None

        if not claim.kpi_id:
            notes.append("Challenge did not include a recognizable KPI identifier.")
        else:
            kpi = kpis_by_id.get(claim.kpi_id)
            if kpi is None:
                notes.append(f"KPI '{claim.kpi_id}' is not present in the contract obligations.")
            else:
                in_scope = True
                threshold = kpi.threshold
                unit = kpi.unit
                notes.append(
                    f"KPI '{claim.kpi_id}' exists in contract with threshold {kpi.threshold} {kpi.unit}."
                )

        checks.append(
            LegalChallengeCheck(
                claim=claim,
                in_contract_scope=in_scope,
                expected_threshold=threshold,
                expected_unit=unit,
                notes=notes,
            )
        )

    return checks