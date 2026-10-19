# Terngi AI — Translation & Conversation API

[![CI](https://github.com/Terngi-AI/tergniai-multilang/actions/workflows/ci.yml/badge.svg)](https://github.com/Terngi-AI/tergniai-multilang/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Good first issues](https://img.shields.io/github/issues/Terngi-AI/tergniai-multilang/good%20first%20issue?label=good%20first%20issues&color=7057ff)](https://github.com/Terngi-AI/tergniai-multilang/labels/good%20first%20issue)
[![GitHub stars](https://img.shields.io/github/stars/Terngi-AI/tergniai-multilang?style=social)](https://github.com/Terngi-AI/tergniai-multilang/stargazers)

**Open-source translation and AI conversation for Nigerian languages.**

A FastAPI service that translates between **English, Yoruba, Hausa, Igbo and Nigerian Pidgin** and holds
multilingual conversations with an LLM. It can use several providers at once:
[Azure Translator](https://learn.microsoft.com/azure/ai-services/translator/),
[Groq](https://groq.com/) or any OpenAI-compatible API, and
[MORENA](https://huggingface.co/vamboai/morena-1.5b-instruct), an open African-language model
you can run for free.

## Why this project?

More than 100 million people speak Yoruba, Hausa or Igbo, yet these languages are still
poorly served by most software. Terngi AI gives developers a simple, self-hostable API to
build apps, chatbots and services that speak to people in their own language, and it is
built in the open so native speakers and developers can improve it together.

⭐ **If this is useful to you, star the repo** — it helps more people find it.

## Features

- **Multiple providers, models and keys** — Azure, Groq, OpenRouter, Together, Cerebras,
  Hugging Face, Ollama or MORENA, tried in order; keys rotate and failing keys, models or
  providers are skipped automatically
- **Free, local African-language model** — run [MORENA](docs/MORENA.md) with llama.cpp
- **Translate** text between any two supported languages, one at a time or in batches
- **Auto-detect** the source language — pass `"from_language": "auto"` to any endpoint
- **Converse** in any supported language; the reply comes back in the target language,
  with optional multi-turn memory (`memory_context`)
- **Translation cache** (in-memory TTL/LRU) to save quota on repeated phrases
- **API-key authentication** (`X-API-Key`) and **per-client rate limiting**
- **Request IDs** (`X-Request-ID`) and timing headers for tracing
- Input validation, upstream timeouts and consistent JSON error responses
- Liveness (`/health`) and readiness (`/health/ready`) probes
- Docker image with a health check, running as a non-root user

## Quick start

### Prerequisites

- Python 3.10+
- At least one provider: a [Groq API key](https://console.groq.com/keys) (free tier),
  [MORENA running locally](docs/MORENA.md) (free), an Azure Translator key, or any
  OpenAI-compatible API

### Run locally

```bash
git clone https://github.com/Terngi-AI/tergniai-multilang.git
cd tergniai-multilang
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env   # then fill in your keys
uvicorn main:app --reload
```

Open http://localhost:8000/docs for the interactive API docs.

### Run with Docker

```bash
docker build -t terngi-ai .
docker run --rm -p 8000:8000 --env-file .env terngi-ai
```

### Run with MORENA (free, no API keys needed)

```bash
docker compose --profile morena up
```

This starts the API and a llama.cpp server with MORENA 1.5B (downloaded on first start,
about 0.9 GB). See [docs/MORENA.md](docs/MORENA.md).

## Configuration

All configuration comes from environment variables (see [`.env.example`](.env.example)).

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_TRANSLATOR_KEYS` | no* | — | Azure Translator keys (comma-separated, rotated) |
| `AZURE_TRANSLATOR_ENDPOINT` | no | `https://api.cognitive.microsofttranslator.com` | Translator endpoint |
| `AZURE_TRANSLATOR_LOCATION` | no | `global` | Azure resource region |
| `LLM_PROVIDERS` | no | `groq` | LLM providers in priority order |
| `<NAME>_API_KEYS` | yes* | — | Keys for a provider, e.g. `GROQ_API_KEYS=k1,k2` (`<NAME>_API_KEY` also works) |
| `<NAME>_MODELS` | no | provider default | Models to try in order, e.g. `GROQ_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b` |
| `<NAME>_BASE_URL` | for custom providers | preset | OpenAI-compatible base URL |
| `CHAT_PROVIDERS` | no | `LLM_PROVIDERS` | Providers used for `/v1/converse` |
| `TRANSLATION_PROVIDERS` | no | `azure` + `LLM_PROVIDERS` | Providers used for translation, in order |
| `DETECTION_PROVIDERS` | no | `azure` + LLM providers except MORENA | Providers used for language detection |
| `KEY_COOLDOWN_SECONDS` | no | `60` | How long to skip a rate-limited key |
| `INVALID_KEY_COOLDOWN_SECONDS` | no | `3600` | How long to skip a rejected key |
| `REQUEST_TIMEOUT` | no | `30` | Upstream timeout in seconds |
| `MAX_CONTENT_LENGTH` | no | `5000` | Max characters per message |
| `MAX_MEMORY_MESSAGES` | no | `20` | Max turns in `memory_context` |
| `API_KEYS` | no | *(auth disabled)* | Comma-separated client keys accepted in `X-API-Key` |
| `RATE_LIMIT_PER_MINUTE` | no | `60` | Requests per minute per client; `0` disables |
| `CACHE_TTL_SECONDS` | no | `3600` | Translation cache lifetime; `0` disables |
| `CACHE_MAX_ITEMS` | no | `1000` | Max cached translations |
| `MAX_BATCH_SIZE` | no | `25` | Max texts per batch request |
| `MAX_BATCH_CHARACTERS` | no | `50000` | Max total characters per batch |
| `CORS_ORIGINS` | no | *(disabled)* | Comma-separated allowed origins |
| `LOG_LEVEL` | no | `INFO` | Python log level |

\* You need at least one provider. Built-in provider names are `groq`, `openrouter`,
`together`, `cerebras`, `huggingface`, `openai`, `ollama` and `morena`; any other name works
when you set `<NAME>_BASE_URL` to an OpenAI-compatible API.

**How fallback works:** for each request, providers are tried in order. Within a provider,
each model is tried in order, and keys rotate between requests. A key that is rejected
(401/403) or rate-limited (429) is skipped for a while; a model that errors or returns
unusable output is skipped for that request. The app starts without keys; endpoints with
no configured provider return `503`.

Example, using two Groq keys, OpenRouter as a backup and MORENA for translation:

```bash
LLM_PROVIDERS=groq,openrouter,morena
GROQ_API_KEYS=gsk_key_one,gsk_key_two
GROQ_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b
OPENROUTER_API_KEYS=sk-or-...
OPENROUTER_MODELS=meta-llama/llama-3.3-70b-instruct
TRANSLATION_PROVIDERS=morena,groq,openrouter
```

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | API info and supported languages |
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (are upstream keys configured?) |
| `GET` | `/v1/languages` | Supported language codes |
| `POST` | `/v1/translate` | Translate text |
| `POST` | `/v1/translate/batch` | Translate up to 25 texts in one request |
| `POST` | `/v1/detect` | Detect the language of a text |
| `POST` | `/v1/converse` | Translate and get an LLM reply |

### Authentication & rate limits

When `API_KEYS` is set, every `/v1/*` endpoint except `/v1/languages` requires an
`X-API-Key` header. Each client (API key, or IP address when no key is sent) may make
`RATE_LIMIT_PER_MINUTE` requests per minute. Responses include `X-RateLimit-Limit` and
`X-RateLimit-Remaining`; when exceeded you get `429` with a `Retry-After` header.

> The cache and rate limiter are in-memory, so each server process keeps its own state.
> Run behind a shared limiter (e.g. your API gateway) if you scale out to many replicas.

### Translate

```bash
curl -X POST http://localhost:8000/v1/translate \
  -H 'Content-Type: application/json' \
  -d '{"content": "Good morning", "from_language": "en", "to_language": "yo"}'
```

### Batch translate

```bash
curl -X POST http://localhost:8000/v1/translate/batch \
  -H 'Content-Type: application/json' -H 'X-API-Key: <your-key>' \
  -d '{"texts": ["Good morning", "Thank you"], "from_language": "en", "to_language": "ig"}'
```

### Detect language

```bash
curl -X POST http://localhost:8000/v1/detect \
  -H 'Content-Type: application/json' \
  -d '{"content": "Ina kwana?"}'
# {"language": "ha", "language_name": "Hausa", "score": 1.0, "is_supported": true}
```

### Converse

```bash
curl -X POST http://localhost:8000/v1/converse \
  -H 'Content-Type: application/json' \
  -d '{
        "content": "Ina kwana?",
        "from_language": "auto",
        "to_language": "en",
        "memory_context": [
          {"role": "user", "content": "My name is Ada"},
          {"role": "assistant", "content": "Nice to meet you, Ada!"}
        ]
      }'
```

Errors use one shape:

```json
{"error": true, "message": "Target language 'fr' not supported. ...", "status_code": 400}
```

## Project layout

```
main.py              FastAPI app and error handlers
middleware.py        Request IDs, API-key auth and rate limiting
config.py            Settings loaded from environment variables
models.py            Pydantic request/response models
routes/              HTTP endpoints
services/            Providers (Azure, LLMs, MORENA), key rotation, cache, language helpers
docs/                Guides, e.g. running MORENA
tests/               Pytest suite (upstream services are mocked)
```

## Development

```bash
pytest --cov          # tests + coverage
ruff check . && ruff format .
mypy .
pre-commit install    # run checks automatically on every commit
```

CI runs lint, type checks, tests on Python 3.10–3.13, a Docker smoke test, secret scanning
and a dependency audit on every pull request.

## Contributing

Contributions of every size are welcome, and you don't need to be an expert:

- 🟢 **New here?** Pick a [good first issue](https://github.com/Terngi-AI/tergniai-multilang/labels/good%20first%20issue).
- 🗣️ **Speak Yoruba, Hausa, Igbo or another Nigerian language?** Help review translations
  and build our [evaluation set](https://github.com/Terngi-AI/tergniai-multilang/labels/languages). Native speakers are our most valuable contributors.
- 🛠️ **Experienced developer?** See [help wanted](https://github.com/Terngi-AI/tergniai-multilang/labels/help%20wanted) for streaming, Redis, speech and more.
- 💬 **Questions or ideas?** Start a conversation in [Discussions](https://github.com/Terngi-AI/tergniai-multilang/discussions).

Read [CONTRIBUTING.md](CONTRIBUTING.md) to get set up in a few minutes, and follow our
[Code of Conduct](CODE_OF_CONDUCT.md). Report security issues privately as described in
[SECURITY.md](SECURITY.md).

### Contributors

<a href="https://github.com/Terngi-AI/tergniai-multilang/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Terngi-AI/tergniai-multilang" alt="Contributors" />
</a>

## License

[MIT](LICENSE)
