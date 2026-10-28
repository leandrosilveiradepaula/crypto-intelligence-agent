import unittest
from unittest.mock import Mock
from datetime import date
from scripts.probe_bybit_archive_week import probe_week, ORIGIN
from test_bybit_archive_week import samples

class FakeResponse:
    def __init__(self,url,blob,code=200):
        self.url,self.blob,self.code=url,blob,code
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def geturl(self): return self.url
    def getcode(self): return self.code
    def read(self,n): return self.blob[:n]

class WeeklyProbeTests(unittest.TestCase):
    def test_defaults_never_call_transport(self):
        for flags in ((False,False),(True,False),(False,True)):
            result=probe_week(allow_public_network=flags[0],
                allow_weekly_archive_probe=flags[1],
                opened=lambda *a,**k:self.fail("unapproved GET"))
            self.assertEqual(result["requests_attempted"],0)

    def test_exact_seven_gets_and_sanitized_output(self):
        fixture=samples(date(2020,3,25))
        seen=[]
        def open_request(request,*,timeout):
            index=len(seen)
            self.assertLess(index,7)
            seen.append(request.full_url)
            self.assertEqual(request.get_method(),"GET")
            self.assertEqual(timeout,10)
            self.assertEqual(request.full_url,ORIGIN+fixture[index][0])
            return FakeResponse(request.full_url,fixture[index][1])
        report=probe_week(allow_public_network=True,
                          allow_weekly_archive_probe=True,opened=open_request)
        self.assertEqual(report["requests_attempted"],7)
        self.assertEqual(report["trades"],7)
        self.assertEqual(report["archive_count"],7)
        self.assertEqual(len(seen),7)
        self.assertNotIn("9000.5",str(report))
        self.assertFalse(report["rights_authorized"])
        self.assertFalse(report["orders_sent"])

    def test_failure_halts_without_retry(self):
        seen=[]
        fixture=samples(date(2020,3,25))
        def open_request(request,*,timeout):
            seen.append(request.full_url)
            i=len(seen)-1
            return FakeResponse(request.full_url,fixture[i][1],403 if i==2 else 200)
        report=probe_week(allow_public_network=True,
            allow_weekly_archive_probe=True,opened=open_request)
        self.assertEqual(report["requests_attempted"],3)
        self.assertEqual(report["status"],"http_or_redirect_rejected_no_retry")
        self.assertEqual(len(seen),3)

if __name__=="__main__":
    unittest.main()
