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

# ---------------------------------------------------------------------------
# OpenTelemetry — custom spans only (Option B)
# The Foundry agent server runtime already configures its own TracerProvider
# and exports to App Insights. We only grab a tracer to add custom spans.
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("legal-tax-orchestrator", "1.0.0")
except ImportError:
    # Fallback: create no-op implementations so span code still runs
    import contextlib
    from types import SimpleNamespace

    class _NoOpSpan:
        def set_attribute(self, *a, **kw): pass
        def set_status(self, *a, **kw): pass
        def record_exception(self, *a, **kw): pass

    class _NoOpTracer:
        @contextlib.contextmanager
        def start_as_current_span(self, *a, **kw):
            yield _NoOpSpan()

    tracer = _NoOpTracer()
    trace = SimpleNamespace(StatusCode=SimpleNamespace(ERROR=2, OK=0))

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

# Stop-words to remove when auto-fixing $search queries
_SEARCH_STOP_WORDS = {
    "do", "we", "need", "to", "update", "our", "the", "a", "an", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "does", "did",
    "will", "would", "could", "should", "may", "might", "shall", "can", "get",
    "check", "find", "any", "about", "from", "with", "for", "of", "in", "on",
    "at", "by", "my", "your", "their", "its", "this", "that", "these", "those",
    "what", "how", "when", "where", "which", "who", "whom", "there", "here",
    "new", "comply", "if", "it", "not", "no", "yes", "or", "and", "but", "so",
}


def _fix_search_query(query_parameters: str) -> str:
    """Auto-fix $search queries: extract keywords and join with OR.

    If the agent passes a long sentence as $search (common failure mode),
    this strips stop-words and joins remaining nouns with OR for broad matching.
    Leaves $filter and other query types untouched.
    """
    import re
    logger.info("_fix_search_query input: %r", query_parameters[:150])

    # Try multiple quote patterns - the model may use different quoting
    match = re.search(r'\$search="([^"]*)"', query_parameters)
    if not match:
        match = re.search(r"\$search='([^']*)'", query_parameters)
    if not match:
        # Try matching escaped quotes (JSON-style)
        match = re.search(r'\$search=\\"([^\\]*)\\"', query_parameters)
    if not match:
        # Try without quotes at all (just grab everything after $search=)
        match = re.search(r'\$search=(.+?)(?:&|$)', query_parameters)
    if not match:
        logger.info("_fix_search_query: no $search pattern found, returning unchanged")
        return query_parameters

    search_value = match.group(1).strip('"').strip("'")
    logger.info("_fix_search_query matched: '%s'", search_value)

    # If it already has OR or field targeting (subject:, from:), leave it alone
    if " OR " in search_value or ":" in search_value:
        logger.info("_fix_search_query: already has OR or field targeting, skipping")
        return query_parameters

    # If it's already short (1-2 words), leave it alone
    words = search_value.split()
    if len(words) <= 2:
        logger.info("_fix_search_query: only %d words, skipping", len(words))
        return query_parameters

    # Extract meaningful keywords (remove stop-words and short words)
    keywords = [w for w in words if w.lower().rstrip("?.,!") not in _SEARCH_STOP_WORDS and len(w) > 2]

    # Keep at most 4 keywords, join with OR
    keywords = keywords[:4] if keywords else words[:2]
    fixed_search = " OR ".join(keywords)

    # Replace in the original query string
    fixed_query = query_parameters[:match.start(1)] + fixed_search + query_parameters[match.end(1):]
    # Strip any leftover quotes around the OR expression and re-wrap
    fixed_query = re.sub(r'\$search="?([^"]*)"?', r'$search="\1"', fixed_query)
    logger.info("Auto-fixed $search: '%s' -> '%s'", search_value, fixed_search)
    logger.info("_fix_search_query output: %r", fixed_query[:150])
    return fixed_query


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
    with tracer.start_as_current_span(
        "toolbox_mcp_call",
        attributes={
            "toolbox.tool_name": tool_name,
            "toolbox.arguments": json.dumps(arguments)[:500],
            "gen_ai.operation.name": "execute_tool",
        },
    ) as span:
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
                error_msg = f"Error from toolbox: {err.get('message', str(err))}"
                span.set_attribute("toolbox.error", error_msg)
                span.set_status(trace.StatusCode.ERROR, error_msg)
                return error_msg

            result = data.get("result", {})
            content_items = result.get("content", [])
            texts = []
            for item in content_items:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict) and "reply" in parsed:
                            span.set_attribute("toolbox.response_preview", parsed["reply"][:200])
                            return parsed["reply"]
                        texts.append(text[:4000])
                    except (json.JSONDecodeError, TypeError):
                        texts.append(text[:4000])

            output = "\n".join(texts) if texts else "(no content returned)"
            span.set_attribute("toolbox.response_preview", output[:200])
            return output

        except httpx.HTTPStatusError as e:
            logger.error("Toolbox HTTP error: %s %s", e.response.status_code, e.response.text[:500])
            span.set_status(trace.StatusCode.ERROR, f"HTTP {e.response.status_code}")
            span.set_attribute("toolbox.http_status", e.response.status_code)
            return f"Error calling email service: HTTP {e.response.status_code}"
        except Exception as e:
            logger.error("Toolbox call failed: %s", str(e))
            span.set_status(trace.StatusCode.ERROR, str(e))
            span.record_exception(e)
            return f"Error calling email service: {str(e)}"


# ---------------------------------------------------------------------------
# Helper — call a prompt agent via Responses API
# ---------------------------------------------------------------------------

def _call_agent(agent_name: str, message: str) -> str:
    """Call a Foundry prompt agent via the Responses API and return its text."""
    with tracer.start_as_current_span(
        "invoke_prompt_agent",
        attributes={
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": agent_name,
            "gen_ai.input.messages": json.dumps([{"role": "user", "content": message[:500]}]),
        },
    ) as span:
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
        result = "".join(text_parts) or "(no response)"
        span.set_attribute("gen_ai.output.messages", json.dumps([{"role": "assistant", "content": result[:500]}]))
        span.set_attribute("gen_ai.response.id", getattr(resp, "id", ""))
        return result


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
    with tracer.start_as_current_span(
        "classify_user",
        attributes={"user.email": user_email, "gen_ai.operation.name": "execute_tool"},
    ) as span:
        logger.info("classify_user called for %s", user_email)
        result = _call_agent(CLASSIFIER_AGENT, f"Look up the role for user: {user_email}")
        span.set_attribute("user.role_result", result[:200])
        return result


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
    with tracer.start_as_current_span(
        "route_to_requestor_agent",
        attributes={"gen_ai.operation.name": "execute_tool", "agent.target": REQUESTOR_AGENT},
    ):
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
    with tracer.start_as_current_span(
        "route_to_legal_agent",
        attributes={"gen_ai.operation.name": "execute_tool", "agent.target": LEGAL_AGENT},
    ):
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
    with tracer.start_as_current_span(
        "route_to_tax_agent",
        attributes={"gen_ai.operation.name": "execute_tool", "agent.target": TAX_AGENT},
    ):
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
    with tracer.start_as_current_span(
        "get_current_user",
        attributes={"gen_ai.operation.name": "execute_tool", "toolbox.tool": "WorkIQUser.GetMyDetails"},
    ):
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
    query_parameters: Annotated[str, "OData query parameters starting with '?'. For $search use OR between keywords: '?$search=\"vendor OR contracts OR privacy\"'. Can target fields: '?$search=\"subject:vendor OR body:privacy\"'. For filters: '?$filter=isRead eq false', '?$filter=receivedDateTime ge 2025-01-01T00:00:00Z&$top=25'"],
) -> str:
    """Search emails using OData query parameters against Microsoft Graph API.

    Faster than natural language search and has no indexing delay.
    CRITICAL for $search: Use OR between keywords for broad matching.
    Think: "What would the email SUBJECT line say?" and extract those nouns.
    Format: ?$search="word1 OR word2 OR word3"
    Example: For question about vendor contracts and data privacy, use:
      ?$search="vendor OR contracts OR privacy"
    NOT: ?$search="data privacy regulation" (AND logic, too restrictive)
    You can also target fields: subject:vendor OR body:privacy
    Use $filter for property-based filtering (isRead, receivedDateTime, etc.).
    Note: $search CANNOT be combined with $filter, $orderBy, or $skip.
    """
    # --- Auto-fix: if the model passed a long $search without OR, extract keywords ---
    logger.info("search_emails_query INPUT: %r", query_parameters[:150])
    query_parameters = _fix_search_query(query_parameters)
    logger.info("search_emails_query OUTPUT: %r", query_parameters[:150])
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


@tool
def search_m365_content(
    query: Annotated[str, "Natural language query to search across all M365 content (emails, attachments, OneDrive, SharePoint)"],
) -> str:
    """Search across all Microsoft 365 content using WorkIQ Copilot.

    Searches emails, email attachments, OneDrive files, and SharePoint
    documents in a single semantic query. Returns relevance-ranked results.
    Use this when the user wants to find information across files and documents,
    or doesn't know which source contains what they need.
    Slower than direct email search (up to 30s) but covers all sources.
    """
    logger.info("search_m365_content: %s", query[:100])
    return _call_toolbox_mcp("WorkIQCopilot.Search", {"message": query})


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

### M365 content requests → `search_m365_content`
When the user asks to search files, documents, OneDrive, SharePoint, or attachments:
- Use `search_m365_content` for broad semantic search across all M365 content

## Composite Workflow A: Answer Questions from Email

When the user explicitly asks to search their **email/inbox** for an answer:

0. **Get assigned questions first** — if you do NOT already know the question ID,
   call `route_to_legal_agent` or `route_to_tax_agent` with the expert's email
   and instruction "List assigned questions for [email]". This gives you the
   question ID(s) and text. If there's one question, proceed. If multiple,
   list them and ask the user which one they want to answer from email.
   REMEMBER the question ID(s) for step 4.
1. **Search emails (keyword first)** — call `search_emails_query` using OR
   between keywords so ANY matching word returns results.
   Think: "What would the email SUBJECT line say?" — pick those nouns.
   Format: `?$search="word1 OR word2 OR word3"`
   Use 2-4 keywords joined by OR. Drop verbs (update, check, get, need).
   Examples:
   - "Do we need to update vendor contracts for data privacy?" → `?$search="vendor OR contracts OR privacy"`
   - "What are the new tax filing deadlines?" → `?$search="tax OR filing OR deadlines"`
   - "Any emails about the merger?" → `?$search="merger"`
   If no results are returned, fall back to `search_emails` with a broader
   natural language query using more of the question text.
2. **Get full email** — call `get_email_message` with the most relevant match's
   message ID to retrieve the complete body.
3. **Draft an answer** — synthesize the email content into a clear, professional
   answer that directly addresses the assigned question. Do NOT just paste the
   raw email. Extract the relevant information, summarize it, and phrase it as
   a proper response to the question.
4. **Route to specialist with drafted answer** — call `route_to_legal_agent` or
   `route_to_tax_agent` with a message that includes:
   - The expert's email
   - The question ID (REQUIRED — from step 0)
   - Instruction: "Submit the following answer for question ID '[question_id]': [drafted answer text]"
   - The drafted answer text
   - Source attribution: "Based on email from [sender] dated [date] with subject '[subject]'"
   You MUST include the question ID. If you don't have it, go back to step 0.

## Composite Workflow B: Answer Questions from Files/M365 Content

When the user asks to search their **files, documents, OneDrive, SharePoint,
attachments**, or says something broad like "find the answer in my stuff" /
"check my documents":

0. **Get assigned questions first** — if you do NOT already know the question ID,
   call `route_to_legal_agent` or `route_to_tax_agent` with the expert's email
   and instruction "List assigned questions for [email]". This gives you the
   question ID(s) and text. If there's one question, proceed. If multiple,
   list them and ask the user which one they want to answer from files.
   REMEMBER the question ID(s) for step 3.
1. **Search M365 content** — call `search_m365_content` with key terms extracted
   from the question text.
2. **Draft an answer** — synthesize the returned content into a clear, professional
   answer that directly addresses the assigned question. Do NOT just paste the
   raw content. Extract the relevant information, summarize it, and phrase it as
   a proper response to the question.
3. **Route to specialist with drafted answer** — call `route_to_legal_agent` or
   `route_to_tax_agent` with a message that includes:
   - The expert's email
   - The question ID (REQUIRED — from step 0)
   - Instruction: "Submit the following answer for question ID '[question_id]': [drafted answer text]"
   - The drafted answer text
   - Source attribution: "Based on [document title/filename] from [source]"
   You MUST include the question ID. If you don't have it, go back to step 0.

### Choosing between Workflow A and B:
- User says "email", "inbox", "message from" → Workflow A
- User says "files", "documents", "OneDrive", "SharePoint", "attachments" → Workflow B
- User says "find the answer" (ambiguous) → Workflow B (broadest coverage)
- User provides their own answer text directly → Workflow C

Do NOT return raw content to the user. Always draft a proper answer first.
If no relevant content is found, inform the user and ask for clarification.

## Composite Workflow C: User Provides Their Own Answer

When the expert writes their own answer (not from email or files):

1. **Get assigned questions** — if you do NOT already know the question ID,
   call `route_to_legal_agent` or `route_to_tax_agent` with the expert's email
   and instruction "List assigned questions for [email]". If there's one question,
   proceed. If multiple, list them and ask which one they're answering.
2. **Confirm** — show the user's answer back and ask: "Submit this answer for
   question '[question text]'?" (ask ONCE only).
3. **Submit** — on confirmation, call the specialist agent with:
   "For expert [email]: Use submit_answer to submit the following answer
   for question_id '[question_id]'. Answer text: [user's answer text]"

## Submission Rules
- After drafting an answer, ask the user ONCE if they want to submit it.
- When the user confirms (says "yes", "submit", "correct", "go ahead", etc.),
  IMMEDIATELY call `route_to_legal_agent` or `route_to_tax_agent` with this
  EXACT message format (fill in the values from the conversation):

  "For expert [expert_email]: Use submit_answer to submit the following answer
  for question_id '[question_id]'. Answer text: [the full drafted answer text]"

  Do NOT call get_assigned_questions again. Do NOT re-list questions.
  Do NOT ask for confirmation again. Just submit with the above message.
- NEVER ask for confirmation more than once. One "yes" = submit now.
- If you already have the user's confirmation, do not re-display the answer
  or ask "are you sure?" — just submit it.
- You ALREADY KNOW the question_id and drafted answer from earlier in this
  conversation. Look back in the conversation history to find them.
  Do NOT tell the user "I can't find" the question — it's in YOUR OWN history.

### Batch Submission (same answer to multiple questions)
- If the user says "submit to all questions", "yes for all", "apply to all",
  or similar, submit the SAME drafted answer to ALL their assigned questions.
- Call the specialist agent ONCE PER question_id with the same answer text.
  Example: if user has question IDs q1, q2, q3 — make 3 separate calls:
  "For expert [email]: Use submit_answer for question_id 'q1'. Answer text: ..."
  "For expert [email]: Use submit_answer for question_id 'q2'. Answer text: ..."
  "For expert [email]: Use submit_answer for question_id 'q3'. Answer text: ..."
- Report back which submissions succeeded and which failed.

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
            search_m365_content,
        ],
        default_options={"store": True},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
