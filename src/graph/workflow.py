from __future__ import annotations
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from src.models.schemas import (
    WorkflowInput,
    WorkflowResult,
    ContractExtraction,
    ResearchOutput,
    RevisorOutput,
)
from src.agents.legal import extract_contract_obligations
from src.agents.researcher import gather_and_compute
from src.agents.revisor import audit_outputs
from src.agents.account_manager import finalize_report


class AuditState(TypedDict):
    player_name: str
    sponsor_name: str
    contract_text: str
    csv_path: Optional[str]
    legal_output: Optional[ContractExtraction]
    research_output: Optional[ResearchOutput]
    revisor_output: Optional[RevisorOutput]
    final_summary: Optional[str]
    billing_letter: Optional[str]


def legal_node(state: AuditState) -> AuditState:
    legal = extract_contract_obligations(
        contract_text=state["contract_text"],
        player_name=state["player_name"],
        sponsor_name=state["sponsor_name"],
    )
    state["legal_output"] = legal
    return state


def researcher_node(state: AuditState) -> AuditState:
    research = gather_and_compute(
        legal_output=state["legal_output"],
        csv_path=state.get("csv_path"),
    )
    state["research_output"] = research
    return state


def revisor_node(state: AuditState) -> AuditState:
    rev = audit_outputs(
        legal_output=state["legal_output"],
        research_output=state["research_output"],
    )
    state["revisor_output"] = rev
    return state


def account_manager_node(state: AuditState) -> AuditState:
    summary, letter = finalize_report(
        legal_output=state["legal_output"],
        research_output=state["research_output"],
        revisor_output=state["revisor_output"],
    )
    state["final_summary"] = summary
    state["billing_letter"] = letter
    return state


def _build_graph():
    graph = StateGraph(AuditState)
    graph.add_node("legal", legal_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("revisor", revisor_node)
    graph.add_node("account_manager", account_manager_node)

    graph.set_entry_point("legal")
    graph.add_edge("legal", "researcher")
    graph.add_edge("researcher", "revisor")
    graph.add_edge("revisor", "account_manager")
    graph.add_edge("account_manager", END)

    return graph.compile()


APP_GRAPH = _build_graph()


def run_workflow(wf_input: WorkflowInput) -> WorkflowResult:
    initial_state: AuditState = {
        "player_name": wf_input.player_name,
        "sponsor_name": wf_input.sponsor_name,
        "contract_text": wf_input.contract_text,
        "csv_path": wf_input.csv_path,
        "legal_output": None,
        "research_output": None,
        "revisor_output": None,
        "final_summary": None,
        "billing_letter": None,
    }
    out = APP_GRAPH.invoke(initial_state)

    return WorkflowResult(
        legal_output=out["legal_output"],
        research_output=out["research_output"],
        revisor_output=out["revisor_output"],
        final_summary=out["final_summary"],
        billing_letter=out["billing_letter"],
    )
