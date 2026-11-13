# J1 / D329 - Server-bounded trade clock metadata (research only)

## Live observed problem

On 13 November 2026, D328's first lease at 12:59:31-13:01:58 UTC processed 3,107 frames and ACK=1. It discarded **50 closed candidates** only because their last-trade timestamps were out of the declared candle hours. The SQLite received 0 confirmed rows and the systemd N2 fallback succeeded. The exact direction of those timestamps was NOT recorded, so their being postclose is a hypothesis, not a proved fact.

Bybit's official V5 websocket kline documentation uses confirm=true for a closed candle, start/end for its grid, outer ts for the server message generation time and inner timestamp for the last matched order. Reference: https://bybit-exchange.github.io/docs/v5/websocket/public/kline

## Narrow research compatibility

The strict offline parser remains default. Only the owner-active systemd runner may opt into admitting a confirmed kline with last-trade timestamp STRICTLY after end, provided it is not later than the original server ts, and that original server ts and original receipt are after the UTC hour close and within the pre-existing 120 second cap. No re-dating of metadata, OHLC, receipt or start/end; all 50 subscribed symbols, payload types, decimal and scope checks apply. A timestamp before start or after server remains non-evidence.

The private immutable SQLite stores the original last-trade timestamp and revalidates its causal server bound. The report counts accepted_postclose_trade_clock plus separate discarded_trade_before_start and discarded_trade_after_end_unbounded in aggregate, without prices, identities or raw timestamps. Default library users remain strictly fail-closed.

This is NOT authenticated financial data, independently validated OHLCV, permission for signals/orders, a reconstructed missing candle or a replacement for D323 24h/36h observations. Postclose metadata must be disclosed as a data-quality caveat and can be crosschecked through a separately gated, quota-bounded independent reference before research approval.

## Validation and deployment

test_j1_n50_ws_server_bounded_trade_clock_d329.py covers 50 postclose confirmed events, faithful immutable metadata, default strict rejection, prestart/server-future/stale/integrity negatives, no 24h and no orders. Recovery script D329 only updates the existing private D328 checkout from its pinned SHA, validates tests before quiescing N2 and reuses the installed WS/rotation timers with N2 rollback. No new rank bootstrap, 372 GET replay, database migration, or real trading. Full CI and SHA review before merge; deployment is an independent root gate.
