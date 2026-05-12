targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment used to generate resource names.')
param environmentName string

@description('Primary location for all resources.')
param location string

@description('Principal ID of the current deployer (for Cosmos RBAC). Set via azd or leave empty.')
param deployerPrincipalId string = ''

@description('Login server for the shared container registry (e.g. acr.azurecr.io).')
param containerRegistryLoginServer string = ''

var tags = {
  'azd-env-name': environmentName
}
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var resourceGroupName = 'rg-${environmentName}'

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module cosmos 'cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

module containerApps 'containerapp.bicep' = {
  name: 'containerApps'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    cosmosAccountEndpoint: cosmos.outputs.accountEndpoint
    cosmosAccountName: cosmos.outputs.accountName
    containerRegistryLoginServer: containerRegistryLoginServer
  }
}

// Grant Cosmos RBAC to deployer for local tooling (seed scripts, debugging)
module deployerCosmos 'deployer-cosmos-rbac.bicep' = if (!empty(deployerPrincipalId)) {
  name: 'deployerCosmosRbac'
  scope: rg
  params: {
    cosmosAccountName: cosmos.outputs.accountName
    principalId: deployerPrincipalId
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.accountEndpoint
output AZURE_CONTAINER_APP_FQDN string = containerApps.outputs.containerAppFqdn
output AZURE_CONTAINER_APP_PRINCIPAL_ID string = containerApps.outputs.containerAppPrincipalId
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerApps.outputs.containerRegistryEndpoint
