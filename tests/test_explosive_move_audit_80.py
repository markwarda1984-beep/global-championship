import csv, tempfile, unittest
from pathlib import Path
from explosive_move_audit_80 import audit

class TestAudit(unittest.TestCase):
    def test_missing_data_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            result=audit(Path(d))
            self.assertEqual(result['status'],'INSUFFICIENT_DAILY_CHANGE_DATA')
            self.assertFalse(result['orders_enabled'])
    def test_explosive_move_is_not_a_buy(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'reports';p.mkdir()
            with (p/'latest.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=['ticker','return_1d_pct','volume_ratio'])
                writer.writeheader();writer.writerow({'ticker':'TEST','return_1d_pct':145,'volume_ratio':8})
            result=audit(Path(d))
            self.assertEqual(len(result['flagged']),1)
            self.assertFalse(result['flagged'][0]['pre_move_signal_verified'])
            self.assertEqual(result['flagged'][0]['missed_valid_buy'],'UNDETERMINED')
            self.assertEqual(result['buy_signals_generated'],0)
