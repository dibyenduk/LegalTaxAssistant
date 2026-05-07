@description('Location for all resources.')
param location string

@description('Unique token for resource naming.')
param resourceToken string

@description('Tags for all resources.')
param tags object

var cosmosAccountName = 'cosmos-${resourceToken}'
var databaseName = 'LegalTaxAssistantDB'

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: cosmosAccountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// Users container — partition key: /email
resource usersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'Users'
  properties: {
    resource: {
      id: 'Users'
      partitionKey: {
        paths: ['/email']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          { path: '/*' }
        ]
        compositeIndexes: [
          [
            { path: '/role', order: 'ascending' }
            { path: '/expertType', order: 'ascending' }
          ]
        ]
      }
    }
  }
}

// Requests container — partition key: /requestorEmail
resource requestsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'Requests'
  properties: {
    resource: {
      id: 'Requests'
      partitionKey: {
        paths: ['/requestorEmail']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          { path: '/*' }
        ]
        compositeIndexes: [
          [
            { path: '/requestorEmail', order: 'ascending' }
            { path: '/status', order: 'ascending' }
            { path: '/createdAt', order: 'descending' }
          ]
        ]
      }
    }
  }
}

// Questions container — partition key: /requestId
resource questionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'Questions'
  properties: {
    resource: {
      id: 'Questions'
      partitionKey: {
        paths: ['/requestId']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          { path: '/*' }
        ]
        compositeIndexes: [
          [
            { path: '/assignedTo', order: 'ascending' }
            { path: '/status', order: 'ascending' }
          ]
          [
            { path: '/requestId', order: 'ascending' }
            { path: '/status', order: 'ascending' }
          ]
        ]
      }
    }
  }
}

// Answers container — partition key: /questionId
resource answersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'Answers'
  properties: {
    resource: {
      id: 'Answers'
      partitionKey: {
        paths: ['/questionId']
        kind: 'Hash'
      }
    }
  }
}

// AuditLog container — partition key: /requestId for request-centric queries
resource auditLogContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'AuditLog'
  properties: {
    resource: {
      id: 'AuditLog'
      partitionKey: {
        paths: ['/requestId']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          { path: '/*' }
        ]
        compositeIndexes: [
          [
            { path: '/entityType', order: 'ascending' }
            { path: '/timestamp', order: 'descending' }
          ]
        ]
      }
      defaultTtl: 7776000  // 90 days retention
    }
  }
}

output accountEndpoint string = cosmosAccount.properties.documentEndpoint
output accountName string = cosmosAccount.name
