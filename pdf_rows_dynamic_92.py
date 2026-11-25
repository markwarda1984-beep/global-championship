from pathlib import Path
import fitz,json,re,bisect
F=Path(__file__).resolve().parent/'.source-cache'
def rows(stem,page,years,folder=None,clip=None):
 folder=Path(folder) if folder else F
 doc=fitz.open(stream=(folder/(stem+'.raw')).read_bytes(),filetype='pdf');pdf_page=doc[page-1];rect=fitz.Rect(clip) if clip else pdf_page.rect
 # Text coordinates are unrotated, whereas page.rect describes the displayed page.
 words=[]
 for word in pdf_page.get_text('words'):
  box=fitz.Rect(word[:4])*pdf_page.rotation_matrix
  if not rect.contains(box):continue
  transformed=(*tuple(box),*word[4:])
  if any(old[4]==word[4] and abs((old[0]+old[2]-box.x0-box.x1)/2)<2 and abs((old[1]+old[3]-box.y0-box.y1)/2)<2 for old in words[-12:]):continue
  words.append(transformed)
 doc.close();groups=[]
 for w in sorted(words,key=lambda x:((x[1]+x[3])/2,x[0])):
  cy=(w[1]+w[3])/2
  g=next((g for g in groups[-5:] if abs(g[0]-cy)<2.5),None)
  if g is None:g=[cy,[]];groups.append(g)
  g[1].append(w)
 header=None
 for y,ws in groups:
  found={year:[w for w in ws if w[4]==str(year) and (w[0]+w[2])/2>rect.x0+rect.width*.45] for year in years}
  if all(found.values()) and any(len(v)>1 for v in found.values()):return [] # Ambiguous company/group columns require an explicit clip.
  if all(len(v)==1 for v in found.values()):
   xmap={int(w[4]):(w[0]+w[2])/2 for w in ws if re.fullmatch(r'20[0-3][0-9]',w[4]) and (w[0]+w[2])/2>rect.x0+rect.width*.45}
   xmap.update({year:(v[0][0]+v[0][2])/2 for year,v in found.items()})
   if min(xmap.values())>rect.x0+rect.width*.45:header=(y,xmap);break
 if header is None:return []
 _,xs=header;physical=sorted(xs,key=xs.get);gap=abs(xs[physical[1]]-xs[physical[0]]);first=xs[physical[0]]-gap*.55;boundaries=[(xs[a]+xs[b])/2 for a,b in zip(physical,physical[1:])]
 out=[];section=None
 for y,ws in groups:
  if y<=header[0]:continue
  ws=sorted(ws,key=lambda w:w[0]);label=' '.join(w[4] for w in ws if (w[0]+w[2])/2<first)
  section_label=label.lower().replace('-',' ').strip()
  if section_label in ('current liabilities','non current liabilities','noncurrent liabilities','current assets','non current assets','noncurrent assets'):section=section_label
  nums={year:[] for year in years}
  for w in ws:
   token=w[4];cx=(w[0]+w[2])/2
   if cx<first or not re.fullmatch(r'\(?-?[\d,]+(?:\.\d+)?\)?|[-–—]',token):continue
   year=physical[bisect.bisect_right(boundaries,cx)]
   if year in nums:nums[year].append(token)
  if label and all(len(v)==1 for v in nums.values()):out.append({'label':label,'values':{str(k):v[0] for k,v in nums.items()},'y':round(y,1),'section':section})
 return out
if __name__=='__main__':
 import sys
 print(json.dumps(rows(sys.argv[1],int(sys.argv[2]),list(map(int,sys.argv[3:]))),indent=2))
