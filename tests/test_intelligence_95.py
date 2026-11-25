import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from background_research_93 import migrate_retry_policy,retry_hours,choose_batch
from guidance_95 import extract
from session_quotes_95 import parse
from evidence_recovery_91 import recover_series,reviewed_eog_capex
from reviewed_pdf_95 import amount,parse as parse_pdf
NOW=datetime(2026,11,25,tzinfo=timezone.utc)
class RetryTests(unittest.TestCase):
 def test_legacy_week_delay_shortened_once_without_erasing_provider_cooldown(self):
  last=NOW-timedelta(hours=8);state={'provider_cooldowns':{'www.sec.gov':(NOW+timedelta(hours=20)).isoformat()},'companies':{'X':{'last_attempt_utc':last.isoformat(),'next_attempt_utc':(last+timedelta(days=7)).isoformat(),'collection_status':'PRIMARY_SERIES_REFRESHED_REASSESSMENT_PENDING'}}}
  migrate_retry_policy(state,NOW);self.assertEqual(state['companies']['X']['next_attempt_utc'],(last+timedelta(hours=4)).isoformat());self.assertTrue(state['provider_cooldowns']);saved=copy.deepcopy(state);migrate_retry_policy(state,NOW+timedelta(hours=1));self.assertEqual(state,saved)
 def test_failures_do_not_reach_seven_days(self):self.assertEqual(retry_hours('SOURCE_FETCH_OR_PARSE_FAILED',10),24)
 def test_supported_refresh_daily(self):self.assertEqual(retry_hours('PRIMARY_SERIES_REFRESHED_REASSESSMENT_PENDING',1,True),24)
 def test_all_originals_can_enter_forward_research_rotation(self):
  row={'ticker':'ADBE','scenarios':{'base':1}};self.assertEqual(choose_batch([row],{},NOW,20,{'ADBE'}),[row])
class GuidanceTests(unittest.TestCase):
 def parse(self,t,html,cik):
  meta={'url':f'https://www.sec.gov/Archives/edgar/data/{cik}/123/ex99.htm','sha256':hashlib.sha256(html.encode()).hexdigest(),'accession':'123','filed':'2026-11-24'}
  return extract(t,html,meta,{'cik':cik,'financial_currency':'USD','issuer_name':t},NOW)
 def test_dell_point_uses_updated_annual_not_prior_or_quarter(self):
  s='Fourth-Quarter Guidance GAAP diluted EPS $ 7.90 Full-Year Guidance FY27 Previous FY27 Updated GAAP diluted EPS $ 24.37 $ 28.24 Non-GAAP diluted EPS $ 25.50 $ 29.68 Fiscal Year Ending January 29, 2027'
  r=self.parse('DELL',s,1571996);self.assertEqual(r['facts']['low'],28.24);self.assertEqual(r['facts']['guidance_shape'],'POINT');self.assertEqual(r['facts']['target_period_end'],'2027-01-29')
 def test_dell_non_gaap_only_never_substituted(self):
  s='Full-Year Guidance FY27 Previous FY27 Updated Non-GAAP diluted EPS $ 25.50 $ 29.68 Fiscal Year Ending January 29, 2027';self.assertIsNone(self.parse('DELL',s,1571996))
 def test_adobe_full_year_scope_and_reviewed_week_calendar(self):
  s='fourth quarter FY2026 targets: Earnings per share 1 GAAP: $4.65 to $4.70 The following table summarizes Adobe’s updated FY2026 targets: Earnings per share 2 GAAP: $18.12 to $18.17 Non-GAAP: $24.45 to $24.50 diluted share count of ~400 million for FY2026.'
  r=self.parse('ADBE',s,796343);self.assertEqual(r['facts']['low'],18.12);self.assertEqual(r['facts']['target_period_end'],'2026-11-27')
 def test_adobe_new_year_requires_new_calendar_review(self):
  s='table summarizes Adobe’s updated FY2027 targets: Earnings per share GAAP: $20.00 to $21.00 diluted share count of ~400 million for FY2027';self.assertIsNone(self.parse('ADBE',s,796343))
 def test_floor_is_not_invented_upper_earnings_forecast(self):
  s='Updated Full Year 2026 Earnings Outlook to At Least $19.50 Per Share; Adjusted Earnings of At Least $20.50 Per Share Diluted earnings per share ........ $4.56 $2.59 $17.50 $13.21 At least $19.50'
  r=self.parse('UNH',s,731766);self.assertEqual(r['facts']['low'],19.5);self.assertFalse(r['facts']['high_is_guided_ceiling']);self.assertEqual(r['facts']['guidance_shape'],'FLOOR')
 def test_wrong_issuer_rejected(self):self.assertIsNone(self.parse('DELL','Full-Year Guidance',1))
class SessionTests(unittest.TestCase):
 def doc(self):
  t=int(NOW.timestamp())-3600
  return {'chart':{'result':[{'meta':{'symbol':'HPE','currency':'USD','currentTradingPeriod':{'pre':{'start':t,'end':t+600},'regular':{'start':t+600,'end':t+1200},'post':{'start':t+1200,'end':t+1800}}},'timestamp':[t+100,t+700,t+1300],'indicators':{'quote':[{'close':[40,41,42]}]}}]}}
 def test_sample_timestamps_and_labels_come_from_provider_periods(self):
  r=parse(self.doc(),'HPE',NOW,'https://example.test/chart');self.assertEqual(r['sessions']['pre_market']['price'],40);self.assertEqual(r['sessions']['after_hours']['session'],'AFTER_HOURS');self.assertLess(r['sessions']['after_hours']['provider_epoch'],NOW.timestamp());self.assertIn('NOT_EXECUTABLE',r['sessions']['regular']['timestamp_basis'])
 def test_future_sample_rejected(self):
  d=self.doc();d['chart']['result'][0]['timestamp'][-1]=int(NOW.timestamp())+60;r=parse(d,'HPE',NOW,'https://example.test/chart');self.assertIsNone(r['sessions']['after_hours'])
 def test_no_timestamp_no_fabricated_session_price(self):
  d=self.doc();d['chart']['result'][0]['timestamp']=[];d['chart']['result'][0]['indicators']['quote'][0]['close']=[];r=parse(d,'HPE',NOW,'https://example.test/chart');self.assertFalse(any(r['sessions'].values()))
 def test_symbol_and_shape_mismatches_fail(self):
  with self.assertRaises(ValueError):parse(self.doc(),'DELL',NOW,'https://example.test/chart')
  d=self.doc();d['chart']['result'][0]['timestamp'].pop()
  with self.assertRaises(ValueError):parse(d,'HPE',NOW,'https://example.test/chart')
 def test_quote_currency_mismatch_cannot_silently_enter_dashboard(self):
  r=parse(self.doc(),'HPE',NOW,'https://example.test/chart','AUD');self.assertEqual(r['status'],'SESSION_CURRENCY_MISMATCH_REVIEW_REQUIRED');self.assertFalse(any(r['sessions'].values()))
 def test_regular_sample_never_mislabeled_as_premarket(self):
  d=self.doc();x=d['chart']['result'][0];x['timestamp']=[x['timestamp'][1]];x['indicators']['quote'][0]['close']=[41];r=parse(d,'HPE',NOW,'https://example.test/chart');self.assertIsNone(r['sessions']['pre_market']);self.assertIsNone(r['sessions']['after_hours'])
class FinancialInputTests(unittest.TestCase):
 def raw(self,cik=16868):
  row={'start':'2025-01-01','end':'2025-12-31','val':10,'accn':'a','filed':'2026-02-04','form':'6-K'}
  return {'cik':cik,'entityName':'Issuer','facts':{'us-gaap':{'NetIncomeLoss':{'units':{'CAD':[row]}}}}}
 def test_cni_incorporated_annual_6k_allowed_only_for_reviewed_identity(self):
  self.assertEqual(recover_series('CNI',self.raw(),NOW,16868)['financial_currency'],'CAD')
  self.assertIsNone(recover_series('OTHER',self.raw(),NOW,16868)['financial_currency'])
 def test_no_interim_6k_masquerades_as_annual(self):
  d=self.raw();d['facts']['us-gaap']['NetIncomeLoss']['units']['CAD'][0]['start']='2025-10-01';self.assertIsNone(recover_series('CNI',d,NOW,16868)['financial_currency'])
 def test_eog_components_require_same_filing_currency_and_interval(self):
  row={'start':'2025-01-01','end':'2025-12-31','val':6,'accn':'a','filed':'2026-02-24','form':'10-K'};tags=['PaymentsToAcquireOilAndGasPropertyAndEquipment','PaymentsToAcquireOtherPropertyPlantAndEquipment'];d={'facts':{'us-gaap':{t:{'units':{'USD':[dict(row)]}} for t in tags}}};self.assertEqual(reviewed_eog_capex(d,NOW)[0]['value'],12)
  d['facts']['us-gaap'][tags[1]]['units']['USD'][0]['accn']='b';self.assertEqual(reviewed_eog_capex(d,NOW),[])
 def test_changed_pdf_not_reapproved(self):
  with self.assertRaises(ValueError):parse_pdf(b'changed',{'sha256':'0'*64},NOW)
 def test_parenthesized_cash_and_explicit_dash(self):self.assertEqual(amount('(1,298)'),-1298);self.assertEqual(amount('—'),0)

class PdfGeometryTests(unittest.TestCase):
 def read_table(self,rotation=0,duplicate_header=False):
  import fitz
  from pdf_rows_dynamic_92 import rows
  doc=fitz.open();page=doc.new_page(width=842 if rotation else 595,height=595 if rotation else 842);page.set_rotation(rotation)
  def text(x,y,value):
   point=fitz.Point(x,y)*page.derotation_matrix if rotation else fitz.Point(x,y)
   page.insert_text(point,value,fontsize=10,rotate=90 if rotation else 0)
  text(500,20,'2026');text(501,20,'2026')
  text(350,80,'2026');text(450,80,'2025')
  if duplicate_header:text(300,80,'2026')
  text(50,120,'Profit');text(350,120,'10');text(450,120,'9')
  with tempfile.TemporaryDirectory() as folder:
   (Path(folder)/'fixture.raw').write_bytes(doc.tobytes());doc.close();return rows('fixture',1,[2026,2025],folder)
 def test_rotated_primary_table_uses_display_coordinates(self):
  r=self.read_table(90);self.assertEqual(r[0]['label'],'Profit');self.assertEqual(r[0]['values'],{'2026':'10','2025':'9'})
 def test_unrelated_duplicate_year_text_is_not_ambiguous_table_header(self):self.assertEqual(len(self.read_table()),1)
 def test_actual_ambiguous_year_columns_still_rejected(self):self.assertEqual(self.read_table(duplicate_header=True),[])

class SessionCollectorIntegrationTests(unittest.TestCase):
 def test_real_watchlist_has_no_currency_column_and_daily_close_is_preserved(self):
  import shutil
  from unittest.mock import Mock,patch
  from session_quotes_95 import collect
  source=Path(__file__).resolve().parents[1]/'watchlist.csv'
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);shutil.copyfile(source,root/'watchlist.csv');(root/'data').mkdir()
   payload={'stocks':[{'ticker':'BABA','name':'Alibaba','sector':'Original 30','currency':'USD','price':123,'history':[]}],'bitcoin':{},'scan_sydney':'2026-11-25','stock_quotes_available':1,'validated_buy_count':0}
   (root/'data/latest.json').write_text(json.dumps(payload))
   doc=SessionTests().doc();doc['chart']['result'][0]['meta']['symbol']='BABA';response=Mock(status_code=200);response.json.return_value=doc
   with patch('session_quotes_95.requests.get',return_value=response):report=collect(root,now=NOW,limit=1)
   self.assertEqual(len(report['companies']),200);row=json.loads((root/'data/latest.json').read_text())['stocks'][0]
   self.assertEqual(row['price'],123);self.assertEqual(row['pre_market_price'],40);self.assertEqual(row['valuation_price_session'],'DAILY_CLOSE');self.assertIn('Pre-market UTC',(root/'data/index.html').read_text())
