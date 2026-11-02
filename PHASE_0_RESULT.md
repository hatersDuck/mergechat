# Phase 0 Result

Date: 2026-11-02

## Objective

Implement the Phase 0 feasibility spike described in `PHASE_0_PLAN.md`, using
`src/sandbox/max.py` as the Max/PyMax reference and `src/sandbox/jev.py` as the
JEV reference.

The result is a working local application for:

- Max account onboarding and passive chat monitoring.
- Message normalization, deduplication, and persistence.
- JEV order classification and attribute extraction.
- Manual labeling, dataset export, and quality metrics.
- Operational health, session security, and retention.

Phase 0 remains a spike. It is not a production deployment.

## What Was Implemented

### Application structure

Added the Python package under `src/mergechat`:

- `config.py` - environment-backed settings.
- `logging.py` - JSON logs with phone/secret redaction.
- `domain/` - platform-independent chat, message, label, and health models.
- `security/sessions.py` - encrypted Max session storage.
- `storage/` - SQLAlchemy models, repositories, async database setup, migrations.
- `connectors/` - connector protocol, Max connector, session store, normalizer,
  and lifecycle registry.
- `jev/` - JEV client, versioned prompts, answer validation, and service.
- `processing/` - ingestion, deduplication helpers, classification orchestration,
  and metrics.
- `api/` - FastAPI application, auth middleware, schemas, and route modules.
- `web/` - bundled Phase 0 control-room GUI (HTML, CSS, vanilla JS).
- `main.py` - `mergechat` console entry point.

### Max connector

Implemented over `PyMax.WebClient`:

- QR onboarding with the QR link exposed through the onboarding API.
- Account-specific session files under `sessions/<account_id>.db`.
- Encrypted session copy persisted in `account_sessions`.
- Restore of encrypted sessions after restart.
- Selected-chat subscription and passive message reading.
- New message, edit, and delete event handling.
- Chat listing restricted to group chats (`CHAT`).
- Reconnect tracking, health snapshots, and connection errors surfaced to the API.
- Session revocation and account deletion endpoints.
- QR link cleared after successful authentication.
- Atomic decrypted-session restore using a temporary file and `os.replace`.

### Storage and data lifecycle

Implemented:

- `account_sessions`
- `chats`
- `raw_messages`
- `classifications`
- `manual_labels`
- `processing_runs`

Important behavior:

- Unique message identity on
  `(platform, external_chat_id, external_message_id)`.
- Idempotent ingestion; duplicate events do not create duplicate rows.
- Edits update the stored message and return it to `pending`.
- Deletes clear text, attachments, and raw payload, delete derived
  classifications/labels, and mark the row `deleted`.
- Deleted messages cannot be revived by edits or classified again.
- Deleted messages are excluded from normal reads, exports, and metrics.
- Retention uses `received_at` and rejects windows below one day.
- SQLite is used for the spike; the schema is written to be portable to
  PostgreSQL.

### JEV integration

Implemented with the official `typesafe-sdk` async client:

- Reuses one `AsyncTypeSafeClient` per application process.
- Uses the same shared question definitions as the sandbox.
- Validates all required `noul` answers and allowed `choice` values.
- Stores `is_order`, confidence, animal type, headcount, capacity fit,
  route/contact/quote presence flags, usage, model, latency, and prompt version.
- Records failed classification attempts and marks messages for review.
- Supports single-message classification and batch classification.
- Batch classification atomically claims rows, uses bounded concurrency, and
  recovers stale `processing` claims.

JEV limitation found during the spike:

- JEV system-one supports `noul`, `choice`, `score`, and `box` questions, not
  arbitrary JSON extraction.
- Route, date, price, and contact cannot be extracted as free text through this
  API. They are stored as `null`, with presence flags and an
  `attributes.extraction_notes` explanation.
- A separate extraction model would be required for a complete `OrderCard`.

### API

Implemented endpoints:

```text
POST   /accounts
GET    /accounts
POST   /accounts/{id}/connect
GET    /accounts/{id}/status
GET    /accounts/{id}/health
POST   /accounts/{id}/listener/start
POST   /accounts/{id}/listener/stop
POST   /accounts/{id}/disconnect
DELETE /accounts/{id}/session
DELETE /accounts/{id}

GET    /accounts/{id}/chats
POST   /accounts/{id}/chats/selection

GET    /messages
GET    /messages/{id}
GET    /messages/{id}/classification
POST   /messages/{id}/classify
POST   /messages/{id}/label
GET    /messages/{id}/label

POST   /classifications/run
GET    /classifications/export
GET    /classifications/metrics

POST   /labels/import
GET    /healthz
GET    /
```

Authentication:

- If `MERGECHAT_API_TOKEN` is set, data endpoints require
  `Authorization: Bearer <token>`.
- Without a token, unauthenticated access is limited to loopback clients.
- Forwarded-header requests are not treated as loopback.
- `/healthz` and documentation endpoints remain public.

### Web control room

The FastAPI process also serves a bundled single-page control room at `/ui/`.
It covers the full Phase 0 surface: account creation, QR onboarding and status
polling, health inspection, listener control, session revocation and account
deletion; chat refresh and selection; message browsing, single-message
classification and manual labelling; batch classification, quality metrics and
JSONL export; and bulk label import. The UI stores the optional bearer token and
selected account in browser-local storage. Static assets are public; every data
request still passes through the existing authentication middleware.

### CLI scripts

Added:

- `scripts/run_max_listener.py` - create/connect an account and run the listener.
- `scripts/classify_messages.py` - classify pending messages through JEV.
- `scripts/export_dataset.py` - export messages, labels, and classifications as
  JSON Lines.
- `scripts/prune_messages.py` - apply the configured retention window.

All scripts apply Alembic migrations before use.

### Migrations and deployment safety

- Added `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, and
  `migrations/versions/0001_phase0.py`.
- Application and CLI startup now run Alembic migrations instead of unversioned
  `create_all`.
- Transient account statuses are reset to `disconnected` on startup.
- `alembic check` reports no pending schema differences.

### Tests

Added 25 tests covering:

- Message normalization and millisecond timestamps.
- Message deduplication and edit handling.
- Delete-event content removal and non-revival.
- Selected-chat persistence.
- Retention by receive time.
- Atomic pending-message claiming.
- Connector start, chat filtering, subscription changes, and failure propagation.
- JEV answer parsing, confidence thresholding, missing answers, and invalid
  choices.
- Session encryption roundtrip, wrong key, and placeholder rejection.
- Classification persistence and failure recording.
- Quality metrics.
- API account lifecycle, auth enforcement, health, and public UI delivery.

## Verification Performed

### Automated checks

```text
pytest:        25 passed
ruff:          All checks passed
mypy:          Success: no issues found in 43 source files
alembic check: No new upgrade operations detected
```

### Live JEV verification

A live JEV call was executed against `https://polza.ai/api`:

- Model: `jev-1.14.0`.
- Sample message: horse transport request.
- Result: `is_order=true`.
- Confidence: `0.97` on the first sample; `0.94` on the second.
- Animal type: `horses`.
- JEV latency observed: approximately 1.1-3.9 seconds per request.
- Usage observed: 896 input / 272 output tokens for one sample.
- End-to-end SQLite persistence was also verified: message stored, classified,
  and marked `classified` with metrics updated.

### Migration verification

Verified on a fresh SQLite database:

- `alembic upgrade head` creates all six domain tables plus `alembic_version`.
- `alembic check` reports no drift.
- Application startup `ensure_schema` applies the same migration.
- The `alembic_version` row is `0001_phase0`.

### Max verification

Verified without a real account:

- `WebClient` construction with configured settings.
- Connector start, selected-chat filtering, edit/delete registration, reconnect
  state, and connection-failure propagation using a fake client.
- Session encryption and atomic restore logic.

Not yet verified against a real Max account:

- QR authentication end to end.
- Reading real group chats.
- Group attachment payloads.
- Real reconnect behavior over time.
- Max rate limits, warnings, or bans.

## Review Findings Addressed

A code review was run on the uncommitted implementation. The coordinated fixes
addressed:

- Unauthenticated data access beyond loopback.
- QR login link exposure after authentication.
- Weak session key derivation and placeholder keys.
- Unversioned runtime schema creation.
- Retention deleting by sender timestamp instead of receive time.
- Unbounded retention windows.
- Incomplete soft-delete behavior and deleted-message revival.
- Failed messages retrying forever and starving new work.
- Duplicate classification under concurrent runs.
- Max auth failures returning HTTP 200.
- Stale `connected` status after restart.
- JEV choice values not checked against criteria.
- JEV question duplication between the app and sandbox.
- Per-call JEV client creation.
- N+1 export queries and unbounded metrics loading.
- Serial batch classification.
- Incorrect reconnect counting.

## Remaining Work

Phase 0 acceptance is not complete until these are measured with a real account:

1. Authenticate a dedicated Max account through QR.
2. Select and monitor 5-10 real group chats.
3. Collect a representative message sample.
4. Manually label at least 100 messages.
5. Measure precision/recall against the 90% / 80% targets.
6. Measure message volume, ingestion latency, JEV latency, failure rate, and
   token cost per 1,000 messages.
7. Run for multiple days and record reconnects, session survival, account
   warnings, and bans.
8. Review Max ToS, 152-FZ data residency, and JEV data-processing terms.
9. Decide whether Max is suitable for Phase 1 or whether to switch to VK or
   Telegram.

Known Phase 0 limitations:

- Real Max account behavior is unverified.
- JEV cannot perform free-text route/date/price/contact extraction.
- Max 2FA still uses the console password provider.
- SQLite and the in-process connector registry are suitable for a single-process
  spike, not a production multi-worker deployment.
- No automated media processing (OCR/ASR/image/PDF) is implemented.

## Go/No-Go Status

Undecided. The implementation is ready for a real-account trial, but the
go/no-go decision still depends on:

- Stable Max group-chat access.
- Acceptable account and legal risk.
- Dependable JEV output.
- Measured recall close to the 80% target.
- Acceptable session uptime and processing cost.

## How to Run

```bash
uv sync
cp .env.example .env
# Set MERGECHAT_SESSION_ENCRYPTION_KEY and MERGECHAT_JEV_API_KEY.
# Generate a key with: openssl rand -base64 32

uv run mergechat
# Swagger UI: http://127.0.0.1:8000/docs
```

With a non-loopback bind, also set `MERGECHAT_API_TOKEN`.

```bash
MERGECHAT_API_HOST=0.0.0.0 MERGECHAT_API_TOKEN=<token> uv run mergechat
```

Run checks:

```bash
uv run pytest
uv run ruff check src tests scripts
uv run mypy src/mergechat
uv run alembic check
```

## Session Artifacts

- `src/mergechat/` - application code, including the bundled GUI under `web/`.
- `migrations/` - Alembic schema.
- `tests/` - 25 tests.
- `scripts/` - listener, classification, export, and retention helpers.
- `README.md` - setup and usage.
- `docs/phase-0-report.md` - earlier evidence report scaffold.
- `PHASE_0_RESULT.md` - this session result.
