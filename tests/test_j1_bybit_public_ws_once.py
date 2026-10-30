"""J1 #328: all tests inject fake sockets; no real network."""
import json
import unittest
from unittest.mock import patch
from crypto_intelligence_agent.bybit_public_ws_once import observe_once, owner_probe, TOPIC, HOUR_MS

FIRST = 1793282400000
ACK = {"success":True,"ret_msg":"subscribe","conn_id":"private","op":"subscribe"}
def frame(confirm=True):
    return {"topic":TOPIC,"type":"snapshot","ts":FIRST+HOUR_MS+1200,"data":[{
        "start":FIRST,"end":FIRST+HOUR_MS-1,"interval":"60", "open":"10", "high":"11",
        "low":"9","close":"10","volume":"1.5","turnover":"15.0", "confirm":confirm,
        "timestamp":FIRST+HOUR_MS-500}]}

class Socket:
    def __init__(self, frames): self.frames=list(frames);self.closed=False;self.sent=[]
    def send(self,payload): self.sent.append(payload)
    def recv(self,timeout):
        if not self.frames: raise TimeoutError()
        v=self.frames.pop(0)
        if isinstance(v, Exception): raise v
        return json.dumps(v) if isinstance(v,dict) else v
    def close(self): self.closed=True

class Tests(unittest.TestCase):
    def call(self, frames, *, max_frames=4, tick=None):
        sock=Socket(frames)
        report=observe_once(session_factory=lambda:sock, wall_ms=lambda:FIRST+HOUR_MS+2000,
                            clock=tick or (lambda:0),max_frames=max_frames,max_seconds=2).sanitized_report()
        self.assertTrue(sock.closed)
        self.assertEqual(json.loads(sock.sent[0]),{"op":"subscribe","args":[TOPIC]})
        self.assertNotIn("private",str(report))
        self.assertNotIn("BTCUSDT",str(report))
        return report
    def test_closed_success(self):
        x=self.call([ACK,frame()]);self.assertEqual(x["confirmed_closed_events"],1)
        self.assertEqual(x["status"],"ws_one_closed_hour_observed_only")
        self.assertFalse(x["marketwide_top50_verified"])
    def test_open_stays_incomplete(self):
        x=self.call([ACK,frame(False)],max_frames=2);self.assertEqual(x["status"],"ws_frame_budget_exhausted")
    def test_failed_ack(self):
        bad=dict(ACK,success=False);self.assertEqual(self.call([bad])["status"],"ws_subscription_explicitly_rejected")
    def test_missing_ack_rejected(self):
        self.assertEqual(self.call([frame()],max_frames=1)["status"],"ws_unacknowledged_market_data")
    def test_bad_envelopes(self):
        mutations=[lambda f:f.update(topic="kline.5.BTCUSDT"), lambda f:f["data"][0].update(turnover="NaN"),
                   lambda f:f["data"][0].update(open=10.1), lambda f:f["data"][0].update(high="8"),
                   lambda f:f["data"][0].update(confirm=1), lambda f:f["data"][0].update(start=FIRST+1),
                   lambda f:f.update(ts=FIRST+HOUR_MS+9000), lambda f:f.update(type="delta")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                f=frame();mutate(f)
                self.assertEqual(self.call([ACK,f])["status"],"ws_failed_closed")
    def test_duplicate_json_and_oversized(self):
        self.assertEqual(self.call([ACK,'{"topic":1,"topic":2}'])["status"],"ws_failed_closed")
        self.assertEqual(self.call([ACK,"a"*20000])["status"],"ws_failed_closed")
    def test_socket_fails_no_retry(self):
        x=self.call([ACK,OSError("private credential error")]);self.assertEqual(x["status"],"ws_failed_closed")
    def test_timeout_no_polling_beyond_deadline(self):
        clocks=iter([0,3]);x=self.call([ACK],tick=lambda:next(clocks,3));self.assertEqual(x["status"],"ws_observation_timeout")
    def test_opt_in_blocks_network(self):
        with patch('crypto_intelligence_agent.bybit_public_ws_once._real_session_factory',side_effect=AssertionError("network")):
            x=owner_probe(allow_public_websocket=False,confirm_region_and_personal_research=True)
        self.assertEqual(x["frames_seen"],0)
        self.assertEqual(x["status"],"ws_owner_opt_in_or_posix_required")

    def test_first_frame_categories_never_echo_raw_fields(self):
        samples = [
            (dict(ACK, success=False, ret_msg="SECRET123"), "ws_subscription_explicitly_rejected"),
            ({"op":"subscribe", "success": True}, "ws_subscription_fields_missing"),
            (dict(ACK, surprise="SECRET123"), "ws_subscription_fields_unexpected"),
            (dict(ACK, success="true"), "ws_subscription_fields_invalid"),
            
            ({"op":"ping", "ret_msg":"pong"}, "ws_unexpected_control_before_ack"),
            ({"unknown":"SECRET123"}, "ws_unexpected_first_frame"),
        ]
        for payload, expected in samples:
            with self.subTest(expected=expected):
                result = self.call([payload])
                self.assertEqual(result["status"], expected)
                self.assertNotIn("SECRET123", str(result))
                self.assertFalse(result["subscription_acknowledged"])
                self.assertEqual(result["confirmed_closed_events"], 0)
                self.assertFalse(result["orders_sent"])


    def test_preack_closed_then_ack_promotes_only_after_ack(self):
        self.assertEqual(self.call([frame(), ACK])["confirmed_closed_events"], 1)

    def test_preack_open_then_ack_then_closed(self):
        self.assertEqual(self.call([frame(False), ACK, frame()])["confirmed_closed_events"], 1)

    def test_preack_rejected_ack_cannot_promote(self):
        bad = dict(ACK, success=False)
        x = self.call([frame(), bad])
        self.assertEqual(x["confirmed_closed_events"], 0)
        self.assertEqual(x["status"], "ws_subscription_explicitly_rejected")

    def test_preack_bad_frame_fails_closed(self):
        bad = frame()
        bad["topic"] = "kline.60.WRONGUSDT"
        self.assertEqual(self.call([bad])["status"], "ws_failed_closed")

    def test_preack_budget(self):
        self.assertEqual(self.call([frame()] * 9, max_frames=10)["status"], "ws_preack_frame_limit")

    def test_subsecond_confirmed_close_and_small_clock_skew(self):
        from crypto_intelligence_agent.bybit_public_ws_once import _check_closed
        f=frame()
        f["ts"]=FIRST+HOUR_MS+100
        self.assertTrue(_check_closed(f,received_ms=FIRST+HOUR_MS+100))
        self.assertTrue(_check_closed(f,received_ms=FIRST+HOUR_MS-800))

    def test_excessive_clock_skew_fails_safely(self):
        from crypto_intelligence_agent.bybit_public_ws_once import _check_closed
        from crypto_intelligence_agent.market_data import DataValidationError
        with self.assertRaises(DataValidationError):
            _check_closed(frame(),received_ms=FIRST+HOUR_MS-9000)
        sock=Socket([ACK,frame()])
        report=observe_once(session_factory=lambda:sock,wall_ms=lambda:FIRST+HOUR_MS-9000,
                            clock=lambda:0,max_frames=3,max_seconds=3).sanitized_report()
        self.assertEqual(report["status"],"ws_failed_closed")
        self.assertEqual(report["failure_category"],"kline_clock")
        self.assertNotIn("BTCUSDT",str(report))

    def test_post_ack_error_categories_are_sanitized(self):
        cases=[(dict(frame(),type="delta"),"kline_type"),
               (dict(frame(),ts=FIRST+HOUR_MS+9000),"kline_clock"),
               (dict(frame(),data=[dict(frame()["data"][0],turnover="NaN")]),"kline_decimal")]
        for bad,expected in cases:
            with self.subTest(category=expected):
                sock=Socket([ACK,bad])
                report=observe_once(session_factory=lambda:sock,wall_ms=lambda:FIRST+HOUR_MS+2000,
                                    clock=lambda:0,max_seconds=3).sanitized_report()
                self.assertEqual(report["status"],"ws_failed_closed")
                self.assertEqual(report["failure_category"],expected)
                self.assertTrue(sock.closed)

    def test_documented_public_pong_shapes_and_open_kline(self):
        from crypto_intelligence_agent.bybit_public_ws_once import _is_public_pong
        self.assertTrue(_is_public_pong({"success":True,"ret_msg":"pong","conn_id":"private","req_id":"","op":"ping"}))
        self.assertTrue(_is_public_pong({"op":"pong","args":["1672916271846"]}))
        self.assertFalse(_is_public_pong({"op":"pong","args":["not_timestamp"]}))
        self.assertFalse(_is_public_pong({"op":"pong","args":["1672916271846"],"data":[1]}))
        self.assertFalse(_is_public_pong({"op":"pong","args":["1672916271846"],"extra":"private"}))
        x=self.call([ACK,frame(False),{"success":True,"ret_msg":"pong","conn_id":"private","req_id":"","op":"ping"},frame()],max_frames=4)
        self.assertEqual(x["status"],"ws_one_closed_hour_observed_only")

    def test_alternative_pong_and_control_fail_closed(self):
        x=self.call([ACK,{"op":"pong","args":["1672916271846"]},frame()],max_frames=3)
        self.assertEqual(x["confirmed_closed_events"],1)
        x=self.call([ACK,{"op":"pong","args":["bad"]}],max_frames=2)
        self.assertEqual(x["failure_category"],"unexpected_control")
        self.assertFalse(x["confirmed_closed_events"])

    def test_kline_failure_categories_are_disjoint(self):
        cases=[(dict(frame(),surprise="private"),"kline_root_keys"),
               (dict(frame(),topic="kline.60.OTHERUSDT"),"kline_topic"),
               (dict(frame(),type="delta"),"kline_type"),
               (dict(frame(),data="invalid"),"kline_rows_type"),
               (dict(frame(),data=[dict(frame()["data"][0],surprise="private")]),"kline_fields")]
        for bad,expected in cases:
            with self.subTest(expected=expected):
                sock=Socket([ACK,bad])
                x=observe_once(session_factory=lambda:sock,wall_ms=lambda:FIRST+HOUR_MS+2000,clock=lambda:0,max_frames=2,max_seconds=2).sanitized_report()
                self.assertEqual(x["failure_category"],expected)
                self.assertEqual(x["confirmed_closed_events"],0)
                self.assertNotIn("private",str(x))

    def test_empty_and_multiple_rows_without_partial_approval(self):
        empty=frame();empty["data"]=[]
        self.assertEqual(self.call([ACK,empty,frame()],max_frames=3)["confirmed_closed_events"],1)
        self.assertEqual(self.call([ACK,empty],max_frames=2)["confirmed_closed_events"],0)
        multiple=frame();multiple["data"]=[dict(frame(False)["data"][0]), dict(frame()["data"][0])]
        self.assertEqual(self.call([ACK,multiple],max_frames=2)["confirmed_closed_events"],1)
        invalid=frame();invalid["data"]=[dict(frame()["data"][0]),dict(frame()["data"][0],turnover="NaN")]
        self.assertEqual(self.call([ACK,invalid],max_frames=2)["confirmed_closed_events"],0)
        bad_type=frame();bad_type["data"]=[None]
        self.assertEqual(self.call([ACK,bad_type],max_frames=2)["failure_category"],"kline_rows_nonobject")
        overflow=frame();overflow["data"]=[dict(frame()["data"][0]) for _ in range(9)]
        self.assertEqual(self.call([ACK,overflow],max_frames=2)["failure_category"],"kline_rows_overflow")
        bad_clock=frame();bad_clock["data"]=[];bad_clock["ts"]=FIRST+HOUR_MS+9000
        self.assertEqual(self.call([ACK,bad_clock],max_frames=2)["failure_category"],"kline_clock")

    def test_budget_type(self):
        with self.assertRaises(Exception):observe_once(session_factory=lambda:Socket([]),max_frames=True)

if __name__ == '__main__':unittest.main()
