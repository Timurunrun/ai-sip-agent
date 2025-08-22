import os

# Использует переменную окружения LLM_PROVIDER = 'openai' | 'groq'
# По умолчанию: openai
_provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

if _provider == "groq":
    from .groq_agent import get_llm_agent, process_transcript, process_transcript_async  # noqa: F401
else:
    from .openai_agent import get_llm_agent, process_transcript, process_transcript_async  # noqa: F401

__all__ = [
    "get_llm_agent",
    "process_transcript",
    "process_transcript_async",
]
