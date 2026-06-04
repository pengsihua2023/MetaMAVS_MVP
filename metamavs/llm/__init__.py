"""Phase 4: optional LLM interpretation layer (Anthropic Claude).

Entirely optional and additive — if no API key is configured (or ``llm.enabled``
is false, or the SDK/key fails), every entry point degrades to a no-op and the
deterministic Phase 1-3 pipeline is unchanged. No LLM key is ever required to
run MetaMAVS.
"""

from .client import generate, llm_available

__all__ = ["generate", "llm_available"]
