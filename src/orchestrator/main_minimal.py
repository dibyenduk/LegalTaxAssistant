"""Minimal orchestrator for testing connectivity."""
import os
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini"),
        credential=DefaultAzureCredential(),
    )
    agent = Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        default_options={"store": False},
    )
    server = ResponsesHostServer(agent)
    server.run()

if __name__ == "__main__":
    main()
