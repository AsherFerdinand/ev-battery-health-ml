"""Evaluate frozen estimators ONLY on explicitly reviewed canonical external data.
No model fitting, feature changes, calibration or parameter search in this file.
"""
import argparse,json
from types import SimpleNamespace
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from pipeline import ROOT,sha256
from phase2 import engineered
from phase4_freeze import verify,MODEL_DIR
OUT=ROOT/'reports/phase4/direct_transfer'
COLUMNS=['cell','cycle','time_s','voltage_v','current_a','temperature_c','ambient_c']

def validate_metadata(meta):
 required=['dataset','chemistry','nominal_capacity_ah','discharge_protocol','capacity_reference_protocol','sampling_description','temperature_source','ambient_source','provenance','units','compatibility_review']
 missing=[k for k in required if k not in meta or not meta[k]]
 if missing:raise ValueError('Unverified metadata: '+','.join(missing))
 if meta['compatibility_review']!='verified_without_feature_changes':raise ValueError('Compatibility not verified; no inference allowed')
 if float(meta['nominal_capacity_ah'])<=0:raise ValueError('Invalid nominal capacity')
 if meta['units']!=dict(time='s',voltage='V',current='A_negative_discharge',temperature='degC',capacity='Ah'):raise ValueError('Canonical units/sign not confirmed')
 if meta['ambient_source'] not in ['recorded','documented_test_setpoint']:raise ValueError('Ambient temperature must not be guessed')

def prepare(samples,capacities):
 if set(COLUMNS)-set(samples.columns):raise ValueError('Missing required measurement columns; no imputation allowed')
 if set(['cell','cycle','capacity_ah'])-set(capacities.columns):raise ValueError('Missing independent measured capacity label')
 if capacities.duplicated(['cell','cycle']).any():raise ValueError('Duplicate capacity labels')
 rows=[];rejections=[]
 for (cell,cycle),g in samples.groupby(['cell','cycle'],sort=True):
  g=g.sort_values('time_s')
  try:
   if g.time_s.duplicated().any():raise ValueError('Duplicate time stamps')
   if not np.isfinite(g[COLUMNS[2:]].to_numpy(dtype=float)).all():raise ValueError('Nonfinite/missing measured channels; no substitution')
   if g.current_a.median()>=0:raise ValueError('Canonical discharge current must be negative')
   if g.ambient_c.max()-g.ambient_c.min()>1e-6:raise ValueError('Varying ambient is incompatible with scalar NASA ambient feature; needs explicit review')
   d=SimpleNamespace(Time=g.time_s.to_numpy(),Voltage_measured=g.voltage_v.to_numpy(),Current_measured=g.current_a.to_numpy(),Temperature_measured=g.temperature_c.to_numpy())
   f=engineered(d,float(g.ambient_c.iloc[0]),900)
   label=capacities[(capacities.cell==cell)&(capacities.cycle==cycle)]
   if len(label)!=1 or not np.isfinite(label.capacity_ah.iloc[0]) or label.capacity_ah.iloc[0]<=0:raise ValueError('Missing/invalid measured capacity')
   rows.append(dict(cell=cell,cycle=cycle,capacity_ah=float(label.capacity_ah.iloc[0]),**f))
  except ValueError as e:rejections.append(dict(cell=str(cell),cycle=int(cycle),reason=str(e)))
 return pd.DataFrame(rows),rejections

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path,help='Reviewed canonical data directory containing metadata.json, samples.csv, capacities.csv');args=parser.parse_args()
 frozen=verify();meta=json.loads((args.directory/'metadata.json').read_text());validate_metadata(meta)
 samples=pd.read_csv(args.directory/'samples.csv');capacities=pd.read_csv(args.directory/'capacities.csv');df,reject=prepare(samples,capacities)
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'rejections.json').write_text(json.dumps(reject,indent=2))
 if df.empty:raise ValueError('No compatible external cycles; no performance claim permitted')
 df['actual_soh_pct']=df.capacity_ah/float(meta['nominal_capacity_ah'])*100
 predictions=[];shifts=[]
 for model,record in frozen['models'].items():
  reg=joblib.load(MODEL_DIR/record['artifact']) # Only own hash-verified local artifacts.
  pred=reg.predict(df[record['features']])
  for row,y in zip(df.itertuples(),pred):predictions.append(dict(model=model,cell=row.cell,cycle=row.cycle,actual_soh_pct=row.actual_soh_pct,predicted_soh_pct=float(y),residual_pp=float(y-row.actual_soh_pct)))
  for feature in record['features']:
   lo=record['training_feature_min'][feature];hi=record['training_feature_max'][feature]
   for cell,g in df.groupby('cell'):shifts.append(dict(model=model,cell=cell,feature=feature,nasa_min=lo,nasa_max=hi,external_min=float(g[feature].min()),external_max=float(g[feature].max()),fraction_outside_nasa_range=float(((g[feature]<lo)|(g[feature]>hi)).mean())))
 p=pd.DataFrame(predictions);p.to_csv(OUT/'predictions.csv',index=False)
 m=p.groupby(['model','cell']).agg(n=('cycle','size'),mae_pp=('residual_pp',lambda x:abs(x).mean()),rmse_pp=('residual_pp',lambda x:np.sqrt(np.mean(x*x))),signed_bias_pp=('residual_pp','mean')).reset_index();m['flag_mae_gt5']=m.mae_pp>5;m.to_csv(OUT/'cell_metrics.csv',index=False)
 pd.DataFrame(shifts).to_csv(OUT/'feature_shift.csv',index=False);p.reindex(p.residual_pp.abs().sort_values(ascending=False).index).head(50).to_csv(OUT/'failure_cases.csv',index=False)
 (OUT/'evaluation_manifest.json').write_text(json.dumps(dict(dataset_metadata=meta,inputs={n:sha256(args.directory/n) for n in ['metadata.json','samples.csv','capacities.csv']},frozen_manifest_sha256=sha256(MODEL_DIR/'freeze_manifest.json'),external_retraining=False,actual_evaluation=True),indent=2));verify();print(m.to_string(index=False))
if __name__=='__main__':main()
