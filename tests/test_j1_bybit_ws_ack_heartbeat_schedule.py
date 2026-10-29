"""WS3 offline compatibility and one-shot gates; never connects to network."""
import json
import unittest
from unittest.mock import patch
from crypto_intelligence_agent.bybit_public_ws_once import (
    _subscription_ack, _public_pong, seconds_to_closed_hour_probe,
    owner_probe, observe_once, HOUR_MS,
)
from test_j1_bybit_public_ws_once import ACK, FIRST, Socket, frame
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.bybit_ws_offline_pipeline import ingest_offline_ws_batch
from crypto_intelligence_agent.bybit_closed_stream_cache import SQLiteOfflineClosedStreamJournal
from test_j1_bybit_closed_stream_cache import scope
from pathlib import Path
from tempfile import TemporaryDirectory

class Tests(unittest.TestCase):
    def test_documented_ack_optional_id(self):
        good=dict(ACK,req_id='abc')
        self.assertTrue(_subscription_ack(good))
        sock=Socket([good,frame()])
        result=observe_once(session_factory=lambda:sock, wall_ms=lambda:FIRST+HOUR_MS+2000,
                            clock=lambda:0,max_seconds=3)
        self.assertEqual(result.confirmed_closed_events,1)
        self.assertTrue(sock.closed)
        with TemporaryDirectory() as d:
            journal=SQLiteOfflineClosedStreamJournal.create(Path(d)/'ws.sqlite')
            report=ingest_offline_ws_batch(frames=[(json.dumps(good),FIRST)],scope=scope(),journal=journal)
            self.assertTrue(report.acknowledged)
    def test_ack_rejects_invalid_and_surprises(self):
        for bad in (dict(ACK,req_id=1),dict(ACK,other='x'),dict(ACK,success=1),
                    dict(ACK,op='ping'),dict(ACK,req_id='a'*129),dict(ACK,ret_msg=5),
                    dict(ACK,success=False)):
            self.assertFalse(_subscription_ack(bad))
    def test_pong_shape(self):
        self.assertTrue(_public_pong({'op':'ping','ret_msg':'pong'}))
        self.assertTrue(_public_pong({'op':'ping','ret_msg':'pong','conn_id':'abc'}))
        for bad in ({'op':'subscribe','ret_msg':'pong'}, {'op':'ping','ret_msg':'bad'},
                    {'op':'ping','ret_msg':'pong','strange':5}, {'op':'ping','ret_msg':'pong','success':False}):
            self.assertFalse(_public_pong(bad))
    def test_ping_after_20_seconds_not_reconnection(self):
        clocks=iter([0,0,21,22,23,23])
        sock=Socket([ACK,{'op':'ping','ret_msg':'pong'},frame()])
        res=observe_once(session_factory=lambda:sock, clock=lambda:next(clocks,23),
                         wall_ms=lambda:FIRST+HOUR_MS+2000,max_seconds=90)
        self.assertEqual(res.confirmed_closed_events,1)
        self.assertEqual([json.loads(x)['op'] for x in sock.sent],['subscribe','ping'])
    def test_schedule_at_utc_boundary(self):
        self.assertEqual(seconds_to_closed_hour_probe(FIRST+HOUR_MS-10_000),0)
        self.assertEqual(seconds_to_closed_hour_probe(FIRST+1_000),3579)
        with self.assertRaises(DataValidationError): seconds_to_closed_hour_probe(True)
    def test_owner_requires_schedule_no_network(self):
        with patch('crypto_intelligence_agent.bybit_public_ws_once._real_session_factory',side_effect=AssertionError('network')):
            res=owner_probe(allow_public_websocket=True,confirm_region_and_personal_research=True)
        self.assertEqual(res['status'],'ws_closed_hour_schedule_required')
    def test_owner_scheduled_exactly_once(self):
        calls=[]
        sock=Socket([dict(ACK,req_id='x'),frame()])
        with patch('crypto_intelligence_agent.bybit_public_ws_once._real_session_factory',side_effect=lambda:(calls.append(1) or sock)):
            with patch('crypto_intelligence_agent.bybit_public_ws_once.observe_once',return_value=type('R',(),{'sanitized_report':lambda self:{'status':'ok'}})()):
                res=owner_probe(allow_public_websocket=True,confirm_region_and_personal_research=True,
                                schedule_closed_utc_hour=True,clock_ms=lambda:FIRST+1000,sleeper=lambda t:calls.append(t))
        self.assertEqual(calls,[3579])
        self.assertEqual(res['status'],'ok')
if __name__=='__main__': unittest.main()
