# Legal & Tax Assistant

A Foundry-hosted application that allows **Requestors** to submit legal and tax questions, which are assigned to **Legal Experts** or **Tax Experts**. Built on **Microsoft Foundry** using the **Microsoft Agent Framework** with **Python**. This repository deploys the agents and backend; it does not contain a Teams bot or Teams application package.

## Architecture
```
Foundry Playground / authenticated Responses client
    -> Orchestrator (Hosted Agent)
        -> WorkIQ toolboxes (delegated user identity)
        -> Four prompt agents -> Public HTTPS MCP /sse
            -> VNet-integrated Container App -> Private endpoint -> Cosmos DB
```

| Component | Location | Hosting |
|-----------|----------|---------|
| MCP Server | `src/mcp_server/` | Azure Container Apps |
| Prompt Agents | `src/agents/` | Foundry Prompt Agents |
| Orchestrator | `src/orchestrator/` | Foundry Hosted Agent (Container) |
| Infrastructure | `infra/` | Bicep (Cosmos DB, private networking, Container Apps, RBAC) |

---

## Prerequisites

See [`PREREQUISITES.md`](PREREQUISITES.md) for the full list of dependencies including Azure tenant setup, Microsoft 365 licenses, Foundry project, resource providers, and developer tools.

**Deployment prerequisites:**

- An Azure subscription with permission for subscription-scope Bicep deployments,
  resource creation, and the role assignments below.
- An existing Foundry project with hosted-agent support, an enabled project
  managed identity, and a deployed chat model. The current configuration uses
  `gpt-5.4`. Foundry itself and its model are **not** created by this repository.
- Foundry project permissions to create agent versions, connections, and toolboxes,
  and permission for the hosted agent to invoke the project's model and agents.
- An existing Azure Container Registry in the application resource group, or
  permission to create one. Use classic registry RBAC; the templates grant
  `AcrPull`, not ABAC repository roles.
- Microsoft 365 test users with the mailbox/OneDrive access, Agent 365 availability,
  licenses, and tenant consent required by the selected catalog tools. Confirm
  current requirements in your tenant; do not assume Copilot-backed operations
  are covered by an E3/E5 license alone.
- PowerShell 7, Azure CLI, Azure Developer CLI with compatible Foundry extensions,
  Bicep CLI, and Python 3.11+ for provisioning helpers. Python 3.12 is a useful
  local default matching the orchestrator image. Docker is optional: builds run
  remotely in ACR.

For private Cosmos access from a developer machine or CI runner, also arrange an
approved private-network route and private DNS. The templates do not create a VPN.

---

## End-to-end deployment

Run the following steps from the **repository root in PowerShell 7**, after
approving the Azure changes and costs. Keep the same shell so the variables
remain available. Replace every `<...>` placeholder before running commands.
These steps use the existing [azure.yaml](azure.yaml); do not regenerate it with
an agent scaffold command.

**Order:** configure prerequisites -> provision infrastructure -> deploy MCP ->
verify private Cosmos -> register users -> provision all four prompt agents ->
configure WorkIQ -> configure Foundry registry access -> deploy orchestrator ->
verify the complete path.

`azd up` is **not** an end-to-end setup command for this repository: it does not
run the prompt-agent provisioning script, seed users, or create the WorkIQ
connections/toolboxes. Use the staged sequence below.

### 1. Authenticate and select the environment

```powershell
az login
azd auth login
az account set --subscription '<subscription-id>'

$subscriptionId = '<subscription-id>'
$environmentName = '<azd-environment-name>'
$location = 'westus3'
$appResourceGroup = "rg-$environmentName"
$registryName = '<globally-unique-acr-name>'
$foundryResourceGroup = '<existing-foundry-resource-group>'
$foundryAccount = '<existing-foundry-account>'
$foundryProject = '<existing-foundry-project>'
$model = 'gpt-5.4' # The deployment name, not merely a model catalog name.
$projectEndpoint = "https://$foundryAccount.services.ai.azure.com/api/projects/$foundryProject"
$projectId = "/subscriptions/$subscriptionId/resourceGroups/$foundryResourceGroup/providers/Microsoft.CognitiveServices/accounts/$foundryAccount/projects/$foundryProject"
$registryId = "/subscriptions/$subscriptionId/resourceGroups/$appResourceGroup/providers/Microsoft.ContainerRegistry/registries/$registryName"
$registryHost = "$registryName.azurecr.io"

# Install missing extensions; update only to versions compatible with your azd.
azd extension install azure.ai.agents
azd extension install azure.ai.connections
azd extension install azure.ai.toolboxes

# FIRST deployment only:
azd env new $environmentName --subscription $subscriptionId --location $location

# INSTEAD, when continuing an existing deployment:
# azd env select $environmentName
```

For this deployed instance, the azd environment is `legaltaxassist0428`, the
application resource group is `rg-legaltaxassist0428`, and Foundry is in a
separate resource group/region. An existing Foundry project can be reused; its
resource group does not have to match the application resource group.

Before continuing, create the Foundry project/model in the
[Foundry portal](https://ai.azure.com/) if they do not already exist. Verify the
project endpoint, ARM resource ID, project managed identity, model deployment,
and hosted-agent availability. Do not mix values from different projects.

### 2. Prepare the registry, providers, and azd settings

The application resource group name is derived as `rg-<environmentName>` by
Bicep. The registry must already exist **in that group** before provisioning.
For a new deployment only:

```powershell
az group create --name $appResourceGroup --location $location
az acr create --resource-group $appResourceGroup --name $registryName `
    --location $location --sku Basic --admin-enabled false
```

Reuse an existing registry rather than recreating it. Register any missing
providers and wait for registration to finish:

```powershell
foreach ($provider in @(
    'Microsoft.Resources', 'Microsoft.DocumentDB', 'Microsoft.Network',
    'Microsoft.App', 'Microsoft.OperationalInsights',
    'Microsoft.ContainerRegistry', 'Microsoft.CognitiveServices'
)) {
    az provider register --namespace $provider --wait
}

azd env set AZURE_CONTAINER_REGISTRY_NAME $registryName
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT $registryHost
azd env set AZURE_CONTAINER_REGISTRY_RESOURCE_ID $registryId
azd env set AZURE_AI_PROJECT_ID $projectId
azd env set AZURE_AI_PROJECT_ENDPOINT $projectEndpoint
azd env set FOUNDRY_PROJECT_ENDPOINT $projectEndpoint
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME $model
azd env set MODEL_DEPLOYMENT_NAME $model
azd env get-values
```

Keep azd values local; do not commit credentials or environment files, or paste
the full environment output into logs/tickets. `FOUNDRY_PROJECT_ENDPOINT` above
is a **local deployment setting**. Do not add it to the hosted service's
`environmentVariables`: Foundry reserves `FOUNDRY_*` and `AGENT_*` names.

Provisioning supplies `AZURE_RESOURCE_GROUP`, `AZURE_COSMOS_ENDPOINT`,
`AZURE_COSMOS_ACCOUNT_NAME`, `AZURE_CONTAINER_APP_NAME`,
`AZURE_CONTAINER_APP_PRINCIPAL_ID`, `AZURE_CONTAINER_APP_FQDN`, and networking
outputs. Do not manually redirect the MCP target to a legacy app.

### 3. Validate and provision private Cosmos infrastructure

Review [infra/main.bicep](infra/main.bicep) and
[infra/main.parameters.json](infra/main.parameters.json). The default network is
`10.97.0.0/16`, with `10.97.0.0/23` for Container Apps and `10.97.2.0/24` for the
private endpoint. If these overlap another network, adjust the Bicep parameters
and their parameter-file mapping before deploying; arbitrary azd variables are
not automatically passed to Bicep.

```powershell
pwsh -File .\infra\tests\Test-PrivateCosmos.ps1
azd provision --preview --no-prompt
# Review the preview and obtain approval before applying:
azd provision --no-prompt
```

Expect a Cosmos account, `LegalTaxAssistantDB`, five containers, a new VNet,
separate subnets, a Cosmos Sql private endpoint, a **new in-group**
`privatelink.documents.azure.com` zone/link, Log Analytics, a new
VNet-integrated Container Apps environment/app, and MCP identity permissions.
Cosmos public access and local/key authentication are disabled. Do not reuse the
private DNS zone in another resource group.

For an existing deployment, preserve the environment name/location and review
the preview for account settings or resource drift. Use incremental deployment;
do not delete legacy resources or existing data. The
[migration runbook](docs/private-cosmos-migration.md) records the current topology.

**Important:** provisioning applies a bootstrap image to the MCP app. It is not
a working MCP deployment. Every provision run must be followed by the registry
configuration and real MCP image deployment in step 4, even on a previously
working environment.

### 4. Deploy MCP and verify its private database path

```powershell
$rg = azd env get-value AZURE_RESOURCE_GROUP
$app = azd env get-value AZURE_CONTAINER_APP_NAME
$principal = azd env get-value AZURE_CONTAINER_APP_PRINCIPAL_ID
$cosmos = azd env get-value AZURE_COSMOS_ACCOUNT_NAME
$pe = azd env get-value AZURE_COSMOS_PRIVATE_ENDPOINT_NAME

# Confirm the Bicep-created AcrPull assignment; allow time for RBAC propagation.
az role assignment list --scope $registryId `
    --query "[?principalId=='$principal'].{role:roleDefinitionName,scope:scope}" -o table

# Explicitly configure image pulls; azd does not reliably add this link.
az containerapp registry set --resource-group $rg --name $app `
    --server $registryHost --identity system
azd deploy mcp-server --no-prompt

$fqdn = azd env get-value AZURE_CONTAINER_APP_FQDN
$mcpUrl = "https://$fqdn/sse"
Invoke-RestMethod "https://$fqdn/health" -TimeoutSec 120

az cosmosdb show --resource-group $rg --name $cosmos `
    --query '{publicNetworkAccess:publicNetworkAccess,disableLocalAuth:disableLocalAuth}' -o json
az network private-endpoint show --resource-group $rg --name $pe `
    --query 'privateLinkServiceConnections[].privateLinkServiceConnectionState.status' -o tsv
az network private-dns record-set a list --resource-group $rg `
    --zone-name privatelink.documents.azure.com -o table
az network private-dns link vnet list --resource-group $rg `
    --zone-name privatelink.documents.azure.com -o table
az cosmosdb sql role assignment list --resource-group $rg --account-name $cosmos `
    --query "[?principalId=='$principal'].{role:roleDefinitionId,scope:scope}" -o table
az containerapp exec --resource-group $rg --name $app --command /bin/sh
```

Inside that **Linux container shell**, run this read-only check, then `exit` to
return to PowerShell:

```sh
python -c 'import os,socket,ipaddress; from urllib.parse import urlparse; from mcp_server.cosmos_client import CosmosDBClient; host=urlparse(os.environ["COSMOS_ENDPOINT"]).hostname; addresses={entry[4][0] for entry in socket.getaddrinfo(host,443)}; print("Cosmos DNS:",addresses); assert addresses and all(ipaddress.ip_address(a).is_private for a in addresses); print("Users count:",CosmosDBClient().query_items("Users","SELECT VALUE COUNT(1) FROM c"))'
```

Require `publicNetworkAccess=Disabled`, `disableLocalAuth=true`, an `Approved`
private endpoint, a DNS link to the new VNet, private IPs matching the DNS records,
and a successful managed-identity query. An empty Users container is normal for
a new deployment. `/health` alone proves only process liveness. **Do not cut over
prompt agents until the actual Cosmos query succeeds.**

### 5. Prepare Python helpers and initial user roles

In the original PowerShell shell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\src\agents\requirements.txt
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:FOUNDRY_PROJECT_ENDPOINT = $projectEndpoint
$env:MODEL_DEPLOYMENT_NAME = $model
$env:MCP_SERVER_URL = $mcpUrl
```

The Users container must contain the actual signed-in users' emails and roles:
`Requestor`, `LegalExpert` with `expertType=Legal`, and `TaxExpert` with
`expertType=Tax`. See [the user model](src/mcp_server/models.py).

**Existing database:** inspect/preserve its users; do not reseed it as a
deployment step. **New test database:** review and adapt `SEED_USERS` in
[src/seed_data.py](src/seed_data.py) before running it. It seeds **users only**,
not requests. It generates new IDs, so repeated runs can create duplicate emails;
it is not an idempotent user-management tool.

Run the seed script only from an approved private-network host with this checkout
and working private DNS. If the seed identity lacks Cosmos data-plane access,
an authorized administrator can grant it as follows (use the actual seeder's
object ID, not necessarily the deployer's):

```powershell
$seederPrincipalId = '<seeding-user-or-service-principal-object-id>'
$cosmosId = az cosmosdb show --resource-group $rg --name $cosmos --query id -o tsv
az cosmosdb sql role assignment create --resource-group $rg --account-name $cosmos `
    --principal-id $seederPrincipalId --scope $cosmosId `
    --role-definition-id "$cosmosId/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
```

On that network-connected host, install the MCP dependencies in its virtual
environment and seed once:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\src\mcp_server\requirements.txt
$env:COSMOS_ENDPOINT = azd env get-value AZURE_COSMOS_ENDPOINT
.\.venv\Scripts\python.exe .\src\seed_data.py --endpoint $env:COSMOS_ENDPOINT
```

Transfer/select the same deployment configuration if using a separate host.
The MCP image does not include the seed script. Check actual records afterward:
the script can print individual write errors and still print "Seed complete."
Do not enable public access or account keys to make seeding work.

### 6. Provision all four prompt agents explicitly

This step is mandatory: neither Bicep nor `azd deploy orchestrator` creates
the prompt agents.

```powershell
.\.venv\Scripts\python.exe -m agents.provision_agents `
    --project-endpoint $projectEndpoint `
    --model $model `
    --mcp-server-url $mcpUrl
if ($LASTEXITCODE -ne 0) { throw 'Prompt-agent provisioning failed.' }
```

The script loads all four YAML files in
[src/agents/definitions](src/agents/definitions) and creates a **new version**
for each agent, retaining previous versions:

| Definition | Agent name |
|------------|------------|
| [classifier_agent.yaml](src/agents/definitions/classifier_agent.yaml) | ClassifierAgent-2 |
| [requestor_agent.yaml](src/agents/definitions/requestor_agent.yaml) | RequestorAgent-2 |
| [legal_agent.yaml](src/agents/definitions/legal_agent.yaml) | LegalAgent-2 |
| [tax_agent.yaml](src/agents/definitions/tax_agent.yaml) | TaxAgent-2 |

It substitutes the model and configures each agent's allowed MCP tools against
`$mcpUrl`. The names must match the four specialist environment variables in
[azure.yaml](azure.yaml). The script's health poll can warn and continue, so its
success message is not a substitute for step 4 or the following verification.

Read back every latest definition, not just the first agent:

```powershell
@'
import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

with AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                     credential=DefaultAzureCredential()) as client:
    for name in ("ClassifierAgent-2", "RequestorAgent-2", "LegalAgent-2", "TaxAgent-2"):
        version = client.agents.get(agent_name=name).as_dict()["versions"]["latest"]
        definition = version["definition"]
        urls = [t["server_url"] for t in definition.get("tools", []) if t["type"] == "mcp"]
        assert definition["model"] == os.environ["MODEL_DEPLOYMENT_NAME"], name
        assert urls and all(url == os.environ["MCP_SERVER_URL"] for url in urls), name
        print(name, "version", version["version"], "model", definition["model"], "MCP", urls)
'@ | .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) { throw 'Prompt-agent readback failed.' }
```

In the Foundry playground, invoke `ClassifierAgent-2` with a synthetic
nonexistent address such as `private-endpoint-smoke@example.invalid`. Require
`Unknown` **and** inspect the trace to confirm a successful `get_user_role` MCP
call. A partial script failure may leave agent versions mixed; inspect all four
before proceeding.

### 7. Configure the four WorkIQ connections and toolboxes

These are separate from prompt agents and are not provisioned by Bicep.
The orchestrator defaults to the base name `DkWorkIQMail`:

| Connection / tool namespace | Toolbox | Agent 365 server path | Catalog object ID |
|-----------------------------|---------|-----------------------|-------------------|
| WorkIQUser | DkWorkIQMail-User | mcp_MeServer | microsoft-365-user-profile-mcp-frontier |
| WorkIQMail | DkWorkIQMail-Mail | mcp_MailTools | microsoft-outlook-mail-mcp-frontier |
| WorkIQOneDrive | DkWorkIQMail-OneDrive | mcp_OneDriveRemoteServer | microsoft-onedrive-mcp-frontier |
| WorkIQCopilot | DkWorkIQMail-Copilot | mcp_M365Copilot | microsoft-copilot-chat-frontier |

Create these in the selected Foundry project using the portal/tool catalog, or
the CLI below. Check the current catalog/tenant settings before creation. The
verified catalog configuration uses `UserEntraToken` with audience
`ea9ffc3e-8a23-4a7d-836d-234d7c7565c1`. Do not replace these servers with
`https://workiq.svc.cloud.microsoft/mcp`; that is a different tool surface.

For an existing project, first inspect:

```powershell
azd ai connection list --project-endpoint $projectEndpoint --output table
azd ai toolbox list --project-endpoint $projectEndpoint --output table
```

**Fresh project only:** the following creates all four pairs. For partial/existing
setups, run only the missing creation operations; do not overwrite existing
connections or toolbox versions. If a toolbox already exists but its connection
is missing, restore the connection without recreating the toolbox.

```powershell
$workIQ = @(
    @{Name='WorkIQUser'; Suffix='User'; Path='mcp_MeServer'; Catalog='microsoft-365-user-profile-mcp-frontier'},
    @{Name='WorkIQMail'; Suffix='Mail'; Path='mcp_MailTools'; Catalog='microsoft-outlook-mail-mcp-frontier'},
    @{Name='WorkIQOneDrive'; Suffix='OneDrive'; Path='mcp_OneDriveRemoteServer'; Catalog='microsoft-onedrive-mcp-frontier'},
    @{Name='WorkIQCopilot'; Suffix='Copilot'; Path='mcp_M365Copilot'; Catalog='microsoft-copilot-chat-frontier'}
)
New-Item -ItemType Directory -Force .\.azure\toolbox-specs | Out-Null
foreach ($entry in $workIQ) {
    azd ai connection create $entry.Name --kind remote-tool `
        --target "https://agent365.svc.cloud.microsoft/agents/servers/$($entry.Path)" `
        --auth-type user-entra-token --audience 'ea9ffc3e-8a23-4a7d-836d-234d7c7565c1' `
        --metadata 'type=catalog_MCP' `
        --metadata "toolEntityId=azureml://location/eastus/apiCenter/registry-prod-bl/type/tools/objectId/$($entry.Catalog)/version/1" `
        --project-endpoint $projectEndpoint --no-prompt
    if ($LASTEXITCODE -ne 0) { throw "Connection creation failed: $($entry.Name)" }

    $toolbox = "DkWorkIQMail-$($entry.Suffix)"
    $spec = ".\.azure\toolbox-specs\$toolbox.yaml"
    "name: $toolbox`ndescription: Legal Tax WorkIQ $($entry.Suffix)`nconnections:`n  - name: $($entry.Name)" |
        Set-Content -LiteralPath $spec -Encoding utf8
    azd ai toolbox create $toolbox --from-file $spec `
        --project-endpoint $projectEndpoint --no-prompt
    if ($LASTEXITCODE -ne 0) { throw "Toolbox creation failed: $toolbox" }
}
```

Verify discovery on **each** toolbox. The following uses the provisioning
virtual environment and does not print bearer tokens:

```powershell
@'
import json
import os
import urllib.request
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
for suffix in ("User", "Mail", "OneDrive", "Copilot"):
    name = "DkWorkIQMail-" + suffix
    url = os.environ["FOUNDRY_PROJECT_ENDPOINT"] + "/toolboxes/" + name + "/mcp?api-version=v1"
    headers = {
        "Authorization": "Bearer " + credential.get_token("https://ai.azure.com/.default").token,
        "Foundry-Features": "Toolboxes=V1Preview",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = json.dumps({"jsonrpc": "2.0", "id": "verify", "method": "tools/list", "params": {}}).encode()
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(name + ": " + json.dumps(result["error"]))
    tools = result.get("result", {}).get("tools", [])
    assert tools, name
    if suffix == "User":
        assert any(t["name"] == "WorkIQUser___GetMyDetails" for t in tools), name
    print(name, len(tools), "tools")
'@ | .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) { throw 'WorkIQ toolbox discovery failed.' }
```

JSON-RPC errors can arrive inside HTTP 200 responses. A successful signed-in
developer call does not prove hosted end-user delegation; step 10 checks that path.

### 8. Give the Foundry project access to the application registry

The MCP app's `AcrPull` assignment does not cover the Foundry hosted agent.
Grant the **Foundry project** managed identity (not the parent account identity)
access to the same registry:

```powershell
$projectPrincipal = az rest --method get `
    --url "https://management.azure.com${projectId}?api-version=2025-06-01" `
    --query identity.principalId -o tsv
if (-not $projectPrincipal) { throw 'Enable the Foundry project managed identity first.' }
az role assignment list --scope $registryId `
    --query "[?principalId=='$projectPrincipal'].{role:roleDefinitionName,scope:scope}" -o table
# If AcrPull is missing:
az role assignment create --assignee-object-id $projectPrincipal `
    --assignee-principal-type ServicePrincipal --role AcrPull --scope $registryId

# Create only if a matching ContainerRegistry connection is absent:
azd ai connection create legal-tax-acr --kind container-registry `
    --target "https://$registryHost" --auth-type project-managed-identity `
    --audience 'https://containerregistry.azure.net/' `
    --metadata "ResourceId=$registryId" `
    --project-endpoint $projectEndpoint --no-prompt
```

Allow RBAC propagation and verify that the connection targets this registry.
Registry admin credentials are not required.

### 9. Deploy the hosted orchestrator

[azure.yaml](azure.yaml) is the authoritative runtime definition, not the legacy
`agent.yaml` or `agent.manifest.yaml` files. It declares remote Docker builds,
`LegalTaxOrchestrator-3`, Responses **2.0.0**, **1 CPU / 2 GiB**, the model, four
prompt-agent names, and the WorkIQ base name. The smaller 0.25 CPU tier rejected
this application's image during deployment.

```powershell
azd deploy orchestrator --no-prompt
azd ai agent show orchestrator --output json
```

Require the new version to be `active`. Record its version, image, endpoint,
and playground URL. Container dependencies are installed during the remote build;
local installation of the orchestrator dependencies is not needed to deploy.
Do not run `azd provision` for an orchestrator-only update: that would reset MCP
to its bootstrap configuration.

### 10. Verify the complete application

Start a **new conversation on the newly deployed version**, not an existing
session pinned to an old version. Use the playground URL from step 9, or:

```powershell
azd ai agent invoke orchestrator `
    'Read-only verification: identify me with get_current_user, then classify_user. Report my email and role. Do not access mail/files or perform writes.' `
    --new-session --no-prompt
azd ai agent monitor orchestrator --tail 200
```

Require the actual WorkIQ `GetMyDetails` call and classifier delegation in the
trace/logs, an email matching the invoking user, and the role stored in Cosmos.
The hosted raw MCP client must forward
`get_request_context().platform_headers()` on discovery and tool calls.
The Foundry bearer token authenticates the workload; the trusted per-request
call ID lets Foundry resolve the delegated user. Never fabricate that context.
After collecting logs, stop only your test session:

```powershell
# Copy the Session value printed by invoke:
azd ai agent sessions stop '<test-session-id>' --agent-name LegalTaxOrchestrator-3 --no-prompt
```

Then test the business workflow with approved test data and all three user roles:
create a request, add legal/tax questions, assign experts, draft and confirm
answers, submit each answer, and submit the completed request. Test mailbox and
OneDrive reads separately with the user's permissions; only test sends/writes
after explicit confirmation. Agent deployment or identity lookup alone does not
prove these workflows.

**Security boundary:** MCP ingress is public HTTPS and this repository does not
yet add MCP caller authentication/backend authorization. Private Cosmos does not
secure the public MCP API. Address that separately before production exposure.
No Teams integration or Blob Storage deployment is included.

### Subsequent updates and troubleshooting

| Change | Required action |
|--------|-----------------|
| MCP code only | `azd deploy mcp-server --no-prompt`, then verify health and Cosmos access |
| Prompt YAML/model/MCP URL | Repeat step 6 explicitly and verify all four new versions |
| Orchestrator code/runtime configuration | Repeat steps 9-10; use a fresh session |
| Infrastructure | Preview/provision, repeat step 4, and reverify agents if the MCP URL changed |
| Missing WorkIQ connection | Restore the exact connection from step 7; do not redeploy unrelated resources |

| Symptom | Check |
|---------|-------|
| `Connection WorkIQUser can't be found` | The matching connection must exist in the same project as the toolbox |
| `User identity authentication ... not supported for this caller` | Trusted caller-context forwarding, delegated invocation, Responses 2.0.0, and a fresh session |
| MCP image pull failure | App identity's AcrPull assignment and explicit `az containerapp registry set` |
| Hosted image pull failure | Project identity's AcrPull assignment and Foundry ContainerRegistry connection |
| Cosmos 403 or DNS failure | Private route/DNS and Cosmos data-plane role assignment, not just Azure Contributor |
| `Unknown` for a real user | Exact email/role in Users; do not treat it as successful registration |
| `FastMCP` import failure | Preserve the MCP SDK constraint `mcp<2` |
| Reserved environment-variable error | Remove explicit hosted `FOUNDRY_*`/`AGENT_*` declarations |

Keep previous agent versions and legacy resources until the complete rollout is
accepted. Use [the migration runbook](docs/private-cosmos-migration.md) for the
verified deployment history and networking diagnostics.

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
| `submit_answer` | Record an answer and finalize the question as Submitted |
| `mark_question_submitted` | Compatibility tool for legacy Answered questions; already Submitted questions are unchanged |
| `send_request` | Send a request for review |
| `submit_request` | Submit a completed request |
| `get_experts_by_type` | List experts by type (legal/tax) |

**Answer submission workflow:**
1. The expert drafts an answer manually or using email/document context.
2. The orchestrator obtains the user's confirmation once before routing the answer to a specialist.
3. The specialist calls `submit_answer` with the question ID, request ID, expert email, answer text, and actor email. The answer is recorded and the question moves directly from Assigned (or legacy Answered) to Submitted.
4. No separate finalization call is needed. `mark_question_submitted` remains available for legacy Answered questions; repeating it for a Submitted question performs no writes and creates no audit entries.
5. The requestor can call `submit_request` only when every question is Submitted.

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

**Deploy:** follow [step 6](#6-provision-all-four-prompt-agents-explicitly), including
the virtual environment, `PYTHONPATH`, explicit arguments, and all-agent readback.

**Deployment order:** Provision and deploy the MCP Server, verify private Cosmos
access, then run prompt-agent provisioning explicitly. Infrastructure provisioning
does not automatically switch agents to the new endpoint.

**How it works:**
1. Reads each YAML definition from `src/agents/definitions/`
2. Substitutes `${MODEL_DEPLOYMENT_NAME}` with the specified model
3. Creates a new version of each named agent in Foundry via the `azure-ai-projects` SDK
4. Configures MCP tool connections pointing to the MCP Server SSE endpoint

---

### 3. Orchestrator (`src/orchestrator/`)

The orchestrator is a **Foundry Hosted Agent** — a containerized Python application using the Microsoft Agent Framework. It receives user messages via the Responses API protocol and routes them to the appropriate prompt agent.

**Files:**
| File | Description |
|------|-------------|
| `main.py` | Agent implementation with tool functions and routing logic |
| [`azure.yaml`](azure.yaml) | Current azd runtime definition: protocol, resources, Docker build, and environment variables |
| `agent.yaml` | Legacy container spec, retained for reference |
| `agent.manifest.yaml` | Legacy initialization manifest, retained for reference |
| `Dockerfile` | Container image (`python:3.12-slim`, port 8088) |
| `requirements.txt` | Python dependencies |

**How it works:**
1. **Identify user** — calls `WorkIQUser.GetMyDetails` toolbox to get the user's email (via OBO token)
2. **Classify role** — calls `ClassifierAgent-2` to determine if the user is a Requestor, Legal Expert, or Tax Expert
3. **Route message** — forwards the user's message to the appropriate specialist agent (`RequestorAgent-2`, `LegalAgent-2`, or `TaxAgent-2`)
4. **Email/OneDrive tools** — provides tools to search emails and OneDrive via `WorkIQMail` toolbox

Hosted toolbox requests must forward
`get_request_context().platform_headers()` from the AgentServer SDK alongside
the Foundry bearer token, on both `tools/list` and `tools/call`. The platform
call ID lets Foundry resolve the invoking user's delegated identity; the
container's managed-identity token alone does not provide that user context.
Resolve these headers for every invocation rather than caching them with tool
definitions. Never substitute a user-supplied email or object ID for trusted
platform context.

With the orchestrator dependencies installed, run the context regressions from
the repository root:

```powershell
python -m unittest discover -s src\orchestrator\tests -p test_toolbox_context.py -v
```

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

**Environment variables** (set in the orchestrator service's `environmentVariables` in [`azure.yaml`](azure.yaml)):
| Variable | Description |
|----------|-------------|
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | GPT model deployment name |
| `CLASSIFIER_AGENT_NAME` | Name of the classifier agent (default: `ClassifierAgent-2`) |
| `REQUESTOR_AGENT_NAME` | Name of the requestor agent (default: `RequestorAgent-2`) |
| `LEGAL_AGENT_NAME` | Name of the legal agent (default: `LegalAgent-2`) |
| `TAX_AGENT_NAME` | Name of the tax agent (default: `TaxAgent-2`) |
| `DKWORKIQ_TOOLBOX_NAME` | Base name for the four suffixed toolboxes (default: `DkWorkIQMail`) |

`FOUNDRY_PROJECT_ENDPOINT` is injected by the hosted platform. Do not declare it
in the service's environment variables: `FOUNDRY_*` names are reserved.
The current hosting SDK requires Responses protocol `2.0.0`, which supplies
trusted user and per-request call IDs; the legacy `1.0.0` declaration is not compatible.

**Deploy:**
```bash
azd deploy orchestrator
```

This builds the Docker image, pushes it to ACR via remote build, and creates a new agent version in Foundry.

**Current agent name:** `LegalTaxOrchestrator-3` (configured in [`azure.yaml`](azure.yaml)).
The private-Cosmos migration deploys MCP independently; redeploy the hosted
orchestrator separately using the command above.

---

## Infrastructure (`infra/`)

Provisioned via Bicep templates using `azd provision`.

| Template | Resources Created |
|----------|-------------------|
| `main.bicep` | Resource group, orchestrates modules and explicit deployment outputs |
| `cosmos.bicep` | Cosmos DB account + Users, Requests, Questions, Answers, and AuditLog containers |
| `network.bicep` | New VNet, dedicated subnets, Cosmos private endpoint, in-group private DNS zone and link |
| `containerapp.bicep` | New VNet-integrated Container Apps environment + MCP Server app |
| `acr-pull.bicep` | New MCP identity's AcrPull permission on the existing in-group registry |
| `deployer-cosmos-rbac.bicep` | Optional Cosmos data-plane RBAC when `deployerPrincipalId` is supplied; not enabled by the current parameter file |

**Provision:** follow [step 3](#3-validate-and-provision-private-cosmos-infrastructure),
then always complete [step 4](#4-deploy-mcp-and-verify-its-private-database-path)
to replace the bootstrap image and restore managed-identity registry pulls.

---

## Seed Data

Follow [step 5](#5-prepare-python-helpers-and-initial-user-roles). The script seeds
users only, requires Cosmos data-plane permissions **and** private connectivity,
and must not be rerun blindly against an existing database.

---

## Testing from Foundry Portal

1. Go to [Azure AI Foundry](https://ai.azure.com)
2. Navigate to your project → Agents → `LegalTaxOrchestrator-3`
3. Select the active version reported by `azd ai agent show orchestrator` and start a new playground conversation
4. Follow [step 10](#10-verify-the-complete-application) to verify actual tool calls, identity, role, and business workflows

---

## Project Structure

```
LegalTaxAssistant/
├── azure.yaml                     # azd service definitions
├── Dockerfile                     # MCP Server container image
├── infra/                         # Bicep infrastructure templates
│   ├── main.bicep
│   ├── cosmos.bicep
│   ├── network.bicep
│   ├── containerapp.bicep
│   ├── acr-pull.bicep
│   ├── deployer-cosmos-rbac.bicep
│   └── tests/
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
│   │   ├── requirements.txt
│   │   └── tests/
│   ├── seed_data.py
│   └── tests/
└── architecture/
    └── architecture-diagram.md
```
