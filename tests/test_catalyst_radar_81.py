import sys, unittest, tempfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalyst_radar_81 import classify_filing,evaluate_snapshot,run
NOW=datetime(2026,11,23,tzinfo=timezone.utc)
class TestCatalystRadar(unittest.TestCase):
    def test_untrusted_url_rejected(self):
        self.assertIsNone(classify_filing({'url':'https://sec.gov.evil.com/a','published_at':'2026-11-22'},NOW))
    def test_keyword_is_not_verified_catalyst(self):
        x=classify_filing({'url':'https://www.sec.gov/Archives/test','title':'Contract and public offering','published_at':'2026-11-22'},NOW)
        self.assertTrue(x['catalyst_keyword_flag']);self.assertTrue(x['dilution_keyword_flag'])
        self.assertFalse(x['primary_document_contents_verified'])
    def test_negative_controls_retained(self):
        prev={'observations':[{'ticker':'UP','price':1},{'ticker':'DOWN','price':2}]}
        cur=[{'ticker':'UP','price':2},{'ticker':'DOWN','price':0.5}]
        x=evaluate_snapshot(cur,prev)
        self.assertTrue(x[0]['is_large_positive_move']);self.assertTrue(x[1]['is_large_negative_move'])
    def test_offline_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            x=run(Path(d),offline=True)
            self.assertFalse(x['orders_enabled']);self.assertFalse(x['missed_opportunity_audit_validated'])
if __name__=='__main__':unittest.main()
