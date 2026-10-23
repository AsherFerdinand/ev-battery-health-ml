"""Create immutable NASA-only transfer artifacts; never fit on external data."""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
import json
from datetime import datetime,timezone
import joblib
import pandas as pd
from pipeline import ROOT,CELLS,sha256
from phase2 import BASE,estimator,nested_select
from phase3 import FOCUSED
MODEL_DIR=ROOT/'models/phase4'
REPORT_DIR=ROOT/'reports/phase4'
RECIPES={'random_forest':BASE,'hist_gradient_boosting':FOCUSED}

def main():
 MODEL_DIR.mkdir(parents=True,exist_ok=True);REPORT_DIR.mkdir(parents=True,exist_ok=True)
 manifest=MODEL_DIR/'freeze_manifest.json'
 if manifest.exists():
  verify();print('Existing freeze verified; no retraining.');return
 data_path=ROOT/'reports/phase3/features.csv'
 df=pd.read_csv(data_path);df=df[df.window=='15min'].copy()
 if set(df.cell)!=set(CELLS) or df.duplicated(['cell','cycle']).any():raise ValueError('Invalid NASA training cohort')
 metadata=dict(created_utc=datetime.now(timezone.utc).isoformat(),training_dataset='NASA B0005/B0006/B0007/B0018 only',training_rows=len(df),training_cells=list(CELLS),window_seconds=900,target='100 * measured NASA capacity_Ah / 2.0',selection='Phase 3 recipes unchanged. Inner leave-one-NASA-cell-out CV across all four cells, macro-cell MAE; final refit on all NASA cells. No single final Phase 3 artifact existed. These are new final NASA-only fits, NOT external retraining.',models={},source_hashes={p:sha256(ROOT/p) for p in ['phase2.py','phase3.py','phase4_freeze.py','window_experiment.py','pipeline.py','reports/phase3/recommendation.json']},training_features_sha256=sha256(data_path),raw_sha256={c:sha256(ROOT/f'data/raw/{c}.mat') for c in CELLS},external_data_used=False)
 import importlib.metadata
 metadata['versions']={n:importlib.metadata.version(n) for n in ['numpy','pandas','scipy','scikit-learn','joblib']}
 for model,cols in RECIPES.items():
  config,scores=nested_select(df,cols,model)
  reg=estimator(model,config);reg.fit(df[cols],df.soh_pct)
  path=MODEL_DIR/(model+'.joblib');joblib.dump(reg,path)
  metadata['models'][model]=dict(features=cols,selected_config=config,nasa_cv_candidate_mae=scores,artifact=path.name,artifact_sha256=sha256(path),imputation='NASA training medians; external missingness prohibited before prediction',scaling='NASA training only',training_feature_min={c:float(df[c].min()) for c in cols},training_feature_max={c:float(df[c].max()) for c in cols})
 manifest.write_text(json.dumps(metadata,indent=2))
 print(json.dumps({m:v['selected_config'] for m,v in metadata['models'].items()},indent=2));verify()

def verify():
 metadata=json.loads((MODEL_DIR/'freeze_manifest.json').read_text())
 for name,expected in metadata['source_hashes'].items():
  if sha256(ROOT/name)!=expected:raise ValueError('Frozen source changed: '+name)
 if sha256(ROOT/'reports/phase3/features.csv')!=metadata['training_features_sha256']:raise ValueError('Frozen NASA features changed')
 for c,h in metadata['raw_sha256'].items():
  if sha256(ROOT/f'data/raw/{c}.mat')!=h:raise ValueError('NASA raw changed: '+c)
 for model,record in metadata['models'].items():
  if sha256(MODEL_DIR/record['artifact'])!=record['artifact_sha256']:raise ValueError('Frozen model hash changed: '+model)
 return metadata
if __name__=='__main__':main()
