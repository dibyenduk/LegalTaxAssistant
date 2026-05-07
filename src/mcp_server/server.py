"""MCP Server entry point for Legal Tax Assistant Tools."""

from __future__ import annotations

import json
import logging
import os

from mcp.server.fastmcp import FastMCP

from .cosmos_client import CosmosDBClient
from .tools import LegalTaxTools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server — disable DNS rebinding protection for cloud deployment
mcp = FastMCP(
    "LegalTaxAssistantTools",
    host="0.0.0.0",
    port=8080,
    transport_security={
        "enable_dns_rebinding_protection": False,
    },
)

# Lazy-init tools (created on first use so env vars are available)
_tools: LegalTaxTools | None = None


def get_tools() -> LegalTaxTools:
    global _tools
    if _tools is None:
        db = CosmosDBClient()
        _tools = LegalTaxTools(db)
    return _tools


# --- MCP Tool Registrations ---


@mcp.tool()
def get_user_role(email: str) -> str:
    """Get a user's role by their email address. Returns the user's role (Requestor, LegalExpert, TaxExpert) and display name."""
    result = get_tools().get_user_role(email)
    return json.dumps(result)


@mcp.tool()
def create_request(requestor_email: str, title: str, actor_email: str) -> str:
    """Create a new request for legal/tax questions. The requestor_email is the person submitting the request. actor_email is the currently logged-in user."""
    result = get_tools().create_request(requestor_email, title, actor_email)
    return json.dumps(result)


@mcp.tool()
def add_questions_to_request(
    request_id: str, questions: str, actor_email: str
) -> str:
    """Add questions to a request. questions should be a JSON array of objects with 'questionText' and 'questionType' (Legal or Tax) fields. Example: [{"questionText": "What are the tax implications?", "questionType": "Tax"}]"""
    parsed_questions = json.loads(questions)
    result = get_tools().add_questions_to_request(
        request_id, parsed_questions, actor_email
    )
    return json.dumps(result)


@mcp.tool()
def assign_question(
    question_id: str, request_id: str, assigned_to: str, actor_email: str
) -> str:
    """Assign a question to an expert or requestor. question_id is the question to assign, assigned_to is the expert's email."""
    result = get_tools().assign_question(
        question_id, request_id, assigned_to, actor_email
    )
    return json.dumps(result)


@mcp.tool()
def get_requests_by_user(email: str) -> str:
    """Get all requests submitted by a specific user (requestor)."""
    result = get_tools().get_requests_by_user(email)
    return json.dumps(result)


@mcp.tool()
def get_request_status(request_id: str) -> str:
    """Get the full status of a request including all questions and their answers."""
    result = get_tools().get_request_status(request_id)
    return json.dumps(result)


@mcp.tool()
def get_assigned_questions(email: str) -> str:
    """Get all questions assigned to a specific user (expert or requestor)."""
    result = get_tools().get_assigned_questions(email)
    return json.dumps(result)


@mcp.tool()
def submit_answer(
    question_id: str,
    request_id: str,
    answered_by: str,
    answer_text: str,
    source: str = "Manual",
    email_message_id: str = "",
    actor_email: str = "",
) -> str:
    """Submit an answer to a question. source can be 'Manual' or 'Email'. If from email, provide email_message_id."""
    result = get_tools().submit_answer(
        question_id,
        request_id,
        answered_by,
        answer_text,
        source,
        email_message_id or None,
        actor_email or answered_by,
    )
    return json.dumps(result)


@mcp.tool()
def mark_question_submitted(
    question_id: str, request_id: str, actor_email: str
) -> str:
    """Mark a question as submitted (answer finalized). The question must be in 'Answered' status."""
    result = get_tools().mark_question_submitted(question_id, request_id, actor_email)
    return json.dumps(result)


@mcp.tool()
def send_request(request_id: str, actor_email: str) -> str:
    """Send a draft request to experts for review. Moves request from Draft to InProgress and auto-assigns questions to available experts."""
    result = get_tools().send_request(request_id, actor_email)
    return json.dumps(result)


@mcp.tool()
def submit_request(request_id: str, actor_email: str) -> str:
    """Submit a request for final review. All questions in the request must be in 'Submitted' status."""
    result = get_tools().submit_request(request_id, actor_email)
    return json.dumps(result)


@mcp.tool()
def get_experts_by_type(expert_type: str) -> str:
    """Get available experts for a question type. expert_type should be 'Legal' or 'Tax'."""
    result = get_tools().get_experts_by_type(expert_type)
    return json.dumps(result)


# --- Health endpoint for Container App probes ---

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount


async def health_check(request):
    return JSONResponse({"status": "healthy", "service": "LegalTaxAssistantTools"})


def create_app() -> Starlette:
    """Build composite ASGI app: health endpoint + MCP SSE."""
    sse = mcp.sse_app()
    return Starlette(
        routes=[
            Route("/health", health_check),
            Mount("/", app=sse),
        ],
    )


def main():
    """Run the MCP server with SSE transport on a composite ASGI app."""
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    logger.info(f"Starting LegalTaxAssistantTools MCP Server on port {port}")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
