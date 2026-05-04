"""Legal & Tax Assistant Orchestrator — Hosted Agent.

Uses the Microsoft Agent Framework with FoundryChatClient and tool functions.
The orchestrator automatically identifies users via WorkIQUser toolbox (OBO token),
classifies their role via ClassifierAgent, and caches both for the session.
It then routes messages to the appropriate specialist prompt agent.

The DKWorkIQ Foundry Toolbox provides user identity (WorkIQUser) and email
(WorkIQMail) via direct MCP protocol calls wrapped in @tool functions.

Conversation state is persisted (store=True) so the user's identity and role
are remembered across turns without re-identification.

ResponsesHostServer wraps the agent for Foundry hosted deployment.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated

import httpx
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

# ---------------------------------------------------------------------------
# Configuration — platform-injected + agent.yaml declared env vars
# ---------------------------------------------------------------------------
MODEL_DEPLOYMENT_NAME = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME",
                                       os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o-mini"))
CLASSIFIER_AGENT = os.environ.get("CLASSIFIER_AGENT_NAME", "ClassifierAgent-2")
REQUESTOR_AGENT = os.environ.get("REQUESTOR_AGENT_NAME", "RequestorAgent-2")
LEGAL_AGENT = os.environ.get("LEGAL_AGENT_NAME", "LegalAgent-2")
TAX_AGENT = os.environ.get("TAX_AGENT_NAME", "TaxAgent-2")


# ---------------------------------------------------------------------------
# DKWorkIQ Toolbox — direct MCP calls wrapped in @tool functions
# ---------------------------------------------------------------------------

_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(_credential, "https://ai.azure.com/.default")


def _get_toolbox_url() -> str:
    """Build the toolbox MCP endpoint URL."""
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    toolbox_name = os.environ.get("DKWORKIQ_TOOLBOX_NAME", "DkWorkIQMail")
    return os.environ.get(
        "DKWORKIQ_TOOLBOX_ENDPOINT",
        f"{project_endpoint}/toolboxes/{toolbox_name}/mcp?api-version=v1",
    )


def _call_toolbox_mcp(tool_name: str, arguments: dict) -> str:
    """Call a tool on the DKWorkIQ toolbox via MCP protocol (JSON-RPC over HTTP).

    Uses synchronous httpx to keep @tool functions simple.
    Returns the text content from the MCP response or an error message.
    """
    url = _get_toolbox_url()
    headers = {
        "Authorization": f"Bearer {_token_provider()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Foundry-Features": "Toolboxes=V1Preview",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    logger.info("Calling toolbox MCP: %s with args: %s", tool_name, json.dumps(arguments)[:200])

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            err = data["error"]
            return f"Error from toolbox: {err.get('message', str(err))}"

        result = data.get("result", {})
        content_items = result.get("content", [])
        texts = []
        for item in content_items:
            if item.get("type") == "text":
                text = item.get("text", "")
                # Parse and extract just the reply if it's a large JSON blob
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and "reply" in parsed:
                        return parsed["reply"]
                    texts.append(text[:4000])  # Truncate large responses
                except (json.JSONDecodeError, TypeError):
                    texts.append(text[:4000])

        return "\n".join(texts) if texts else "(no content returned)"

    except httpx.HTTPStatusError as e:
        logger.error("Toolbox HTTP error: %s %s", e.response.status_code, e.response.text[:500])
        return f"Error calling email service: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error("Toolbox call failed: %s", str(e))
        return f"Error calling email service: {str(e)}"


# ---------------------------------------------------------------------------
# Helper — call a prompt agent via Responses API
# ---------------------------------------------------------------------------

def _call_agent(agent_name: str, message: str) -> str:
    """Call a Foundry prompt agent via the Responses API and return its text."""
    from azure.ai.projects import AIProjectClient
    client = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )
    openai = client.get_openai_client()
    resp = openai.responses.create(
        model=MODEL_DEPLOYMENT_NAME,
        input=message,
        extra_body={
            "agent_reference": {"name": agent_name, "type": "agent_reference"}
        },
    )
    text_parts: list[str] = []
    for item in getattr(resp, "output", []):
        if getattr(item, "type", "") == "message":
            for part in getattr(item, "content", []):
                if getattr(part, "type", "") == "output_text":
                    text_parts.append(getattr(part, "text", ""))
    return "".join(text_parts) or "(no response)"


# ---------------------------------------------------------------------------
# Tool functions — invoked automatically by the Agent when the model decides
# ---------------------------------------------------------------------------

@tool
def classify_user(
    user_email: Annotated[str, "The email address of the user to classify"],
) -> str:
    """Classify a user by their email address.

    Calls the ClassifierAgent which uses the LegalTaxTools MCP server
    to look up the user's role (Requestor, LegalExpert, TaxExpert).
    Returns the user's role and display name.
    """
    logger.info("classify_user called for %s", user_email)
    return _call_agent(CLASSIFIER_AGENT, f"Look up the role for user: {user_email}")


@tool
def route_to_requestor_agent(
    message: Annotated[str, "The full message/instruction to send to the RequestorAgent"],
) -> str:
    """Route a message to the RequestorAgent for handling requestor workflows.

    The RequestorAgent has access to the LegalTaxTools MCP server and can:
    - Create requests (create_request)
    - Add questions to requests (add_questions_to_request)
    - View request status (get_request_status)
    - List the user's requests (get_requests_by_user)
    - Submit completed requests (submit_request)

    Include the user's email and any relevant context in the message.
    """
    logger.info("route_to_requestor_agent: %s", message[:100])
    return _call_agent(REQUESTOR_AGENT, message)


@tool
def route_to_legal_agent(
    message: Annotated[str, "The full message/instruction to send to the LegalAgent"],
) -> str:
    """Route a message to the LegalAgent for handling legal expert workflows.

    The LegalAgent has access to the LegalTaxTools MCP server and can:
    - View assigned legal questions (get_assigned_questions)
    - Submit answers to legal questions (submit_answer)
    - Mark questions as submitted/finalized (mark_question_submitted)

    Include the expert's email and any relevant context in the message.
    """
    logger.info("route_to_legal_agent: %s", message[:100])
    return _call_agent(LEGAL_AGENT, message)


@tool
def route_to_tax_agent(
    message: Annotated[str, "The full message/instruction to send to the TaxAgent"],
) -> str:
    """Route a message to the TaxAgent for handling tax expert workflows.

    The TaxAgent has access to the LegalTaxTools MCP server and can:
    - View assigned tax questions (get_assigned_questions)
    - Submit answers to tax questions (submit_answer)
    - Mark questions as submitted/finalized (mark_question_submitted)

    Include the expert's email and any relevant context in the message.
    """
    logger.info("route_to_tax_agent: %s", message[:100])
    return _call_agent(TAX_AGENT, message)


# ---------------------------------------------------------------------------
# Toolbox tool wrappers — clean names (no dots) to avoid model API issues
# ---------------------------------------------------------------------------

@tool
def get_current_user() -> str:
    """Get the current signed-in user's profile information (email, display name, job title).

    Call this ONCE at the start of a conversation to identify who is talking.
    The result is cached in conversation history — do not call again in the
    same session.
    """
    logger.info("get_current_user called")
    return _call_toolbox_mcp("WorkIQUser.GetMyDetails", {
        "select": "displayName,mail,userPrincipalName,jobTitle"
    })


@tool
def search_emails(
    message: Annotated[str, "Natural language search query for finding emails (e.g., 'emails from John about the project', 'unread messages from last week')"],
) -> str:
    """Search a user's email inbox using natural language powered by Microsoft 365 Copilot.

    Use this for queries that require interpretation or relevance ranking.
    Can be slow (up to 30 seconds). For simple keyword/filter searches,
    use search_emails_query instead.
    """
    logger.info("search_emails: %s", message[:100])
    return _call_toolbox_mcp("WorkIQMail.SearchMessages", {"message": message})


@tool
def search_emails_query(
    query_parameters: Annotated[str, "OData query parameters starting with '?'. Examples: '?$search=\"from:alice subject:budget\"', '?$filter=isRead eq false', '?$filter=receivedDateTime ge 2025-01-01T00:00:00Z&$top=25'"],
) -> str:
    """Search emails using OData query parameters against Microsoft Graph API.

    Faster than natural language search and has no indexing delay.
    Use $search for keyword/KQL queries (from:, to:, subject:, cc:, bcc:).
    Use $filter for property-based filtering (isRead, receivedDateTime, etc.).
    Note: $search CANNOT be combined with $filter, $orderBy, or $skip.
    """
    logger.info("search_emails_query: %s", query_parameters[:100])
    return _call_toolbox_mcp("WorkIQMail.SearchMessagesQueryParameters", {
        "queryParameters": query_parameters,
        "preferTextBody": True,
    })


@tool
def get_email_message(
    message_id: Annotated[str, "The Graph message ID of the email to retrieve"],
) -> str:
    """Get the full content of a specific email message by its Graph message ID.

    Returns the complete email including body, headers, and attachments info.
    """
    logger.info("get_email_message: id=%s", message_id)
    return _call_toolbox_mcp("WorkIQMail.GetMessage", {"messageId": message_id})


# ---------------------------------------------------------------------------
# Orchestrator Agent
# ---------------------------------------------------------------------------

ORCHESTRATOR_INSTRUCTIONS = """\
You are the Legal & Tax Assistant orchestrator. You identify users automatically,
classify their role, cache both for the session, and route requests to the
appropriate specialist agent.

## First Message Workflow (user not yet identified)
1. **Identify the user** — call `get_current_user` to get their email and name
   from their signed-in session. Do NOT ask the user for their email.
2. **Classify the user** — call `classify_user` with the email to get their role
   (Requestor, LegalExpert, or TaxExpert).
3. **Remember both** — the user's email, name, and role are now known for the
   entire conversation. Do NOT call get_current_user or classify_user again.
4. **Greet the user** briefly with their name and role, then handle their request.

## Subsequent Messages (user already identified)
Skip steps 1-2. You already know the user's email and role from earlier in the
conversation. Route directly based on their role and intent.

## Routing by Role

### Requestor → `route_to_requestor_agent`
Include in the message:
- The user's email
- What they want to do (create request, add questions, check status, etc.)
- Any details they provided (question text, question types)

### LegalExpert → `route_to_legal_agent`
Include in the message:
- The expert's email
- What they want to do (view assigned questions, submit answer, etc.)
- Any details they provided (answer text, question ID)

### TaxExpert → `route_to_tax_agent`
Include in the message:
- The expert's email
- What they want to do (view assigned questions, submit answer, etc.)
- Any details they provided (answer text, question ID)

### Email requests → `search_emails` / `search_emails_query` / `get_email_message`
When the user asks about emails:
- Use `search_emails_query` for deterministic queries (keyword, date, sender filters)
- Use `search_emails` for natural language queries needing relevance ranking
- Use `get_email_message` to read a full message by ID

## Rules
- NEVER ask the user for their email — always use `get_current_user`.
- Call `get_current_user` and `classify_user` only ONCE per conversation.
- If `get_current_user` fails, ask the user for their email as a fallback.
- If the user is not found in the system, inform them politely.
- Always include the user's email when routing to specialist agents.
- Relay the specialist agent's response back to the user as-is.
- Be friendly and concise.
"""


def main() -> None:
    credential = DefaultAzureCredential()
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=MODEL_DEPLOYMENT_NAME,
        credential=credential,
    )

    agent = Agent(
        client=client,
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        tools=[
            get_current_user,
            classify_user,
            route_to_requestor_agent,
            route_to_legal_agent,
            route_to_tax_agent,
            search_emails,
            search_emails_query,
            get_email_message,
        ],
        default_options={"store": True},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
