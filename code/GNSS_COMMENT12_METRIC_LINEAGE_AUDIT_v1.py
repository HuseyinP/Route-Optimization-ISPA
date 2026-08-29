# -*- coding: utf-8 -*-
"""
GNSS_COMMENT12_METRIC_LINEAGE_AUDIT_v1.py

Read-only provenance audit for Reviewer Comment 12.

It separates the identity of a Stage-1 predictor from the statistical branch
in which it is used. In particular, CMC_P95, CMC_ROBUST and CN0 may each occur
with different outcomes/adjustments; those claims are not interchangeable.

Outputs are written to:
C:\IEEE\GNSS_ANALYSIS\COMMENT12_METRIC_LINEAGE_AUDIT_V1
"""
from pathlib import Path
import math, re
import numpy as np
import pandas as pd

ROOT=Path(r"C:\IEEE")
AROOT=ROOT/"GNSS_ANALYSIS"
OUT=AROOT/"COMMENT12_METRIC_LINEAGE_AUDIT_V1"; OUT.mkdir(parents=True,exist_ok=True)
REGS=[
 AROOT/"COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1"/"COMMENT12_FINAL_EVIDENCE_REGISTRY.csv",
 ROOT/"COMMENT12_FINAL_EVIDENCE_REGISTRY.csv"]
HINTS=("COMMENT11","COMMENT12","CLUSTER","DEPENDENCE","PERMUT","LOTO","ICC","CORREL","ASSOCI","PRODUCT_ADJUST","FIXED_EFFECT")
SKIPS=("MANUSCRIPT_NUMERICAL","REVISION_ACTION","SECTION_CONSISTENCY","STATISTIC_INVENTORY","METRIC_LINEAGE")
METRICS=["CMC_P95","CMC_ROBUST","CN0"]
EXPECTED={m:("RMSE2D","PRODUCT_ADJUSTED","TEST_BLOCKED_EXACT_PERMUTATION") for m in METRICS}
ALIASES={
"CMC_P95":["CMC_P95","GPS_L1_CMC_P95","CMC P95","CMC_ABS_P95","P95_CMC"],
"CMC_ROBUST":["CMC_ROBUST","CMC_ROBUST_DISPERSION","ROBUST_CMC_DISPERSION","CMC_ROBUST_SIGMA","ROBUST_SIGMA_CMC"],
"CN0":["CN0","CNO","C_N0","C/N0","MEDIAN_CN0","CN0_MEDIAN"]}
OUTCOMES={
"RMSE2D":["RMSE2D","RMSE_2D","2D_RMSE","HORIZONTAL_RMSE","MEDIAN_HORIZONTAL_RMSE","CLEAN_RMSE2D"],
"RMSE3D":["RMSE3D","RMSE_3D","3D_RMSE","MEDIAN_3D_RMSE","CLEAN_RMSE3D"],
"PRODUCT_SENSITIVITY":["PRODUCT_SENSITIVITY","PRODUCT_RANGE","RMSE_RANGE","HORIZONTAL_RMSE_RANGE","ACROSS_PRODUCT_RANGE"]}

def nt(x):
 s=str(x or "").upper().replace("₀","0")
 return re.sub(r"_+","_",re.sub(r"[^A-Z0-9]+","_",s)).strip("_")
def fin(x):
 try:return math.isfinite(float(x))
 except:return False
def ff(x):
 try:return float(x)
 except:return np.nan
def canon(v,d):
 n=nt(v)
 for k,aa in d.items():
  for a in aa:
   z=nt(a)
   if n==z or (len(z)>=4 and z in n): return k
 return None
def metric(v):return canon(v,ALIASES)
def outcome(v):return canon(v,OUTCOMES)
def adjustment(s):
 n=nt(s)
 if "PRODUCT_ADJUST" in n or "PRODUCT_RESID" in n or "ADJUSTED_FOR_PRODUCT" in n:return "PRODUCT_ADJUSTED"
 if "FIXED_EFFECT" in n or "PARTIAL_R2" in n:return "PRODUCT_FIXED_EFFECT"
 if "UNADJUSTED" in n:return "UNADJUSTED"
 if "LOTO" in n or "LEAVE_ONE_TEST_OUT" in n:return "LOTO"
 return "UNRESOLVED"
def testname(s):
 n=nt(s)
 if "TEST_BLOCK" in n and ("EXACT" in n or "PERMUT" in n):return "TEST_BLOCKED_EXACT_PERMUTATION"
 if "FIXED_EFFECT" in n and "PERMUT" in n:return "FIXED_EFFECT_PERMUTATION"
 if "EXACT" in n and "PERMUT" in n:return "EXACT_PERMUTATION"
 if "PERMUT" in n:return "PERMUTATION"
 if "SPEARMAN" in n:return "SPEARMAN"
 if "ICC" in n:return "ICC"
 return "UNRESOLVED"
def findreg():
 for p in REGS:
  if p.exists():return p
 raise FileNotFoundError("Final evidence registry not found:\n"+"\n".join(map(str,REGS)))
def discover():
 out=[]
 if not AROOT.exists():return out
 for p in AROOT.rglob("*.csv"):
  u=p.name.upper()
  if any(x in u for x in SKIPS):continue
  if any(x in u for x in HINTS):out.append(p)
 return sorted(set(out),key=lambda p:str(p).lower())
def readcsv(p):
 try:
  if p.stat().st_size>80*1024**2:return None
  return pd.read_csv(p)
 except:
  try:return pd.read_csv(p,sep=None,engine="python")
  except:return None
def role(c):
 n=nt(c)
 if n in ("RHO","SPEARMAN_RHO") or "RHO" in n:return "RHO"
 if n in ("P","P_VALUE","PVALUE","EXACT_P","PERMUTATION_P") or n.endswith("_P_VALUE"):return "P"
 if n in ("Q","Q_VALUE","QVALUE") or "FDR" in n:return "Q"
 if n in ("N","SAMPLE_SIZE","DATASET_N","N_DATASETS"):return "N"
 if n in ("METRIC","METRIC_NAME","QUALITY_METRIC","PREDICTOR") or ("METRIC" in n and "VALUE" not in n):return "METRIC"
 if n in ("OUTCOME","OUTCOME_NAME","RESPONSE","DEPENDENT_VARIABLE") or "OUTCOME" in n:return "OUTCOME"
 return "OTHER"
def rowtxt(r):
 return " | ".join(f"{c}={v}" for c,v in r.items() if not pd.isna(v))
def firstnum(r,cols):
 for c in cols:
  if fin(r.get(c)):return float(r[c]),c
 return np.nan,""
def infer_metric(r,df):
 for c in df.columns:
  if role(c)=="METRIC":
   m=metric(r.get(c,""))
   if m:return m
 for v in r.values:
  if not pd.isna(v):
   m=metric(v)
   if m:return m
 return None
def infer_outcome(r,df):
 for c in df.columns:
  if role(c)=="OUTCOME":
   o=outcome(r.get(c,""))
   if o:return o
 t=rowtxt(r)
 return outcome(t) or "UNRESOLVED"

def main():
 regp=findreg(); reg=pd.read_csv(regp)
 prim=reg[reg["Evidence_Role"].astype(str)=="PRIMARY_INFERENCE"].copy()
 locks={}
 for _,r in prim.iterrows():
  m=metric(r.get("Metric","")) or str(r.get("Metric",""))
  if m in METRICS:
   locks[m]={"rho":ff(r["Rho"]),"p":ff(r["P"]),"claim":str(r["Claim_ID"]),
             "source":str(r.get("Source_CSV","")),"row":str(r.get("Source_Row","")),
             "N":ff(r.get("N",np.nan))}
 if set(locks)!=set(METRICS):raise RuntimeError(f"Primary metric mismatch: {sorted(locks)}")

 files=discover()
 if regp not in files:files.append(regp)
 inventory=[]; columns=[]; claims=[]
 for p in sorted(set(files),key=lambda x:str(x).lower()):
  df=readcsv(p)
  if df is None:
   inventory.append({"File":str(p),"Read_Status":"SKIP_OR_PARSE_FAIL"})
   continue
  ms=set(); os=set()
  for c in df.columns:
   m=metric(c); o=outcome(c)
   if m:ms.add(m)
   if o:os.add(o)
   columns.append({"File":str(p),"Column":c,"Role":role(c),"Canonical_Metric":m or "",
                   "Canonical_Outcome":o or "","Dtype":str(df[c].dtype),
                   "NonNull_N":int(df[c].notna().sum())})
  inventory.append({"File":str(p),"Read_Status":"OK","Rows":len(df),"Columns":len(df.columns),
                    "Metric_Columns":"|".join(sorted(ms)),"Outcome_Columns":"|".join(sorted(os))})
  rc=[c for c in df.columns if role(c)=="RHO"]; pc=[c for c in df.columns if role(c)=="P"]
  qc=[c for c in df.columns if role(c)=="Q"]; nc=[c for c in df.columns if role(c)=="N"]
  if not rc and not pc:continue
  for i,r in df.iterrows():
   m=infer_metric(r,df)
   if m not in METRICS:continue
   rho,rhoc=firstnum(r,rc); pv,pcv=firstnum(r,pc); q,qc1=firstnum(r,qc); n,nc1=firstnum(r,nc)
   if not any(fin(x) for x in (rho,pv,q)):continue
   txt=rowtxt(r); o=infer_outcome(r,df); a=adjustment(txt+" "+p.name); t=testname(txt+" "+p.name)
   claims.append({"Source_File":str(p),"Source_Row_1Based_Data":i+1,"Metric":m,"Outcome":o,
                  "Adjustment":a,"Statistical_Test":t,"Rho":rho if fin(rho) else "",
                  "P":pv if fin(pv) else "","Q":q if fin(q) else "","N":n if fin(n) else "",
                  "Rho_Column":rhoc,"P_Column":pcv,"Q_Column":qc1,"N_Column":nc1,"Row_Text":txt[:2500]})

 primary=[]; blockers=[]
 for m in METRICS:
  lock=locks[m]; eo,ea,et=EXPECTED[m]; scored=[]
  for c in [x for x in claims if x["Metric"]==m]:
   sc=10; why=["metric"]
   if c["Outcome"]==eo:sc+=8;why.append("outcome")
   if c["Adjustment"]==ea:sc+=8;why.append("adjustment")
   if c["Statistical_Test"]==et:sc+=8;why.append("test")
   if fin(c["Rho"]) and abs(float(c["Rho"])-lock["rho"])<=5e-6:sc+=12;why.append("rho")
   if fin(c["P"]) and abs(float(c["P"])-lock["p"])<=5e-6:sc+=12;why.append("p")
   if lock["source"] and Path(lock["source"]).name.lower()==Path(c["Source_File"]).name.lower():sc+=20;why.append("registry_source")
   scored.append((sc,why,c))
  scored.sort(key=lambda z:z[0],reverse=True)
  if not scored:
   status="BLOCKED_NO_UPSTREAM_ROW"; c={}
   blockers.append({"Metric":m,"Issue":status,"Detail":"No upstream statistical row linked."})
  else:
   sc,why,c=scored[0]
   sem=(c["Outcome"]==eo and c["Adjustment"]==ea and c["Statistical_Test"]==et)
   num=(fin(c["Rho"]) and abs(float(c["Rho"])-lock["rho"])<=5e-6 and fin(c["P"]) and abs(float(c["P"])-lock["p"])<=5e-6)
   amb=len(scored)>1 and scored[1][0]==sc
   if sem and num and not amb:status="PASS_FULL_LINEAGE"
   elif num:status="VERIFY_SEMANTIC_LINEAGE"
   elif sem:status="BLOCKED_NUMERIC_MISMATCH"
   elif amb:status="VERIFY_AMBIGUOUS_SOURCE_ROW"
   else:status="BLOCKED_LINEAGE_INCOMPLETE"
   if status!="PASS_FULL_LINEAGE":blockers.append({"Metric":m,"Issue":status,"Detail":"Complete semantic + numerical lineage not proven."})
  primary.append({"Metric":m,"Expected_Outcome":eo,"Expected_Adjustment":ea,"Expected_Test":et,
                  "Registry_Claim_ID":lock["claim"],"Registry_Rho":lock["rho"],"Registry_P":lock["p"],
                  "Registry_Source_CSV":lock["source"],"Registry_Source_Row":lock["row"],
                  "Matched_Source_File":c.get("Source_File",""),"Matched_Source_Row":c.get("Source_Row_1Based_Data",""),
                  "Matched_Outcome":c.get("Outcome",""),"Matched_Adjustment":c.get("Adjustment",""),
                  "Matched_Test":c.get("Statistical_Test",""),"Matched_Rho":c.get("Rho",""),
                  "Matched_P":c.get("P",""),"Matched_Q":c.get("Q",""),"Lineage_Status":status,
                  "Evidence":"|".join(why) if scored else ""})

 branches=[]
 for m in METRICS:
  gs={}
  for c in claims:
   if c["Metric"]!=m:continue
   k=(c["Outcome"],c["Adjustment"],c["Statistical_Test"]);gs.setdefault(k,[]).append(c)
  for k,ii in sorted(gs.items()):
   rr=sorted(set(str(c["Rho"]) for c in ii if c["Rho"]!=""))
   pp=sorted(set(str(c["P"]) for c in ii if c["P"]!=""))
   qq=sorted(set(str(c["Q"]) for c in ii if c["Q"]!=""))
   isp=k==EXPECTED[m]
   branches.append({"Metric":m,"Outcome":k[0],"Adjustment":k[1],"Statistical_Test":k[2],
                    "Rows_N":len(ii),"Rho_Values":"|".join(rr),"P_Values":"|".join(pp),"Q_Values":"|".join(qq),
                    "Is_Primary_Branch":isp,"Interpretation":"PRIMARY" if isp else "DISTINCT_BRANCH_DO_NOT_SUBSTITUTE",
                    "Source_Files":"|".join(sorted(set(Path(c["Source_File"]).name for c in ii)))})

 pd.DataFrame(inventory).to_csv(OUT/"COMMENT12_LINEAGE_SOURCE_INVENTORY.csv",index=False,encoding="utf-8-sig")
 pd.DataFrame(columns).to_csv(OUT/"COMMENT12_LINEAGE_COLUMN_DICTIONARY.csv",index=False,encoding="utf-8-sig")
 pd.DataFrame(claims).to_csv(OUT/"COMMENT12_LINEAGE_CLAIM_MAP.csv",index=False,encoding="utf-8-sig")
 pd.DataFrame(primary).to_csv(OUT/"COMMENT12_LINEAGE_PRIMARY_LOCK.csv",index=False,encoding="utf-8-sig")
 pd.DataFrame(branches).to_csv(OUT/"COMMENT12_LINEAGE_BRANCH_SEPARATION.csv",index=False,encoding="utf-8-sig")
 if blockers:pd.DataFrame(blockers).to_csv(OUT/"COMMENT12_LINEAGE_BLOCKERS.csv",index=False,encoding="utf-8-sig")
 s=OUT/"COMMENT12_LINEAGE_AUDIT_SUMMARY.txt"
 with s.open("w",encoding="utf-8") as f:
  f.write("GNSS Comment 12 — Metric Lineage Audit v1\n"+"="*100+"\n\n")
  f.write(f"Registry: {regp}\nCandidate CSVs: {len(files)}\nRelevant statistical rows: {len(claims)}\nBlockers/verification: {len(blockers)}\n\n")
  f.write("PRIMARY LINEAGE\n"+"-"*100+"\n")
  for r in primary:
   f.write(f"{r['Metric']:10s} -> {r['Expected_Outcome']} | {r['Expected_Adjustment']} | {r['Expected_Test']} | rho={r['Registry_Rho']:.6f}, p={r['Registry_P']:.6f} | {r['Lineage_Status']}\n")
   f.write(f"  matched source={r['Matched_Source_File'] or 'NONE'} row={r['Matched_Source_Row'] or 'NA'}; outcome={r['Matched_Outcome'] or 'NA'}; adjustment={r['Matched_Adjustment'] or 'NA'}; test={r['Matched_Test'] or 'NA'}; rho={r['Matched_Rho'] or 'NA'}; p={r['Matched_P'] or 'NA'}; q={r['Matched_Q'] or 'NA'}\n")
  f.write("\nDISTINCT BRANCHES\n"+"-"*100+"\n")
  for r in branches:
   f.write(f"{r['Metric']:10s} | {r['Outcome']:19s} | {r['Adjustment']:20s} | {r['Statistical_Test']:31s} | rho={r['Rho_Values'] or 'NA'} | p={r['P_Values'] or 'NA'} | q={r['Q_Values'] or 'NA'} | {r['Interpretation']}\n")
  if blockers:
   f.write("\nBLOCKERS / VERIFY\n"+"-"*100+"\n")
   for b in blockers:f.write(f"{b['Metric']} | {b['Issue']} | {b['Detail']}\n")
  f.write("\nPUBLICATION RULE\n"+"-"*100+"\n")
  f.write("No global numerical replacement is permitted. Revise the manuscript section by section. For each sentence first lock predictor, outcome, adjustment, statistical method, and authoritative source row; then insert the corresponding statistic. Preserve unadjusted, 3D-RMSE, product-sensitivity, LOTO, fixed-effect and ICC branches as distinct evidence.\n")
 print(s.read_text(encoding="utf-8"))
if __name__=="__main__":main()
