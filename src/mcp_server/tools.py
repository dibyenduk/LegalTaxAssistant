"""MCP tool implementations for Legal Tax Assistant."""

from __future__ import annotations

from typing import Any

from .cosmos_client import CosmosDBClient
from .models import (
    Answer,
    AnswerSource,
    AuditAction,
    AuditLogEntry,
    Question,
    QuestionInput,
    QuestionStatus,
    QuestionType,
    Request,
    RequestStatus,
    utc_now,
)


class LegalTaxTools:
    """All MCP tool logic backed by Cosmos DB."""

    def __init__(self, db: CosmosDBClient):
        self.db = db

    # --- Helpers ---

    def _audit(
        self,
        entity_type: str,
        entity_id: str,
        request_id: str,
        action: AuditAction,
        performed_by: str,
        details: dict | None = None,
    ) -> None:
        entry = AuditLogEntry(
            entityType=entity_type,
            entityId=entity_id,
            requestId=request_id,
            action=action,
            performedBy=performed_by,
            details=details or {},
        )
        self.db.create_item("AuditLog", entry.model_dump())

    # --- Tool: get_user_role ---

    def get_user_role(self, email: str) -> dict[str, Any]:
        """Get a user's role by email."""
        users = self.db.query_items(
            "Users",
            "SELECT * FROM c WHERE c.email = @email",
            parameters=[{"name": "@email", "value": email}],
            partition_key=email,
        )
        if not users:
            return {"error": f"User not found: {email}"}
        user = users[0]
        return {
            "email": user["email"],
            "displayName": user["displayName"],
            "role": user["role"],
            "expertType": user.get("expertType"),
        }

    # --- Tool: create_request ---

    def create_request(
        self, requestor_email: str, title: str, actor_email: str
    ) -> dict[str, Any]:
        """Create a new request."""
        req = Request(requestorEmail=requestor_email, title=title)
        result = self.db.create_item("Requests", req.model_dump())
        self._audit("Request", req.id, req.id, AuditAction.CREATED, actor_email)
        return {"id": result["id"], "status": result["status"], "title": result["title"]}

    # --- Tool: add_questions_to_request ---

    def add_questions_to_request(
        self,
        request_id: str,
        questions: list[dict[str, str]],
        actor_email: str,
    ) -> list[dict[str, Any]]:
        """Add questions to a request. Each question needs questionText and questionType."""
        created = []
        for q_input in questions:
            qi = QuestionInput(**q_input)
            question = Question(
                requestId=request_id,
                questionText=qi.questionText,
                questionType=qi.questionType,
            )
            result = self.db.create_item("Questions", question.model_dump())
            self._audit(
                "Question", question.id, request_id, AuditAction.CREATED, actor_email
            )
            created.append(
                {
                    "id": result["id"],
                    "questionText": result["questionText"],
                    "questionType": result["questionType"],
                    "status": result["status"],
                }
            )
        return created

    # --- Tool: assign_question ---

    def assign_question(
        self,
        question_id: str,
        request_id: str,
        assigned_to: str,
        actor_email: str,
    ) -> dict[str, Any]:
        """Assign a question to an expert or requestor."""
        item = self.db.read_item("Questions", question_id, partition_key=request_id)
        if not item:
            return {"error": f"Question not found: {question_id}"}

        if item["status"] not in (QuestionStatus.UNASSIGNED, QuestionStatus.ASSIGNED):
            return {"error": f"Cannot assign question in status: {item['status']}"}

        item["assignedTo"] = assigned_to
        item["assignedBy"] = actor_email
        item["status"] = QuestionStatus.ASSIGNED
        item["updatedAt"] = utc_now()

        result = self.db.replace_item(
            "Questions", question_id, item, etag=item.get("_etag")
        )

        # Move request to InProgress if still Draft
        req_items = self.db.query_items(
            "Requests",
            "SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": request_id}],
        )
        if req_items and req_items[0]["status"] == RequestStatus.DRAFT:
            req = req_items[0]
            req["status"] = RequestStatus.IN_PROGRESS
            req["updatedAt"] = utc_now()
            self.db.replace_item("Requests", request_id, req, etag=req.get("_etag"))

        self._audit(
            "Question",
            question_id,
            request_id,
            AuditAction.ASSIGNED,
            actor_email,
            {"assignedTo": assigned_to},
        )
        return {
            "id": result["id"],
            "assignedTo": result["assignedTo"],
            "status": result["status"],
        }

    # --- Tool: get_requests_by_user ---

    def get_requests_by_user(self, email: str) -> list[dict[str, Any]]:
        """Get all requests for a requestor."""
        results = self.db.query_items(
            "Requests",
            "SELECT c.id, c.title, c.status, c.createdAt, c.updatedAt FROM c WHERE c.requestorEmail = @email ORDER BY c.createdAt DESC",
            parameters=[{"name": "@email", "value": email}],
            partition_key=email,
        )
        return results

    # --- Tool: get_request_status ---

    def get_request_status(self, request_id: str) -> dict[str, Any]:
        """Get full status of a request including all questions and answers."""
        # Find the request (cross-partition since we don't have requestorEmail)
        requests = self.db.query_items(
            "Requests",
            "SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": request_id}],
        )
        if not requests:
            return {"error": f"Request not found: {request_id}"}
        req = requests[0]

        # Get all questions for this request
        questions = self.db.query_items(
            "Questions",
            "SELECT * FROM c WHERE c.requestId = @requestId",
            parameters=[{"name": "@requestId", "value": request_id}],
            partition_key=request_id,
        )

        # Get answers for all questions
        question_ids = [q["id"] for q in questions]
        answers_by_question: dict[str, list] = {}
        for qid in question_ids:
            ans = self.db.query_items(
                "Answers",
                "SELECT * FROM c WHERE c.questionId = @qid",
                parameters=[{"name": "@qid", "value": qid}],
                partition_key=qid,
            )
            if ans:
                answers_by_question[qid] = ans

        questions_with_answers = []
        for q in questions:
            questions_with_answers.append(
                {
                    "id": q["id"],
                    "questionText": q["questionText"],
                    "questionType": q["questionType"],
                    "assignedTo": q.get("assignedTo"),
                    "status": q["status"],
                    "answers": answers_by_question.get(q["id"], []),
                }
            )

        return {
            "id": req["id"],
            "title": req["title"],
            "status": req["status"],
            "requestorEmail": req["requestorEmail"],
            "createdAt": req["createdAt"],
            "questions": questions_with_answers,
        }

    # --- Tool: get_assigned_questions ---

    def get_assigned_questions(self, email: str) -> list[dict[str, Any]]:
        """Get all questions assigned to a user (cross-partition query)."""
        results = self.db.query_items(
            "Questions",
            "SELECT c.id, c.requestId, c.questionText, c.questionType, c.status, c.assignedTo, c.createdAt FROM c WHERE c.assignedTo = @assignedTo AND c.status IN ('Assigned', 'Answered')",
            parameters=[{"name": "@assignedTo", "value": email}],
        )
        return results

    # --- Tool: submit_answer ---

    def submit_answer(
        self,
        question_id: str,
        answered_by: str,
        answer_text: str,
        request_id: str | None = None,
        source: str = "Manual",
        email_message_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        """Submit an answer to a question."""
        # Validate question exists and is in correct state
        question = None
        if request_id:
            question = self.db.read_item("Questions", question_id, partition_key=request_id)

        # Fallback: cross-partition query if point-read fails or no request_id
        if not question:
            results = self.db.query_items(
                "Questions",
                "SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": question_id}],
            )
            if results:
                question = results[0]
                request_id = question.get("requestId", request_id)

        if not question:
            return {"error": f"Question not found: {question_id}"}

        if question["status"] not in (QuestionStatus.ASSIGNED, QuestionStatus.ANSWERED):
            return {"error": f"Cannot answer question in status: {question['status']}"}

        # Create the answer
        answer = Answer(
            questionId=question_id,
            requestId=request_id,
            answeredBy=answered_by,
            answerText=answer_text,
            source=AnswerSource(source),
            emailMessageId=email_message_id,
        )
        result = self.db.create_item("Answers", answer.model_dump())

        # Update question status directly to Submitted (skip Answered intermediate state)
        question["status"] = QuestionStatus.SUBMITTED
        question["updatedAt"] = utc_now()
        self.db.replace_item(
            "Questions", question_id, question, etag=question.get("_etag")
        )

        self._audit(
            "Answer",
            answer.id,
            request_id,
            AuditAction.ANSWERED,
            actor_email or answered_by,
            {"source": source},
        )

        return {
            "id": result["id"],
            "questionId": result["questionId"],
            "answeredBy": result["answeredBy"],
            "source": result["source"],
        }

    # --- Tool: mark_question_submitted ---

    def mark_question_submitted(
        self, question_id: str, actor_email: str, request_id: str | None = None
    ) -> dict[str, Any]:
        """Mark a question as submitted (answer finalized)."""
        question = None
        if request_id:
            question = self.db.read_item("Questions", question_id, partition_key=request_id)

        # Fallback: cross-partition query if point-read fails or no request_id
        if not question:
            results = self.db.query_items(
                "Questions",
                "SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": question_id}],
            )
            if results:
                question = results[0]
                request_id = question.get("requestId", request_id)

        if not question:
            return {"error": f"Question not found: {question_id}"}

        if question["status"] != QuestionStatus.ANSWERED:
            return {
                "error": f"Question must be in 'Answered' status to submit, current: {question['status']}"
            }

        question["status"] = QuestionStatus.SUBMITTED
        question["updatedAt"] = utc_now()
        result = self.db.replace_item(
            "Questions", question_id, question, etag=question.get("_etag")
        )

        self._audit(
            "Question", question_id, request_id, AuditAction.SUBMITTED, actor_email
        )
        return {"id": result["id"], "status": result["status"]}

    # --- Tool: send_request ---

    def send_request(self, request_id: str, actor_email: str) -> dict[str, Any]:
        """Send a draft request to experts for review (Draft → InProgress).

        This auto-assigns each question to an available expert of the matching type.
        """
        requests = self.db.query_items(
            "Requests",
            "SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": request_id}],
        )
        if not requests:
            return {"error": f"Request not found: {request_id}"}
        req = requests[0]

        if req["status"] != RequestStatus.DRAFT:
            return {"error": f"Request must be Draft to send, current: {req['status']}"}

        # Get questions for this request
        questions = self.db.query_items(
            "Questions",
            "SELECT * FROM c WHERE c.requestId = @requestId",
            parameters=[{"name": "@requestId", "value": request_id}],
            partition_key=request_id,
        )
        if not questions:
            return {"error": "Cannot send request with no questions."}

        # Auto-assign questions to experts
        assigned_count = 0
        for q in questions:
            q_type = q.get("questionType", "")
            experts = self.db.query_items(
                "Users",
                "SELECT * FROM c WHERE c.expertType = @type",
                parameters=[{"name": "@type", "value": q_type}],
            )
            if experts:
                expert = experts[0]
                q["assignedTo"] = expert["email"]
                q["status"] = QuestionStatus.ASSIGNED
                q["updatedAt"] = utc_now()
                self.db.replace_item("Questions", q["id"], q, etag=q.get("_etag"))
                assigned_count += 1

        # Move request to InProgress
        req["status"] = RequestStatus.IN_PROGRESS
        req["updatedAt"] = utc_now()
        result = self.db.replace_item("Requests", request_id, req, etag=req.get("_etag"))

        self._audit(
            "Request", request_id, request_id, AuditAction.SUBMITTED, actor_email,
            details={"transition": "Draft->InProgress", "questionsAssigned": assigned_count},
        )
        return {
            "id": result["id"],
            "status": result["status"],
            "questionsAssigned": assigned_count,
            "totalQuestions": len(questions),
        }

    # --- Tool: submit_request ---

    def submit_request(self, request_id: str, actor_email: str) -> dict[str, Any]:
        """Submit a request (all questions must be answered/submitted)."""
        # Find the request
        requests = self.db.query_items(
            "Requests",
            "SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": request_id}],
        )
        if not requests:
            return {"error": f"Request not found: {request_id}"}
        req = requests[0]

        if req["status"] != RequestStatus.IN_PROGRESS:
            return {"error": f"Request must be InProgress to submit, current: {req['status']}"}

        # Check all questions are submitted
        questions = self.db.query_items(
            "Questions",
            "SELECT c.id, c.status FROM c WHERE c.requestId = @requestId",
            parameters=[{"name": "@requestId", "value": request_id}],
            partition_key=request_id,
        )
        not_submitted = [
            q for q in questions if q["status"] != QuestionStatus.SUBMITTED
        ]
        if not_submitted:
            return {
                "error": f"{len(not_submitted)} question(s) are not yet submitted.",
                "pendingQuestions": [q["id"] for q in not_submitted],
            }

        req["status"] = RequestStatus.SUBMITTED
        req["submittedAt"] = utc_now()
        req["updatedAt"] = utc_now()
        result = self.db.replace_item("Requests", request_id, req, etag=req.get("_etag"))

        self._audit(
            "Request", request_id, request_id, AuditAction.SUBMITTED, actor_email
        )
        return {"id": result["id"], "status": result["status"], "submittedAt": result["submittedAt"]}

    # --- Tool: get_experts_by_type ---

    def get_experts_by_type(self, expert_type: str) -> list[dict[str, Any]]:
        """Get available experts for a question type (Legal or Tax)."""
        results = self.db.query_items(
            "Users",
            "SELECT c.email, c.displayName, c.role, c.expertType FROM c WHERE c.expertType = @expertType AND c.isActive = true",
            parameters=[{"name": "@expertType", "value": expert_type}],
        )
        return results
