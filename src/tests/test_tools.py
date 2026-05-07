"""Unit tests for Legal Tax Assistant MCP tools.

Uses an in-memory mock of CosmosDBClient so tests run without Azure.
"""

from __future__ import annotations

import json
import copy
import unittest
from typing import Any
from uuid import uuid4

from mcp_server.models import (
    ExpertType,
    QuestionStatus,
    QuestionType,
    RequestStatus,
    UserRole,
)
from mcp_server.tools import LegalTaxTools


class MockCosmosDBClient:
    """In-memory mock of CosmosDBClient for unit testing."""

    def __init__(self):
        self._containers: dict[str, list[dict[str, Any]]] = {
            "Users": [],
            "Requests": [],
            "Questions": [],
            "Answers": [],
            "AuditLog": [],
        }

    def create_item(self, container_name: str, item: dict[str, Any]) -> dict[str, Any]:
        item = copy.deepcopy(item)
        item["_etag"] = str(uuid4())
        self._containers[container_name].append(item)
        return item

    def read_item(
        self, container_name: str, item_id: str, partition_key: str
    ) -> dict[str, Any] | None:
        for item in self._containers[container_name]:
            if item["id"] == item_id:
                return copy.deepcopy(item)
        return None

    def upsert_item(self, container_name: str, item: dict[str, Any]) -> dict[str, Any]:
        item = copy.deepcopy(item)
        item["_etag"] = str(uuid4())
        for i, existing in enumerate(self._containers[container_name]):
            if existing["id"] == item["id"]:
                self._containers[container_name][i] = item
                return item
        self._containers[container_name].append(item)
        return item

    def replace_item(
        self,
        container_name: str,
        item_id: str,
        item: dict[str, Any],
        etag: str | None = None,
    ) -> dict[str, Any]:
        item = copy.deepcopy(item)
        item["_etag"] = str(uuid4())
        for i, existing in enumerate(self._containers[container_name]):
            if existing["id"] == item_id:
                self._containers[container_name][i] = item
                return item
        raise Exception(f"Item not found: {item_id}")

    def query_items(
        self,
        container_name: str,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query mock — filters items by matching all parameters against item fields.

        Only includes an item if every param field exists in the item AND matches.
        """
        items = self._containers[container_name]
        if not parameters:
            return [copy.deepcopy(i) for i in items]

        param_map = {p["name"]: p["value"] for p in parameters}
        results = []

        for item in items:
            match = True
            for param_name, param_value in param_map.items():
                field = param_name.lstrip("@")
                if field not in item:
                    match = False
                    break
                if item[field] != param_value:
                    match = False
                    break
            if match:
                results.append(copy.deepcopy(item))

        return results

    def delete_item(
        self, container_name: str, item_id: str, partition_key: str
    ) -> None:
        self._containers[container_name] = [
            i for i in self._containers[container_name] if i["id"] != item_id
        ]


class TestGetUserRole(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        # Seed a test user
        self.db.create_item("Users", {
            "id": "u1",
            "email": "legal@test.com",
            "displayName": "Legal Expert",
            "role": UserRole.LEGAL_EXPERT,
            "expertType": ExpertType.LEGAL,
            "isActive": True,
        })

    def test_get_existing_user(self):
        result = self.tools.get_user_role("legal@test.com")
        self.assertEqual(result["role"], "LegalExpert")
        self.assertEqual(result["displayName"], "Legal Expert")

    def test_get_nonexistent_user(self):
        result = self.tools.get_user_role("nobody@test.com")
        self.assertIn("error", result)


class TestCreateRequest(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)

    def test_create_request(self):
        result = self.tools.create_request("req@test.com", "Test Request", "req@test.com")
        self.assertIn("id", result)
        self.assertEqual(result["status"], RequestStatus.DRAFT)
        self.assertEqual(result["title"], "Test Request")

    def test_audit_log_created(self):
        self.tools.create_request("req@test.com", "Audit Test", "req@test.com")
        audits = self.db._containers["AuditLog"]
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["action"], "Created")


class TestAddQuestions(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        result = self.tools.create_request("req@test.com", "Test", "req@test.com")
        self.request_id = result["id"]

    def test_add_questions(self):
        questions = [
            {"questionText": "Legal Q?", "questionType": "Legal"},
            {"questionText": "Tax Q?", "questionType": "Tax"},
        ]
        result = self.tools.add_questions_to_request(
            self.request_id, questions, "req@test.com"
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["questionType"], "Legal")
        self.assertEqual(result[1]["questionType"], "Tax")
        self.assertEqual(result[0]["status"], QuestionStatus.UNASSIGNED)


class TestAssignQuestion(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        req = self.tools.create_request("req@test.com", "Test", "req@test.com")
        self.request_id = req["id"]
        questions = self.tools.add_questions_to_request(
            self.request_id,
            [{"questionText": "Legal Q?", "questionType": "Legal"}],
            "req@test.com",
        )
        self.question_id = questions[0]["id"]

    def test_assign_question(self):
        result = self.tools.assign_question(
            self.question_id, self.request_id, "expert@test.com", "req@test.com"
        )
        self.assertEqual(result["assignedTo"], "expert@test.com")
        self.assertEqual(result["status"], QuestionStatus.ASSIGNED)

    def test_assign_nonexistent_question(self):
        result = self.tools.assign_question(
            "bad-id", self.request_id, "expert@test.com", "req@test.com"
        )
        self.assertIn("error", result)


class TestSubmitAnswer(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        req = self.tools.create_request("req@test.com", "Test", "req@test.com")
        self.request_id = req["id"]
        questions = self.tools.add_questions_to_request(
            self.request_id,
            [{"questionText": "Legal Q?", "questionType": "Legal"}],
            "req@test.com",
        )
        self.question_id = questions[0]["id"]
        self.tools.assign_question(
            self.question_id, self.request_id, "expert@test.com", "req@test.com"
        )

    def test_submit_answer(self):
        result = self.tools.submit_answer(
            self.question_id,
            self.request_id,
            "expert@test.com",
            "The answer is 42.",
            "Manual",
        )
        self.assertIn("id", result)
        self.assertEqual(result["answeredBy"], "expert@test.com")

    def test_cannot_answer_unassigned(self):
        # Create a new unassigned question
        questions = self.tools.add_questions_to_request(
            self.request_id,
            [{"questionText": "New Q?", "questionType": "Tax"}],
            "req@test.com",
        )
        result = self.tools.submit_answer(
            questions[0]["id"],
            self.request_id,
            "expert@test.com",
            "Answer",
        )
        self.assertIn("error", result)


class TestMarkQuestionSubmitted(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        req = self.tools.create_request("req@test.com", "Test", "req@test.com")
        self.request_id = req["id"]
        questions = self.tools.add_questions_to_request(
            self.request_id,
            [{"questionText": "Q?", "questionType": "Legal"}],
            "req@test.com",
        )
        self.question_id = questions[0]["id"]
        self.tools.assign_question(
            self.question_id, self.request_id, "expert@test.com", "req@test.com"
        )
        self.tools.submit_answer(
            self.question_id, self.request_id, "expert@test.com", "Answer"
        )

    def test_mark_submitted(self):
        result = self.tools.mark_question_submitted(
            self.question_id, self.request_id, "expert@test.com"
        )
        self.assertEqual(result["status"], QuestionStatus.SUBMITTED)

    def test_cannot_submit_unanswered(self):
        # Create another assigned-but-unanswered question
        questions = self.tools.add_questions_to_request(
            self.request_id,
            [{"questionText": "Q2?", "questionType": "Tax"}],
            "req@test.com",
        )
        self.tools.assign_question(
            questions[0]["id"], self.request_id, "expert@test.com", "req@test.com"
        )
        result = self.tools.mark_question_submitted(
            questions[0]["id"], self.request_id, "expert@test.com"
        )
        self.assertIn("error", result)


class TestSubmitRequest(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        req = self.tools.create_request("req@test.com", "Full Flow", "req@test.com")
        self.request_id = req["id"]
        questions = self.tools.add_questions_to_request(
            self.request_id,
            [{"questionText": "Q?", "questionType": "Legal"}],
            "req@test.com",
        )
        self.question_id = questions[0]["id"]
        self.tools.assign_question(
            self.question_id, self.request_id, "expert@test.com", "req@test.com"
        )
        self.tools.submit_answer(
            self.question_id, self.request_id, "expert@test.com", "Answer"
        )
        self.tools.mark_question_submitted(
            self.question_id, self.request_id, "expert@test.com"
        )

    def test_submit_request(self):
        result = self.tools.submit_request(self.request_id, "req@test.com")
        self.assertEqual(result["status"], RequestStatus.SUBMITTED)
        self.assertIn("submittedAt", result)

    def test_cannot_submit_with_pending_questions(self):
        # Add an unanswered question
        self.tools.add_questions_to_request(
            self.request_id,
            [{"questionText": "Q2?", "questionType": "Tax"}],
            "req@test.com",
        )
        result = self.tools.submit_request(self.request_id, "req@test.com")
        self.assertIn("error", result)


class TestGetExpertsByType(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        self.db.create_item("Users", {
            "id": "u1", "email": "legal@test.com", "displayName": "Legal",
            "role": "LegalExpert", "expertType": "Legal", "isActive": True,
        })
        self.db.create_item("Users", {
            "id": "u2", "email": "tax@test.com", "displayName": "Tax",
            "role": "TaxExpert", "expertType": "Tax", "isActive": True,
        })

    def test_get_legal_experts(self):
        result = self.tools.get_experts_by_type("Legal")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["email"], "legal@test.com")

    def test_get_tax_experts(self):
        result = self.tools.get_experts_by_type("Tax")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["email"], "tax@test.com")


class TestGetAssignedQuestions(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        req = self.tools.create_request("req@test.com", "Test", "req@test.com")
        self.request_id = req["id"]
        questions = self.tools.add_questions_to_request(
            self.request_id,
            [
                {"questionText": "Q1?", "questionType": "Legal"},
                {"questionText": "Q2?", "questionType": "Tax"},
            ],
            "req@test.com",
        )
        self.q1_id = questions[0]["id"]
        self.q2_id = questions[1]["id"]
        self.tools.assign_question(
            self.q1_id, self.request_id, "legal@test.com", "req@test.com"
        )
        self.tools.assign_question(
            self.q2_id, self.request_id, "tax@test.com", "req@test.com"
        )

    def test_get_assigned_to_legal(self):
        result = self.tools.get_assigned_questions("legal@test.com")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["questionType"], "Legal")

    def test_get_assigned_to_tax(self):
        result = self.tools.get_assigned_questions("tax@test.com")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["questionType"], "Tax")


class TestGetRequestStatus(unittest.TestCase):
    def setUp(self):
        self.db = MockCosmosDBClient()
        self.tools = LegalTaxTools(self.db)
        req = self.tools.create_request("req@test.com", "Status Test", "req@test.com")
        self.request_id = req["id"]

    def test_get_status_empty_request(self):
        result = self.tools.get_request_status(self.request_id)
        self.assertEqual(result["title"], "Status Test")
        self.assertEqual(result["questions"], [])

    def test_get_status_with_questions(self):
        self.tools.add_questions_to_request(
            self.request_id,
            [{"questionText": "Q?", "questionType": "Legal"}],
            "req@test.com",
        )
        result = self.tools.get_request_status(self.request_id)
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(result["questions"][0]["status"], QuestionStatus.UNASSIGNED)

    def test_nonexistent_request(self):
        result = self.tools.get_request_status("bad-id")
        self.assertIn("error", result)


class TestFullWorkflow(unittest.TestCase):
    """End-to-end test of the complete request lifecycle."""

    def test_full_lifecycle(self):
        db = MockCosmosDBClient()
        tools = LegalTaxTools(db)

        # Seed users
        db.create_item("Users", {
            "id": "u1", "email": "req@test.com", "displayName": "Requestor",
            "role": "Requestor", "expertType": None, "isActive": True,
        })
        db.create_item("Users", {
            "id": "u2", "email": "legal@test.com", "displayName": "Legal Expert",
            "role": "LegalExpert", "expertType": "Legal", "isActive": True,
        })

        # 1. Requestor creates a request
        req = tools.create_request("req@test.com", "Q1 Review", "req@test.com")
        self.assertEqual(req["status"], "Draft")

        # 2. Add questions
        questions = tools.add_questions_to_request(
            req["id"],
            [{"questionText": "Legal question?", "questionType": "Legal"}],
            "req@test.com",
        )
        q_id = questions[0]["id"]

        # 3. Assign to expert
        assign = tools.assign_question(
            q_id, req["id"], "legal@test.com", "req@test.com"
        )
        self.assertEqual(assign["status"], "Assigned")

        # 4. Expert answers
        answer = tools.submit_answer(
            q_id, req["id"], "legal@test.com", "The answer.", actor_email="legal@test.com"
        )
        self.assertNotIn("error", answer)

        # 5. Expert marks submitted
        mark = tools.mark_question_submitted(q_id, req["id"], "legal@test.com")
        self.assertEqual(mark["status"], "Submitted")

        # 6. Requestor submits request
        submit = tools.submit_request(req["id"], "req@test.com")
        self.assertEqual(submit["status"], "Submitted")

        # Verify audit trail
        audits = db._containers["AuditLog"]
        actions = [a["action"] for a in audits]
        self.assertIn("Created", actions)
        self.assertIn("Assigned", actions)
        self.assertIn("Answered", actions)
        self.assertIn("Submitted", actions)


if __name__ == "__main__":
    unittest.main()
