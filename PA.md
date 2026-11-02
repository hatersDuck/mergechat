# Messenger order aggregation system — design document v0.2
**Status:** early concept / hypothesis validation.  
**Author:** solo engineer.  
**Note:** this is an overall picture, not a final technical specification. `TODO` means the item is intentionally unresolved and should be validated by a spike.
---

## 1. Setting the task
The client is a private carrier (horse carrier). Orders appear in many work chats across different messengers: VK, Telegram, WhatsApp, Max, and possibly others. The client is often on the move and does not want to manually monitor chats.
The service reads selected chats, uses an LLM to identify order messages, and sends only relevant orders to the client.
Key filtering idea:
- **Primary pass:** batch LLM classification every 15 minutes.  
  Prompt: “Here is the list of messages. Mark where the order is located and specify the keywords by which you identified it.”
- **Secondary pass:** the LLM extracts control words. These words go into a prefilter. Messages containing control words are processed immediately, without waiting for the batch.
- **Extension:** the LLM extracts order attributes such as route, date, type of shipment, price, and contact, turning a notification into an order card.
The product is not a general chat monitor. It is an order-detection tool for a chat participant, acting on the client’s behalf.
---
## 2. Scope and non-goals
### In scope for MVP
- Connect client sessions for selected platforms.
- Read selected group chats.
- Normalize and store messages.
- Detect order messages using prefilter + LLM.
- Extract basic order attributes.
- Send notifications and order cards to the client.
- Collect “not an order” feedback.
### Out of scope for MVP
- Sending messages automatically to chats.
- Official omnichannel customer-support features.
- A farm of technical accounts.
- Full web cabinet, if the Telegram bot is sufficient for the first hypothesis.
- WhatsApp, unless legal and ban risks are resolved.
### Platform priority
Initial MVP candidate: **Max + VK**.  
WhatsApp is high-risk and deferred.
---
## 3. Account connection architecture
**Selected model:** client-owned sessions live and work on our server. The client logs in to the required platforms, then selects the chats to monitor. The server subscribes to updates from those chats.
Onboarding flow:
1. Client starts onboarding.
2. Client connects a platform account.
3. Session is stored securely on the server.
4. System retrieves the list of chats available to that account.
5. Client marks the chats to monitor.
6. Server subscribes to updates from selected chats.
The alternative “farm of technical accounts” model is postponed. It is more expensive and becomes relevant when scaling to many clients. The code should keep an `AccountProvider` abstraction so the session source can be switched later.
**Private chats:** the client first enters the chat from their phone, then clicks “update list” in the UI. The system refreshes the chat list.
**MVP UI:** a Telegram bot. It can use inline keyboards and a checkbox-like buttons for chat selection. For non-Telegram platforms, login/session creation may still require a minimal web flow or another onboarding mechanism. `TODO`.
---
## 4. Technical implementation by platform
This section is intentionally incomplete. Platform connectors are the core product and must be validated before full implementation.
| Platform | Candidate method | Status | Key questions |
|---|---|---|---|
| Max | PyMax (Python library) | Candidate | Can it read group chats? Session model? Rate limits? Ban risk? Media? |
| VK | TODO | TODO | User token / LongPoll? Group chat access? Limits? ToS risk? |
| Telegram | TODO | TODO | Bot API cannot read arbitrary chats. MTProto userbot likely. Ban risk? Session security? |
| WhatsApp | TODO | Deferred | Unofficial userbot is high ban risk. Official API cannot read arbitrary group chats as a participant. Legal review needed. |
| Others | TODO | TODO | Evaluate only after first two platforms work. |
**Important:** the platform layer must be isolated behind a connector interface. Each connector should expose:
- `connect(session)`
- `list_chats()`
- `subscribe(chat_ids)`
- `normalize(message) -> RawMessage`
- `health_check()`
This allows replacing or adding platforms without rewriting the pipeline.
---
## 5. Message processing pipeline
Pipeline:
`Chat Connector -> Redis queue -> normalization -> PostgreSQL -> prefilter -> LLM -> order cards -> delivery`
Steps:
1. **Normalization** to a single format:  
   `{platform, chat, author, text, timestamp, attachments, message_id}`
2. **Storage:** save all messages in PostgreSQL. History is valuable and allows reprocessing.
3. **Prefilter:** match against the control-word base.  
   - Match: immediate LLM run.  
   - No match: send to packet buffer.
4. **Batch classification:** every 15 minutes or after N accumulated messages. One prompt per package. Select orders, extract attributes (route, date, cargo, price, contact), and specify control words. Batching is cheaper and faster than per-message processing.
5. **Feedback loop:** new control words are added to the prefilter after moderation.
6. **Delivery:** notification + order card + feedback button “not an order” for additional filter training.
**Aggregation clarification:** “wait all connectors” should not block processing indefinitely. Each connector flushes with a timeout. If one platform is slow, the batch proceeds without it.
### Latency SLA
Because the product value includes “be first to respond,” latency matters.
- Known control words: target **< 1–2 minutes**.
- Unknown messages in batch: target **< 15 minutes**.
- `TODO`: validate whether 15 minutes is acceptable for the target chats. If not, reduce batch interval or improve prefilter coverage.
---
## 6. Minimal data model
- `AccountSession`: platform, encrypted session data, status, last health check.
- `Chat`: platform, external chat ID, title, selected flag.
- `RawMessage`: chat, author, text, timestamp, attachments, raw payload.
- `OrderCard`: source message, route, date, cargo type, price, contact, confidence, status.
- `ControlWord`: word/phrase, source, active flag, moderation status.
- `Feedback`: order card, user label (“order” / “not order”), timestamp.
All sensitive fields must be encrypted at rest where applicable.
---
## 7. MVP UI: Telegram bot
The first UI is a Telegram bot.
Possible commands:
- `/start` — onboarding.
- `/connect` — connect a platform session.
- `/chats` — show chat list.
- `/select` — select chats using checkbox-like inline keyboards.
- `/orders` — show recent order cards.
- `/feedback` — mark an order as “not an order”.
The Telegram bot can handle chat selection. For non-Telegram session login, a minimal web page or deep-link flow may be needed. `TODO`.
---
## 8. LLM quality and evaluation
This is a first hypothesis, not a solved problem.
Needs:
- A labeled dataset of real horse-transport chats.
- A defined output schema in JSON.
- Prompt versioning.
- Precision and recall targets.
- Cost per 1,000 messages.
- Confidence threshold and fallback rules.
For order detection, **missing an order is usually worse than a false positive**. Metrics should reflect that asymmetry.
Model choice is `TODO`. Data flow must respect 152-FZ. If messages contain personal data, sending them to a foreign LLM may create cross-border transfer issues. Local or Russian-hosted models should be evaluated.
Feedback button “not an order” is part of the training and correction loop.
---
## 9. Security, legal, and compliance
### Session security
Session files and tokens give full access to the client’s account.
Requirements:
- Encryption at rest.
- Key stored outside the database.
- KMS/HSM or equivalent.
- No tokens in logs.
- Audit access.
- Revocation flow.
- Explicit client consent.
A server compromise must not expose all client sessions in plaintext.
### Platform ToS and legal risk
- Positioning as “a tool of the chat participant on his behalf” does not automatically eliminate ToS violations.
Legal review is required before WhatsApp and possibly before VK.
### 152-FZ
The system processes personal data: names, phone numbers, routes, possibly cargo details.
Requirements:
- Privacy policy.
- Storage in the Russian Federation.
- Data minimization.
- Retention policy.
- Clear LLM data-processing terms.
### Account bans
Mitigations:
- Passive reading only.
- No outgoing messages from monitoring.
- Backup connectors. 
- Session health monitoring.
- Reauthorization flow in the UI.
- Platform-specific rate limits.
---
## 10. Risks
| Risk | Severity | Mitigation |
|---|---|---|
| Account bans, especially WhatsApp | High | Passive reading, no outgoing messages, backup connectors, health checks, defer WhatsApp |
| Legal / platform ToS | High | Legal review, positioning, avoid high-risk platforms until resolved |
| 152-FZ personal data | High | RF storage, minimization, retention, careful LLM data flow |
| Session security | High | Encryption at rest, key outside DB, no logging, audit, revocation |
| LLM false positives / omissions | Medium | Confidence threshold, keyword OR LLM duplication, feedback button |
| Private chats not visible | Medium | Client enters chat manually, then “update list” |
| Latency too high for “first to respond” | Medium | Immediate prefilter, shorter batch interval, SLA measurement |
| Platform API fragility | Medium | Connector abstraction, health checks, graceful degradation |
| Cost per client | Medium | Batch LLM, prefilter, measure tokens per order |
---
## 11. MVP plan and estimates
**Status:**  This is early. Timeline and budget are not final.
MVP definition:
- Connect sessions.
- Select groups to read.
- Read messages.
- Detect orders.
- Notify via Telegram bot.
- Store in DB.
Initial platform candidate: **Max + VK**.  
Max has a Python library candidate: PyMax.  
VK is `TODO`.  
### Phases
**Phase 0 — Feasibility spike**
- Pick one platform (Max or Telegram).
- Connect a real session.
- Read 5–10 real chats.
- Manually label orders.
- Measure detection quality, latency, cost, and ban risk.
**Phase 1 — MVP**
- Add second platform if Phase 0 succeeds.
- Implement Redis queue, PostgreSQL storage, prefilter, LLM batch, Telegram bot delivery.
- Add feedback button.
**Phase 2 — Evaluation**
- Measure precision/recall.
- Check session survival over 30 days.
- Measure cost per client.
- Decide whether to continue, change platforms, or stop.
### MVP success metrics
- 1–2 platforms connected.
- 50 chats monitored.
- Precision > 90%.
- Recall > 80%.
- No bans in 30 days.
- LLM cost below an acceptable threshold per client per month.
---

## 12. Open questions / TODO
- Exact capabilities of PyMax for Max.
- VK connection method and ToS risk.
- Telegram connector choice: bot API vs MTProto userbot.
- WhatsApp: defer or reject.
- Minimal web onboarding for non-Telegram platforms.
- LLM model choice and data flow under 152-FZ.
- Labeled dataset and evaluation protocol.
- Latency SLA validation.
- Cost model.
- Session encryption and key management design.
- Media handling: images, voice, PDFs, OCR/ASR.
- Message edits, deletes, forwarded messages.
- Deduplication and idempotency.

---
## 13. Competitive analysis
This is a preliminary and superficial observation, not a current priority.
Two classes of competitors exist:
1. **Omnichannel aggregators for business** — Wazzup, Chat2Desk, Pact.im, Umnico, Teletype, Jivo. They provide a single window for messages from businesses to customers through official APIs. They do not monitor other people’s group chats where the client is just a participant.
2. **Chat order parsers** — Panteon Bot, Grabil Bot, Find Lead, JobRadar. Mostly keyword bots, almost all Telegram-only. Subscription around 490–1500 ₽/month. Small players; no obvious LLM classification.

At this stage, competitor analysis does not drive the design. The immediate task is to validate whether the platform connectors and LLM pipeline work at all.
---

## 14. Conclusion
This document describes the overall picture, not a final design.
The product thesis is plausible: semantic order detection across multiple messengers for a chat participant. The main uncertainties are platform access, legal/ToS risk, session security, latency, and LLM quality.