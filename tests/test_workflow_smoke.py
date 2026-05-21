from src.models.schemas import WorkflowInput
from src.graph.workflow import run_workflow


def test_workflow_runs_end_to_end():
    wf_input = WorkflowInput(
        player_name="Tester",
        sponsor_name="BrandX",
        contract_text="goals: 15 assists: 10",
        csv_path=None,
    )
    out = run_workflow(wf_input)
    assert out.legal_output.player_name == "Tester"
    assert out.research_output is not None
    assert out.revisor_output.decision in ["approved", "needs_revision"]
    assert isinstance(out.billing_letter, str)
