ports Management MVP (Football Sponsorship Audit)
Local-first MVP to audit player sponsorship contracts against performance indicators and generate billing letters.

Stack
Python 3.11+
LangGraph (workflow orchestration)
Streamlit (local UI)
Agents
Legal Agent: parses contract and extracts KPI/payment obligations.
Researcher Agent: gathers KPI evidence (mock + real API hook).
Revisor Agent: audits consistency and flags issues.
Account Manager Agent: builds final summary + billing letter.
Supported Contract Languages (MVP prompts)
English, Spanish, Portuguese, Italian, French, German, Dutch
Run locally
python -m venv .venv
# mac/linux
source .venv/bin/activate
# windows
# .venv\Scripts\activate

pip install -e .
cp .env.example .env
streamlit run app.py
Project structure
app.py Streamlit UI
src/graph/workflow.py LangGraph orchestration
src/agents/* agent implementations
src/models/schemas.py typed state/models
src/tools/* parsers, data connectors, report generation
data/fixtures sample files
Notes
MVP uses deterministic + mock logic so it runs without paid services.
Real API integration point exists in src/tools/data_sources.py.

Optional LLM-assisted agents
- Default mode is deterministic (no LLM calls).
- To enable LLM-assisted role reasoning in Legal, Researcher, and Revisor agents:
	- Set `LLM_PROVIDER=openai`
	- Set `OPENAI_API_KEY=...` (or use APIM subscription key + custom auth mode)
	- Optionally tune `LLM_MODEL` (default: `gpt-4o-mini`) and `LLM_TIMEOUT_SECONDS`
- If provider config is missing/invalid, agents automatically fall back to deterministic logic.

Azure Foundry via APIM
- The LLM client supports OpenAI-compatible endpoints behind Azure API Management.
- Typical APIM setup:
	- `LLM_PROVIDER=openai`
	- `OPENAI_BASE_URL=https://<your-apim-name>.azure-api.net`
	- `OPENAI_CHAT_PATH=/openai/deployments/<deployment-name>/chat/completions`
	- `OPENAI_API_VERSION=2024-06-01`
	- `OPENAI_AUTH_MODE=none` (if APIM handles auth upstream)
	- `APIM_SUBSCRIPTION_KEY=<your-subscription-key>`
	- `APIM_SUBSCRIPTION_HEADER=Ocp-Apim-Subscription-Key`
	- `LLM_INCLUDE_MODEL=false` (Azure deployment path usually identifies model)
- If your APIM policy expects upstream `api-key` or bearer auth, set:
	- `OPENAI_AUTH_MODE=api-key` or `OPENAI_AUTH_MODE=bearer`
	- `OPENAI_API_KEY=<key-for-policy-or-upstream>`
- You can inject extra APIM headers with `APIM_EXTRA_HEADERS_JSON`, for example:
	- `{"x-region":"westeurope"}`