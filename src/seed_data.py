"""Seed script to populate Cosmos DB with test users for the Legal Tax Assistant."""

from __future__ import annotations

import argparse
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.cosmos_client import CosmosDBClient
from mcp_server.models import ExpertType, User, UserRole

SEED_USERS = [
    User(
        email="mkankalia@MngEnvMCAP629447.onmicrosoft.com",
        displayName="M Kankalia",
        role=UserRole.REQUESTOR,
    ),
    User(
        email="dkankalia@MngEnvMCAP629447.onmicrosoft.com",
        displayName="D Kankalia",
        role=UserRole.LEGAL_EXPERT,
        expertType=ExpertType.LEGAL,
    ),
    User(
        email="vkankalia@MngEnvMCAP629447.onmicrosoft.com",
        displayName="V Kankalia",
        role=UserRole.TAX_EXPERT,
        expertType=ExpertType.TAX,
    ),
]


def seed(endpoint: str | None = None):
    """Seed the database with test users using Entra ID authentication."""
    db = CosmosDBClient(endpoint=endpoint)

    print("Seeding users...")
    for user in SEED_USERS:
        try:
            db.create_item("Users", user.model_dump())
            print(f"  ✓ Created: {user.displayName} ({user.role})")
        except Exception as e:
            if "Conflict" in str(e):
                print(f"  ⊘ Already exists: {user.displayName}")
            else:
                print(f"  ✗ Error creating {user.displayName}: {e}")

    print("\nSeed complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Legal Tax Assistant database")
    parser.add_argument("--endpoint", help="Cosmos DB endpoint (uses DefaultAzureCredential)")
    args = parser.parse_args()

    seed(endpoint=args.endpoint or os.environ.get("COSMOS_ENDPOINT"))
