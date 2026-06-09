"""Thin, defensive wrapper around the Anthropic Claude API.

Loads the key from a project ``.env`` (or the environment), caches the stable
system prompt for cheap repeat calls, and never raises into the workflow: any
missing-key / SDK / API failure returns ``None`` so the caller falls back to
deterministic behaviour.
"""

from __future__ import annotations

import json
import os
import re

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


def resolve_params(llm_cfg: dict | None, agent: str) -> dict:
    """Resolve ``{model, effort, max_tokens}`` for ``agent`` from an llm config dict.

    Applies any per-agent override in ``llm_cfg['overrides'][agent]`` over the
    top-level ``llm.*`` values; falls back to library defaults if absent. ``agent``
    is one of: qc, taxonomy, abundance, novel_virus, risk_assessment,
    llm_interpretation.
    """

    llm_cfg = llm_cfg or {}
    override = (llm_cfg.get("overrides") or {}).get(agent) or {}
    return {
        "model": override.get("model") or llm_cfg.get("model") or DEFAULT_MODEL,
        "effort": override.get("effort") or llm_cfg.get("effort") or "medium",
        "max_tokens": int(override.get("max_tokens") or llm_cfg.get("max_tokens") or 4000),
    }


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
    cached_prefix: str | None = None,
) -> str | None:
    """Generate text from Claude, or return None on any failure / no key.

    If ``cached_prefix`` is given (e.g. a large shared reference) it is the
    FIRST system block and carries the cache breakpoint — stable across agents
    so the prefix is reused via prompt caching. The agent-specific ``system``
    follows it; the per-run ``user`` content stays uncached.
    """

    if not llm_available():
        logger.info("LLM not available (no ANTHROPIC_API_KEY or SDK) — skipping interpretation")
        return None

    try:
        import anthropic

        client = anthropic.Anthropic()
        if cached_prefix:
            system_blocks = [
                {"type": "text", "text": cached_prefix, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": system},
            ]
        else:
            system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_blocks,
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


def generate_json(system: str, user: str, **kwargs) -> dict | None:
    """Like :func:`generate` but parse the reply as JSON; None on any failure.

    Tolerant of ```json code fences and surrounding prose — extracts the first
    balanced object. Returns None (→ deterministic fallback) if parsing fails.
    """

    text = generate(system, user, **kwargs)
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text
    try:
        return json.loads(raw)
    except Exception:
        try:
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start:end + 1])
        except Exception:
            pass
    logger.warning("LLM JSON parse failed — falling back to deterministic output")
    return None
