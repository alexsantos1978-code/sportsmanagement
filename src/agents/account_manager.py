from __future__ import annotations
from src.models.schemas import ContractExtraction, ResearchOutput, RevisorOutput
from src.tools.report_generator import build_summary, build_billing_letter


def finalize_report(
    legal_output: ContractExtraction,
    research_output: ResearchOutput,
    revisor_output: RevisorOutput,
):
    summary = build_summary(legal_output, research_output, revisor_output)
    letter = build_billing_letter(legal_output, research_output, revisor_output)
    return summary, letter