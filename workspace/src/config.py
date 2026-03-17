"""
config.py — Environment variable loading and fail-fast validation.

Loads .env if present, then reads all required env vars into a Config dataclass.
Raises RuntimeError immediately if required vars are missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the workspace directory (or wherever it lives) if present.
# This is a no-op in production environments where vars are injected directly.
load_dotenv()


@dataclass
class Config:
    """All environment configuration for the OfficeQA finance agent."""

    # Model selection
    model_id: str = "claude-sonnet-4-6"

    # Google Cloud settings
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    google_genai_use_vertexai: bool = True
    google_application_credentials: str = ""

    # Corpus settings
    corpus_source: str = "local"
    corpus_dir: Path = field(default_factory=lambda: Path("../corpus/transformed").resolve())
    csv_full_path: Path = field(default_factory=lambda: Path("../officeqa_full.csv").resolve())
    csv_pro_path: Path = field(default_factory=lambda: Path("../officeqa_pro.csv").resolve())


def get_config() -> Config:
    """
    Read all environment variables, apply defaults, validate, and return Config.

    Raises:
        RuntimeError: if GOOGLE_CLOUD_PROJECT is not set.
    """
    model_id = os.environ.get("MODEL_ID", "claude-sonnet-4-6")

    google_cloud_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not google_cloud_project:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT environment variable is required but not set. "
            "Set it to your GCP project ID (e.g. export GOOGLE_CLOUD_PROJECT=my-project)."
        )

    google_cloud_location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

    genai_use_vertexai_raw = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true")
    google_genai_use_vertexai = genai_use_vertexai_raw.lower() in ("true", "1", "yes")

    google_application_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

    corpus_source = os.environ.get("CORPUS_SOURCE", "local")

    corpus_dir = Path(os.environ.get("CORPUS_DIR", "../corpus/transformed")).resolve()
    csv_full_path = Path(os.environ.get("CSV_FULL_PATH", "../officeqa_full.csv")).resolve()
    csv_pro_path = Path(os.environ.get("CSV_PRO_PATH", "../officeqa_pro.csv")).resolve()

    return Config(
        model_id=model_id,
        google_cloud_project=google_cloud_project,
        google_cloud_location=google_cloud_location,
        google_genai_use_vertexai=google_genai_use_vertexai,
        google_application_credentials=google_application_credentials,
        corpus_source=corpus_source,
        corpus_dir=corpus_dir,
        csv_full_path=csv_full_path,
        csv_pro_path=csv_pro_path,
    )
