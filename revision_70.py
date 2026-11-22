"""Experimental research overlay; no orders or automatic buy authorization."""
import statistics as st
import copy

def stable_revision(f, ni, shares, observed_dilution, cfg):
    if len(f)<4 or min(f)<=0 or min(ni)<=0 or shares<=0:
        return None
    growth=(f[-1]/f[0])**(1/(len(f)-1))-1
    eg=(ni[-1]/ni[0])**(1/(len(ni)-1))-1
    rates=[b/a-1 for a,b in zip(f,f[1:])]
    volatility=st.pstdev(rates)
    # Risk proxy, not an empirically calibrated cost of equity.
    rate=min(.16,max(.10,.10+volatility*.15))
    g=max(-.08,min(.12,growth,eg))
    start=min(f[-1],st.mean(f[-3:])*(1+max(0,g))) / shares
    eps=st.mean(ni[-3:])/shares
    dilution=max(.0,min(.15,observed_dilution))
    def dcf(c,g,r):
        flows=[c*(1+g)**min(i,5)*1.02**max(0,i-5) for i in range(1,11)]
        return sum(v/(1+r)**i for i,v in enumerate(flows,1))+flows[-1]*1.02/(r-.02)/(1+r)**10
    scenarios={}; methods={}
    for k,scale,shift,dr,extra in [('bear',.75,-.05,.04,.10),('base',1,0,0,.03),('bull',1.15,.03,-.015,0)]:
        rr=max(.085,rate+dr); gg=max(-.12,min(.15,g+shift)); dd=min(.30,dilution+extra)
        cash=dcf(start*scale,gg,rr)/(1+dd)
        earnings=eps*scale/rr/(1+dd)
        forward=eps*scale*(1+gg)/(rr-.02)/(1+dd)
        # Weight DCF more when observed cashflows are stable; no market price input.
        w=max(.4,min(.7,.7-volatility))
        scenarios[k]=w*cash+(1-w)*earnings
        methods[k]={'dcf':cash,'normalized_earnings':earnings,'forward_earnings_crosscheck':forward,'dcf_weight':w,'discount_rate':rr,'growth':gg,'dilution_stress':dd}
    if not scenarios['bear']<=scenarios['base']<=scenarios['bull']:return None
    return {'scenarios':scenarios,'methods':methods,'cashflow_start_per_share':start,'risk_proxy_volatility':volatility,'status':'EXPERIMENTAL_RESEARCH_ONLY','historical_multiple_status':'NOT_AVAILABLE_POINT_IN_TIME_DATA_REQUIRED'}
