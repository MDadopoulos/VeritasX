"""
model_adapter.py — Model factory dispatching on MODEL_ID prefix.

Provides a single get_model() function that reads MODEL_ID from config
and returns the appropriate LangChain chat model instance.

Supported prefixes:
  "gemini-"  -> ChatGoogleGenerativeAI (langchain-google-genai)
  "claude-"  -> ChatAnthropicVertex (langchain-google-vertexai[anthropic])

All downstream code calls get_model() and never imports a specific model class
directly — this centralises the model swap logic so changing MODEL_ID is the
only code change needed to switch between Gemini and Claude.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Config


def get_model(config: "Config | None" = None):
    """
    Return the appropriate LangChain chat model based on MODEL_ID.

    Args:
        config: Optional Config instance. If None, get_config() is called
                to read from environment. Pass a config in tests to avoid
                loading real environment variables.

    Returns:
        ChatGoogleGenerativeAI for "gemini-*" model IDs.
        ChatAnthropicVertex for "claude-*" model IDs.

    Raises:
        ValueError: if MODEL_ID does not start with "gemini-" or "claude-".
    """
    if config is None:
        from src.config import get_config
        config = get_config()

    model_id = config.model_id

    if model_id.startswith("gemini-"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_id,
            project=config.google_cloud_project,
            location=config.google_cloud_location,
        )

    if model_id.startswith("claude-"):
        from langchain_google_vertexai.model_garden import ChatAnthropicVertex
        return ChatAnthropicVertex(
            model_name=model_id,
            project=config.google_cloud_project,
            location=config.google_cloud_location,
        )

    raise ValueError(
        f"Unsupported MODEL_ID: {model_id!r}. "
        "Must start with 'gemini-' or 'claude-'."
    )
