"""
Configuration settings for the Terngi Translation API

Secrets are read from environment variables (or a local `.env` file).
Never hardcode API keys in this file.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

from dotenv import find_dotenv, load_dotenv

# Load variables from a local .env file if present (no-op in production).
# ENV_FILE picks a different file; the test suite points it at /dev/null.
load_dotenv(os.getenv("ENV_FILE") or find_dotenv(usecwd=True))

# Define supported languages
# Codes are ISO 639-1 where one exists (Nigerian Pidgin uses ISO 639-3 "pcm").
# This matches the twelve African languages of the MORENA model, plus English and French.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "French",
    # West Africa
    "yo": "Yoruba",
    "ha": "Hausa",
    "ig": "Igbo",
    "pcm": "Nigerian Pidgin",
    # East Africa
    "sw": "Swahili",
    "rw": "Kinyarwanda",
    # Southern Africa
    "sn": "Shona",
    "zu": "isiZulu",
    "xh": "isiXhosa",
    "tn": "Setswana",
    "af": "Afrikaans",
    "nr": "isiNdebele",
}


def _env_list(name: str) -> List[str]:
    """Read a comma-separated environment variable as a list of non-empty values"""
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


def _unique(values: List[str]) -> List[str]:
    return list(dict.fromkeys(values))


# Azure Translator configuration. Several keys may be given; they are rotated, and a key
# that is rejected or rate-limited is skipped for a while.
AZURE_TRANSLATOR_KEYS = _unique(
    _env_list("AZURE_TRANSLATOR_KEYS") + _env_list("AZURE_TRANSLATOR_KEY")
)
AZURE_TRANSLATOR_ENDPOINT = os.getenv(
    "AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com"
)
AZURE_TRANSLATOR_LOCATION = os.getenv("AZURE_TRANSLATOR_LOCATION", "global")


@dataclass(frozen=True)
class LLMProvider:
    """
    A language model provider

    kind "openai" is any OpenAI-compatible chat completions API (Groq, OpenRouter,
    Together, Cerebras, Hugging Face, Ollama, vLLM, ...). kind "morena" is a llama.cpp
    server running Vambo AI's MORENA model, which uses its own prompt format.
    """

    name: str
    kind: str
    base_url: str
    api_keys: Tuple[str, ...]
    models: Tuple[str, ...]
    requires_key: bool = True

    @property
    def configured(self) -> bool:
        has_credentials = bool(self.api_keys) or not self.requires_key
        return bool(self.base_url and self.models and has_credentials)


# Known providers: kind, base URL, default model, whether an API key is required
PROVIDER_PRESETS: Dict[str, Tuple[str, str, str, bool]] = {
    "groq": ("openai", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", True),
    "openrouter": ("openai", "https://openrouter.ai/api/v1", "", True),
    "together": ("openai", "https://api.together.xyz/v1", "", True),
    "cerebras": ("openai", "https://api.cerebras.ai/v1", "", True),
    "huggingface": ("openai", "https://router.huggingface.co/v1", "", True),
    "openai": ("openai", "https://api.openai.com/v1", "", True),
    "ollama": ("openai", "http://localhost:11434/v1", "", False),
    "morena": ("morena", "http://localhost:8080", "morena-1.5b-instruct", False),
}


def _load_provider(name: str) -> LLMProvider:
    """
    Build a provider from environment variables prefixed with its name, e.g. for "groq":
    GROQ_API_KEYS / GROQ_API_KEY, GROQ_MODELS / GROQ_MODEL, GROQ_BASE_URL, GROQ_KIND
    """
    kind, base_url, model, requires_key = PROVIDER_PRESETS.get(name, ("openai", "", "", True))
    prefix = name.upper().replace("-", "_")
    models = (
        _env_list(f"{prefix}_MODELS") or _env_list(f"{prefix}_MODEL") or ([model] if model else [])
    )
    return LLMProvider(
        name=name,
        kind=os.getenv(f"{prefix}_KIND", kind),
        base_url=os.getenv(f"{prefix}_BASE_URL", base_url).rstrip("/"),
        api_keys=tuple(_unique(_env_list(f"{prefix}_API_KEYS") + _env_list(f"{prefix}_API_KEY"))),
        models=tuple(_unique(models)),
        requires_key=requires_key,
    )


# LLM providers in priority order, e.g. LLM_PROVIDERS=groq,openrouter,morena
LLM_PROVIDERS: Dict[str, LLMProvider] = {
    name: _load_provider(name) for name in _unique(_env_list("LLM_PROVIDERS") or ["groq"])
}

# Which providers handle each task, tried in order ("azure" or an LLM provider name).
# MORENA is not used for language detection by default.
CHAT_PROVIDERS = _env_list("CHAT_PROVIDERS") or list(LLM_PROVIDERS)
TRANSLATION_PROVIDERS = _env_list("TRANSLATION_PROVIDERS") or ["azure", *LLM_PROVIDERS]
DETECTION_PROVIDERS = _env_list("DETECTION_PROVIDERS") or [
    "azure",
    *(name for name, provider in LLM_PROVIDERS.items() if provider.kind != "morena"),
]

# How long (seconds) to skip a key after it is rejected or rate-limited
KEY_COOLDOWN_SECONDS = float(os.getenv("KEY_COOLDOWN_SECONDS", "60"))
INVALID_KEY_COOLDOWN_SECONDS = float(os.getenv("INVALID_KEY_COOLDOWN_SECONDS", "3600"))

# Timeout (seconds) for calls to upstream services
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "30"))

# Request limits
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", "5000"))
MAX_MEMORY_MESSAGES = int(os.getenv("MAX_MEMORY_MESSAGES", "20"))

# Batch translation limits (Azure allows at most 50,000 characters per request)
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "25"))
MAX_BATCH_CHARACTERS = int(os.getenv("MAX_BATCH_CHARACTERS", "50000"))

# Translation cache (set CACHE_TTL_SECONDS=0 to disable)
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
CACHE_MAX_ITEMS = int(os.getenv("CACHE_MAX_ITEMS", "1000"))

# Client authentication: comma-separated keys accepted in the X-API-Key header.
# Leave empty to disable authentication (e.g. for local development).
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]

# Requests per minute allowed per client (API key or IP). 0 disables rate limiting.
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

# Comma-separated list of allowed CORS origins (empty disables CORS)
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# System prompt for conversations
SYSTEM_PROMPT = """You are Terngi AI, a helpful, culturally aware assistant that specializes in multilingual conversations.
If asked who you are, say you are Terngi AI; do not claim to be any other assistant.
Your responses should be clear, natural, and conversational.
If the user provides context from previous conversations, use it to give more relevant and personalized responses.
Keep your responses informative but concise.
Respond only in English - your response will be translated if needed.
"""
