# Reflect — personal support conversations

Reflect is a local development prototype for supportive, therapist-style conversations informed by a user's own stated profile. It is an AI companion, not a licensed therapist, clinical treatment, or emergency service.

## Run locally

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

In another terminal:

```bash
source .venv/bin/activate
streamlit run streamlit.py
```

Open http://localhost:8501. Optional admin UI: `streamlit run admin_dashboard.py --server.port 8502`.

Configure `.env`:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_TIMEOUT=180
API_KEY=choose-a-long-random-private-key
ADMIN_USERNAME=...
ADMIN_PASSWORD=...
DB_SQLITE_PATH=data/sync_data.db
```

Install [Ollama](https://ollama.com/download), then start the server and download both models:

```bash
ollama serve
# In another terminal:
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

Qwen3 8B is the default local chat model (about 5.2 GB download, plus runtime memory).
For stronger responses on a machine with sufficient memory, pull `qwen3:14b` and set
`OLLAMA_MODEL=qwen3:14b`. Local inference has no provider API fees; it uses your hardware.
Replies, JSON profile extraction and embeddings use Ollama only.
Legacy OpenAI/Google keys are ignored. Keep `.env` private. `/health` checks that both
models are installed and the server is reachable. `OLLAMA_TIMEOUT` allows for local inference
latency; `OLLAMA_NUM_CTX` defaults to 8192 tokens. Thinking output is disabled.

Old personal memory vectors are skipped and replaced on the next consenting chat or profile
update; profiles and history are preserved.

## Profiles and memory

- The UI creates a stable user ID; save it to resume a profile across conversations. Resuming opens the latest saved conversation, and the sidebar lets you open older saved chats. New conversation starts a fresh thread.
- Memory is off by default. With consent, conversation text and a structured profile are saved in SQLite.
- The profile captures explicitly stated background, goals, stressors, coping preferences, support network, and communication preferences. It is AI-generated and editable; it is not a clinical assessment.
- After each consenting turn, the profile is updated and embedded with `nomic-embed-text` (768 dimensions). A new message is embedded to retrieve the current user's relevant profile vector by cosine similarity. The current profile, the latest 20 messages in the current conversation, and up to 20 recent messages from earlier conversations also inform the reply. The UI displays the full saved thread, while model context is bounded. The initial store uses one replaceable vector per profile, not a long-term event-memory timeline.
- All history and vector queries filter by user ID. Conversations have separate IDs. Opt-out erases saved profile content, transcripts, and vectors. Deleting removes the user too. Backups and provider retention are outside this local deletion mechanism.
- Without consent, the UI sends recent in-session messages as temporary context; the backend does not persist or embed their text. WhatsApp without memory processes each message independently.
- Embedding/profile-extraction outages do not prevent a normal reply; the prior profile or recent conversation remains available.

## Optional infrastructure

Reusable Redis and Elasticsearch clients remain in `clients.py`. They connect only when
explicitly requested; normal chat, consent, profile and history storage use SQLite.
`GET /health/infrastructure` requires `x-api-key` and checks these optional services.
`/health` continues to check Ollama independently.

`services/search_by_embedding.py` retains generic Elasticsearch vector search with an explicit
index and optional filters. `services/get_chat_history.py` retains a read-only Redis history
helper with user/conversation keys under `REDIS_KEY_PREFIX`. Neither helper automatically
persists chat data or replaces SQLite. Any future integration must preserve consent and user isolation.

All accommodation routes, tools, prompts, sync workers and API settings have been removed.
Existing database files are preserved; old sync tables are no longer created or used.
Copied infrastructure credentials were replaced with localhost defaults. Fresh API and admin
credentials are in the private `.env`; existing clients must use its new `API_KEY`.
Use `.env.example` as the template for a new installation.

`chat_app.service` is an optional Linux deployment template expecting `/opt/ai-therapist`,
its `.venv`, and a writable data directory for `www-data`. Adjust paths/user for your server.
It runs one worker to match the current in-process conversation locks.

## API

`http://localhost:8000/docs` documents the endpoints. All profile and conversation routes require `x-api-key` matching `.env` `API_KEY`.

```bash
curl -X POST http://localhost:8000/profiles \
  -H 'x-api-key: YOUR_API_KEY' -H 'Content-Type: application/json' \
  -d '{"memory_consent":true,"profile":{"preferred_name":"Alex"}}'
```

Use the returned `user_id`:

```bash
curl -X POST http://localhost:8000/chat/chat \
  -H 'x-api-key: YOUR_API_KEY' -H 'Content-Type: application/json' \
  -d '{"user_id":"web:YOUR_ID","conversation_id":"session-1","message":"Work has been stressful lately."}'
```

Replies are returned directly as JSON; this replaces the old Redis queue response contract. Use GET/PUT/DELETE `/profiles/{user_id}` to inspect, correct, opt out, or remove data. GET `/chat/history/{user_id}/{conversation_id}` retrieves saved history.

The shared API key is for the trusted local UI/server adapters; it is an administrator credential that can access every user. Do not expose it to public clients. Public web accounts need individual authentication and ownership authorization before deployment.

## Meta WhatsApp Cloud API adapter

Configure these from your Meta application dashboard:

```dotenv
WHATSAPP_VERIFY_TOKEN=your-own-random-webhook-verification-secret
WHATSAPP_APP_SECRET=your-meta-app-secret
WHATSAPP_ACCESS_TOKEN=your-meta-access-token
WHATSAPP_PHONE_NUMBER_ID=your-business-phone-number-id
WHATSAPP_API_VERSION=the-supported-version-from-your-meta-dashboard
```

Expose the API through HTTPS. Register `https://YOUR_HOST/webhooks/whatsapp` as the callback URL, use the matching verification token, and subscribe to message webhooks. GET handles the verification challenge; POST checks the HMAC signature over the original bytes, validates the receiving phone-number ID, and ignores status events and non-text messages. Outbound replies use Meta's `/messages` API only in response to incoming text events. No live Meta message has been sent during development.

Each sender maps to `whatsapp:<sender-id>` and has a distinct profile. First contact introduces the AI and memory choices. Supported commands: `REMEMBER ON`, `REMEMBER OFF`, `DELETE MY DATA`. Duplicate webhook IDs are ignored using SQLite.

The adapter is a development foundation: accepted events run in in-process background tasks, not a durable queue. A server restart can lose pending work, and failed outbound deliveries are counted by the admin screen but are not automatically retried. Before public WhatsApp rollout, add durable jobs/outbox retries, provider delivery-status handling, and account-specific Meta eligibility review. Use one API worker for the current local implementation; per-user locking is in-process. Core conversation service does not depend on WhatsApp and can later be moved behind a durable worker.

## Verification and limits

```bash
python -m unittest discover -s tests -v
```

Tests cover Ollama request/response adaptation, embedding failures, profile updates, isolation, consent, deletion, signature validation, duplicate events, and API validation using temporary databases and mocked AI calls. They do not establish clinical safety or live-provider compatibility. Prompts instruct the model to avoid diagnosis and medication advice, encourage real-world support, and prioritize immediate safety when danger is disclosed; this is not a validated crisis detection system.
