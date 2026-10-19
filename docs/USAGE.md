# Using Terngi AI

This guide takes you from zero to a working API, then shows every endpoint with
**curl**, **Python** and **JavaScript** examples.

- [1. Choose a setup](#1-choose-a-setup)
- [2. Run the API](#2-run-the-api)
- [3. Languages](#3-languages)
- [4. Endpoints](#4-endpoints): translate, batch, detect, converse, **agent**
- [5. Errors, limits and auth](#5-errors-limits-and-auth)
- [6. Troubleshooting](#6-troubleshooting)

---

## 1. Choose a setup

You need at least one provider. Pick the row that fits you and put the settings in `.env`
(copy [`.env.example`](../.env.example) first).

| Setup | Cost | What you get | `.env` |
|---|---|---|---|
| **Groq only** | Free tier | Everything, including the agent | `GROQ_API_KEYS=gsk_...` |
| **Groq + MORENA** (recommended) | Free | MORENA translates into African languages locally; Groq handles chat, detection and the agent | `LLM_PROVIDERS=groq,morena`<br>`GROQ_API_KEYS=gsk_...`<br>`TRANSLATION_PROVIDERS=morena,groq` |
| **MORENA only** | Free, no keys | Translation only (no detection, chat is weak, no agent) | `LLM_PROVIDERS=morena`<br>`TRANSLATION_PROVIDERS=morena` |
| **Azure + Groq** | Azure paid tier | Azure translation with LLM fallback | `AZURE_TRANSLATOR_KEYS=...`<br>`GROQ_API_KEYS=gsk_...` |

Get a free Groq key at <https://console.groq.com/keys>. To survive rate limits, add several
keys and models:

```bash
GROQ_API_KEYS=gsk_first,gsk_second
GROQ_MODELS=openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b
```

Other OpenAI-compatible providers work the same way. Add the name to `LLM_PROVIDERS` and set
`<NAME>_API_KEYS` and `<NAME>_MODELS` (built in: `openrouter`, `together`, `cerebras`,
`huggingface`, `openai`, `ollama`). Any other name needs `<NAME>_BASE_URL`.

## 2. Run the API

**Python**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

**MORENA** (only for setups that use it), in a second terminal:

```bash
brew install llama.cpp          # or see https://github.com/ggml-org/llama.cpp
llama-server --hf-repo vamboai/morena-1.5b-instruct-gguf \
  --hf-file morena-1.5b-instruct-Q4_K_M.gguf --port 8080 -c 4096
```

**Docker Compose** (API and MORENA together):

```bash
docker compose --profile morena up
```

Check that it's ready:

```bash
curl http://localhost:8000/health/ready
# {"status":"ready","services":{"translator":true,"llm":true,"agent":true}}
```

Interactive docs: <http://localhost:8000/docs>.

## 3. Languages

| Code | Language | Code | Language |
|---|---|---|---|
| `en` | English | `sw` | Swahili |
| `fr` | French | `rw` | Kinyarwanda |
| `yo` | Yoruba | `sn` | Shona |
| `ha` | Hausa | `zu` | isiZulu |
| `ig` | Igbo | `xh` | isiXhosa |
| `pcm` | Nigerian Pidgin | `tn` | Setswana |
| `af` | Afrikaans | `nr` | isiNdebele |

Wherever a request takes `from_language` (or `language` for the agent), you can pass
`"auto"` to detect it. `GET /v1/languages` returns this list.

## 4. Endpoints

All examples assume `BASE=http://localhost:8000`. If the server sets `API_KEYS`, add the
header `X-API-Key: <key>`.

### Translate: `POST /v1/translate`

```bash
curl -X POST $BASE/v1/translate -H 'Content-Type: application/json' \
  -d '{"content": "Good morning, how is your family?", "from_language": "en", "to_language": "yo"}'
```

```json
{"translated_text": "Ẹ kú àárọ̀, báwo ni ẹbí yín ṣe wà?", "from_language": "en",
 "to_language": "yo", "original_text": "Good morning, how is your family?"}
```

### Batch translate: `POST /v1/translate/batch`

Up to 25 texts (50,000 characters) in one request; results come back in order.

```bash
curl -X POST $BASE/v1/translate/batch -H 'Content-Type: application/json' \
  -d '{"texts": ["Thank you", "Good night"], "from_language": "en", "to_language": "ha"}'
# {"translations": ["Na gode", "Barka da dare"], "from_language": "en", "to_language": "ha"}
```

### Detect language: `POST /v1/detect`

```bash
curl -X POST $BASE/v1/detect -H 'Content-Type: application/json' \
  -d '{"content": "Wetin you dey do for house?"}'
# {"language": "pcm", "language_name": "Nigerian Pidgin", "score": 0.99, "is_supported": true}
```

### Converse: `POST /v1/converse`

Simple chat: the message is translated to English, answered, and the answer is translated
back. Pass earlier turns in `memory_context`.

```bash
curl -X POST $BASE/v1/converse -H 'Content-Type: application/json' \
  -d '{"content": "Ina kwana?", "from_language": "auto", "to_language": "ha"}'
```

### Agent: `POST /v1/agent`

The agent is the most capable endpoint. It understands any supported language and decides
for itself when to use tools:

| Tool | What it does |
|---|---|
| `translate` | Translates through the provider chain (MORENA, Azure, LLMs) |
| `detect_language` | Identifies a language |
| `list_languages` | Lists supported languages |
| `get_current_time` | Current date and time in any time zone (default `Africa/Lagos`) |

Request fields:

| Field | Default | Meaning |
|---|---|---|
| `message` | required | What the user said, in any supported language |
| `language` | `"auto"` | Language of `message` |
| `reply_language` | same as `language` | Language of the answer |
| `history` | `null` | Earlier turns: `[{"role": "user" \| "assistant", "content": "..."}]` |

```bash
curl -X POST $BASE/v1/agent -H 'Content-Type: application/json' \
  -d '{"message": "How do I say \"thank you very much\" in Swahili, isiZulu and Hausa?"}'
```

```json
{
  "answer": "- Swahili: asante sana\n- isiZulu: Ngiyabonga kakhulu\n- Hausa: na gode sosai",
  "language": "en",
  "reply_language": "en",
  "steps": [
    {"tool": "translate", "arguments": {"text": "thank you very much", "target_language": "sw"},
     "output": {"translation": "asante sana", "source_language": "en", "target_language": "sw"}},
    "..."
  ]
}
```

Ask in Igbo and the answer comes back in Igbo:

```bash
curl -X POST $BASE/v1/agent -H 'Content-Type: application/json' \
  -d '{"message": "Nnọọ! Kedu ụbọchị taa?"}'
# {"answer": "Ụtụtụ ọma! Taa bụ Mọnde, Ọktoba 19, 2026.", "language": "ig", "reply_language": "ig",
#  "steps": [{"tool": "get_current_time", ...}, {"tool": "translate", ...}]}
```

Ask in English and get the answer in Hausa:

```bash
curl -X POST $BASE/v1/agent -H 'Content-Type: application/json' \
  -d '{"message": "Give me two tips for staying healthy during harmattan.", "reply_language": "ha"}'
```

`steps` shows exactly which tools ran and what they returned, which helps with debugging
and building UIs. See [AGENT.md](AGENT.md) for how it works and how to add tools.

### Python client

```python
import httpx

BASE = "http://localhost:8000"
HEADERS = {}  # {"X-API-Key": "..."} if the server requires it

with httpx.Client(base_url=BASE, headers=HEADERS, timeout=60) as api:
    r = api.post(
        "/v1/translate",
        json={
            "content": "Welcome to our school.",
            "from_language": "en",
            "to_language": "ig",
        },
    )
    r.raise_for_status()
    print(r.json()["translated_text"])

    history = []
    for question in ["Ẹ káàrọ̀!", "Kí ni olú-ìlú Nàìjíríà?"]:
        r = api.post("/v1/agent", json={"message": question, "history": history})
        r.raise_for_status()
        reply = r.json()["answer"]
        print(reply)
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": reply}]
```

### JavaScript (browser or Node 18+)

```js
const BASE = "http://localhost:8000";

async function agent(message, replyLanguage) {
  const res = await fetch(`${BASE}/v1/agent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" /*, "X-API-Key": "..." */ },
    body: JSON.stringify({ message, reply_language: replyLanguage }),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.message);
  return body.answer;
}

console.log(await agent("What should I pack for a trip to Kigali?", "rw"));
```

To call the API from a web page on another origin, set `CORS_ORIGINS` on the server.

## 5. Errors, limits and auth

Every error has the same shape:

```json
{"error": true, "message": "Target language 'de' not supported. ...", "status_code": 400}
```

| Status | Meaning |
|---|---|
| `400` | Unsupported language, or batch too large |
| `401` | Missing or invalid `X-API-Key` (only when `API_KEYS` is set) |
| `422` | Invalid request body (details in `details`) |
| `429` | Rate limit exceeded; wait `Retry-After` seconds |
| `502` | Every configured provider failed |
| `503` | No provider is configured for this task |

Every response carries `X-Request-ID` (send your own to trace a request) and
`X-RateLimit-Remaining`.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `503 ... not configured` | Add a provider key, or check `GET /health/ready` |
| `502` on translation | Look at the server log: it names the provider and status that failed |
| Logs show `key …abcd was rejected` | That key is revoked or wrong; it's skipped for an hour |
| Logs show `rate-limited` | Add more keys or models; requests move to the next one automatically |
| MORENA requests fail | Check `curl localhost:8080/health`; translation falls back to the next provider meanwhile |
| Agent returns `503` | The agent needs an OpenAI-compatible provider (e.g. Groq); MORENA alone can't run it |
