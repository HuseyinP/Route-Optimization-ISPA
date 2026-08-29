# -*- coding: utf-8 -*-
"""
GNSS_COMMENT12_UPSTREAM_PROVENANCE_SCANNER_v1_1.py
Fast read-only provenance scanner. v1.1 first filters CSVs by header, then
loads only relevant dataset-level candidates and uses vectorized numeric
matching. It never edits source data or the manuscript.
"""
from pathlib import Path
import re, math, traceback
import numpy as np
import pandas as pd

ROOT=Path(r"C:\IEEE"); A=ROOT/"GNSS_ANALYSIS"; PYC=ROOT/"PY_CODES"
OUT=A/"COMMENT12_UPSTREAM_PROVENANCE_SCANNER_V1_1"; OUT.mkdir(parents=True,exist_ok=True)
C11=A/"COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1"
PRIMARY=["COMMENT11_V1_1_PRIMARY_DATASET_AUDIT.csv","COMMENT11_V1_1_PRIMARY_DATASET_AUDIT(1).csv"]
SECONDARY=["COMMENT11_V1_1_SECONDARY_DATASET_AUDIT.csv","COMMENT11_V1_1_SECONDARY_DATASET_AUDIT(1).csv"]
EXCLUDE=("COMMENT12_UPSTREAM_PROVENANCE","COMMENT12_METRIC_LINEAGE","COMMENT12_MANUSCRIPT_NUMERICAL",
"COMMENT12_FINAL_EVIDENCE_REGISTRY","COMMENT11_V1_1_PRIMARY_DATASET_AUDIT",
"COMMENT11_V1_1_SECONDARY_DATASET_AUDIT","COMMENT11_V1_1_PRIMARY_SECONDARY_COMPARISON",
"COMMENT11_V1_1_BLOCKED_PERMUTATION")
ALIASES={
"CMC_P95":("CMC_P95","CMC P95","P95_CMC","CMC_ABS_P95"),
"CMC_ROBUST":("CMC_ROBUST","ROBUST_CMC","ROBUST CMC","CMC_ROBUST_DISPERSION"),
"CN0":("CN0","CNO","C/N0","C_N0"),
"OUTCOME":("OUTCOME","HORIZONTAL_RMSE","RMSE2D","RMSE_2D","RMSE_HORIZONTAL")}
IDS=("DATASET","PHYSICAL_DATASET","DATASET_ID","RECEIVER","DEVICE","STATION","SITE","TEST","SESSION","SET","NAME","ID")
ATOL=1e-7; RTOL=1e-8; MAX_MB=40; MAX_ROWS=250000; MAX_FILES=120

def nt(x):
 s=str(x if x is not None else "").upper().replace("₀","0")
 return re.sub(r"_+","_",re.sub(r"[^A-Z0-9]+","_",s)).strip("_")
def find(names):
 for n in names:
  q=C11/n
  if q.exists(): return q
 for n in names:
  h=list(A.rglob(n)) if A.exists() else []
  if h:return h[0]
 return None
def rd(q,**kw):
 try:return pd.read_csv(q,**kw)
 except UnicodeDecodeError:return pd.read_csv(q,encoding="latin1",**kw)
def cols_for(cols,t):
 aa=[nt(x) for x in ALIASES[t]]; out=[]
 for c in cols:
  n=nt(c)
  if n in aa or any(len(a)>=4 and a in n for a in aa):out.append(c)
 return out
def infer_id(df):
 nm={nt(c):c for c in df.columns}
 for k in ("PHYSICAL_DATASET","DATASET_ID","DATASET"):
  if k in nm and df[nm[k]].nunique(dropna=True)>=.8*len(df):return [nm[k]]
 ts=[c for c in df if "TEST" in nt(c) or "SESSION" in nt(c) or nt(c)=="SET"]
 rs=[c for c in df if any(x in nt(c) for x in ("RECEIVER","DEVICE","STATION","SITE"))]
 for a in ts:
  for b in rs:
   s=df[a].astype(str).map(nt)+"_"+df[b].astype(str).map(nt)
   if s.nunique()==len(df):return [a,b]
 for c in df:
  if any(x in nt(c) for x in IDS) and df[c].nunique(dropna=True)==len(df):return [c]
 return []
def mkid(df,cs):
 s=df[cs[0]].astype(str).map(nt)
 for c in cs[1:]:s=s+"_"+df[c].astype(str).map(nt)
 return s
def anchor(q):
 df=rd(q); ids=infer_id(df)
 if not ids:raise RuntimeError(f"Cannot infer anchor ID: {q}")
 df=df.copy();df["_ID"]=mkid(df,ids)
 mp={}
 for t in ALIASES:
  cc=cols_for(df.columns,t)
  if cc:mp[t]=cc[0]
 miss=set(ALIASES)-set(mp)
 if miss:raise RuntimeError(f"Anchor missing {miss}: {q}; columns={list(df.columns)}")
 return df,ids,mp
def header_scan():
 inv=[]; short=[]
 fs=sorted(A.rglob("*.csv"),key=lambda x:str(x).lower()) if A.exists() else []
 for i,q in enumerate(fs,1):
  if any(x in q.name.upper() for x in EXCLUDE):continue
  mb=q.stat().st_size/1024**2
  if mb>MAX_MB:
   inv.append({"File":str(q),"MB":mb,"Status":"SKIP_SIZE","Groups":""});continue
  try:
   h=rd(q,nrows=0); groups=[t for t in ALIASES if cols_for(h.columns,t)]
   hasid=any(any(x in nt(c) for x in IDS) for c in h.columns)
   status="SHORTLIST" if groups else "IRRELEVANT"
   inv.append({"File":str(q),"MB":mb,"Status":status,"Groups":"|".join(groups),"Has_ID":hasid})
   if groups:short.append((10*len(groups)+(5 if hasid else 0),q,groups))
  except Exception as e:inv.append({"File":str(q),"MB":mb,"Status":"HEADER_FAIL","Groups":""})
  if i%300==0:print(f"Header scan {i}/{len(fs)}")
 short.sort(key=lambda z:(-z[0],str(z[1]).lower()))
 return inv,short[:MAX_FILES]
def idcols(df):
 a=[]
 for c in df:
  n=nt(c);sc=0
  if n in IDS:sc+=10
  if any(x in n for x in IDS):sc+=4
  if df[c].dtype==object:sc+=2
  if sc:a.append((sc,c))
 return [c for _,c in sorted(a,reverse=True)[:8]]
def bestmatch(an,acol,df,ccol):
 av=pd.to_numeric(an[acol],errors="coerce").to_numpy(float)
 cv=pd.to_numeric(df[ccol],errors="coerce").to_numpy(float)
 va=np.isfinite(av);vc=np.isfinite(cv)
 if not vc.any():return None
 # reduce rows to values close to any of only 11 anchor values
 ix=np.where(vc)[0]; C=cv[ix]
 keep=np.any(np.isclose(av[va,None],C[None,:],atol=ATOL,rtol=RTOL),axis=0)
 ix=ix[keep]
 if not len(ix):return None
 sub=df.iloc[ix]; C=cv[ix]
 V=np.isclose(av[:,None],C[None,:],atol=ATOL,rtol=RTOL)
 specs=[[c] for c in idcols(sub)]
 ts=[c for c in idcols(sub) if "TEST" in nt(c) or "SESSION" in nt(c)]
 rs=[c for c in idcols(sub) if any(x in nt(c) for x in ("RECEIVER","DEVICE","STATION","SITE","NAME"))]
 specs += [[a,b] for a in ts[:3] for b in rs[:4] if a!=b]
 aid=an["_ID"].astype(str).map(nt).to_numpy();best=None
 for sp in specs:
  cid=mkid(sub,sp).astype(str).map(nt).to_numpy()
  I=np.zeros((len(aid),len(cid)),bool)
  for i,a in enumerate(aid):
   I[i]=[(a==c) or (len(a)>=3 and len(c)>=3 and (a in c or c in a)) for c in cid]
  m=np.any(V&I,axis=1)&va;n=int(m.sum());den=int(va.sum())
  r={"Candidate_ID_Columns":"+".join(sp),"Anchor_N":den,"Match_N":n,"Match_Fraction":n/den if den else 0,
     "Matched_IDs":"|".join(aid[m]),"Unmatched_IDs":"|".join(aid[va&~m])}
  if best is None or n>best["Match_N"]:best=r
 return best
def scan(short,pa,sa,pm,sm):
 rows=[];log=[]
 specs=[("STAGE1","CMC_P95",pa,pm["CMC_P95"]),("STAGE1","CMC_ROBUST",pa,pm["CMC_ROBUST"]),
 ("STAGE1","CN0",pa,pm["CN0"]),("STAGE2_ADJUSTED","OUTCOME",pa,pm["OUTCOME"])]
 if sa is not None:specs.append(("STAGE2_UNADJUSTED","OUTCOME",sa,sm["OUTCOME"]))
 for k,(score,q,groups) in enumerate(short,1):
  try:
   df=rd(q)
   if len(df)>MAX_ROWS:log.append({"File":str(q),"Status":"SKIP_ROWS","Rows":len(df)});continue
   log.append({"File":str(q),"Status":"LOADED","Rows":len(df)})
   for stage,t,an,acol in specs:
    if t not in groups:continue
    for c in cols_for(df.columns,t)[:8]:
     b=bestmatch(an,acol,df,c)
     if b and b["Match_N"]:
      rows.append({"Stage":stage,"Target":t,"Candidate_File":str(q),"Candidate_Column":c,
      "Header_Score":score,**b,"Evidence_Level":"A_STRONG_DATASET_NUMERIC" if b["Match_Fraction"]>=.9 else "A_PARTIAL_DATASET_NUMERIC"})
  except Exception as e:log.append({"File":str(q),"Status":f"FAIL:{type(e).__name__}","Rows":""})
  if k%20==0:print(f"Candidate scan {k}/{len(short)}")
 return rows,log
def codehits(top):
 if not PYC.exists():return []
 terms=sorted(set([Path(r["Candidate_File"]).name for r in top]+[str(r["Candidate_Column"]) for r in top]))
 pats={"CMC_P95":r"CMC_P95|quantile\s*\(\s*0?\.95|percentile.*95",
 "CMC_ROBUST":r"CMC_ROBUST|ROBUST.*CMC|CMC.*ROBUST|median_absolute_deviation|1\.4826",
 "CN0":r"\bCN0\b|\bCNO\b|C/N0","RMSE2D":r"HORIZONTAL_RMSE|RMSE2D|horizontal.*RMSE",
 "PRODUCT_ADJUST":r"PRODUCT_ADJUST|product.*adjust|adjust.*product|residuali"}
 out=[]
 for q in sorted(PYC.rglob("*.py"),key=lambda x:str(x).lower()):
  try:
   if q.stat().st_size>4*1024**2:continue
   txt=q.read_text(encoding="utf-8",errors="ignore")
  except:continue
  if not any(x.lower() in txt.lower() for x in terms) and not any(re.search(p,txt,re.I) for p in pats.values()):continue
  for i,line in enumerate(txt.splitlines(),1):
   for t in terms:
    if t.lower() in line.lower():out.append({"Script":str(q),"Line":i,"Group":"SOURCE_REFERENCE","Pattern":t,"Snippet":line.strip()[:500]})
   for g,pat in pats.items():
    if re.search(pat,line,re.I):out.append({"Script":str(q),"Line":i,"Group":g,"Pattern":pat,"Snippet":line.strip()[:500]})
 return out
def main():
 pp=find(PRIMARY);sp=find(SECONDARY)
 if pp is None:raise FileNotFoundError("Primary Comment11 audit not found")
 pa,pids,pm=anchor(pp)
 if sp:sa,sids,sm=anchor(sp)
 else:sa=None;sids=[];sm={}
 print("Phase 1/4: header-only discovery")
 inv,short=header_scan()
 pd.DataFrame(inv).to_csv(OUT/"COMMENT12_V1_1_HEADER_INVENTORY.csv",index=False,encoding="utf-8-sig")
 pd.DataFrame([{"Rank":i+1,"Header_Score":x[0],"File":str(x[1]),"Groups":"|".join(x[2])} for i,x in enumerate(short)]).to_csv(OUT/"COMMENT12_V1_1_SHORTLIST.csv",index=False,encoding="utf-8-sig")
 print(f"Phase 2/4: {len(short)} shortlisted files")
 rows,log=scan(short,pa,sa,pm,sm);d=pd.DataFrame(rows)
 if not d.empty:d=d.sort_values(["Stage","Target","Match_Fraction","Header_Score"],ascending=[1,1,0,0])
 s1=d[d.Stage=="STAGE1"] if not d.empty else pd.DataFrame()
 s2=d[d.Stage.str.startswith("STAGE2")] if not d.empty else pd.DataFrame()
 s1.to_csv(OUT/"COMMENT12_V1_1_STAGE1_CANDIDATES.csv",index=False,encoding="utf-8-sig")
 s2.to_csv(OUT/"COMMENT12_V1_1_STAGE2_CANDIDATES.csv",index=False,encoding="utf-8-sig")
 pd.DataFrame(log).to_csv(OUT/"COMMENT12_V1_1_LOAD_LOG.csv",index=False,encoding="utf-8-sig")
 expected=[("STAGE1","CMC_P95"),("STAGE1","CMC_ROBUST"),("STAGE1","CN0"),("STAGE2_ADJUSTED","OUTCOME")]
 if sa is not None:expected.append(("STAGE2_UNADJUSTED","OUTCOME"))
 top=[];blocks=[]
 for st,t in expected:
  g=d[(d.Stage==st)&(d.Target==t)] if not d.empty else pd.DataFrame()
  if g.empty:blocks.append({"Issue":f"NO_CANDIDATE_{st}_{t}","Detail":"No dataset+numeric candidate"});continue
  r=g.iloc[0].to_dict();top.append(r)
  if r["Match_Fraction"]<.9:blocks.append({"Issue":f"NO_STRONG_{st}_{t}","Detail":f"{r['Match_N']}/{r['Anchor_N']} {r['Candidate_File']}::{r['Candidate_Column']}"})
 pd.DataFrame(top).to_csv(OUT/"COMMENT12_V1_1_TOP_CANDIDATES.csv",index=False,encoding="utf-8-sig")
 print("Phase 3/4: top candidates selected")
 h=codehits(top);pd.DataFrame(h).to_csv(OUT/"COMMENT12_V1_1_CODE_HITS.csv",index=False,encoding="utf-8-sig")
 print("Phase 4/4: targeted code scan complete")
 if blocks:pd.DataFrame(blocks).to_csv(OUT/"COMMENT12_V1_1_BLOCKERS.csv",index=False,encoding="utf-8-sig")
 smry=OUT/"COMMENT12_V1_1_SUMMARY.txt"
 with smry.open("w",encoding="utf-8") as f:
  f.write("GNSS Comment 12 — Fast Upstream Provenance Scanner v1.1\n"+"="*100+"\n\n")
  f.write(f"Primary anchor: {pp}\nPrimary ID: {pids}\nSecondary anchor: {sp or 'NOT FOUND'}\nSecondary ID: {sids or 'N/A'}\n")
  f.write(f"Header files inspected: {len(inv)}\nShortlisted: {len(short)}\nCandidate matches: {len(d)}\nCode hits: {len(h)}\nBlockers: {len(blocks)}\n\nTOP CANDIDATES\n"+"-"*100+"\n")
  for r in top:f.write(f"{r['Stage']:18s} | {r['Target']:10s} | {r['Match_N']}/{r['Anchor_N']} ({r['Match_Fraction']:.3f}) | {r['Candidate_File']} :: {r['Candidate_Column']} | ID={r['Candidate_ID_Columns']} | {r['Evidence_Level']}\n")
  f.write("\nRule: >=90% dataset-ID + numeric match = strong Level-A evidence. Confirm Level-B transformation semantics from code hits before FULL_LINEAGE_PASS. No manuscript global replacement.\n")
  if blocks:
   f.write("\nBLOCKERS\n"+"-"*100+"\n")
   for b in blocks:f.write(f"{b['Issue']} | {b['Detail']}\n")
 print(smry.read_text(encoding="utf-8"))
if __name__=="__main__":
 try:main()
 except Exception:
  e=traceback.format_exc();print(e)
  pd.DataFrame([{"Issue":"FATAL_ERROR","Detail":e}]).to_csv(OUT/"COMMENT12_V1_1_BLOCKERS.csv",index=False,encoding="utf-8-sig")
  raise
