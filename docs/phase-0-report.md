# Phase 0 spike report

Status: in progress. Infrastructure is implemented; Max account evidence and a
labelled evaluation sample are still required.

## Verified so far

| Item | Evidence |
|---|---|
| JEV authentication and structured output | Live `system_one` call returned eight validated answers. |
| JEV model | `jev-1.14.0` |
| Sample order message | "6 horses Moscow -> St. Petersburg" classified `is_order=true`, confidence `0.97`. |
| JEV latency | ~1.1-3.9 s across two live requests. |
| JEV usage | 896 input tokens, 272 output tokens for the sample. |
| End-to-end classification | Sample message stored in SQLite, classified as order (`0.94`) and marked `classified`. |
| Message deduplication | Unit test ingests the same external id twice and stores one row. |
| Edit handling | Unit test updates the stored text for the same external id. |
| Session encryption | Unit tests cover roundtrip, missing key and wrong key. |
| Connector filtering | Unit test verifies only selected group chats are emitted. |
| Schema | Alembic `upgrade head` and `alembic check` pass on SQLite. |

## JEV capability finding

JEV system-one exposes `noul`, `choice`, `score` and `box` answers, not
arbitrary JSON extraction. The spike therefore cannot fill route, date, price
or contact as free text through JEV alone. It stores:

- `is_order` and confidence from the noul probability.
- Animal type, headcount and capacity fit as choices.
- Route/contact/quote presence as noul flags.
- `null` route/date/price/contact fields, with `attributes.extraction_notes`
  documenting the limitation.

A separate extraction model is needed if the product requires a complete
`OrderCard` from one call.

## Evidence still to collect

1. Max QR authentication with a dedicated account.
2. Successful listing and reading of 5-10 real group chats.
3. Listener restart and reconnect counts over a multi-day run.
4. Message volume per chat per day.
5. A manually labelled sample of at least 100 messages.
6. Precision, recall and false-negative review against the 90% / 80% targets.
7. Cost per 1,000 messages using recorded token usage.
8. Max warnings, restrictions or bans observed during the run.
9. Review of Max ToS, 152-FZ data residency and JEV data-processing terms.

## Go/no-go

Not decided. Continue only if Max access is stable, account risk is acceptable,
JEV output is dependable, and measured recall can plausibly reach the target.
