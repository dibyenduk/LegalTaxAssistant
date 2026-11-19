targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment used to generate resource names.')
param environmentName string

@description('Primary location for all resources.')
param location string

@description('Principal ID of the current deployer (for Cosmos RBAC). Set via azd or leave empty.')
param deployerPrincipalId string = ''

@description('Name of the existing container registry in the application resource group.')
param containerRegistryName string

@description('Address space for the new application VNet.')
param vnetAddressPrefix string = '10.97.0.0/16'

@description('Dedicated Container Apps subnet within the application VNet.')
param containerAppsSubnetPrefix string = '10.97.0.0/23'

@description('Private endpoint subnet within the application VNet.')
param privateEndpointSubnetPrefix string = '10.97.2.0/24'

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

module network 'network.bicep' = {
  name: 'privateCosmosNetwork'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    cosmosAccountName: cosmos.outputs.accountName
    vnetAddressPrefix: vnetAddressPrefix
    containerAppsSubnetPrefix: containerAppsSubnetPrefix
    privateEndpointSubnetPrefix: privateEndpointSubnetPrefix
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
    infrastructureSubnetId: network.outputs.containerAppsSubnetId
  }
}

module registryAccess 'acr-pull.bicep' = {
  name: 'mcpRegistryAccess'
  scope: rg
  params: {
    registryName: containerRegistryName
    principalId: containerApps.outputs.containerAppPrincipalId
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
output AZURE_COSMOS_ACCOUNT_NAME string = cosmos.outputs.accountName
output AZURE_CONTAINER_APP_NAME string = containerApps.outputs.containerAppName
output AZURE_CONTAINER_APPS_ENVIRONMENT_NAME string = containerApps.outputs.environmentName
output AZURE_CONTAINER_APP_FQDN string = containerApps.outputs.containerAppFqdn
output AZURE_CONTAINER_APP_PRINCIPAL_ID string = containerApps.outputs.containerAppPrincipalId
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistryName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registryAccess.outputs.loginServer
output AZURE_VNET_NAME string = network.outputs.vnetName
output AZURE_COSMOS_PRIVATE_ENDPOINT_NAME string = network.outputs.privateEndpointName
output AZURE_COSMOS_PRIVATE_DNS_ZONE_NAME string = network.outputs.privateDnsZoneName
