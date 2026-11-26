import json
import tempfile
import unittest
from pathlib import Path
from reporting_bridge import publish, verify, LIMIT

class ReportingBridgeTests(unittest.TestCase):
    def fixture(self, root):
        reports=root/'reports';reports.mkdir()
        rows=[{'ticker':f'T{i:03}', 'universe':'ORIGINAL_200','price':10,'currency':'USD','quote_date':'2026-11-25','scenarios':{'base':20},'assessment_status':'SUPPORTED','missing_inputs':[]} for i in range(200)]
        for name,value in {
            'valuation_90_latest.json':{'companies':rows},
            'dynamic_earnings_92_latest.json':{'companies':[], 'coverage_comparison':{'all_200_assessed':200}},
            'valuation_60_latest.json':{'companies':[{'ticker':'T000','selected_entry':8,'validation_status':'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL'},{'ticker':'T001','selected_entry':9,'validation_status':'NOT VALIDATED'}]},
            'session_quotes_95_latest.json':{'companies':{'T000':{'sessions':{'pre_market':{'price':11,'as_of_utc':'2026-11-25T12:00:00Z','session':'PRE_MARKET','freshness':'DATED_SESSION_SAMPLE_NOT_LIVE'}}}}}
        }.items(): (reports/name).write_text(json.dumps(value))
        return reports

    def test_roundtrip_chunks_missing_and_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);reports=self.fixture(root)
            before={p.name:p.read_bytes() for p in reports.glob('*.json')}
            manifest=publish(root)
            self.assertEqual(before,{p.name:p.read_bytes() for p in reports.glob('*.json')})
            out=reports/'bridge';verify(out)
            self.assertTrue(all(p.stat().st_size<LIMIT for p in out.glob('*.json')))
            idx=json.loads((out/'dashboard.json').read_text())
            rows=[r for part in idx['chunks'] for r in json.loads((root/part['path']).read_text())['rows']]
            self.assertEqual(rows[0]['entry_limit'],8)
            self.assertEqual(rows[0]['pct_above_entry'],25)
            self.assertIsNone(rows[1]['entry_limit'])
            self.assertEqual(rows[0]['sessions']['pre_market']['price'],11)
            self.assertTrue(rows[1]['sessions']['after_hours']['missing'])
            self.assertEqual(rows[0]['april_2026']['status'],'MISSING_VERIFIED_COMPARABLE_BASELINE')
            self.assertTrue(manifest['inputs']['dynamic_earnings_92_weekly.json']['missing'])
            (out/'obsolete_999.json').write_text('{}');publish(root)
            self.assertFalse((out/'obsolete_999.json').exists())
            (out/'dashboard_001.json').write_text('{}')
            with self.assertRaises(AssertionError):verify(out)

    def test_refuses_incomplete_universe_and_unsafe_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);reports=self.fixture(root)
            path=reports/'valuation_90_latest.json';data=json.loads(path.read_text())
            data['orders_enabled']=True;path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):publish(root)
            data.pop('orders_enabled');data['companies'].pop();path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):publish(root)
