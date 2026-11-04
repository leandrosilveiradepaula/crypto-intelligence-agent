"""J1/OPS22: disposable WS x REST single-candle corroboration, never trading.

One public WebSocket subscription and at most ONE public HTTP GET. All candle
content remains in process memory; output is only allowlisted counters/status.
This compares two transports from the SAME provider, not independent venues.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import math
import os
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .bybit_linear_candle_research import stage_bybit_linear_kline
from .bybit_public_ws_once import (
    StreamSession, _bounded_json, _is_public_pong, _subscription_ack,
    _validate_one_kline_row,
)
from .bybit_ws_rest_offline_corroboration import corroborate_anomalous_close_offline
from .market_data import DataGapError, DataValidationError
from .research_registry_catalog import load_reviewed_registry

HOUR_MS = 3_600_000
MAX_FRAMES = 256
MAX_PREACK_MARKET_FRAMES = 8
MAX_SECONDS = 90
MAX_BODY_BYTES = 32_768
MAX_WAIT_AFTER_WS_SECONDS = 3
REST_TIMEOUT_SECONDS = 8
SYMBOL = "BTCUSDT"
TOPIC = "kline.60.BTCUSDT"
REST_ENDPOINT = "https://api.bybit.com/v5/market/kline"


@dataclass(frozen=True)
class OneCandleCorroboration:
    status: str
    subscription_acks: int = 0
    ws_frames: int = 0
    ws_anomalous_closes_observed: int = 0
    rest_gets: int = 0
    fields_compared: int = 0
    fields_equal: int = 0

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "subscription_acks": self.subscription_acks,
            "ws_frames": self.ws_frames,
            "ws_anomalous_closes_observed": self.ws_anomalous_closes_observed,
            "rest_gets": self.rest_gets,
            "fields_compared": self.fields_compared,
            "fields_equal": self.fields_equal,
            "same_provider_two_transports_only": True,
            "ws_candle_approved": False,
            "source_authenticated": False,
            "canonical_ohlcv_approved": False,
            "marketwide_top50_verified": False,
            "closed_24h_complete": False,
            "data_stored": False,
            "credentials_used": False,
            "orders_sent": False,
            "live_trading_authorized": False,
        }


def public_rest_once(start_ms: int, end_ms: int) -> dict:
    """Exactly one request, no retries or redirects to other hosts."""
    if (type(start_ms) is not int or type(end_ms) is not int or
            start_ms <= 0 or start_ms % HOUR_MS or
            end_ms != start_ms + HOUR_MS - 1):
        raise DataValidationError("REST hour range invalid")
    query = urlencode({
        "category": "linear", "symbol": SYMBOL, "interval": "60",
        "start": start_ms, "end": end_ms, "limit": 1,
    })
    req = Request(REST_ENDPOINT + "?" + query, method="GET",
                  headers={"Accept": "application/json", "User-Agent": "CIA-OPS22-public-research/1"})
    # urlopen normally follows redirects. Refuse redirects to preserve single
    # endpoint/network destination without trusting unreviewed Location.
    from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    with build_opener(NoRedirect(), HTTPSHandler()).open(req, timeout=REST_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise DataValidationError("REST response status invalid")
        if response.headers.get("Content-Length"):
            length = int(response.headers["Content-Length"])
            if length > MAX_BODY_BYTES or length < 1:
                raise DataValidationError("REST payload size invalid")
        raw = response.read(MAX_BODY_BYTES + 1)
    if len(raw) < 2 or len(raw) > MAX_BODY_BYTES:
        raise DataValidationError("REST response exceeds bounded size")
    payload = json.loads(raw)
    if type(payload) is not dict:
        raise DataValidationError("REST response envelope invalid")
    return payload


def compare_one_candle_once(
    *, session_factory: Callable[[], StreamSession],
    rest_fetch_once: Callable[[int, int], dict],
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
    seconds: int = MAX_SECONDS,
    max_frames: int = MAX_FRAMES,
) -> OneCandleCorroboration:
    """One already-authorized, disposable probe. No persistent artifacts."""
    if (not callable(session_factory) or not callable(rest_fetch_once)
            or not callable(clock) or not callable(wall_ms)
            or not callable(sleeper) or type(seconds) is not int
            or not 30 <= seconds <= MAX_SECONDS or type(max_frames) is not int
            or not 2 <= max_frames <= MAX_FRAMES):
        return OneCandleCorroboration("capability_abstain")
    ack = frames = closed = gets = 0
    preack_market_frames = 0
    outcome = "ws_no_qualifying_close_abstain"
    candidate = None
    receipt = 0
    started = clock()
    if type(started) not in (int, float) or not math.isfinite(started):
        return OneCandleCorroboration("clock_abstain")
    last_ping = started
    pending_ping = None
    try:
        with closing(session_factory()) as session:
            session.send(json.dumps({"op": "subscribe", "req_id": "cia-ops22-single",
                                     "args": [TOPIC]}, separators=(",", ":")))
            while frames < max_frames:
                now_mono = clock()
                remaining = seconds - (now_mono - started)
                if remaining <= 0:
                    break
                if pending_ping is not None and now_mono - pending_ping >= 45:
                    outcome = "ws_pong_timeout_abstain"
                    break
                if now_mono - last_ping >= 20:
                    session.send('{"op":"ping"}')
                    last_ping = now_mono
                    if pending_ping is None:
                        pending_ping = now_mono
                try:
                    data = session.recv(min(remaining, 5.0))
                except TimeoutError:
                    continue
                frames += 1
                frame = _bounded_json(data)
                if _is_public_pong(frame):
                    pending_ping = None
                    continue
                if frame.get("op") == "subscribe":
                    if (ack or not _subscription_ack(frame) or
                            frame.get("req_id", "") not in ("", "cia-ops22-single")):
                        outcome = "ws_ack_invalid_abstain"
                        break
                    ack = 1
                    outcome = "ws_no_qualifying_close_abstain"
                    continue
                if "op" in frame:
                    outcome = "ws_unexpected_control_abstain"
                    break
                if not ack:
                    # Bybit may deliver subscribed-topic data before ACK.
                    # Discard a bounded number of structurally valid envelopes:
                    # never buffer, validate as candle, or retroactively promote.
                    if (type(frame) is not dict or set(frame) !=
                            {"topic", "type", "ts", "data"} or
                            frame.get("topic") != TOPIC or
                            frame.get("type") != "snapshot" or
                            type(frame.get("ts")) is not int or
                            type(frame.get("data")) is not list or
                            len(frame["data"]) != 1 or
                            type(frame["data"][0]) is not dict):
                        outcome = "ws_preack_envelope_abstain"
                        break
                    preack_market_frames += 1
                    if preack_market_frames > MAX_PREACK_MARKET_FRAMES:
                        outcome = "ws_preack_budget_abstain"
                        break
                    outcome = "ws_ack_missing_abstain"
                    continue
                if (type(frame) is not dict or set(frame) !=
                        {"topic", "type", "ts", "data"} or
                        frame["topic"] != TOPIC or frame["type"] != "snapshot" or
                        type(frame["ts"]) is not int or type(frame["data"]) is not list or
                        len(frame["data"]) != 1 or type(frame["data"][0]) is not dict):
                    outcome = "ws_envelope_abstain"
                    break
                row = frame["data"][0]
                now = wall_ms()
                if type(now) is not int or now <= 0:
                    outcome = "clock_abstain"
                    break
                start, end, stamp = row.get("start"), row.get("end"), row.get("timestamp")
                if (any(type(x) is not int for x in (start, end, stamp)) or
                        start <= 0 or start % HOUR_MS or
                        end != start + HOUR_MS - 1 or
                        type(row.get("confirm")) is not bool):
                    outcome = "ws_row_abstain"
                    break
                # Do not trust a confirmed *different* hour, stale frame or
                # future event. Only the most recently completed UTC hour.
                last_hour = (now // HOUR_MS - 1) * HOUR_MS
                if row["confirm"] is not True:
                    _validate_one_kline_row(row, frame["ts"], now,
                                            diagnostic_ignore_trade_stamp=True)
                    continue
                if (start != last_hour or not end < stamp <= frame["ts"] <= now or
                        not end + 1 <= now <= end + 120_001):
                    outcome = "ws_close_chronology_abstain"
                    break
                _validate_one_kline_row(row, frame["ts"], now,
                                        diagnostic_ignore_trade_stamp=True)
                candidate = frame
                receipt = now
                closed = 1
                break
        if candidate is None:
            return OneCandleCorroboration(outcome, ack, frames, closed)
        # The REST sample MUST be observed after close +1s. Do not rewrite the
        # WS receipt time. A possible early WS close is only compared by the
        # separate non-authorizing early-receipt switch in OPS21.
        cutoff = candidate["data"][0]["end"] + 1 + 1_000
        time_to_wait = max(0, cutoff - wall_ms())
        if time_to_wait > MAX_WAIT_AFTER_WS_SECONDS * 1000:
            return OneCandleCorroboration("rest_window_abstain", ack, frames, closed)
        if time_to_wait:
            sleeper(time_to_wait / 1_000)
        at_rest = wall_ms()
        if (type(at_rest) is not int or at_rest < cutoff or
                at_rest - receipt > 15_000):
            return OneCandleCorroboration("rest_clock_abstain", ack, frames, closed)
        begin = candidate["data"][0]["start"]
        end = candidate["data"][0]["end"]
        gets = 1  # count attempted requests, including failures
        try:
            page = rest_fetch_once(begin, end)
        except HTTPError as error:
            code = "rest_rate_limit_abstain" if error.code in (429, 418) else "rest_http_abstain"
            return OneCandleCorroboration(code, ack, frames, closed, gets)
        except (OSError, TimeoutError, URLError, ValueError, TypeError, UnicodeError):
            return OneCandleCorroboration("rest_transport_abstain", ack, frames, closed, gets)
        if type(page) is not dict or type(page.get("retCode")) is not int:
            return OneCandleCorroboration("rest_envelope_abstain", ack, frames, closed, gets)
        if page["retCode"] == 10006:
            return OneCandleCorroboration("rest_rate_limit_abstain", ack, frames, closed, gets)
        if page["retCode"] != 0:
            return OneCandleCorroboration("rest_rejected_abstain", ack, frames, closed, gets)
        # stage() requires contemporaneous contract metadata. It is asserted
        # locally as a synthetic research fixture, NEVER venue-authenticated.
        reference = stage_bybit_linear_kline(
            page, symbol=SYMBOL, quote_currency="USDT",
            contract_type="LinearPerpetual", contract_status="Trading",
            contract_observed_at_ms=at_rest, observed_at_ms=at_rest,
            max_contract_age_ms=0, interval="1h",
            start_open_ms=begin, end_open_ms=begin + HOUR_MS,
            close_safety_ms=1000, max_candles=1)
        result = corroborate_anomalous_close_offline(
            frame=candidate, received_at_ms=receipt, reference=reference,
            diagnostic_early_receipt=True)
        return OneCandleCorroboration(
            "ws_rest_match_unverified" if result.fields_equal == 6 else
            "ws_rest_diverge_abstain", ack, frames, closed, gets,
            result.fields_compared, result.fields_equal)
    except (DataGapError, DataValidationError, ValueError, TypeError, KeyError, AttributeError):
        return OneCandleCorroboration("validation_abstain", ack, frames, closed, gets)
    except (OSError, TimeoutError, RuntimeError, ImportError):
        return OneCandleCorroboration("ws_transport_abstain", ack, frames, closed, gets)
    except Exception:
        return OneCandleCorroboration("unexpected_abstain", ack, frames, closed, gets)


def owner_compare_one_candle(*, allow_public_network: bool = False,
                             allow_public_websocket: bool = False,
                             allow_one_public_rest_get: bool = False,
                             confirm_region_and_personal_research: bool = False,
                             session_factory=None, rest_fetch_once=None,
                             clock: Callable[[], float] = time.monotonic,
                             wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
                             sleeper: Callable[[float], None] = time.sleep) -> OneCandleCorroboration:
    if (allow_public_network is not True or allow_public_websocket is not True or
            allow_one_public_rest_get is not True or
            confirm_region_and_personal_research is not True):
        return OneCandleCorroboration("owner_opt_in_required")
    if os.name != "posix" or os.geteuid() == 0:
        return OneCandleCorroboration("owner_nonroot_required")
    try:
        registry = load_reviewed_registry("expanded-52", as_of_ms=wall_ms())
        if not any(a.base == "BTC" for a in registry.assets):
            return OneCandleCorroboration("registry_invalid_abstain")
    except (DataValidationError, ValueError, TypeError, OSError):
        return OneCandleCorroboration("registry_invalid_abstain")
    if session_factory is None:
        from .bybit_public_ws_once import _real_session_factory
        session_factory = _real_session_factory
    if rest_fetch_once is None:
        rest_fetch_once = public_rest_once
    return compare_one_candle_once(
        session_factory=session_factory, rest_fetch_once=rest_fetch_once,
        clock=clock, wall_ms=wall_ms, sleeper=sleeper,
    )
