# Legal & Tax Assistant - Solution Architecture

## Overview

The Legal & Tax Assistant is a multi-agent AI system deployed on **Microsoft Foundry** that helps organizations manage legal and tax question workflows. It uses a hosted agent orchestrator pattern with specialized prompt agents connected to MCP servers for data operations.

## Architecture Diagram

```mermaid
graph TB
    %% Styling
    classDef user fill:#0078D4,stroke:#005A9E,color:#fff,stroke-width:2px
    classDef foundry fill:#5C2D91,stroke:#3B1D6E,color:#fff,stroke-width:2px
    classDef hosted fill:#0063B1,stroke:#004578,color:#fff,stroke-width:2px
    classDef prompt fill:#00B7C3,stroke:#008B94,color:#fff,stroke-width:2px
    classDef mcp fill:#107C10,stroke:#0B5A0B,color:#fff,stroke-width:2px
    classDef data fill:#D83B01,stroke:#A52C01,color:#fff,stroke-width:2px
    classDef infra fill:#767676,stroke:#4A4A4A,color:#fff,stroke-width:2px

    %% User Layer
    User["👤 User<br/>(Requestor / Legal Expert / Tax Expert)"]:::user

    %% Microsoft Foundry Platform
    subgraph Foundry["☁️ Microsoft Foundry Platform"]
        direction TB
        
        subgraph HostedAgent["🤖 Hosted Agent Container"]
            Orchestrator["LegalTaxOrchestrator<br/>(Hosted Agent)<br/>ResponsesHostServer<br/>agent_framework + FoundryChatClient"]:::hosted
        end

        subgraph PromptAgents["📋 Prompt Agents (Foundry-managed)"]
            Classifier["ClassifierAgent<br/>User Role Classification"]:::prompt
            Requestor["RequestorAgent<br/>Create & Manage Requests"]:::prompt
            Legal["LegalAgent<br/>Answer Legal Questions"]:::prompt
            Tax["TaxAgent<br/>Answer Tax Questions"]:::prompt
        end
    end

    %% MCP Server Layer
    subgraph ACA["Azure Container Apps"]
        MCP["🔧 MCP Server<br/>(FastMCP - LegalTaxAssistantTools)<br/>Streamable HTTP Transport"]:::mcp
    end

    %% Data Layer
    subgraph DataLayer["Azure Cosmos DB"]
        Users[(Users)]:::data
        Requests[(Requests)]:::data
        Questions[(Questions)]:::data
        AuditLog[(AuditLog)]:::data
    end

    %% Identity
    EntraID["🔐 Microsoft Entra ID<br/>DefaultAzureCredential"]:::infra

    %% Connections
    User -->|"Chat (Responses Protocol)"| Orchestrator
    Orchestrator -->|"1. Identify & Classify"| Classifier
    Orchestrator -->|"2a. Route Requestors"| Requestor
    Orchestrator -->|"2b. Route Legal Experts"| Legal
    Orchestrator -->|"2c. Route Tax Experts"| Tax
    
    Classifier -->|"MCP: get_user_role"| MCP
    Requestor -->|"MCP: create_request,<br/>add_questions, send_request"| MCP
    Legal -->|"MCP: get_assigned_questions,<br/>submit_answer"| MCP
    Tax -->|"MCP: get_assigned_questions,<br/>submit_answer"| MCP

    MCP -->|"CRUD Operations"| Users
    MCP -->|"CRUD Operations"| Requests
    MCP -->|"CRUD Operations"| Questions
    MCP -->|"Audit Trail"| AuditLog

    EntraID -.->|"RBAC & Auth"| Orchestrator
    EntraID -.->|"Managed Identity"| MCP
```

## Component Details

| Component | Type | Description |
|-----------|------|-------------|
| **LegalTaxOrchestrator** | Hosted Agent (Container) | Python-based orchestrator using Microsoft Agent Framework + FoundryChatClient. Routes users to specialist agents based on role. |
| **ClassifierAgent** | Prompt Agent | Identifies user role (Requestor/LegalExpert/TaxExpert) via MCP tool lookup. |
| **RequestorAgent** | Prompt Agent | Handles request creation, question categorization, and submission workflows. |
| **LegalAgent** | Prompt Agent | Enables legal experts to view assigned questions and submit answers. |
| **TaxAgent** | Prompt Agent | Enables tax experts to view assigned questions and submit answers. |
| **MCP Server** | Azure Container App | FastMCP server exposing CRUD tools over Streamable HTTP transport. |
| **Azure Cosmos DB** | NoSQL Database | Stores Users, Requests, Questions, and AuditLog collections. |
| **Microsoft Entra ID** | Identity Provider | Provides RBAC and managed identity authentication. |

## Data Flow

1. **User** sends a chat message via the Responses Protocol
2. **Orchestrator** identifies the user (via WorkIQ Toolbox) and classifies their role using ClassifierAgent
3. Based on role, the message is routed to the appropriate specialist agent
4. Specialist agents call **MCP tools** to perform operations (create requests, assign questions, submit answers)
5. MCP Server performs **CRUD operations** on Azure Cosmos DB
6. All operations are logged in the **AuditLog** collection
