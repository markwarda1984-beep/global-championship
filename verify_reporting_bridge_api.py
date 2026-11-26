"""Retrieve every bridge file using the standard GitHub Contents JSON API."""
import argparse
import base64
import hashlib
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen


def verify_api(repo, ref):
    headers={'Accept':'application/vnd.github+json','User-Agent':'Championship-reporting-bridge-verifier'}
    if os.environ.get('GH_TOKEN'):headers['Authorization']='Bearer '+os.environ['GH_TOKEN']
    def fetch(path):
        url=f'https://api.github.com/repos/{repo}/contents/{path}?ref={quote(ref, safe="")}'
        with urlopen(Request(url,headers=headers),timeout=45) as response: result=json.load(response)
        assert result.get('encoding')=='base64', 'Standard content retrieval failed for '+path
        raw=base64.b64decode(result['content'])
        assert len(raw)<100_000, path
        return raw
    manifest=json.loads(fetch('reports/bridge/manifest.json'))
    retrieved={}
    for name, info in manifest['files'].items():
        raw=fetch(info['path'])
        assert len(raw)==info['bytes'], name
        assert hashlib.sha256(raw).hexdigest()==info['sha256'],name
        retrieved[name]=json.loads(raw)
    rows=[r for part in retrieved['dashboard.json']['chunks'] for r in retrieved[part['path'].split('/')[-1]]['rows']]
    assert len(rows)==len({r['ticker'] for r in rows})==200
    print(json.dumps({'ref':ref,'files_retrieved':len(retrieved)+1,'stocks':len(rows),'largest_file_bytes':max(v['bytes'] for v in manifest['files'].values()),'coverage':retrieved['coverage.json'],'orders_enabled':manifest['orders_enabled']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',default='markwarda1984-beep/global-championship');p.add_argument('--ref',required=True);a=p.parse_args();verify_api(a.repo,a.ref)
