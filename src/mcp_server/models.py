"""Pydantic models for Legal Tax Assistant entities."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


# --- Enums ---

class UserRole(str, Enum):
    REQUESTOR = "Requestor"
    LEGAL_EXPERT = "LegalExpert"
    TAX_EXPERT = "TaxExpert"


class ExpertType(str, Enum):
    LEGAL = "Legal"
    TAX = "Tax"


class RequestStatus(str, Enum):
    DRAFT = "Draft"
    IN_PROGRESS = "InProgress"
    SUBMITTED = "Submitted"
    COMPLETED = "Completed"


class QuestionStatus(str, Enum):
    UNASSIGNED = "Unassigned"
    ASSIGNED = "Assigned"
    ANSWERED = "Answered"
    SUBMITTED = "Submitted"


class QuestionType(str, Enum):
    LEGAL = "Legal"
    TAX = "Tax"


class AnswerSource(str, Enum):
    MANUAL = "Manual"
    EMAIL = "Email"


class AuditAction(str, Enum):
    CREATED = "Created"
    UPDATED = "Updated"
    ASSIGNED = "Assigned"
    ANSWERED = "Answered"
    SUBMITTED = "Submitted"


# --- Entities ---

class User(BaseModel):
    id: str = Field(default_factory=new_id)
    email: str
    displayName: str
    role: UserRole
    expertType: Optional[ExpertType] = None
    isActive: bool = True
    createdAt: str = Field(default_factory=utc_now)
    updatedAt: str = Field(default_factory=utc_now)


class Request(BaseModel):
    id: str = Field(default_factory=new_id)
    requestorEmail: str
    title: str
    status: RequestStatus = RequestStatus.DRAFT
    createdAt: str = Field(default_factory=utc_now)
    updatedAt: str = Field(default_factory=utc_now)
    submittedAt: Optional[str] = None


class Question(BaseModel):
    id: str = Field(default_factory=new_id)
    requestId: str
    questionText: str
    questionType: QuestionType
    assignedTo: Optional[str] = None
    assignedBy: Optional[str] = None
    status: QuestionStatus = QuestionStatus.UNASSIGNED
    createdAt: str = Field(default_factory=utc_now)
    updatedAt: str = Field(default_factory=utc_now)


class Answer(BaseModel):
    id: str = Field(default_factory=new_id)
    questionId: str
    requestId: str
    answeredBy: str
    answerText: str
    source: AnswerSource = AnswerSource.MANUAL
    emailMessageId: Optional[str] = None
    createdAt: str = Field(default_factory=utc_now)
    updatedAt: str = Field(default_factory=utc_now)


class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=new_id)
    entityType: str
    entityId: str
    requestId: str
    action: AuditAction
    performedBy: str
    timestamp: str = Field(default_factory=utc_now)
    details: dict = Field(default_factory=dict)


# --- Input models for tools ---

class QuestionInput(BaseModel):
    questionText: str
    questionType: QuestionType
