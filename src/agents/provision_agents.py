"""
Provision Foundry Prompt Agents for the Legal & Tax Assistant.

Reads YAML definitions from src/agents/definitions/ and creates/updates
agents in the specified Foundry project using the azure-ai-projects SDK.

Usage:
    python -m agents.provision_agents \
        --project-endpoint <FOUNDRY_PROJECT_ENDPOINT> \
        --model <MODEL_DEPLOYMENT_NAME> \
        --mcp-server-url <MCP_SERVER_SSE_URL>

Environment variables (fallbacks):
    FOUNDRY_PROJECT_ENDPOINT
    MODEL_DEPLOYMENT_NAME
    MCP_SERVER_URL
"""

import argparse
import os
import sys
import time
from pathlib import Path
from string import Template

import yaml
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential


DEFINITIONS_DIR = Path(__file__).parent / "definitions"


def load_agent_definition(yaml_path: str, model: str) -> dict:
    """Load an agent YAML definition and substitute variables."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = f.read()

    rendered = Template(raw).safe_substitute(MODEL_DEPLOYMENT_NAME=model)
    return yaml.safe_load(rendered)


def build_mcp_tool(tool_def: dict, mcp_server_url: str) -> MCPTool:
    """Build an MCPTool instance from a YAML tool definition."""
    return MCPTool(
        server_label=tool_def["server_label"],
        server_url=mcp_server_url,
        allowed_tools=tool_def.get("allowed_tools"),
        require_approval=tool_def.get("require_approval", "never"),
    )


def wait_for_mcp_server(mcp_server_url: str, timeout: int = 120):
    """Poll the MCP server health endpoint until it's ready."""
    import urllib.error
    import urllib.request

    health_url = mcp_server_url.replace("/sse", "/health")
    print(f"Waiting for MCP server at {health_url} ...")

    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    print("MCP server is ready.")
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(5)

    print(f"WARNING: MCP server not reachable after {timeout}s. Proceeding anyway.")


def provision_agent(
    client: AIProjectClient,
    definition: dict,
    mcp_server_url: str,
) -> object:
    """Create or update a single prompt agent using the Agent Definition API."""
    agent_name = definition["name"]
    model = definition["model"]
    instructions = definition["instructions"]
    temperature = definition.get("temperature", 0.3)
    top_p = definition.get("top_p", 1.0)

    # Build tool list
    tools = []
    for tool_def in definition.get("tools", []):
        if tool_def["type"] == "mcp":
            tools.append(build_mcp_tool(tool_def, mcp_server_url))

    print(f"\n{'='*60}")
    print(f"Provisioning agent: {agent_name}")
    print(f"  Model: {model}")
    print(f"  Temperature: {temperature}")
    print(f"  MCP tools: {[t.server_label for t in tools]}")

    try:
        agent_def = PromptAgentDefinition(
            model=model,
            instructions=instructions,
            tools=tools if tools else None,
            temperature=temperature,
            top_p=top_p,
        )

        agent = client.agents.create_version(
            agent_name=agent_name,
            definition=agent_def,
        )

        print(f"  ✅ Agent '{agent_name}' provisioned successfully")
        return agent

    except Exception as e:
        print(f"  ❌ Failed to provision '{agent_name}': {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Provision Foundry Prompt Agents")
    parser.add_argument(
        "--project-endpoint",
        default=os.environ.get("FOUNDRY_PROJECT_ENDPOINT"),
        help="Foundry project endpoint URL",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o"),
        help="Model deployment name",
    )
    parser.add_argument(
        "--mcp-server-url",
        default=os.environ.get("MCP_SERVER_URL"),
        help="MCP server SSE endpoint URL",
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Skip waiting for MCP server health check",
    )
    args = parser.parse_args()

    if not args.project_endpoint:
        print("ERROR: --project-endpoint or FOUNDRY_PROJECT_ENDPOINT required.")
        sys.exit(1)
    if not args.mcp_server_url:
        print("ERROR: --mcp-server-url or MCP_SERVER_URL required.")
        sys.exit(1)

    print(f"Foundry endpoint: {args.project_endpoint}")
    print(f"Model: {args.model}")
    print(f"MCP server: {args.mcp_server_url}")

    if not args.skip_health_check:
        wait_for_mcp_server(args.mcp_server_url)

    credential = DefaultAzureCredential()
    client = AIProjectClient(
        endpoint=args.project_endpoint,
        credential=credential,
    )

    yaml_files = sorted(DEFINITIONS_DIR.glob("*.yaml"))
    if not yaml_files:
        print(f"ERROR: No YAML files found in {DEFINITIONS_DIR}")
        sys.exit(1)

    print(f"\nFound {len(yaml_files)} agent definitions.")
    agents = []

    for yaml_file in yaml_files:
        definition = load_agent_definition(str(yaml_file), args.model)
        agent = provision_agent(client, definition, args.mcp_server_url)
        agents.append((definition["name"], agent))

    print(f"\n{'='*60}")
    print(f"✅ All {len(agents)} agents provisioned successfully!")
    print(f"\nAgent Summary:")
    for name, agent in agents:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
