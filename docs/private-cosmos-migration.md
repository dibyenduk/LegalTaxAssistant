# Private Cosmos migration

## Scope and approval

Live provisioning and MCP deployment have been approved after local validation.
The deployment sections below describe the staged rollout and required checks.

Use subscription `e45a11d6-bb7b-4f12-bb15-5c809203c616`, resource group
`rg-legaltaxassist0428`, and region `westus3`.

All customer-managed migration resources are in this resource group. Do not reuse
or link the Cosmos private DNS zone in `rg-cosmos-workshop`. Azure Container Apps
can create provider-managed infrastructure in its own managed resource group;
that is platform infrastructure, not an external shared application dependency.

## Architecture

### Verified rollout

The approved deployment completed on 2026-11-13 (UTC):

- MCP endpoint: https://ca-mcp-private-jvtju6jxst6a6.orangedesert-90bb7ddb.westus3.azurecontainerapps.io/sse
- Environment: `cae-mcp-private-jvtju6jxst6a6`; app: `ca-mcp-private-jvtju6jxst6a6`.
- Private endpoint `pe-cosmos-jvtju6jxst6a6` is Approved. The new in-group DNS zone
  has account/region records `10.97.2.4` and `10.97.2.5`.
- In-container DNS resolved the normal Cosmos hostname to `10.97.2.4`;
  managed-identity read returned a Users count of 3.
- HTTPS health returned 200. SSE exposed 12 tools, and a read-only role lookup
  returned the expected not-found result for a synthetic address.
- Latest prompt-agent versions: Classifier 9, Requestor 13, Legal 9, Tax 9.
  All four point to the new endpoint. Foundry classifier invocation executed
  an MCP call and returned `Unknown` for the synthetic address.
- Unconnected public Cosmos access was rejected with HTTP 403. Public access
  and local authentication remain disabled; failover and TLS 1.2 are preserved.
- Legacy app/environment and previous prompt-agent versions remain available.
  Previous versions were Classifier 8, Requestor 12, Legal 8, Tax 8.
- Hosted orchestrator configuration was migrated, but its deployment was not changed.
  Evaluation-suite generation was deferred at the user's request.

### Subsequent orchestrator redeployment

With separate user approval, `LegalTaxOrchestrator-3` version **40** was deployed
and verified active on **1 CPU / 2 GiB**, using Responses protocol **2.0.0**.
The smaller 0.25 CPU tier rejected the artifact size, so the user approved the
larger tier after cache removal alone was insufficient.

The existing Foundry project now has a `legal-tax-acr` ContainerRegistry
connection to the in-group registry, and its system identity has resource-scoped
AcrPull. Local azd project metadata was corrected to the selected northcentralus
project. The orchestrator image excludes pip build caches and local-only files.

Do not explicitly configure platform-reserved `FOUNDRY_*` or `AGENT_*`
environment variables. The runtime injects `FOUNDRY_PROJECT_ENDPOINT`.
The current hosting SDK needs protocol 2.0.0 for trusted user/call context.

Fresh-session health invocation succeeded, and an actual `classify_user` call for
a synthetic unknown address delegated successfully through the updated prompt
agent/MCP path and returned `Unknown`. No business data was changed. The three
test sessions were stopped; WorkIQ/OBO and submission workflows were not tested.
The MCP/private-network deployment was not reprovisioned or redeployed.

```text
Existing Foundry prompt agents
             |
        Public HTTPS /sse
             |
New MCP Container App (system-assigned identity)
             |
New workload-profiles ACA environment
             |
New VNet: 10.97.0.0/16
  container-apps:    10.97.0.0/23 (delegated)
  private-endpoints: 10.97.2.0/24 (not delegated)
             |
Cosmos Sql private endpoint + DNS zone group
             |
Existing Cosmos DB account, database, and five containers
```

The new DNS zone is `privatelink.documents.azure.com`, with a link only to this
application VNet. The normal Cosmos endpoint remains unchanged; do not put a
private IP or `privatelink` hostname in application configuration.

The new environment and app use `cae-mcp-private-<resourceToken>` and
`ca-mcp-private-<resourceToken>`. The old environment and app remain intact.
The existing in-group Log Analytics workspace and registry are reused.

MCP HTTPS ingress remains public. This migration does not add endpoint
authentication, private Foundry networking, Blob Storage, VPN, VNet peering, or
Teams integration. Authentication and backend authorization remain separate
release requirements; private Cosmos connectivity does not secure public MCP.

## Local checks

From the repository root in PowerShell 7:

```powershell
pwsh -File .\infra\tests\Test-PrivateCosmos.ps1
git diff --check
```

The infrastructure test compiles Bicep and checks subnet separation, new resource
names, private endpoint targeting, in-group DNS, managed identity, RBAC, retained
Cosmos containers and partition keys, and explicit azd service targeting. It
does not deploy resources or prove live connectivity.

The MCP service requires the version 1 SDK (`mcp<2`): version 2 removed the
`FastMCP` import used by this application. The root `.dockerignore` excludes local
virtual environments, Git metadata, and local azd settings from remote builds.

## Prepare for an approved deployment

1. Confirm Azure CLI and azd are using the approved subscription and environment.
2. Confirm the new address ranges do not overlap future corporate connections.
3. Check current quotas, policies, and deployer rights. ARM role assignments
   require suitable role-assignment permissions in addition to resource creation.
4. Record the old MCP hostname and image in a secure operational record for
   reference. Do not delete the old app, environment, or registry.
5. Use the existing registry in the application resource group:

```powershell
azd env select legaltaxassist0428
azd env set AZURE_CONTAINER_REGISTRY_NAME acrjvtju6jxst6a6
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT acrjvtju6jxst6a6.azurecr.io
```

These are local azd settings. The registry name must refer to an existing registry
in the application resource group using classic registry RBAC, as verified for
this registry. Do not substitute an external/shared registry without changing
the role-assignment module's scope. The project-wide registry setting also
affects future orchestrator image builds; this migration does not deploy the
orchestrator.

The orchestrator deployment definition now lives directly in its
[azure.yaml](../azure.yaml) service, using `kind`, `protocols`,
`container.resources`, and `environmentVariables`. Its legacy
[agent.yaml](../src/orchestrator/agent.yaml) and
[agent.manifest.yaml](../src/orchestrator/agent.manifest.yaml) are retained for
reference, not used as the current azd runtime definition. No hosted orchestrator
deployment is included in this migration; deploy only `mcp-server`.

## Provision and deploy only after approval

Use incremental deployment (azd's default). Do not use complete mode or deployment
stacks that delete resources omitted from the template.

```powershell
azd provision
```

This keeps the existing Cosmos account and data, explicitly disables public
access and local authentication, creates the new networking resources and ACA
app, and grants the new identity Cosmos data access and registry AcrPull.
Provisioning does not update Foundry prompt agents.

The app initially uses a public placeholder image so creating the identity does
not require an ACR role that has not propagated yet. Confirm AcrPull propagation
before deploying the real image, then explicitly configure the app's
managed-identity registry connection. Do not rely on azd to create that connection.
Provisioning is not a successful MCP rollout by itself;
always deploy the real image after provisioning, including on subsequent runs.

```powershell
$rg = azd env get-value AZURE_RESOURCE_GROUP
$app = azd env get-value AZURE_CONTAINER_APP_NAME
$principal = azd env get-value AZURE_CONTAINER_APP_PRINCIPAL_ID
$registryId = az acr show --resource-group $rg --name acrjvtju6jxst6a6 --query id -o tsv
az role assignment list --scope $registryId --query "[?principalId=='$principal'].{role:roleDefinitionName,scope:scope}" -o table

az containerapp registry set --resource-group $rg --name $app --server acrjvtju6jxst6a6.azurecr.io --identity system
azd deploy mcp-server
```

The explicit `resourceName` setting in [azure.yaml](../azure.yaml) prevents azd
from selecting the old app even though it retains an `azd-service-name` tag.
`AZURE_CONTAINER_APP_NAME` must come from the new provisioning outputs; do not set
it to the legacy app.

## Verify before agent cutover

Inspect the resources, all in the approved application resource group:

```powershell
$cosmos = azd env get-value AZURE_COSMOS_ACCOUNT_NAME
$pe = azd env get-value AZURE_COSMOS_PRIVATE_ENDPOINT_NAME
$vnet = azd env get-value AZURE_VNET_NAME
$environment = azd env get-value AZURE_CONTAINER_APPS_ENVIRONMENT_NAME

az cosmosdb show --resource-group $rg --name $cosmos --query "{publicNetworkAccess:publicNetworkAccess,disableLocalAuth:disableLocalAuth}" -o json
az network private-endpoint show --resource-group $rg --name $pe --query "privateLinkServiceConnections[].privateLinkServiceConnectionState.status" -o tsv
az network private-dns link vnet list --resource-group $rg --zone-name privatelink.documents.azure.com --query "[].{vnet:virtualNetwork.id,registration:registrationEnabled}" -o table
az network private-dns record-set a list --resource-group $rg --zone-name privatelink.documents.azure.com -o table
az containerapp env show --resource-group $rg --name $environment --query properties.vnetConfiguration -o json
az cosmosdb sql role assignment list --resource-group $rg --account-name $cosmos --query "[?principalId=='$principal'].{role:roleDefinitionId,scope:scope}" -o table

$fqdn = azd env get-value AZURE_CONTAINER_APP_FQDN
Invoke-RestMethod "https://$fqdn/health"
```

Expected: Cosmos public access Disabled, local authentication disabled, endpoint
Approved, DNS linked to the new VNet, and Cosmos RBAC for the new app identity.
`/health` proves process liveness only, not database access.

Open a shell in the new Linux container:

```powershell
az containerapp exec --resource-group $rg --name $app --command /bin/sh
```

Run this command inside that container (Linux shell quoting):

```sh
python -c 'import os,socket,ipaddress; from urllib.parse import urlparse; from mcp_server.cosmos_client import CosmosDBClient; host=urlparse(os.environ["COSMOS_ENDPOINT"]).hostname; addresses={entry[4][0] for entry in socket.getaddrinfo(host,443)}; print("Cosmos DNS:",addresses); assert addresses and all(ipaddress.ip_address(address).is_private for address in addresses); print("Users count:",CosmosDBClient().query_items("Users","SELECT VALUE COUNT(1) FROM c"))'
```

Require private DNS addresses matching the endpoint records and a successful
read using the managed identity. This is read-only and does not seed users.
Also check that data-plane access from an unconnected public client remains
blocked. Local seed scripts now need an approved private network path and DNS.

## Explicit prompt-agent cutover

Only after the preceding checks succeed, provision new prompt-agent versions
pointing at the new `/sse` endpoint. Use a configured Python environment with
the agent provisioning dependencies:

```powershell
$env:PYTHONPATH = 'src'
$project = azd env get-value FOUNDRY_PROJECT_ENDPOINT
$model = azd env get-value MODEL_DEPLOYMENT_NAME
python -m agents.provision_agents --project-endpoint $project --model $model --mcp-server-url "https://$fqdn/sse"
```

Verify all four agents and then the orchestrator's role classification, request
creation, assignment, answer submission, and final request submission. Never
interpret a health response or a warning from the provisioning script as proof
that these data operations work.

## Failure handling

- DNS failure: inspect the new zone's A records, zone group, and VNet link. Do not
  reuse the zone in another resource group or hard-code a private IP.
- Cosmos 403: distinguish network denial from missing Cosmos data-plane RBAC;
  verify the new app's identity, not the legacy identity.
- Image-pull failure: verify AcrPull propagation and azd's managed-identity
  registry connection before retrying.
- Leave prompt agents unchanged when validation fails. A failed manual cutover
  can leave agent versions mixed; verify each agent before declaring success.
- The old app has no private Cosmos path. Keeping it does not make it a working
  database rollback target. Do not reopen Cosmos public access as a workaround.

## WorkIQ connection recovery

The existing toolboxes in `prj-foundry-demo-ncus-dev-001` referenced four missing
project connections. This produced `Connection WorkIQUser can't be found in this
workspace`; the other three toolboxes failed with the corresponding connection
names. This was independent of Cosmos networking and user roles.

With user approval, all four connections were restored on 2026-11-13 (UTC):

| Connection | Existing toolbox | Agent 365 server path | Catalog object ID |
|---|---|---|---|
| WorkIQUser | DkWorkIQMail-User | mcp_MeServer | microsoft-365-user-profile-mcp-frontier |
| WorkIQMail | DkWorkIQMail-Mail | mcp_MailTools | microsoft-outlook-mail-mcp-frontier |
| WorkIQOneDrive | DkWorkIQMail-OneDrive | mcp_OneDriveRemoteServer | microsoft-onedrive-mcp-frontier |
| WorkIQCopilot | DkWorkIQMail-Copilot | mcp_M365Copilot | microsoft-copilot-chat-frontier |

Each connection uses the catalog-supported `UserEntraToken` authentication mode
and audience `ea9ffc3e-8a23-4a7d-836d-234d7c7565c1`. Targets are
`https://agent365.svc.cloud.microsoft/agents/servers/<server-path>`.
Catalog metadata includes `type=catalog_MCP` and
`toolEntityId=azureml://location/eastus/apiCenter/registry-prod-bl/type/tools/objectId/<catalog-object-id>/version/1`.
Use the current catalog metadata when restoring these again; do not assume the
separate `legal-tax-workiq` connection is interchangeable with these servers.

After restoration, MCP `tools/list` succeeded for all four existing toolboxes
(5 User, 22 Mail, 19 OneDrive, and 1 Copilot tools). A direct read-only
`WorkIQUser___GetMyDetails` invocation also succeeded using the signed-in CLI
identity. Hosted-agent end-user OBO, mail/file operations, and submissions were
not exercised by this recovery check. No orchestrator redeployment, toolbox
version change, or Cosmos change was needed.

### Hosted delegated-identity follow-up

The direct CLI identity check above did not validate hosted caller-context
forwarding. A later hosted invocation reported that user identity authentication
requires a delegated Microsoft Entra user context. The raw MCP client sent its
workload bearer token but omitted the platform headers that let Foundry resolve
the original caller.

The orchestrator now forwards the AgentServer SDK's
`get_request_context().platform_headers()` on discovery and tool calls, resolving
them afresh for every tool invocation even when definitions are cached. It does
not fabricate user/tenant identifiers or replace the delegated authentication
mode.

Version **41** was deployed and verified active on 2026-11-13 (UTC), retaining
1 CPU / 2 GiB and Responses 2.0.0. Four regression tests passed against the
hosted Linux dependencies, including all four namespaces and caller-context
changes between requests. A fresh hosted conversation actually executed
`get_current_user` and `classify_user`, returning the signed-in account and its
expected `LegalExpert` role. Runtime logs confirmed both calls without the
authentication error. The smoke-test session was stopped.

Start a new conversation targeting version 41 or later; existing sessions can
remain pinned to older code. Mail/file operations and write/submission workflows
remain untested. No MCP, Cosmos, toolbox, or connection changes were made by
this orchestrator-only follow-up.
