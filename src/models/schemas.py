from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class KPI(BaseModel):
    id: str
    description: str
    threshold: float
    unit: str
    payout_amount: float
    currency: str = "EUR"


class ContractExtraction(BaseModel):
    player_name: str
    sponsor_name: str
    language_detected: str
    contract_period: str
    base_fee: float = 0.0
    base_currency: str = "EUR"
    kpis: List[KPI] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class KPIObservation(BaseModel):
    kpi_id: str
    source_1: str
    value_1: float
    source_2: str
    value_2: float
    reconciled_value: float
    confidence: float = 0.8


class ResearchOutput(BaseModel):
    observations: List[KPIObservation] = Field(default_factory=list)
    payable_items: List[Dict] = Field(default_factory=list)
    total_variable_due: float = 0.0
    comments: List[str] = Field(default_factory=list)


class RevisorOutput(BaseModel):
    decision: str  # approved | needs_revision
    issues: List[str] = Field(default_factory=list)
    audited_total_due: float = 0.0


class WorkflowInput(BaseModel):
    player_name: str
    sponsor_name: str
    contract_text: str
    csv_path: Optional[str] = None


class WorkflowResult(BaseModel):
    legal_output: ContractExtraction
    research_output: ResearchOutput
    revisor_output: RevisorOutput
    final_summary: str
    billing_letter: str


class ChallengeClaim(BaseModel):
    kpi_id: Optional[str] = None
    asserted_value: Optional[float] = None
    asserted_unit: Optional[str] = None
    rationale: str


class LegalChallengeCheck(BaseModel):
    claim: ChallengeClaim
    in_contract_scope: bool
    expected_threshold: Optional[float] = None
    expected_unit: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class ChallengeReviewResult(BaseModel):
    audit_id: str
    parsed_claims: List[ChallengeClaim] = Field(default_factory=list)
    legal_checks: List[LegalChallengeCheck] = Field(default_factory=list)
    research_checks: List[Dict] = Field(default_factory=list)
    revisor_decision: str
    revisor_notes: List[str] = Field(default_factory=list)