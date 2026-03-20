"""
schemas.py — Pydantic A2A schema models for the HTTP server.

Defines request/response/error Pydantic models used by the FastAPI server
to enforce the A2A-compatible interface: POST /run accepts {uid, question}
and returns {uid, answer}. Error shapes are consistent across 422, 500, 504.

Exports:
    RunRequest      — POST /run request body
    RunResponse     — POST /run success response
    ErrorResponse   — Error body for 422, 500, 504
    HealthResponse  — GET /health response body
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator


class RunRequest(BaseModel):
    """A2A request body for POST /run."""

    model_config = ConfigDict(extra="forbid")

    uid: str
    question: str

    @model_validator(mode="before")
    @classmethod
    def validate_fields(cls, values: dict) -> dict:
        """Validate that uid and question are present, non-empty strings."""
        uid = values.get("uid")
        question = values.get("question")

        if uid is None:
            raise ValueError("uid is required")
        if not isinstance(uid, str):
            raise ValueError(f"uid must be a string, got {type(uid).__name__}")
        if not uid.strip():
            raise ValueError("uid must be a non-empty string")

        if question is None:
            raise ValueError("question is required")
        if not isinstance(question, str):
            raise ValueError(f"question must be a string, got {type(question).__name__}")
        if not question.strip():
            raise ValueError("question must be a non-empty string")

        return values


class RunResponse(BaseModel):
    """A2A success response body for POST /run (HTTP 200)."""

    model_config = ConfigDict(extra="forbid")

    uid: str
    answer: str


class ErrorResponse(BaseModel):
    """Error response body for 422, 500, 504.

    uid is optional — it is only included when it was parseable from the
    request. If the request was malformed before uid could be extracted,
    uid is omitted entirely from the response body.
    """

    model_config = ConfigDict(extra="forbid")

    uid: Optional[str] = None
    reason: str


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    model_config = ConfigDict(extra="forbid")

    status: str
    corpus_files: int
    model_id: str
    credentials: str
