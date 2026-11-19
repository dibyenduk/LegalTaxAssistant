# Prerequisites

Complete list of dependencies needed to deploy and run the Legal & Tax Assistant application.

---

## 1. Azure Tenant & Users

| Requirement | Details |
|-------------|---------|
| **Azure AD (Entra ID) Tenant** | A Microsoft Entra ID tenant. Entra ID is included free with any Azure subscription — no separate license is needed |
| **Azure Subscription** | Active subscription with **Contributor** access and permission to create the required role assignments (for example, Role Based Access Control Administrator at the appropriate scope) |
| **At least 3 Azure AD Users** | One Requestor, one Legal Expert, one Tax Expert (for end-to-end testing) |

---

## 2. Microsoft 365 Licenses

| License | Required? | Purpose |
|---------|-----------|---------|
| **Microsoft 365 E5** (or E3) | ✅ Yes — at least 3 licenses | Provides Exchange Online (email), Microsoft Teams, and OneDrive for the Requestor, Legal Expert, and Tax Expert users |
| **Microsoft 365 Copilot** | ❌ **Not required** | This application uses Azure AI Foundry agents, not Microsoft 365 Copilot. No Copilot license is needed |
| **Microsoft Entra ID (Azure AD)** | ❌ **No separate license** | Entra ID Free is included with every Azure subscription. No P1/P2 license is required for this application |
| **Teams** | ✅ Included in M365 E5/E3 | The orchestrator is published as a Teams Bot for the chat interface |
| **Exchange Online / Outlook** | ✅ Included in M365 E5/E3 | The orchestrator sends email notifications to experts via WorkIQ Mail toolbox (Microsoft Graph) |

---

## 3. Azure AI Foundry

| Requirement | Details |
|-------------|---------|
| **Azure AI Services resource** | Multi-service Cognitive Services resource (e.g., `foundry-demo-ncus-resource`) |
| **Foundry Project** | A project within the AI Services resource (e.g., `prj-foundry-demo-ncus-dev-001`) |
| **Model Deployment** | Deploy `gpt-5.4` (or `gpt-5.4-mini`) model in the Foundry project |
| **Azure Container Registry** | An existing ACR in the application's resource group for managed-identity image pulls. This migration uses `acrjvtju6jxst6a6`; Foundry remains an external prerequisite |
| **Hosted Agents enabled** | Hosted agent capability must be enabled on the Foundry project |

---

## 4. Azure Resource Providers

The following providers must be registered on your Azure subscription:

```bash
az provider register --namespace Microsoft.Resources
az provider register --namespace Microsoft.DocumentDB
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.CognitiveServices
```

> **Tip:** Most of these are registered by default. Run `az provider show --namespace <namespace> --query registrationState` to check.

---

## 5. Azure Resources Provisioned by This Project

These are created automatically by `azd provision` — you do **not** need to create them manually:

| Resource | Provider | Purpose |
|----------|----------|---------|
| Cosmos DB Account + Database + Containers | `Microsoft.DocumentDB` | Stores requests, questions, answers, user roles |
| New Container App + VNet-integrated Managed Environment | `Microsoft.App` | Hosts the MCP Server alongside the retained legacy app/environment |
| VNet + Dedicated Subnets | `Microsoft.Network` | Separates Container Apps infrastructure from the Cosmos private endpoint |
| Cosmos Private Endpoint + New Private DNS Zone and VNet Link | `Microsoft.Network` | Keeps Cosmos connectivity private; all customer-managed networking is in the application resource group |
| Log Analytics Workspace | `Microsoft.OperationalInsights` | Container App logging |

Cosmos public network access and local/key authentication remain disabled.
Seeding or querying Cosmos from a developer machine or CI runner requires an
approved private-network route and private DNS; ordinary internet connectivity
and Contributor access are not sufficient. No VPN or peering is created by this
project. See the [private Cosmos migration runbook](docs/private-cosmos-migration.md)
for local validation, deployment approval, and connectivity verification.

---

## 6. Developer Tools

| Tool | Version | Required? | Purpose |
|------|---------|-----------|---------|
| [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | Latest | ✅ Required | Deployment orchestration (`azd up`, `azd deploy`) |
| [Azure CLI (az)](https://learn.microsoft.com/cli/azure/install-azure-cli) | Latest | ✅ Required | Resource provider registration, ACR login, RBAC |
| [Python](https://www.python.org/downloads/) | 3.11+ | ✅ Required | Agent provisioning scripts, local development |
| [Git](https://git-scm.com/) | Latest | ✅ Required | Source control |
| [Visual Studio Code](https://code.visualstudio.com/) | Latest | 📌 Recommended | IDE for development |
| Docker Desktop | Latest | ❌ **Not required** | All container builds use **remote ACR build** via `azd`. Docker is only needed if you want to test containers locally |

### Recommended VS Code Extensions

- Python (`ms-python.python`)
- Azure Tools (`ms-vscode.vscode-node-azure-pack`)
- Bicep (`ms-azuretools.vscode-bicep`)

---

## 7. Python Dependencies

Installed automatically during deployment via `pip install -r requirements.txt`. Listed here for reference:

| Component | Key Packages |
|-----------|-------------|
| **MCP Server** | `mcp[cli]`, `azure-cosmos`, `azure-identity`, `pydantic`, `uvicorn` |
| **Prompt Agents** | `azure-ai-projects`, `azure-identity`, `pyyaml` |
| **Orchestrator** | `agent-framework`, `agent-framework-foundry-hosting`, `azure-ai-projects`, `azure-identity`, `httpx`, `opentelemetry-api` |

---

## 8. Docker Base Images

Used during remote ACR builds — no local Docker installation required:

| Component | Base Image |
|-----------|-----------|
| MCP Server | `mcr.microsoft.com/devcontainers/python:3.11` |
| Orchestrator | `python:3.12-slim` |

---

## Summary Checklist

- [ ] Azure tenant with 3+ users (Requestor, Legal Expert, Tax Expert)
- [ ] Azure subscription with Contributor access
- [ ] Microsoft 365 E5 or E3 licenses (3 minimum) — for Teams + Outlook
- [ ] Azure AI Foundry project created
- [ ] GPT model deployed in Foundry (gpt-5.4 or gpt-5.4-mini)
- [ ] Azure Container Registry created and accessible from Foundry
- [ ] Hosted Agents enabled on Foundry project
- [ ] Resource providers registered (see section 4)
- [ ] Developer tools installed: azd, az, Python 3.11+, Git
