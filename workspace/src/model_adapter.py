"""
model_adapter.py — Model factory dispatching on MODEL_ID prefix.

Provides a single get_model() function that reads MODEL_ID from the environment
and returns the appropriate LangChain chat model instance.

Supported prefixes:
  "gemini-"  -> ChatGoogleGenerativeAI (langchain-google-genai)
  "claude-"  -> ChatAnthropicVertex (langchain-google-vertexai[anthropic])

All downstream code calls get_model() and never imports a specific model class
directly — this centralises the model swap logic so changing MODEL_ID is the
only code change needed to switch between Gemini and Claude.
"""

from __future__ import annotations

import os


def get_model(model_id: str | None = None):
    """
    Return the appropriate LangChain chat model based on MODEL_ID.

    Args:
        model_id: Optional model ID string. If None, reads MODEL_ID from the
                  environment (defaulting to "gemini-3-flash-preview").

    Returns:
        ChatGoogleGenerativeAI for "gemini-*" model IDs.
        ChatAnthropicVertex for "claude-*" model IDs.

    Raises:
        ValueError: if model_id does not start with "gemini-" or "claude-".
    """
    if model_id is None:
        model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

    if model_id.startswith("gemini-"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            return ChatGoogleGenerativeAI(
                model=model_id,
                google_api_key=api_key,
                #timeout=60,
            )
        return ChatGoogleGenerativeAI(
            model=model_id,
            project=project,
            location=location,
            #timeout=60,
        )

    if model_id.startswith("claude-"):
        from langchain_google_vertexai.model_garden import ChatAnthropicVertex
        return ChatAnthropicVertex(
            model_name=model_id,
            project=project,
            location=location,
            timeout=60,
        )

    raise ValueError(
        f"Unsupported MODEL_ID: {model_id!r}. "
        "Must start with 'gemini-' or 'claude-'."
    )
