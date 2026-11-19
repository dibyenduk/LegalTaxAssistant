$ErrorActionPreference = 'Stop'
$checks = 0

function Assert-Contract {
    param([bool] $Condition, [string] $Message)
    if (-not $Condition) {
        throw $Message
    }
    $script:checks++
}

$infraRoot = Split-Path $PSScriptRoot -Parent
$repoRoot = Split-Path $infraRoot -Parent
$compiled = & az bicep build --file (Join-Path $infraRoot 'main.bicep') --stdout --only-show-errors
if ($LASTEXITCODE -ne 0) {
    throw 'Bicep compilation failed.'
}
$template = ($compiled -join "`n") | ConvertFrom-Json -AsHashtable

function Get-ModuleTemplate {
    param([string] $Name)
    $modules = @($template.resources | Where-Object { $_.type -eq 'Microsoft.Resources/deployments' -and $_.name -eq $Name })
    Assert-Contract ($modules.Count -eq 1) "Expected exactly one module named $Name."
    return $modules[0].properties.template
}

function Get-Resource {
    param([hashtable] $Template, [string] $Type)
    $resources = @($Template.resources | Where-Object { $_.type -eq $Type })
    Assert-Contract ($resources.Count -eq 1) "Expected exactly one $Type resource."
    return $resources[0]
}

$cosmos = Get-ModuleTemplate 'cosmos'
$account = Get-Resource $cosmos 'Microsoft.DocumentDB/databaseAccounts'
Assert-Contract ($account.properties.publicNetworkAccess -eq 'Disabled') 'Cosmos public access must remain disabled.'
Assert-Contract ($account.properties.disableLocalAuth -eq $true) 'Cosmos local authentication must remain disabled.'
Assert-Contract ($account.properties.enableAutomaticFailover -eq $true) 'Preserve existing Cosmos automatic failover.'
Assert-Contract ($account.properties.minimalTlsVersion -eq 'Tls12') 'Preserve the Cosmos TLS 1.2 minimum.'
Assert-Contract ($account.properties.defaultIdentity -eq 'FirstPartyIdentity') 'Preserve the Cosmos default identity.'
Assert-Contract ($account.properties.analyticalStorageConfiguration.schemaType -eq 'WellDefined') 'Preserve the Cosmos analytical schema configuration.'
Assert-Contract ($cosmos.variables.cosmosAccountName.Contains('cosmos-')) 'The existing Cosmos naming convention must be preserved.'
$containers = @($cosmos.resources | Where-Object { $_.type -eq 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers' })
Assert-Contract ($containers.Count -eq 5) 'All five Cosmos containers must be preserved.'
foreach ($container in $containers) {
    $expectedKeys = @{
        Users = '/email'
        Requests = '/requestorEmail'
        Questions = '/requestId'
        Answers = '/questionId'
        AuditLog = '/requestId'
    }
    $name = $container.properties.resource.id
    Assert-Contract ($expectedKeys.ContainsKey($name)) "Unexpected Cosmos container: $name."
    Assert-Contract ($container.properties.resource.partitionKey.paths[0] -eq $expectedKeys[$name]) "Partition key changed for $name."
}

$network = Get-ModuleTemplate 'privateCosmosNetwork'
$vnet = Get-Resource $network 'Microsoft.Network/virtualNetworks'
Assert-Contract ($template.parameters.vnetAddressPrefix.defaultValue -eq '10.97.0.0/16') 'The approved VNet range must be the default.'
Assert-Contract ($template.parameters.containerAppsSubnetPrefix.defaultValue -eq '10.97.0.0/23') 'The approved ACA subnet must be the default.'
Assert-Contract ($template.parameters.privateEndpointSubnetPrefix.defaultValue -eq '10.97.2.0/24') 'The approved private endpoint subnet must be the default.'
Assert-Contract ($vnet.properties.subnets.Count -eq 2) 'Use separate ACA and private endpoint subnets.'
$acaSubnet = @($vnet.properties.subnets | Where-Object { $_.name -eq 'container-apps' })
$peSubnet = @($vnet.properties.subnets | Where-Object { $_.name -eq 'private-endpoints' })
Assert-Contract ($acaSubnet.Count -eq 1 -and $peSubnet.Count -eq 1) 'Both dedicated subnets must exist.'
Assert-Contract ($acaSubnet[0].properties.delegations[0].properties.serviceName -eq 'Microsoft.App/environments') 'ACA subnet delegation is required.'
Assert-Contract (-not $peSubnet[0].properties.ContainsKey('delegations')) 'The private endpoint subnet must not be delegated.'
Assert-Contract ($peSubnet[0].properties.privateEndpointNetworkPolicies -eq 'Disabled') 'Private endpoint subnet policies must be explicitly configured.'
$zone = Get-Resource $network 'Microsoft.Network/privateDnsZones'
Assert-Contract ($zone.name -eq 'privatelink.documents.azure.com') 'Create the Cosmos NoSQL private DNS zone.'
Assert-Contract ($zone.location -eq 'global') 'Private DNS zones must use global location.'
$link = Get-Resource $network 'Microsoft.Network/privateDnsZones/virtualNetworkLinks'
Assert-Contract ($link.properties.registrationEnabled -eq $false) 'Private endpoint DNS does not use VM auto-registration.'
Assert-Contract ($link.properties.virtualNetwork.id.Contains("resourceId('Microsoft.Network/virtualNetworks'")) 'The DNS link must target the application VNet.'
$endpoint = Get-Resource $network 'Microsoft.Network/privateEndpoints'
Assert-Contract ($endpoint.properties.subnet.id.Contains('private-endpoints')) 'The Cosmos endpoint must use the private endpoint subnet.'
Assert-Contract ($endpoint.properties.privateLinkServiceConnections[0].properties.groupIds[0] -eq 'Sql') 'Cosmos NoSQL requires the Sql group.'
Assert-Contract ($endpoint.properties.privateLinkServiceConnections[0].properties.privateLinkServiceId.Contains("resourceId('Microsoft.DocumentDB/databaseAccounts'")) 'The endpoint must target the in-group Cosmos account.'
$zoneGroup = Get-Resource $network 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups'
Assert-Contract ($zoneGroup.properties.privateDnsZoneConfigs[0].properties.privateDnsZoneId.Contains("resourceId('Microsoft.Network/privateDnsZones', 'privatelink.documents.azure.com')")) 'The endpoint must use the new in-group DNS zone.'
$networkModule = @($template.resources | Where-Object { $_.name -eq 'privateCosmosNetwork' })[0]
Assert-Contract ($networkModule.resourceGroup -eq "[variables('resourceGroupName')]") 'Networking must be deployed into the application resource group.'

$aca = Get-ModuleTemplate 'containerApps'
$environment = Get-Resource $aca 'Microsoft.App/managedEnvironments'
$app = Get-Resource $aca 'Microsoft.App/containerApps'
Assert-Contract ($aca.variables.containerAppsEnvName.Contains('cae-mcp-private-')) 'Create a new environment rather than modifying the legacy environment.'
Assert-Contract ($aca.variables.containerAppName.Contains('ca-mcp-private-')) 'Create a new MCP app rather than modifying the legacy app.'
Assert-Contract ($environment.properties.vnetConfiguration.infrastructureSubnetId -eq "[parameters('infrastructureSubnetId')]") 'The environment must use the application subnet.'
Assert-Contract ($environment.properties.vnetConfiguration.internal -eq $false) 'The approved environment keeps public ingress.'
Assert-Contract ($environment.properties.workloadProfiles[0].workloadProfileType -eq 'Consumption') 'Use a workload-profiles Consumption environment.'
Assert-Contract ($app.properties.workloadProfileName -eq 'Consumption') 'The app must select the Consumption profile.'
Assert-Contract ($app.properties.configuration.ingress.external -eq $true) 'Foundry must still reach MCP through public ingress.'
Assert-Contract ($app.properties.configuration.ingress.allowInsecure -eq $false) 'MCP ingress must require HTTPS.'
Assert-Contract ($app.properties.configuration.ingress.targetPort -eq 8080) 'Preserve the MCP server port.'
Assert-Contract ($app.identity.type -eq 'SystemAssigned') 'MCP must use managed identity.'
Assert-Contract (-not $app.properties.configuration.ContainsKey('registries')) 'Initial provisioning must not depend on registry pull before RBAC propagation.'
$cosmosRole = Get-Resource $aca 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments'
Assert-Contract ($cosmosRole.properties.principalId.Contains('identity.principalId')) 'Grant Cosmos access to the new app identity.'
$registry = Get-ModuleTemplate 'mcpRegistryAccess'
$acrRole = Get-Resource $registry 'Microsoft.Authorization/roleAssignments'
Assert-Contract ($registry.variables.acrPullRoleId -eq '7f951dda-4ed3-4680-a7ca-43fe172d538d') 'The new identity needs AcrPull.'
Assert-Contract ($acrRole.properties.principalType -eq 'ServicePrincipal') 'Managed identity role assignment must specify principal type.'
Assert-Contract (@($registry.resources | Where-Object { $_.type -eq 'Microsoft.ContainerRegistry/registries' }).Count -eq 0) 'Reuse the existing in-group registry rather than creating one.'
Assert-Contract ($template.outputs.ContainsKey('AZURE_CONTAINER_APP_NAME')) 'Export the explicit new azd deployment target.'
Assert-Contract ($template.outputs.ContainsKey('AZURE_CONTAINER_APP_PRINCIPAL_ID')) 'Export the new managed identity for verification.'
$azdConfig = Get-Content (Join-Path $repoRoot 'azure.yaml') -Raw
Assert-Contract ($azdConfig -match 'resourceName:\s*\$\{AZURE_CONTAINER_APP_NAME\}') 'azd must explicitly select the new app despite legacy tags.'
Assert-Contract ($azdConfig -notmatch 'postprovision:') 'Provisioning must not switch prompt agents before private connectivity is verified.'
$orchestratorConfig = ($azdConfig -split '    orchestrator:', 2)[1]
Assert-Contract ($orchestratorConfig -match 'kind:\s*hosted') 'The orchestrator runtime must be declared directly in azure.yaml.'
Assert-Contract ($orchestratorConfig -match 'language:\s*docker') 'Preserve container-based orchestrator deployment.'
Assert-Contract ($orchestratorConfig -match 'name:\s*LegalTaxOrchestrator-3') 'Preserve the deployed orchestrator name.'
Assert-Contract ($orchestratorConfig -match 'container:\s+resources:\s+cpu:\s*"1"\s+memory:\s*2Gi') 'Use the approved 1 CPU / 2 GiB orchestrator tier.'
Assert-Contract ($orchestratorConfig -match 'environmentVariables:') 'Preserve the orchestrator environment configuration.'
Assert-Contract ($orchestratorConfig -notmatch 'name:\s*(FOUNDRY_|AGENT_)') 'Hosted platform-reserved environment variables must not be declared.'
Assert-Contract ($orchestratorConfig -match 'protocol:\s*responses\s+version:\s*2\.0\.0') 'Current Foundry hosting requires Responses protocol 2.0.0 for trusted request context.'
$parameters = Get-Content (Join-Path $infraRoot 'main.parameters.json') -Raw | ConvertFrom-Json -AsHashtable
Assert-Contract ($parameters.parameters.containerRegistryName.value -eq '${AZURE_CONTAINER_REGISTRY_NAME}') 'Resolve the approved registry name from the local azd environment.'

Write-Host "Passed $checks private Cosmos infrastructure contract checks."
