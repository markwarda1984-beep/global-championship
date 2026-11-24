"""Dated vendor daily FX, explicitly separate from issuer financial evidence."""
import json
from datetime import datetime,timezone
from pathlib import Path
import yfinance as yf
from evidence_recovery_91 import write

def run(root):
 evidence=json.loads((root/'reports/primary_evidence_91.json').read_text());path=root/'settings/primary_adapters_90.json'
 adapters=json.loads(path.read_text());currencies={r.get('financial_currency') for r in evidence['companies'].values()}-{'USD',None}
 records=[]
 # Bounded batch, native statement currency -> listed quote currency.
 pairs={currency:currency+'USD=X' for currency in sorted(currencies)}
 try:
  frame=yf.download(list(pairs.values()),period='5d',interval='1d',group_by='ticker',auto_adjust=False,progress=False,threads=False)
 except Exception as exc:
  write(root/'reports/fx_recovery_91.json',{'status':'UNAVAILABLE','reason':type(exc).__name__,'orders_enabled':False});return
 for currency,symbol in pairs.items():
  try:
   closes=frame[symbol]['Close'].dropna();value=float(closes.iloc[-1]);as_of=closes.index[-1].date().isoformat()
   if value<=0:raise ValueError('Invalid rate')
   r={'from':currency,'to':'USD','rate':value,'as_of':as_of,'observed_utc':datetime.now(timezone.utc).isoformat(),
      'source_url':f'https://finance.yahoo.com/quote/{symbol}/history/','source_type':'SECONDARY_DATED_DAILY_FX_NOT_ISSUER_FINANCIALS','orders_enabled':False}
   records.append(r)
   for ticker,company in evidence['companies'].items():
    if company.get('financial_currency')==currency and not ticker.endswith('.AX'):adapters.setdefault(ticker,{})['fx']=r
  except (KeyError,IndexError,ValueError,TypeError):records.append({'from':currency,'to':'USD','rate':None,'status':'UNAVAILABLE'})
 write(path,adapters);write(root/'reports/fx_recovery_91.json',{'status':'DATED_RESEARCH_FX','rates':records,'orders_enabled':False})
if __name__=='__main__':run(Path(__file__).resolve().parent)
