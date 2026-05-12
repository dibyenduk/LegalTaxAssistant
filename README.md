# Legal & Tax Assistant

A Teams-based application that allows **Requestors** to submit legal and tax questions, which are automatically assigned to **Legal Experts** or **Tax Experts**. Built on **Microsoft AI Foundry** using the **Microsoft Agent Framework** with **Python**.

## Architecture
```
Teams Client → Teams Bot → Orchestrator (Hosted Agent) → Prompt Agents → MCP Server → Cosmos DB
```

| Component | Location | Hosting |
|-----------|----------|---------|
| MCP Server | `src/mcp_server/` | Azure Container Apps |
| Prompt Agents | `src/agents/` | Foundry Prompt Agents |
| Orchestrator | `src/orchestrator/` | Foundry Hosted Agent (Container) |
| Infrastructure | `infra/` | Bicep (Cosmos DB, Container Apps) |

---

## Prerequisites

See [`PREREQUISITES.md`](PREREQUISITES.md) for the full list of dependencies including Azure tenant setup, Microsoft 365 licenses, Foundry project, resource providers, and developer tools.

**Quick summary:** You need an Azure subscription, 3 M365 E5/E3 licensed users, a Foundry project with a deployed GPT model, an ACR, and `azd` + `az` + Python 3.11+ installed.

---

## Environment Setup

### 1. Initialize azd

```bash
azd init
```

> `azd init` will prompt you for `AZURE_SUBSCRIPTION_ID` and `AZURE_LOCATION` automatically.

### 2. Set required environment variables

These variables must be set manually — they reference external resources not provisioned by this project's Bicep templates:

```bash
# Azure Container Registry (shared ACR, not created by this project's infra)
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT "<youracr>.azurecr.io"
azd env set AZURE_CONTAINER_REGISTRY_NAME "<youracr>"

# Foundry project endpoint (required for agent provisioning and orchestrator deployment)
azd env set FOUNDRY_PROJECT_ENDPOINT "https://<resource>.services.ai.azure.com/api/projects/<project>"
azd env set AZURE_AI_PROJECT_ENDPOINT "https://<resource>.services.ai.azure.com/api/projects/<project>"

# Model deployment name
azd env set MODEL_DEPLOYMENT_NAME "gpt-5.4"

# Enable hosted agents for orchestrator deployment
azd env set ENABLE_HOSTED_AGENTS "true"
```

### Auto-populated variables

The following are set automatically by `azd init` or `azd provision` — do **not** set them manually:

| Variable | Set by |
|----------|--------|
| `AZURE_SUBSCRIPTION_ID` | `azd init` (prompted) |
| `AZURE_LOCATION` | `azd init` (prompted) |
| `AZURE_ENV_NAME` | `azd init` (prompted) |
| `AZURE_RESOURCE_GROUP` | `azd provision` (Bicep output) |
| `AZURE_COSMOS_ENDPOINT` | `azd provision` (Bicep output) |
| `AZURE_CONTAINER_APP_FQDN` | `azd provision` (Bicep output) |
| `SERVICE_MCP_SERVER_IMAGE_NAME` | `azd deploy` (auto-generated) |

---

## Deployment

### Full deployment (all components)

```bash
azd up
```

This will:
1. Provision infrastructure (Cosmos DB, Container Apps) via Bicep
2. Build and deploy the MCP Server to Container Apps
3. Build and deploy the Orchestrator to Foundry as a hosted agent
4. Run the `postprovision` hook to create/update prompt agents

### Individual component deployment

```bash
# Deploy only the MCP Server
azd deploy mcp-server

# Deploy only the Orchestrator
azd deploy orchestrator
```

---

## Component Details

### 1. MCP Server (`src/mcp_server/`)

The MCP Server provides CRUD operations on Cosmos DB via the [Model Context Protocol](https://modelcontextprotocol.io/). It is deployed as an Azure Container App.

**Files:**
| File | Description |
|------|-------------|
| `server.py` | FastMCP server entry point with tool registrations |
| `tools.py` | Tool implementations (request/question/answer CRUD) |
| `cosmos_client.py` | Cosmos DB client wrapper with Entra ID auth |
| `models.py` | Data models (Request, Question, Answer, etc.) |
| `requirements.txt` | Python dependencies |

**MCP Tools exposed:**
| Tool | Description |
|------|-------------|
| `get_user_role` | Look up a user's role by email |
| `create_request` | Create a new request |
| `add_questions_to_request` | Add questions to a request |
| `assign_question` | Assign a question to an expert |
| `get_requests_by_user` | Get all requests for a user |
| `get_request_status` | Get full status of a request |
| `get_assigned_questions` | Get questions assigned to an expert |
| `submit_answer` | Submit an answer to a question |
| `mark_question_submitted` | Mark a question as submitted |
| `send_request` | Send a request for review |
| `submit_request` | Submit a completed request |
| `get_experts_by_type` | List experts by type (legal/tax) |

**Environment variables:**
| Variable | Description |
|----------|-------------|
| `COSMOS_ENDPOINT` | Cosmos DB account endpoint |
| `COSMOS_DATABASE` | Database name (default: `LegalTaxAssistantDB`) |

**Deploy:**
```bash
azd deploy mcp-server
```

**Dockerfile:** `./Dockerfile` (root) — uses `mcr.microsoft.com/devcontainers/python:3.11`, exposes port 8080.

---

### 2. Prompt Agents (`src/agents/`)

Four prompt agents are provisioned in Foundry. They are LLM-based agents (no custom code) defined by YAML files with system prompts and MCP tool configurations.

**Agent definitions** (`src/agents/definitions/`):
| File | Agent Name | Role |
|------|-----------|------|
| `classifier_agent.yaml` | ClassifierAgent-2 | Classifies user role by looking up email in Cosmos DB |
| `requestor_agent.yaml` | RequestorAgent-2 | Handles request creation, question management for requestors |
| `legal_agent.yaml` | LegalAgent-2 | Handles legal Q&A for legal experts |
| `tax_agent.yaml` | TaxAgent-2 | Handles tax Q&A for tax experts |

**Provisioning script:** `src/agents/provision_agents.py`

**Deploy (manual):**
```bash
pip install -r src/agents/requirements.txt

python -m agents.provision_agents \
    --project-endpoint <FOUNDRY_PROJECT_ENDPOINT> \
    --model <MODEL_DEPLOYMENT_NAME> \
    --mcp-server-url <MCP_SERVER_SSE_URL>
```

**Deploy (automatic):** Runs automatically as a `postprovision` hook during `azd up` / `azd provision`.

**How it works:**
1. Reads each YAML definition from `src/agents/definitions/`
2. Substitutes `${MODEL_DEPLOYMENT_NAME}` with the specified model
3. Creates or updates each agent in Foundry via the `azure-ai-projects` SDK
4. Configures MCP tool connections pointing to the MCP Server SSE endpoint

---

### 3. Orchestrator (`src/orchestrator/`)

The orchestrator is a **Foundry Hosted Agent** — a containerized Python application using the Microsoft Agent Framework. It receives user messages via the Responses API protocol and routes them to the appropriate prompt agent.

**Files:**
| File | Description |
|------|-------------|
| `main.py` | Agent implementation with tool functions and routing logic |
| `agent.yaml` | Agent container spec (protocol, CPU/memory) |
| `agent.manifest.yaml` | Agent metadata, env vars, model resources |
| `Dockerfile` | Container image (`python:3.12-slim`, port 8088) |
| `requirements.txt` | Python dependencies |

**How it works:**
1. **Identify user** — calls `WorkIQUser.GetMyDetails` toolbox to get the user's email (via OBO token)
2. **Classify role** — calls `ClassifierAgent-2` to determine if the user is a Requestor, Legal Expert, or Tax Expert
3. **Route message** — forwards the user's message to the appropriate specialist agent (`RequestorAgent-2`, `LegalAgent-2`, or `TaxAgent-2`)
4. **Email/OneDrive tools** — provides tools to search emails and OneDrive via `WorkIQMail` toolbox

**Tool functions:**
| Tool | Description |
|------|-------------|
| `get_current_user` | Gets current user details via WorkIQ toolbox |
| `classify_user` | Classifies user role via ClassifierAgent |
| `route_to_requestor_agent` | Routes message to RequestorAgent |
| `route_to_legal_agent` | Routes message to LegalAgent |
| `route_to_tax_agent` | Routes message to TaxAgent |
| `search_emails` | Search user's emails via WorkIQ |
| `search_emails_query` | Search emails with KQL query |
| `get_email_message` | Get full email content by ID |
| `search_onedrive` | Search OneDrive files |
| `read_onedrive_file` | Read a OneDrive file |
| `search_m365_copilot` | Query M365 Copilot |

**Environment variables** (set in `agent.manifest.yaml`):
| Variable | Description |
|----------|-------------|
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | GPT model deployment name |
| `CLASSIFIER_AGENT_NAME` | Name of the classifier agent (default: `ClassifierAgent-2`) |
| `REQUESTOR_AGENT_NAME` | Name of the requestor agent (default: `RequestorAgent-2`) |
| `LEGAL_AGENT_NAME` | Name of the legal agent (default: `LegalAgent-2`) |
| `TAX_AGENT_NAME` | Name of the tax agent (default: `TaxAgent-2`) |

**Deploy:**
```bash
azd deploy orchestrator
```

This builds the Docker image, pushes it to ACR via remote build, and creates a new agent version in Foundry.

**Current agent name:** `LegalTaxOrchestrator-3` (configured in `agent.yaml` and `agent.manifest.yaml`)

---

## Infrastructure (`infra/`)

Provisioned via Bicep templates using `azd provision`.

| Template | Resources Created |
|----------|-------------------|
| `main.bicep` | Resource group, orchestrates modules |
| `cosmos.bicep` | Cosmos DB account + 5 containers (users, requests, questions, answers, audit_log) |
| `containerapp.bicep` | Container Apps environment + MCP Server app |
| `deployer-cosmos-rbac.bicep` | Cosmos DB RBAC for the deployer (local dev/seed scripts) |

**Provision:**
```bash
azd provision
```

---

## Seed Data

To populate initial test data (users, sample requests):

```bash
cd src
python seed_data.py
```

Requires `COSMOS_ENDPOINT` to be set.

---

## Testing from Foundry Portal

1. Go to [Azure AI Foundry](https://ai.azure.com)
2. Navigate to your project → Agents → `LegalTaxOrchestrator-3`
3. Open the **Playground** tab
4. Send a message (e.g., "Hi") — the orchestrator will identify you and classify your role

---

## Project Structure

```
LegalTaxAssistant/
├── azure.yaml                     # azd service definitions
├── Dockerfile                     # MCP Server container image
├── infra/                         # Bicep infrastructure templates
│   ├── main.bicep
│   ├── cosmos.bicep
│   ├── containerapp.bicep
│   └── deployer-cosmos-rbac.bicep
├── src/
│   ├── mcp_server/                # MCP Server (Container App)
│   │   ├── server.py
│   │   ├── tools.py
│   │   ├── cosmos_client.py
│   │   ├── models.py
│   │   └── requirements.txt
│   ├── agents/                    # Prompt Agent definitions & provisioning
│   │   ├── provision_agents.py
│   │   ├── requirements.txt
│   │   └── definitions/
│   │       ├── classifier_agent.yaml
│   │       ├── requestor_agent.yaml
│   │       ├── legal_agent.yaml
│   │       └── tax_agent.yaml
│   ├── orchestrator/              # Hosted Agent (Foundry container)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── agent.yaml
│   │   ├── agent.manifest.yaml
│   │   └── requirements.txt
│   ├── seed_data.py
│   └── tests/
└── architecture/
    └── architecture-diagram.md
```
