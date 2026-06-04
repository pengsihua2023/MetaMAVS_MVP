"""Thin, defensive wrapper around the Anthropic Claude API.

Loads the key from a project ``.env`` (or the environment), caches the stable
system prompt for cheap repeat calls, and never raises into the workflow: any
missing-key / SDK / API failure returns ``None`` so the caller falls back to
deterministic behaviour.
"""

from __future__ import annotations

import os

from ..utils.logging_utils import get_logger

logger = get_logger("llm.client")

# Default per the claude-api guidance: latest Opus, adaptive thinking.
DEFAULT_MODEL = "claude-opus-4-8"


def _load_env() -> None:
    """Load .env (if python-dotenv is installed) so ANTHROPIC_API_KEY is set."""

    try:
        from dotenv import load_dotenv

        # override=True so a project .env key takes precedence over any key
        # already exported in the shell environment.
        load_dotenv(override=True)
    except Exception:
        pass  # dotenv optional; env var may already be set


def llm_available() -> bool:
    """True if an Anthropic key and the SDK are both present."""

    _load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def generate(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_MODEL,
    effort: str = "medium",
    max_tokens: int = 4000,
    use_thinking: bool = True,
) -> str | None:
    """Generate text from Claude, or return None on any failure / no key.

    The ``system`` prompt is sent as a cached block (stable across runs → cheap
    cache reads); the volatile per-run ``user`` content is not cached.
    """

    if not llm_available():
        logger.info("LLM not available (no ANTHROPIC_API_KEY or SDK) — skipping interpretation")
        return None

    try:
        import anthropic

        client = anthropic.Anthropic()
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
        }
        if use_thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": effort}

        resp = client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        cr = getattr(resp.usage, "cache_read_input_tokens", 0)
        logger.info("LLM ok (%s): %d in, %d out, %d cache-read",
                    model, resp.usage.input_tokens, resp.usage.output_tokens, cr)
        return text or None
    except Exception as exc:  # never propagate into the workflow
        logger.warning("LLM generation failed (%s) — falling back to deterministic output", exc)
        return None
