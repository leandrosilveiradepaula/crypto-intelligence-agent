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
        bad=dict(ACK,success=False);self.assertEqual(self.call([bad])["status"],"ws_subscription_not_acknowledged")
    def test_missing_ack_rejected(self):
        self.assertEqual(self.call([frame()])["status"],"ws_subscription_not_acknowledged")
    def test_bad_envelopes(self):
        mutations=[lambda f:f.update(topic="kline.5.BTCUSDT"), lambda f:f["data"][0].update(turnover="NaN"),
                   lambda f:f["data"][0].update(open=10.1), lambda f:f["data"][0].update(high="8"),
                   lambda f:f["data"][0].update(confirm=1), lambda f:f["data"][0].update(start=FIRST+1),
                   lambda f:f.update(ts=FIRST+HOUR_MS+3000), lambda f:f.update(type="delta")]
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
    def test_budget_type(self):
        with self.assertRaises(Exception):observe_once(session_factory=lambda:Socket([]),max_frames=True)

if __name__ == '__main__':unittest.main()
