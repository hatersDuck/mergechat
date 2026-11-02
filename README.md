# MergeChat Phase 0

Feasibility spike for passive Max chat monitoring and JEV order detection.

## What is implemented

- Async FastAPI onboarding and review API.
- Max connector over `PyMax.WebClient` with QR onboarding, selected-chat
  subscription, reconnect handling, create/edit/delete events, health state and
  an encrypted copy of the session in the application database.
- Platform-independent message normalization and idempotent storage.
- SQLAlchemy async storage for accounts, chats, messages, classifications,
  manual labels and processing runs, with an Alembic migration.
- JEV / TypeSafe system-one integration using the same animal-transport
  questions as `src/sandbox/jev.py`.
- Manual labelling, dataset export and precision/recall metrics.

Automatic replies, Redis, PostgreSQL deployment, VK, Telegram and WhatsApp are
out of scope for Phase 0.

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in `MERGECHAT_SESSION_ENCRYPTION_KEY` (generate one with
`openssl rand -base64 32`) and `MERGECHAT_JEV_API_KEY`. For any access beyond
localhost, also set `MERGECHAT_API_TOKEN`.

Run the API:

```bash
uv run mergechat
# or
uv run uvicorn mergechat.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Web control room: <http://127.0.0.1:8000/ui/> (the root URL redirects here).  
Swagger UI: <http://127.0.0.1:8000/docs>.

## Web control room

The bundled GUI covers every Phase 0 API operation and is served by the same
FastAPI process with no build step:

- Accounts: create, connect via QR link, poll status, inspect health, start and
  stop the listener, disconnect, revoke the session and delete the account.
- Chats: refresh the Max group-chat list, filter it and save the monitored
  selection.
- Messages: browse, filter unlabeled messages, inspect attachments, read the
  latest classification, classify a single message and apply a manual label.
- Classification: run a bounded batch, inspect precision/recall, preview the
  export and download it as JSON Lines.
- Labels: bulk import labels from a JSON payload.

The GUI stores the optional API bearer token and the last selected account in
browser local storage. If `MERGECHAT_API_TOKEN` is set, enter it with the
**API token** button in the top bar. Static UI assets are public; data endpoints
remain protected by the existing authentication middleware.

Run tests and checks:

```bash
uv run pytest
uv run ruff check src tests
```

Apply migrations:

```bash
uv run alembic upgrade head
```

The API and CLI scripts apply Alembic migrations on startup. A database is
therefore versioned consistently and `alembic upgrade head` is safe to run
again.

## Onboarding flow

1. `POST /accounts` with `{"display_name": "Owner"}`.
2. `POST /accounts/{id}/connect`.
   - With an existing encrypted session, Max starts immediately.
   - With no session, the response is `pending_auth` and contains `qr_link`.
     Scan it in the Max app. The API status endpoint then changes to
     `connected`.
3. `GET /accounts/{id}/chats` refreshes and stores group chats.
4. `POST /accounts/{id}/chats/selection` with `{"chat_ids": ["..."]}`.
5. `POST /accounts/{id}/listener/start`.

The listener is passive: the connector subscribes only to selected group chats
and never sends messages.

`DELETE /accounts/{id}/session` disconnects and wipes the local session
material. `DELETE /accounts/{id}` removes the account and all stored data.

## Classification and labelling

```text
POST /messages/{message_id}/classify
GET  /messages/{message_id}/classification
POST /classifications/run          {"account_id": "...", "limit": 50}
GET  /classifications/export
GET  /classifications/metrics
GET  /messages?unlabeled=true
POST /messages/{message_id}/label  {"label": "order", "labeler": "me"}
POST /labels/import                {"labels": [...]}
```

Supported labels are `order`, `not_order` and `uncertain`.

CLI helpers:

```bash
uv run python scripts/run_max_listener.py --account-id <id>
uv run python scripts/classify_messages.py --limit 50
uv run python scripts/export_dataset.py --output dataset.jsonl
uv run python scripts/prune_messages.py --days 30
```

## JEV output limitation

JEV system-one supports `noul`, `choice`, `score` and `box` questions, not
arbitrary JSON extraction. The spike therefore stores:

- `is_order` and `confidence` from the `is_order` noul probability.
- Animal type, headcount and capacity fit as choices.
- Route/contact/quote presence as noul flags.
- A `route_from`/`route_to`/`date`/`price`/`contact` field set that remains
  `null`; free-text extraction still needs a separate LLM step.

This is recorded in every classification's `attributes.extraction_notes`.

## Security notes

- Session files are encrypted with `MERGECHAT_SESSION_ENCRYPTION_KEY` before
  being stored in the application database. The ciphertext uses PBKDF2 and a
  random per-encryption salt.
- Without `MERGECHAT_API_TOKEN`, data endpoints accept only loopback clients.
  Set a token before binding to a non-loopback interface.
- Max QR links are cleared after successful authentication and are not returned
  once the connector is connected.
- Delete events remove message text, attachments, raw payload, classifications,
  and labels instead of leaving retrievable content behind.
- Session data is never returned by the API or written to logs.
- Logs are JSON and redact phone numbers and obvious secret key/value pairs.
- `.env` is git-ignored; `.env.example` contains no real credentials.
- Use a dedicated test Max account and obtain explicit account-owner consent.
- Review Max ToS, 152-FZ data-residency and LLM data-processing terms before
  processing production conversations.
