# MultiAgent Procurement Application

> A state-machine-driven, multi-agent procurement orchestrator built on Google Agent Development Kit (ADK) — from requirement intake to vendor negotiation, with policy enforcement and human-in-the-loop approval built in.

---

## Problem

Enterprise procurement is fragmented and manual:

- Requirements are collected in ad-hoc conversations with no structure.
- Market research and vendor discovery happen outside the system, in browser tabs and spreadsheets.
- Policy compliance — category rules, approval thresholds, vendor restrictions — is enforced manually, or not at all.
- Approval documents are created separately from the sourcing workflow that produced them.
- Negotiation (RFQs, emails, offer comparison) happens in email threads disconnected from procurement records.
- Single-LLM chatbots aren't enough: procurement needs structured multi-step data collection, policy gates, human-in-the-loop approval, persistent sessions, and integration with search, RAG, storage, and email systems.
- Other agents and platforms have no standard way to invoke procurement capabilities.

## Solution

**MultiAgent Procurement Application** is a state-machine-driven multi-agent orchestrator that:

1. Collects procurement requirements step-by-step through a guided conversational workflow.
2. Runs market research via specialized search and scraping agents.
3. Shortlists products and vendors with policy enforcement sourced from YAML config.
4. Generates approval-ready PDF procurement documents and uploads them to S3.
5. Pauses for human approval before negotiation begins.
6. Coordinates post-approval RFQ and vendor negotiation via an external email agent.
7. Persists multi-turn ADK sessions and A2A tasks in a database.
8. Exposes REST and A2A interfaces for integration with portals and other agents.
9. Protects A2A routes with Kong OAuth2 Bearer token validation.

## Features

- 🧭 **Guided 35-state workflow** covering intake, feasibility, market research, selection, delivery, policy, documentation, approval, and negotiation.
- 🤖 **Multi-agent architecture** — a root orchestrator agent coordinates planner, search, vendor selection, and negotiator sub-agents.
- 📜 **YAML-driven policy engine** — category rules, compliance requirements, vendor restrictions, procurement methods, and approval chains, all hot-loaded at runtime.
- 📄 **Automated document generation** — approval-ready PDFs via ReportLab, uploaded directly to AWS S3.
- 🧑‍⚖️ **Human-in-the-loop approval gate** before any vendor negotiation begins.
- 📧 **Automated negotiation** — RFQ dispatch and offer comparison via an external email agent.
- 🔍 **RAG-backed vendor knowledge** using Vertex AI RAG corpora.
- 🔌 **Dual interfaces** — a REST API for direct integration and an A2A (Agent-to-Agent) JSON-RPC endpoint for other agent platforms.
- 🔐 **Kong OAuth2** Bearer token protection on all A2A routes.
- 💾 **Persistent sessions** — ADK sessions and A2A tasks stored in PostgreSQL for durable, resumable conversations.
- 🖥️ **Interactive CLI** for local testing without standing up the full API.

## Architecture

### System architecture

```mermaid
flowchart TD
    subgraph Clients
        WebUI["Web UI"]
        CLI["Interactive CLI"]
        RemoteAgent["Remote A2A Agent"]
    end

    WebUI -->|"POST /chat"| FastAPI["FastAPI (main.py)"]
    CLI -->|"python main.py"| FastAPI
    RemoteAgent -->|"JSON-RPC"| Kong["Kong OAuth2 Middleware"]
    Kong --> A2ASub["A2A Sub-app (a2a_expose/app.py)"]

    FastAPI --> Gateway["gateway_agent"]
    A2ASub --> Gateway

    Gateway --> WFTool["procurement_workflow_tool"]
    WFTool --> HandlerSM["handler.py (Python state machine)"]
    HandlerSM --> RootAgent["procurement_root_agent (ADK root agent)"]

    RootAgent --> Planner["procurement_planner (remote A2A, port 8001)"]
    RootAgent --> Search["procurement_search_agent (Google Search)"]
    RootAgent --> Vendor["vendor_selection_agent (RAG + search + docs)"]
    Vendor --> Negotiator["negotiator_agent (email RFQ / negotiation)"]

    HandlerSM -.-> Postgres[("PostgreSQL: sessions & tasks")]
    RootAgent -.-> Gemini[("Vertex AI / Gemini")]
    Vendor -.-> S3[("AWS S3: generated PDFs")]
    Vendor -.-> GCS[("GCS: RAG corpus")]
    Negotiator -.-> EmailAgent["External Email Agent (HTTP)"]
```

### Workflow state machine

The orchestrator moves through 35 states across 9 phases: Intake → Feasibility → Market Research → Selection → Delivery → Policy → Document → Approval → Negotiation.

```mermaid
stateDiagram-v2
    [*] --> INTENT_ITEM
    INTENT_ITEM --> INTENT_CATEGORY
    INTENT_CATEGORY --> INTENT_PURPOSE
    INTENT_PURPOSE --> INTENT_SPECS
    INTENT_SPECS --> QUANTITY
    QUANTITY --> BUDGET_PER_ITEM
    BUDGET_PER_ITEM --> BUDGET_TOTAL
    BUDGET_TOTAL --> BUDGET_CONFIRMATION
    BUDGET_CONFIRMATION --> FEASIBILITY_ASSESSMENT
    FEASIBILITY_ASSESSMENT --> FEASIBILITY_REVIEW
    FEASIBILITY_REVIEW --> MARKET_RESEARCH
    MARKET_RESEARCH --> RECOMMENDATION_REVIEW
    RECOMMENDATION_REVIEW --> RECOMMENDATION_REFINEMENT
    RECOMMENDATION_REFINEMENT --> SELECTION_CONFIRMATION
    SELECTION_CONFIRMATION --> DELIVERY_TIMELINE
    DELIVERY_TIMELINE --> DELIVERY_ADDRESS
    DELIVERY_ADDRESS --> DELIVERY_CITY
    DELIVERY_CITY --> DELIVERY_STATE
    DELIVERY_STATE --> DELIVERY_COUNTRY
    DELIVERY_COUNTRY --> DELIVERY_POSTAL_CODE
    DELIVERY_POSTAL_CODE --> DELIVERY_CONTACT
    DELIVERY_CONTACT --> DELIVERY_CONFIRMATION
    DELIVERY_CONFIRMATION --> VENDOR_POLICY_EVALUATION
    VENDOR_POLICY_EVALUATION --> VENDOR_REVIEW
    VENDOR_REVIEW --> VENDOR_EXPANSION
    VENDOR_EXPANSION --> QUOTE_REQUEST
    QUOTE_REQUEST --> FINAL_DOCUMENT_DRAFT
    FINAL_DOCUMENT_DRAFT --> FINAL_CONFIRMATION
    FINAL_CONFIRMATION --> COMPLETE
    COMPLETE --> NEGOTIATION_COMPLETE
    NEGOTIATION_COMPLETE --> [*]
```

State logic lives in `orchestrator/agents/handler.py`; the state enum is defined in `orchestrator/core/workflow_state.py`.

### Agent roles

| Agent | File | Role |
|---|---|---|
| `gateway_agent` | `orchestrator/agents/researcher/gateway_agent.py` | A2A entry point; always delegates to `procurement_workflow_tool` |
| `procurement_root_agent` | `orchestrator/agents/researcher/root.py` | Central orchestrator; coordinates sub-agents and policy tools |
| `procurement_planner` | `orchestrator/agents/researcher/planner_remote.py` | Remote A2A agent (`localhost:8001`) for structured requirement extraction |
| `procurement_search_agent` | `orchestrator/agents/researcher/search_agent.py` | Web/product search via Google Search grounding |
| `vendor_selection_agent` | `orchestrator/agents/researcher/vendor_agent.py` | Vendor discovery, RAG lookup, document generation |
| `negotiator_agent` | `orchestrator/agents/researcher/negotiator_agent.py` | Post-approval RFQ, email outreach, offer comparison |
| `email_search_agent` | `orchestrator/agents/researcher/email_search_agent.py` | Finds vendor contact emails via Google Search |

Root agent tools: `planner_agent_a2a_tool`, `search_agent_tool`, `search_queries_agent_tool`, `vendor_rules_tool`, `procurement_method_tool`, `approval_policy_tool`, `complete_policy_bundle_tool`.

### Runtime flows

**REST `/chat`:**
User message → `set_request_ids(user_id, session_id)` → `get_procurement_context()` → `handle_state_input()` → `ADK runner.run_async()` → response parsed (tokens, agents used, clean message) → `AssistantResponse` JSON.

**A2A:**
External agent → Kong Bearer token validation → `POST /a2a/procurement_agent` → `gateway_agent` → `procurement_workflow_tool` → `handle_state_input()` → same state machine as REST.

**Vendor + Negotiation:**
`root_agent` transfers to `vendor_selection_agent` → RAG search + web search + vendor sync → `generate_document_tool` (PDF to S3) → user APPROVE/REJECT in handler → `negotiator_agent` → email search + external email agent for RFQ/negotiation.

## Project structure

```
allyra_adk_procurement_agent/
├── main.py                          # Primary entry point: FastAPI app, CLI REPL, Kong middleware,
│                                     # A2A mount, Vertex AI init, /chat and /health endpoints
├── app.py                           # Legacy/simpler FastAPI wrapper (single global session,
│                                     # no A2A, no Kong auth) — superseded by main.py
├── Dockerfile                       # Python 3.11-slim, exposes port 5000, runs uvicorn main:app
├── requirements.txt                 # Pinned dependencies (google-adk, a2a-sdk, fastapi, etc.)
│
├── a2a_expose/                      # A2A protocol exposure
│   ├── app.py                       # Builds A2A Starlette sub-app via ADK's to_a2a()
│   ├── agent_card.py                # AgentCard metadata for external discovery (4 skills)
│   └── agent_executor.py            # Custom executor: request timing, metadata validation,
│                                     # ADK session mapping
│
├── services/                        # External integrations
│   ├── kong_auth_service.py         # Validates Bearer tokens against Kong Admin API
│   ├── vendor_rag_services.py       # Vertex AI RAG corpus client (upload/list/get/delete/query)
│   └── vendor_file_store.py         # Syncs vendor search results into rag_vendor_files/
│
├── orchestrator/                    # Core orchestration
│   ├── bootstrap_engine.py          # Module-level singleton exporting `engine`
│   ├── engine.py                    # Wraps ADK Runner with DatabaseSessionService
│   │
│   ├── core/                        # Shared models and config
│   │   ├── config.py                 # Request-scoped IDs, APP_NAME, A2A_MOUNT_PATH
│   │   ├── workflow_state.py         # Enum of all 35 workflow states
│   │   ├── procurement_context.py    # Mutable runtime session state container
│   │   ├── procurement_schema.py     # Pydantic ProcurementRequest model
│   │   ├── procurement_document_schema.py  # Pydantic ProcurementDocument model
│   │   └── models.py                 # Shared domain models (Money, DeliveryInfo, etc.)
│   │
│   ├── agents/
│   │   ├── handler.py                # Central hybrid workflow engine (~1600 lines):
│   │   │                             # state transitions + LLM extraction + event processing
│   │   ├── requirements.txt          # Slimmer deps for standalone agent deployment
│   │   │
│   │   ├── researcher/               # ADK agent definitions
│   │   │   ├── root.py                # Root ADK App: procurement_root_agent, plugins, tools
│   │   │   ├── gateway_agent.py        # Thin A2A-facing agent
│   │   │   ├── planner.py              # Local planner agent for requirement extraction
│   │   │   ├── planner_a2a.py          # Standalone A2A server for planner (port 8001)
│   │   │   ├── planner_remote.py       # RemoteA2aAgent client for the planner
│   │   │   ├── search_agent.py         # Google Search product discovery
│   │   │   ├── scrapper_agent.py       # Web scraping for product page extraction
│   │   │   ├── suggested_search_query_agent.py  # Ecommerce search query generation
│   │   │   ├── vendor_agent.py         # Vendor discovery, RAG lookup, document generation
│   │   │   ├── negotiator_agent.py     # Post-approval RFQ/negotiation via email
│   │   │   ├── email_search_agent.py   # Vendor contact discovery via search
│   │   │   └── procurement_report_author_agent.py  # HTML/PDF report generation
│   │   │
│   │   └── writer/                    # YAML policy configuration
│   │       ├── category_policies.yaml    # Category registry, required fields, risk, SLAs
│   │       ├── compliance.yaml           # Security/privacy/audit/ESG rules per category
│   │       ├── vendor_rules.yaml          # Preferred/banned vendors, qualification criteria
│   │       ├── procurement_methods.yaml   # Method definitions with spend thresholds
│   │       └── approvals.yaml             # Approval chains, escalation, delegation
│   │
│   ├── tools/                        # ADK function tools
│   │   ├── procurement_workflow_tool.py   # Bridges A2A gateway to the state machine
│   │   ├── remote_a2a_planner_tool.py     # Wraps remote planner as ADK AgentTool
│   │   ├── search_tool.py                 # Wraps search_agent as a tool
│   │   ├── search_queries_agent_tool.py   # Wraps search query generator
│   │   ├── email_search_agent_tool.py     # Wraps email search agent
│   │   ├── scrapping_tool.py              # HTTP scraper with BeautifulSoup
│   │   ├── read_json.py                   # Safe JSON reader for agent output
│   │   ├── writer_tools.py                # YAML policy loader (5 FunctionTools)
│   │   ├── procurement_schema_tool.py     # Validates dicts against ProcurementRequest
│   │   ├── procurement_document_tool.py   # Generates PDF via ReportLab, uploads to S3
│   │   ├── vendor_document_tool.py        # Triggers PDF generation from vendor_agent
│   │   ├── vendor_rag_tool.py             # Full RAG tool suite
│   │   └── upload_document_tool.py        # Direct RAG upload tool
│   │
│   └── prompts/                      # Agent instruction prompts
│       ├── root_agent_instructions.py     # Root agent system + workflow prompt templates
│       ├── planner_prompt.py              # Planner requirement-gathering instructions
│       ├── search_agent_prompt.py         # Search filtering/scoring instructions
│       ├── scrapper_agent_prompt.py       # Scraping extraction rules
│       ├── vendor_agent_prompt.py         # Vendor discovery, RAG, HIL, negotiation rules
│       ├── negotiator_agent_prompt.py     # Negotiation lifecycle instructions
│       ├── email_search_agent_instructions.py  # Vendor email discovery rules
│       ├── procurement_search_queries_agent_prmpt.py  # Query generation rules
│       └── procurement_report_agent_prompt.py   # HTML/PDF report authoring steps
```

## Prerequisites

- Python 3.11+
- Google Cloud project with Vertex AI enabled, plus a service account
- PostgreSQL-compatible database (ADK sessions + A2A task storage)
- AWS S3 bucket (for procurement PDFs)
- Kong API Gateway (for A2A auth)
- Ability to run the remote planner agent on port 8001

## Setup instructions

### 1. Clone and set up a virtual environment

```bash
git clone <repository-url>
cd allyra_adk_procurement_agent
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root (see [Configuration](#configuration) below for the full list).

### 4. Run the services

```bash
# Terminal 1: Remote planner agent
uvicorn orchestrator.agents.researcher.planner_a2a:a2a_app --host 0.0.0.0 --port 8001

# Terminal 2: Main service
uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

Or run the interactive CLI instead of the API:

```bash
python main.py
```

Or run everything in Docker:

```bash
docker build -t allyra-procurement-agent .
docker run -p 5000:5000 --env-file .env allyra-procurement-agent
```

## Configuration

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@host:5432/db` |
| `GOOGLE_SERVICE_ACCOUNT_BASE64` | Yes | Base64-encoded GCP service account JSON |
| `VERTEX_AI_RAG_PROJECT_ID` | Yes | GCP project ID |
| `VERTEX_AI_RAG_LOCATION` | Yes | GCP region (e.g. `us-central1`) |
| `BASE_URL` | Yes | Public base URL for the A2A agent card |
| `KONG_ADMIN_URL` | For A2A auth | Kong Admin API URL |
| `AWS_ACCESS_KEY_ID` | For PDF upload | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | For PDF upload | AWS credentials |
| `AWS_REGION` | For PDF upload | AWS region |
| `S3_BUCKET_NAME` | For PDF upload | S3 bucket for procurement PDFs |
| `GCS_BUCKET_NAME` | For RAG | GCS bucket backing the vendor RAG corpus |

## API reference

### `POST /chat`

Send a message to the procurement workflow and receive the next state, model usage, and assistant reply.

**Request**

```json
{
  "text": "I need 50 laptops with 16GB RAM for our Bangalore office",
  "user_id": "user-123",
  "session_id": "session-456",
  "organization_id": "org-789"
}
```

**Response**

```json
{
  "state": "INTENT_CATEGORY",
  "tokens": { "prompt": 1200, "completion": 85, "total": 1285 },
  "agents_tools": ["procurement_root_agent"],
  "message": "What category best describes these laptops?"
}
```

### `GET /health`

Returns database connectivity status.

```json
{
  "status": "ok",
  "database": { "ok": true }
}
```

### A2A endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `GET /.well-known/agent-card.json` | None | Public agent card for discovery |
| `POST /a2a/procurement_agent` | Kong Bearer token | JSON-RPC entry point into the workflow |

Required A2A request metadata: `user_id`, `org_id`, `user_name`, `org_name`.

### Example prompts

```
"I need 50 laptops for our Bangalore office with 16GB RAM and a total budget of 40 lakhs."
"Find Dell and HP laptop vendors near Mumbai for 50 units."
"Generate the procurement document for the selected vendor."
"Start negotiation with the approved vendor."
```

## Workflow stages

| Phase | States |
|---|---|
| **Intake** | `INTENT_ITEM` → `INTENT_CATEGORY` → `INTENT_PURPOSE` → `INTENT_SPECS` → `QUANTITY` → `BUDGET_PER_ITEM` → `BUDGET_TOTAL` → `BUDGET_CONFIRMATION` |
| **Feasibility** | `FEASIBILITY_ASSESSMENT` → `FEASIBILITY_REVIEW` |
| **Market Research** | `MARKET_RESEARCH` → `RECOMMENDATION_REVIEW` → `RECOMMENDATION_REFINEMENT` |
| **Selection** | `SELECTION_CONFIRMATION` |
| **Delivery** | `DELIVERY_TIMELINE` → `DELIVERY_ADDRESS` → `DELIVERY_CITY` → `DELIVERY_STATE` → `DELIVERY_COUNTRY` → `DELIVERY_POSTAL_CODE` → `DELIVERY_CONTACT` → `DELIVERY_CONFIRMATION` |
| **Policy** | `VENDOR_POLICY_EVALUATION` → `VENDOR_REVIEW` → `VENDOR_EXPANSION` |
| **Document** | `QUOTE_REQUEST` → `FINAL_DOCUMENT_DRAFT` → `FINAL_CONFIRMATION` |
| **Approval / Negotiation** | `COMPLETE` → `NEGOTIATION_COMPLETE` |

Any procurement can also transition to `CANCELLED` from an active state.

## Policy configuration

All policy rules live as YAML under `orchestrator/agents/writer/` and are loaded at runtime by `orchestrator/tools/writer_tools.py`, which exposes them as five ADK function tools: `category_policy_tool`, `compliance_policy_tool`, `vendor_rules_tool`, `procurement_method_tool`, and `approval_policy_tool` (plus a `complete_policy_bundle_tool` that bundles all five).

| File | Purpose |
|---|---|
| `category_policies.yaml` | Master category registry (e.g. `it_hardware`, `software`) with required fields, risk levels, and SLAs |
| `compliance.yaml` | Security, privacy, audit, and ESG compliance rules per category |
| `vendor_rules.yaml` | Preferred/banned vendors, qualification criteria, and risk classification per category |
| `procurement_methods.yaml` | Procurement method definitions (direct purchase, RFQ, tender) with spend thresholds and steps |
| `approvals.yaml` | Approval chains, escalation rules, and delegation by category and spend tier |

Because these are plain YAML files, policy changes don't require a code deployment — update the file and the next request picks up the new rules.

## Tech stack

- **Agent framework:** Google Agent Development Kit (ADK), A2A SDK
- **Models:** Gemini (`gemini-flash-lite-latest`, `gemini-2.5-flash`)
- **API layer:** FastAPI, Uvicorn
- **Retrieval:** Vertex AI RAG
- **Persistence:** SQLAlchemy (PostgreSQL)
- **Documents:** ReportLab (PDF generation)
- **Storage:** AWS S3, Google Cloud Storage
- **Auth:** Kong OAuth2

## Docker

The included `Dockerfile` builds a Python 3.11-slim image, installs `requirements.txt`, exposes port 5000, and runs the production entry point:

```bash
docker build -t allyra-procurement-agent .
docker run -p 5000:5000 --env-file .env allyra-procurement-agent
```

Internally this runs:

```bash
uvicorn main:app --host 0.0.0.0 --port 5000
```

Note that the Docker image serves the API only — the remote planner agent (port 8001) and PostgreSQL database are expected to run as separate services and be reachable via `DATABASE_URL` and the planner's configured host.
