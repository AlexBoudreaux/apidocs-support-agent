"""One place for env, model names, and paths.

Everything the rest of `app` needs from the environment is read here at import
time. Nothing else in the package touches `os.environ` directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# Explicit path, not find_dotenv(): find_dotenv walks the caller's stack and
# raises AssertionError when it is called from a `python -` stdin script.
load_dotenv(REPO_ROOT / ".env")

# ---------- paths ----------

KB_ROOT = Path(os.environ.get("KB_ROOT", REPO_ROOT / "kb"))
FIXTURES_ROOT = Path(os.environ.get("FIXTURES_ROOT", REPO_ROOT / "fixtures"))
APPROVED_DIR = KB_ROOT / "approved"

# ---------- database ----------

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://apidocs:apidocs@localhost:5433/apidocs"
)

# ---------- models ----------
# Set by Alex at build kickoff. Reasoning effort is a standard ChatOpenAI
# parameter as of langchain-openai>=1.4.1 and passes straight through
# init_chat_model's **kwargs into the request payload as `reasoning_effort`.

MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "openai")
MODEL_STRONG = os.environ.get("MODEL_STRONG", "gpt-5.6-sol")
MODEL_STRONG_REASONING_EFFORT = os.environ.get("MODEL_STRONG_REASONING_EFFORT", "medium")
MODEL_FAST = os.environ.get("MODEL_FAST", "gpt-5.6-luna")
MODEL_FAST_REASONING_EFFORT = os.environ.get("MODEL_FAST_REASONING_EFFORT", "high")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large")

# ---------- langsmith ----------

LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT", "apidocs-support")
LANGSMITH_TRACING = os.environ.get("LANGSMITH_TRACING", "false").lower() == "true"


# ---------- checkpointer serialization ----------
# `TicketState["review"]` holds a Pydantic `ReviewDecision`, so the checkpointer
# round-trips a custom type. langgraph 1.2.11 deserializes it with a warning
# ("This will be blocked in a future version") unless the type is on the
# msgpack allowlist. Entries are (module, qualname) pairs; a bare module string
# is accepted but silently gives you back a plain dict.

CHECKPOINT_ALLOWED_TYPES = [("app.state", "ReviewDecision")]


def checkpoint_serde():
    """Serializer every checkpointer in this project is built with."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_ALLOWED_TYPES)


def chat_model(which: str = "fast", **kwargs):
    """Build a chat model by role. `which` is "fast" or "strong".

    Kept here so every node calls models the same way and 4c/4d/4e never
    re-derive the provider or the reasoning effort.
    """
    from langchain.chat_models import init_chat_model

    if which == "strong":
        name, effort = MODEL_STRONG, MODEL_STRONG_REASONING_EFFORT
    elif which == "fast":
        name, effort = MODEL_FAST, MODEL_FAST_REASONING_EFFORT
    else:
        raise ValueError(f"unknown model role: {which!r}")

    return init_chat_model(
        name,
        model_provider=MODEL_PROVIDER,
        reasoning_effort=effort,
        **kwargs,
    )


def embeddings():
    """Embedding model for the semantic index. 4c uses this."""
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=EMBEDDING_MODEL)
