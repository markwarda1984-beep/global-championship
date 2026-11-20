import unittest
from report_bridge import build

class ReportBridgeTests(unittest.TestCase):
    def test_200_and_ranking(self):
        stocks = [dict(ticker=f'T{i}', name=f'Name{i}', currency='USD', price=100+i,
                       quote_date='2026-11-20', buy_validation='UNRESEARCHED',
                       manual_provisional_buy_price=None, technical_watch_zone=100)
                  for i in range(200)]
        report = build({'stocks': stocks, 'scan_utc': '2026-11-20T00:00:00Z'})
        self.assertEqual(report['universe_count'], 200)
        self.assertEqual(len(report['closest_to_buy_top_10']), 10)
        self.assertEqual(report['closest_to_buy_top_10'][0]['ticker'], 'T0')
        self.assertTrue(all(x['buy_readiness_pct'] is None for x in report['stocks']))
        self.assertFalse(report['orders_enabled'])
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            build({'stocks': [{'ticker':'A'}] * 200})
    def test_model_currency_mismatch_falls_back(self):
        stocks = [dict(ticker=f'T{i}', currency='USD', price=100, technical_watch_zone=90,
                       buy_validation='UNRESEARCHED') for i in range(200)]
        val = {'stocks':[{'ticker':'T0','model_watch_entry':120,'model_status':'INDICATIVE MODEL','price_currency':'EUR'}]}
        r = build({'stocks':stocks}, val)
        self.assertEqual(r['stocks'][0]['provisional_entry'],90)
        self.assertIn('STATISTICAL',r['stocks'][0]['entry_basis'])

if __name__ == '__main__': unittest.main()
