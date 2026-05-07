# Legal & Tax Assistant — Architecture Design Document

**Version:** 1.0  
**Status:** Draft — Pending Approval

---

## 1. Overview

The Legal & Tax Assistant is a Teams-based application that allows **Requestors** to submit legal and tax questions, which are automatically assigned to **Legal Experts** or **Tax Experts**. Experts answer questions (optionally pulling answers from email), and once all questions are answered the request can be submitted as complete.

The system is built on **Microsoft Foundry V2** using the **Microsoft Agent Framework**, with **Python** as the implementation language and **Azure Cosmos DB** as the data store.

---

## 2. Actors & Roles

| Role | Description |
|------|-------------|
| **Requestor** | Creates requests with questions, assigns questions to experts, tracks status, can answer questions themselves, submits completed requests. |
| **Legal Expert** | Views legal questions assigned to them, retrieves answers from email, answers and marks questions submitted. |
| **Tax Expert** | Views tax questions assigned to them, retrieves answers from email, answers and marks questions submitted. |

Roles are stored in Cosmos DB and resolved deterministically (not by LLM classification) to ensure authorization integrity.

---

## 3. User Stories

### 3.1 Requestor
1. Submit a new request — enter questions (one per line); each is auto-classified as Legal or Tax and assigned to the appropriate expert from the database.
2. View status of open requests — see requests, their questions, assignments, and statuses.
3. Assign a question to themselves — take ownership and answer it directly.
4. Get the answer to a question from email — retrieve answer content via Work IQ Email.
5. Answer a question — provide the answer and mark it submitted.
6. Submit the request — once all questions are answered, finalize the request.

### 3.2 Legal Expert
1. View questions assigned to them.
2. Get the answer to a question from email (Work IQ Email).
3. Answer the question and mark it submitted.

### 3.3 Tax Expert
1. View questions assigned to them.
2. Get the answer to a question from email (Work IQ Email).
3. Answer the question and mark it submitted.

---

## 4. High-Level Architecture

```
┌──────────┐    ┌──────────┐    ┌───────────────────┐    ┌──────────────┐
│  Teams   │───▶│ Teams Bot │───▶│  Custom API       │───▶│ Orchestrator │
│  Client  │    │ (auto)   │    │  Middleware        │    │ (Hosted Agent│
└──────────┘    └──────────┘    │  (App Service/Py) │    │  Foundry)    │
                                └───────────────────┘    └──────┬───────┘
                                                                │
                                          ┌─────────────────────┼─────────────────────┐
                                          │                     │                     │
                                          ▼                     ▼                     ▼
                                 ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
                                 │ RequestorAgent-2 │  │  LegalAgent-2   │  │   TaxAgent-2    │
                                 │ (Prompt Agent)   │  │ (Prompt Agent)  │  │ (Prompt Agent)  │
                                 └────────┬─────────┘  └────────┬────────┘  └────────┬────────┘
                                          │                     │                     │
                                          └─────────────────────┼─────────────────────┘
                                                                │
                                          ┌─────────────────────┼──────────────────┐
                                          ▼                                        ▼
                                 ┌──────────────────┐                  ┌────────────────────┐
                                 │ LegalTaxAssistant │                  │   Work IQ Email    │
                                 │ Tools (MCP Server)│                  │   (Built-in Tool)  │
                                 └────────┬──────────┘                  └────────────────────┘
                                          │
                                          ▼
                                 ┌──────────────────┐
                                 │    Cosmos DB      │
                                 └──────────────────┘
```

Additionally, a **ClassifierAgent-2** is used by the Orchestrator to identify the user's role:

```
Orchestrator ──▶ ClassifierAgent-2 ──▶ Work IQ User (built-in) + MCP Server (role lookup)
```

---

## 5. Component Details

### 5.1 Teams Bot
- **Auto-created** when the Orchestrator (Foundry Hosted Agent) is published to Teams via Microsoft Foundry.
- Receives all user messages from Teams.
- Forwards requests to the Custom API Middleware endpoint.

### 5.2 Custom API Middleware (Python / Azure App Service)

**Responsibilities:**
1. Receives HTTP requests from the Teams Bot.
2. Extracts the user's access token from the incoming request.
3. Exchanges the token for an **on-behalf-of (OBO) token** using MSAL.
4. Forwards the request (with OBO token) to the Foundry Orchestrator agent.
5. Passes the **Teams conversation ID** and **message ID** for thread correlation (required, not optional).
6. Returns the Orchestrator's response back to Teams.

**Technology:** Python (Flask or FastAPI), deployed as Azure App Service.

> **⚠ Design Risk — Deployment Topology Validation Required (Phase 0):**  
> It must be validated that the Teams Bot (auto-created by Foundry publish) can be configured to route through the custom middleware, or whether a fully custom Bot Framework bot is needed instead. This is a blocking prerequisite.

### 5.3 Orchestrator (Foundry Hosted Agent)

**Type:** Foundry Hosted Agent (Python, Microsoft Agent Framework)

**Responsibilities:**
1. Receives the user request with the OBO token from middleware.
2. Extracts the user's email from the token claims.
3. Calls **ClassifierAgent-2** to get the user's role from Cosmos DB.
4. **Caches the role** with a TTL (e.g., 5 minutes) to avoid redundant lookups. Cache is invalidated on role updates.
5. Routes the conversation to the appropriate agent based on role:
   - `Requestor` → **RequestorAgent-2**
   - `Legal Expert` → **LegalAgent-2**
   - `Tax Expert` → **TaxAgent-2**
6. Returns the agent's response to the middleware.

**Role resolution is deterministic** — the ClassifierAgent-2 calls the MCP Server which performs a direct Cosmos DB lookup. The LLM is used for conversation routing, not for access control decisions.

### 5.4 ClassifierAgent-2 (Foundry Prompt/Declarative Agent)

**Purpose:** Identifies the user and returns their role.

**Tools:**
| Tool | Type | Purpose |
|------|------|---------|
| Work IQ User | Built-in Foundry Tool | Identifies the user from the credential/token |
| LegalTaxAssistantTools | MCP Server | Looks up user role from Cosmos DB |

**Behavior:** Given a user email/identity, returns one of: `Requestor`, `LegalExpert`, `TaxExpert`, or `Unknown`.

### 5.5 RequestorAgent-2 (Foundry Prompt/Declarative Agent)

**Purpose:** Handles all Requestor workflows.

**Capabilities:**
1. Create a new request with questions.
2. Auto-assign questions to Legal or Tax experts based on question type (using Cosmos DB expert registry).
3. View status of requests and question assignments.
4. Assign questions to the requestor themselves.
5. Get answers from email.
6. Answer questions and mark submitted.

**Tools:**
| Tool | Type | Purpose |
|------|------|---------|
| Work IQ Email | Built-in Foundry Tool | Read/retrieve email content for answers |
| LegalTaxAssistantTools | MCP Server | CRUD operations on requests, questions, answers in Cosmos DB |

### 5.6 LegalAgent-2 (Foundry Prompt/Declarative Agent)

**Purpose:** Handles Legal Expert workflows.

**Capabilities:**
1. Get questions assigned to the user.
2. Get answer from the user's email via Work IQ Email.
3. Answer the question and mark it submitted.

**Tools:**
| Tool | Type | Purpose |
|------|------|---------|
| Work IQ Email | Built-in Foundry Tool | Read email content |
| LegalTaxAssistantTools | MCP Server | Read assigned questions, submit answers to Cosmos DB |

### 5.7 TaxAgent-2 (Foundry Prompt/Declarative Agent)

**Purpose:** Handles Tax Expert workflows. Identical structure to LegalAgent-2 but scoped to tax questions.

**Tools:** Same as LegalAgent-2.

### 5.8 LegalTaxAssistantTools — MCP Server (Python)

**Purpose:** Single MCP Server that provides all Cosmos DB CRUD operations as tools for the agents.

**Deployment:** Containerized Python service deployed via `azd` to Azure Container App with remote Docker build. Uses `mcr.microsoft.com/devcontainers/python:3.11` as the base image.

**Authentication:** Unauthenticated for initial phases. MCP Server authentication and role-based authorization enforcement will be added as a future enhancement (see Section 12).

**Tool Operations:**

| Tool Function | Description | Used By |
|---|---|---|
| `get_user_role` | Get a user's role by email | ClassifierAgent-2, Orchestrator |
| `create_request` | Create a new request with metadata | RequestorAgent-2 |
| `add_questions_to_request` | Add questions to a request | RequestorAgent-2 |
| `assign_question` | Assign a question to an expert or requestor | RequestorAgent-2 |
| `get_requests_by_user` | Get all requests for a requestor | RequestorAgent-2 |
| `get_request_status` | Get status of a request with question details | RequestorAgent-2 |
| `get_assigned_questions` | Get questions assigned to a user | LegalAgent-2, TaxAgent-2, RequestorAgent-2 |
| `submit_answer` | Submit an answer to a question | All role agents |
| `mark_question_submitted` | Mark a question as submitted | All role agents |
| `submit_request` | Finalize a request (all questions must be answered) | RequestorAgent-2 |
| `get_experts_by_type` | Get available experts for a question type | RequestorAgent-2 |

**Authorization enforcement:** Deferred to a future phase. Initially, the MCP Server is unauthenticated and trusts the caller's identity (user email passed as a parameter). Server-side role-based permission enforcement will be added as a future enhancement.

### 5.9 Azure Cosmos DB

**Database:** `LegalTaxAssistantDB`

---

## 6. Data Model

### 6.1 Containers & Entities

#### `Users` Container (Partition Key: `/email`)
```json
{
  "id": "unique-user-id",
  "email": "user@contoso.com",
  "displayName": "John Doe",
  "role": "Requestor | LegalExpert | TaxExpert",
  "expertType": "Legal | Tax | null",
  "isActive": true,
  "createdAt": "2026-04-28T00:00:00Z",
  "updatedAt": "2026-04-28T00:00:00Z"
}
```

#### `Requests` Container (Partition Key: `/requestorEmail`)
```json
{
  "id": "request-uuid",
  "requestorEmail": "requestor@contoso.com",
  "title": "Q1 2026 Tax & Legal Review",
  "status": "Draft | InProgress | Submitted | Completed",
  "createdAt": "2026-04-28T00:00:00Z",
  "updatedAt": "2026-04-28T00:00:00Z",
  "submittedAt": null
}
```

#### `Questions` Container (Partition Key: `/requestId`)
```json
{
  "id": "question-uuid",
  "requestId": "request-uuid",
  "questionText": "What are the tax implications of...",
  "questionType": "Legal | Tax",
  "assignedTo": "expert@contoso.com",
  "assignedBy": "requestor@contoso.com",
  "status": "Unassigned | Assigned | Answered | Submitted",
  "createdAt": "2026-04-28T00:00:00Z",
  "updatedAt": "2026-04-28T00:00:00Z"
}
```

#### `Answers` Container (Partition Key: `/questionId`)
```json
{
  "id": "answer-uuid",
  "questionId": "question-uuid",
  "requestId": "request-uuid",
  "answeredBy": "expert@contoso.com",
  "answerText": "The tax implications are...",
  "source": "Manual | Email",
  "emailMessageId": "email-msg-id-if-from-email",
  "createdAt": "2026-04-28T00:00:00Z",
  "updatedAt": "2026-04-28T00:00:00Z"
}
```

#### `AuditLog` Container (Partition Key: `/entityId`)
```json
{
  "id": "audit-uuid",
  "entityType": "Request | Question | Answer | User",
  "entityId": "entity-uuid",
  "action": "Created | Updated | Assigned | Answered | Submitted",
  "performedBy": "user@contoso.com",
  "timestamp": "2026-04-28T00:00:00Z",
  "details": { }
}
```

### 6.2 State Transitions

**Request Status Flow:**
```
Draft ──▶ InProgress ──▶ Submitted ──▶ Completed
                │                          ▲
                └──────────────────────────┘
                   (if reopened — future)
```
- `Draft` → `InProgress`: When first question is assigned.
- `InProgress` → `Submitted`: When requestor submits (all questions must be Answered/Submitted).
- `Submitted` → `Completed`: Final state.

**Question Status Flow:**
```
Unassigned ──▶ Assigned ──▶ Answered ──▶ Submitted
```
- `Unassigned` → `Assigned`: When assigned to an expert or requestor.
- `Assigned` → `Answered`: When an answer is provided.
- `Answered` → `Submitted`: When marked as submitted by the answerer.

---

## 7. Authentication & Authorization Flow

### 7.1 Token Flow

```
┌───────┐  SSO Token  ┌──────────┐  User Token  ┌────────────┐  OBO Token  ┌──────────────┐
│ Teams │────────────▶│ Teams Bot│─────────────▶│ Middleware │────────────▶│ Orchestrator │
│Client │              └──────────┘               │ (App Svc)  │             │ (Foundry)    │
└───────┘                                         └─────┬──────┘             └──────┬───────┘
                                                        │                          │
                                                   MSAL OBO                   User context
                                                   Exchange                   from token
                                                        │                     claims
                                                        ▼
                                                  Azure AD / Entra ID
```

### 7.2 Identity Propagation

| Hop | Token Type | Audience/Scope | Notes |
|-----|-----------|----------------|-------|
| Teams → Bot | SSO token | Bot App Registration | Auto-handled by Teams |
| Bot → Middleware | User token | Middleware App Registration | Extracted from Bot activity |
| Middleware → Foundry | OBO token | Foundry Agent scope | MSAL `acquire_token_on_behalf_of` |
| Foundry → Work IQ Email | OBO token (passthrough) | Microsoft Graph | Reads user's mailbox |
| Foundry → MCP Server | Unauthenticated (future: App identity + user email claim) | MCP Server endpoint | User email passed as parameter; auth enforcement deferred |

### 7.3 Authorization Enforcement

- **Role resolution** is deterministic: Cosmos DB lookup by email, not LLM-based.
- **MCP Server** is initially unauthenticated; role-based permission enforcement is a future enhancement.
- **Agents** are used for conversational UX, **not** for access control decisions.

> **⚠ Design Risk — OBO Flow Validation Required (Phase 0):**  
> End-to-end OBO token propagation must be validated, especially:
> - Whether Foundry Hosted Agents accept and propagate OBO tokens.
> - Whether Work IQ Email/User tools honor user-scoped tokens.
> - Fallback strategy if some components only support app identity.

---

## 8. Email Integration

**Tool:** Work IQ Email (Built-in Foundry Tool)

| Aspect | Design Decision |
|--------|-----------------|
| Mailbox type | User's personal mailbox (via OBO token) |
| Read vs. Send | Read only — agents retrieve email content as answer source |
| Correlation | Agent prompts user to identify the email; Work IQ Email searches by subject/sender/date |
| Duplicate handling | Answers linked to specific email message IDs to prevent re-use |

---

## 9. Observability & Audit

- **Audit Log** container in Cosmos DB records all state-changing actions with actor, timestamp, and entity reference.
- **Application Insights** for middleware and MCP Server telemetry (request tracing, latency, errors).
- **Foundry built-in logging** for agent conversation traces.
- All API calls include a **correlation ID** propagated from Teams conversation/message IDs.

---

## 10. Operational Guardrails

| Concern | Approach |
|---------|----------|
| Idempotency | MCP operations use request-scoped idempotency keys |
| Retry | Middleware retries Foundry calls with exponential backoff (max 3 retries) |
| Timeout | 30s timeout for agent calls; 10s for Cosmos operations |
| Rate Limiting | Middleware enforces per-user rate limits |
| Prompt Safety | Agent system prompts include guardrails against prompt injection |
| Human Escalation | If agent cannot resolve, escalate to a human support channel (future) |

---

## 11. Implementation Phases

### Phase 0 — Feasibility Spike (Pre-requisite)
- Validate Teams Bot → Custom Middleware routing topology.
- Validate end-to-end OBO token flow (Teams → Middleware → Foundry → Work IQ tools).
- Finalize Cosmos DB schema and provision database.
- Confirm Foundry V2 Hosted Agent deployment model.
- Set up `azd` project structure (`azure.yaml`, Bicep infra templates under `infra/`).

### Phase 1 — MCP Server + Cosmos DB
**Goal:** Build the data layer and MCP Server with full CRUD operations.

**Deployment:** `azd up` with remote Docker build. Dockerfile uses `mcr.microsoft.com/devcontainers/python:3.11` base image. Deployed to Azure Container App.

**Deliverables:**
- `azd` project initialized with Bicep infrastructure-as-code (`infra/`) for Cosmos DB + Container App.
- Cosmos DB provisioned with all containers (`Users`, `Requests`, `Questions`, `Answers`, `AuditLog`).
- Seed data for test users (Requestor, Legal Expert, Tax Expert).
- Python MCP Server implementing all tool operations (see Section 5.8).
- Dockerfile using `mcr.microsoft.com/devcontainers/python:3.11` base image.
- Unit tests for all MCP operations.
- Deployed and testable via `azd up` using remote Docker build.

### Phase 2 — Prompt Agents
**Goal:** Create and configure all Foundry Declarative/Prompt Agents.

**Deployment:** Agent creation scripts deployed via `azd` hooks or post-deployment scripts.

**Deliverables:**
- **ClassifierAgent-2** — prompt + tool bindings (Work IQ User, MCP `get_user_role`).
- **RequestorAgent-2** — prompt + tool bindings (Work IQ Email, MCP CRUD tools).
- **LegalAgent-2** — prompt + tool bindings (Work IQ Email, MCP read/answer tools).
- **TaxAgent-2** — prompt + tool bindings (Work IQ Email, MCP read/answer tools).
- Python scripts for provisioning agents in Foundry V2.
- `azd` hooks to run agent provisioning scripts post-deployment.
- Test each agent individually via Foundry Playground.

### Phase 3 — Orchestrator (Hosted Agent)
**Goal:** Build the Orchestrator that routes conversations to the correct agent.

**Deployment:** `azd up` with remote Docker build. Dockerfile uses `mcr.microsoft.com/devcontainers/python:3.11` base image. Deployed to Foundry as Hosted Agent.

**Deliverables:**
- Python Hosted Agent using Microsoft Agent Framework.
- Dockerfile using `mcr.microsoft.com/devcontainers/python:3.11` base image.
- Role resolution via ClassifierAgent-2 with caching (TTL-based).
- Conversation routing logic (role → agent mapping).
- Deploy to Foundry as Hosted Agent via `azd up`.
- End-to-end test: Orchestrator → ClassifierAgent → Role Agent → MCP → Cosmos.

### Phase 4 — Custom Middleware + Teams Integration
**Goal:** Connect the Teams Bot to the Orchestrator via the custom middleware.

**Deployment:** `azd up` with remote Docker build. Dockerfile uses `mcr.microsoft.com/devcontainers/python:3.11` base image. Deployed to Azure App Service.

**Deliverables:**
- Python middleware (FastAPI) deployed as Azure App Service via `azd up`.
- Dockerfile using `mcr.microsoft.com/devcontainers/python:3.11` base image.
- Token extraction and OBO exchange via MSAL.
- Teams conversation/message ID forwarding.
- Publish Orchestrator to Teams (auto-creates Bot).
- Configure Bot to route through middleware (or implement custom Bot if needed).
- End-to-end test: Teams → Bot → Middleware → Orchestrator → Agents → Cosmos.

---

## 12. Future Enhancements

- **MCP Server authentication:** Add token-based authentication and server-side role-based authorization enforcement to the MCP Server.
- **Proactive notifications:** Send Teams messages to experts when new questions are assigned.
- **Role management UI:** Admin interface for managing user roles.
- **Request reopening:** Allow reopening submitted requests.
- **Analytics dashboard:** Request volume, response times, SLA tracking.
- **Multi-language support:** Localization for non-English users.

---

## 13. Open Questions

| # | Question | Impact |
|---|----------|--------|
| 1 | Can the Foundry-published Teams Bot be configured to route through custom middleware, or is a custom Bot Framework bot required? | Architecture — Phase 0 |
| 2 | Does the Foundry Hosted Agent accept and propagate OBO tokens to child agents and tools? | Auth flow — Phase 0 |
| 3 | Should LegalAgent-2 and TaxAgent-2 be merged into a single ExpertAgent with domain policy? | Simplification — Phase 2 |
| 4 | What is the SLA for question response time? Does the system need reminders/escalation? | Feature scope |
| 5 | Is there a need for an admin role to manage users and roles? | Data model |

---

## Appendix A — Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Orchestrator Framework | Microsoft Agent Framework (azure-ai-agents) |
| Agent Hosting | Microsoft Foundry V2 (Hosted + Declarative Agents) |
| MCP Server | Python (MCP SDK) |
| Middleware | Python (FastAPI), Azure App Service |
| Database | Azure Cosmos DB (NoSQL) |
| Authentication | MSAL Python, Azure AD / Entra ID, OBO flow |
| MCP Server Auth | Unauthenticated (future: token-based auth) |
| Email | Work IQ Email (Foundry built-in tool) |
| User Identity | Work IQ User (Foundry built-in tool) |
| Observability | Azure Application Insights |
| Teams Integration | Bot Framework (auto-published via Foundry) |
| Deployment | Azure Developer CLI (`azd`) |
| Infrastructure as Code | Bicep (`infra/` directory) |
| Container Build | Remote Docker build via `azd` |
| Base Docker Image | `mcr.microsoft.com/devcontainers/python:3.11` (Microsoft image) |
| Container Hosting | Azure Container Apps (MCP Server, Orchestrator) / Azure App Service (Middleware) |
