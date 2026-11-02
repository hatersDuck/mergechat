# Phase 0 Python Project Plan

## Objective

Build a controlled feasibility spike for **Max** that verifies whether the core product hypothesis is technically and operationally viable:

- Connect one real Max account using `PyMax`.
- Read 5-10 real chats selected by the account owner.
- Normalize incoming messages.
- Store messages for analysis.
- Run order detection and attribute extraction through **JEV**.
- Provide a minimal FastAPI onboarding interface for session creation and chat selection.
- Manually label detected messages and calculate quality, latency, usage, and session stability.

Phase 0 must not attempt to implement the complete production pipeline.

## Scope

### Included

- Python project scaffolding.
- Max connector wrapper around `PyMax`.
- Account/session onboarding through FastAPI.
- Chat discovery and selection.
- Passive message reading.
- Message normalization.
- Persistent local storage.
- JEV integration.
- Basic order classification and attribute extraction.
- Manual labeling workflow.
- Message deduplication and idempotent storage.
- Structured logs and operational measurements.
- A spike report with a go/no-go recommendation.

### Excluded

- VK connector.
- Telegram delivery bot.
- WhatsApp.
- Redis queues.
- Production PostgreSQL deployment.
- Automatic replies to Max chats.
- Multi-client account management.
- Full web cabinet.
- Feedback-based automatic model retraining.
- OCR, ASR, image processing, and PDF parsing.

## Recommended Stack

- Python 3.12+
- `uv` for dependency and environment management
- FastAPI and Uvicorn
- Pydantic v2
- SQLAlchemy 2.x
- SQLite for the spike, with database models compatible with PostgreSQL
- Alembic migrations
- `PyMax` for Max access
- JEV official Python client or HTTP API via `httpx`
- `pytest` and `pytest-asyncio`
- Ruff
- Mypy or Pyright
- JSON structured logging

The application should be asynchronous because Max event consumption, FastAPI requests, and JEV requests are I/O-bound.

## Project Structure

```text
mergechat/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── alembic.ini
├── docs/
│   └── phase-0-report.md
├── src/
│   └── mergechat/
│       ├── __init__.py
│       ├── config.py
│       ├── logging.py
│       ├── main.py
│       ├── api/
│       │   ├── app.py
│       │   ├── dependencies.py
│       │   └── routes/
│       │       ├── accounts.py
│       │       ├── chats.py
│       │       ├── messages.py
│       │       ├── classifications.py
│       │       └── labels.py
│       ├── domain/
│       │   ├── account.py
│       │   ├── chat.py
│       │   ├── message.py
│       │   ├── classification.py
│       │   └── label.py
│       ├── connectors/
│       │   ├── base.py
│       │   └── max/
│       │       ├── client.py
│       │       ├── connector.py
│       │       ├── normalizer.py
│       │       └── session.py
│       ├── processing/
│       │   ├── ingestion.py
│       │   ├── deduplication.py
│       │   ├── classifier.py
│       │   └── metrics.py
│       ├── jev/
│       │   ├── client.py
│       │   ├── schemas.py
│       │   ├── prompts.py
│       │   └── service.py
│       ├── storage/
│       │   ├── database.py
│       │   ├── models.py
│       │   └── repositories.py
│       └── security/
│           └── sessions.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── scripts/
    ├── run_max_listener.py
    ├── import_messages.py
    ├── classify_messages.py
    └── export_dataset.py
```

## Core Design

### Max Connector

Define a platform-independent connector interface even though Phase 0 contains only Max:

```python
class Connector(Protocol):
    async def connect(self, session: AccountSession) -> None: ...
    async def list_chats(self) -> list[ChatInfo]: ...
    async def subscribe(self, chat_ids: list[str]) -> None: ...
    async def health_check(self) -> HealthStatus: ...
    def normalize(self, message: object) -> RawMessage: ...
```

The Max implementation should:

- Wrap all direct `PyMax` calls.
- Keep platform-specific payloads out of the rest of the application.
- Expose connection and authorization failures as application exceptions.
- List available chats and subscribe only to explicitly selected chats.
- Read passively without sending messages.
- Record connector health and reconnect attempts.
- Preserve the original Max payload for debugging, subject to retention and privacy rules.

### FastAPI Onboarding

The initial web interface can be API-first, using minimal HTML or the automatically generated API documentation.

Suggested endpoints:

```text
POST   /accounts
POST   /accounts/{account_id}/connect
GET    /accounts/{account_id}/status
GET    /accounts/{account_id}/chats
POST   /accounts/{account_id}/chats/selection
POST   /accounts/{account_id}/listener/start
POST   /accounts/{account_id}/listener/stop
GET    /accounts/{account_id}/health
```

Onboarding flow:

1. Create a local account record.
2. Start Max authentication.
3. Complete the authentication/session flow required by `PyMax`.
4. Encrypt and persist the resulting session data.
5. Retrieve available chats.
6. Select 5-10 chats.
7. Start the passive listener.
8. Display connection status and the last received message time.

Session secrets must not appear in API responses or logs.

### Message Normalization

All Max messages should be converted into a platform-independent structure:

```python
RawMessage(
    platform="max",
    external_message_id="...",
    external_chat_id="...",
    author_external_id="...",
    author_name="...",
    text="...",
    timestamp=...,
    attachments=[],
    raw_payload=...,
)
```

The normalizer must explicitly handle text, empty text, edits, deletes if exposed by Max, forwarded messages, attachments as metadata, missing fields, and unknown message types.

### Storage

Phase 0 should contain at least these tables:

- `account_sessions`
- `chats`
- `raw_messages`
- `classifications`
- `manual_labels`
- `processing_runs`

Important constraints:

- Unique constraint on `(platform, external_chat_id, external_message_id)`.
- Timestamps stored in UTC.
- Raw payload stored separately from normalized fields.
- Processing status tracked per message.
- JEV request and response metadata stored without secrets.
- Session data encrypted before persistence.

The schema must avoid SQLite-specific behavior so it can later move to PostgreSQL with minimal changes.

### JEV Integration

JEV should be isolated behind an application service rather than called directly from processing code.

Responsibilities:

```text
jev/client.py
- Authentication
- HTTP or SDK calls
- Timeout and retry handling
- Response parsing

jev/schemas.py
- Classification request
- Classification response
- Order attribute schema

jev/prompts.py
- Versioned prompt text
- System and user prompt construction

jev/service.py
- Classify one or more messages
- Validate structured output
- Record usage and latency
```

Expected result schema:

```json
{
  "is_order": true,
  "confidence": 0.91,
  "keywords": ["перевозка", "лошадь", "нужен транспорт"],
  "route": {
    "from": null,
    "to": null
  },
  "date": null,
  "cargo_type": "horse",
  "price": null,
  "contact": null,
  "reason": "Message asks for horse transportation."
}
```

Before implementation, verify JEV's official Python package or HTTP API, authentication, structured-output support, batch support, usage reporting, and data-residency implications under 152-FZ.

Malformed responses must be rejected and marked for manual review rather than silently accepted.

### Classification Strategy

Do not implement the complete Redis-based prefilter and batch pipeline during Phase 0. Use two manually triggered modes:

- Single-message classification for debugging and latency measurement.
- Dataset batch classification for quality evaluation.

The classifier should load unprocessed normalized messages, submit bounded batches to JEV, validate every response, store confidence and extracted attributes, record prompt version and latency, and export results for manual labeling.

A basic keyword prefilter may be tested experimentally. Compare JEV on all messages against JEV only on keyword-matching messages to estimate cost reduction and recall loss.

## Implementation Sequence

### 1. Establish the Python package

Create `pyproject.toml`, the `src/` package, test configuration, Ruff and typing configuration, environment configuration, and local run documentation.

Acceptance criteria:

- Application imports successfully.
- Tests run without external services.
- Missing required secrets produce clear configuration errors.

### 2. Build storage models

Implement the Phase 0 schema, migrations, and repositories.

Acceptance criteria:

- Database initializes from a clean directory.
- Duplicate external messages are ignored safely.
- Raw and normalized fields can be queried independently.
- Session data is never returned by normal repository methods.

### 3. Validate PyMax independently

Before integrating FastAPI, verify authentication, session persistence, chat listing, group-chat support, message reading, reconnect behavior, rate limits, payload shape, attachments, forwarded messages, and account-ban or ToS concerns.

Use a dedicated test account where possible.

### 4. Implement the Max connector

Wrap verified PyMax operations in the connector interface.

Acceptance criteria:

- Connector connects and reports health.
- Connector lists chats.
- Connector subscribes only to selected chats.
- Incoming messages are normalized.
- Unknown payloads do not terminate ingestion.

### 5. Add FastAPI onboarding

Implement account creation, Max session connection, chat listing, chat selection, listener start/stop, and health endpoints.

### 6. Implement ingestion and persistence

Run a background listener that receives Max events, normalizes them, checks idempotency, stores them, records ingestion latency, and continues after individual malformed events.

Acceptance criteria:

- At least 5-10 chats can be monitored.
- Messages survive listener restarts.
- Duplicate events do not create duplicate rows.
- Listener errors are visible and recoverable.

### 7. Integrate JEV

Implement the JEV client, schemas, prompts, and classification service.

Acceptance criteria:

- A stored message can be classified manually.
- Structured output is validated.
- Invalid output is recorded as a failed attempt.
- Request latency and usage are recorded.
- Credentials and raw authentication headers never appear in logs.

### 8. Create the labeling workflow

Provide an API or export/import workflow for labels:

```text
GET  /messages?unlabeled=true
POST /messages/{message_id}/label
GET  /classifications/export
POST /labels/import
```

Supported labels should be `order`, `not_order`, and `uncertain`, with timestamp, labeler, and optional comment.

### 9. Measure the hypothesis

Run the system against a representative sample and measure:

- Monitored chats and received messages.
- Messages per chat per day.
- Ingestion and JEV latency.
- JEV failure rate and usage/cost.
- Precision, recall, false positives, and false negatives.
- Session uptime and reconnection count.
- Account warnings or bans.

Track the design-document targets of precision above 90% and recall above 80%, while prioritizing recall because missing an order is usually worse than a false positive.

## Security Requirements

- Encrypt session data with a key supplied outside the database.
- Never log session tokens.
- Never return secrets through the API.
- Keep `.env` out of git.
- Use a separate test account.
- Obtain explicit account consent before monitoring.
- Make message retention configurable.
- Redact phone numbers and tokens in logs.
- Provide session revoke/delete functionality.
- Audit connect, disconnect, and chat-selection actions.

An environment-provided encryption key is acceptable for Phase 0. KMS/HSM integration belongs to production hardening.

## Phase 0 Acceptance Criteria

The spike must answer these questions with evidence:

1. Can PyMax authenticate a real Max account reliably?
2. Can the connector read group chats?
3. Can it monitor at least 5-10 selected chats?
4. Does the listener survive reconnects and restarts?
5. Can messages be normalized and deduplicated?
6. Can JEV classify messages with valid structured output?
7. Does the classifier approach the 80% recall and 90% precision targets?
8. What is the average processing latency?
9. What is JEV usage or cost per 1,000 messages?
10. Are platform restrictions, warnings, or ban risks acceptable?
11. Is FastAPI onboarding practical for the Max session model?
12. Is Max suitable for Phase 1, or should the project switch to VK or Telegram?

## Deliverables

- Working Python repository.
- Max connector prototype.
- FastAPI onboarding API.
- Database schema and migrations.
- Stored normalized message sample.
- JEV integration and versioned prompts.
- Labeled evaluation dataset.
- Precision/recall report.
- Latency and usage report.
- Max connector risk report.
- List of unsupported message types.
- Phase 1 recommendation.

## Go/No-Go Criteria

### Continue to Phase 1 if

- Max reliably reads selected group chats.
- No unacceptable account or legal risk is found.
- JEV produces valid structured output.
- Recall is close to the 80% target and can plausibly improve.
- Session uptime is acceptable.
- FastAPI onboarding is usable.
- Processing cost is compatible with expected client economics.

### Stop or change direction if

- Max cannot provide stable access to required chats.
- Session authentication is too fragile or unsafe.
- Platform restrictions make passive monitoring unacceptable.
- JEV cannot return dependable structured output.
- Recall remains materially below target after prompt iteration.
- Account risk is too high.
- Cost per message or client is not viable.

## Future Phase 1

If the spike succeeds, extend this foundation with:

- PostgreSQL.
- Redis Streams.
- Immediate control-word prefilter.
- Fifteen-minute batch scheduler.
- Telegram notification bot.
- `OrderCard` delivery.
- Feedback buttons.
- Session health workers.
- VK connector.
- Production retention and encryption strategy.

The immediate implementation target is **Max connection, selected-chat ingestion, persistent messages, JEV classification, and evidence-based evaluation**.
