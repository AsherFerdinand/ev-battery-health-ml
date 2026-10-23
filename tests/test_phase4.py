import unittest,json,hashlib,io,zipfile,tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from pipeline import ROOT
from phase4_freeze import verify,MODEL_DIR
from phase4_evaluate import prepare,validate_metadata
from phase4_inspect import inventory
class Phase4Tests(unittest.TestCase):
 @unittest.skipUnless((ROOT/'models/phase4/freeze_manifest.json').exists(), 'Generate experiment artifacts first; see README')
 def test_frozen_integrity_and_nasa_only_provenance(self):
  m=verify();self.assertFalse(m['external_data_used']);self.assertEqual(m['training_rows'],636)
  self.assertEqual(set(m['models']),{'random_forest','hist_gradient_boosting'})
  self.assertEqual(m['window_seconds'],900)
 def test_metadata_does_not_allow_assumed_compatibility(self):
  with self.assertRaises(ValueError):validate_metadata({})
  m=dict(dataset='synthetic test fixture, not external evidence',chemistry='test',nominal_capacity_ah=1.1,discharge_protocol='fixture',capacity_reference_protocol='fixture',sampling_description='10 s fixture',temperature_source='fixture',ambient_source='guessed',provenance='fixture',units=dict(time='s',voltage='V',current='A_negative_discharge',temperature='degC',capacity='Ah'),compatibility_review='verified_without_feature_changes')
  with self.assertRaises(ValueError):validate_metadata(m)
  m['ambient_source']='recorded';validate_metadata(m)
 def fixture(self):
  t=np.arange(0,1001,10,dtype=float)
  return pd.DataFrame(dict(cell='SYNTHETIC',cycle=1,time_s=t,voltage_v=4.2-.0003*t,current_a=-1.,temperature_c=24+.001*t,ambient_c=24.))
 def test_adapter_does_not_use_capacity_as_feature(self):
  x=self.fixture();labels=pd.DataFrame(dict(cell=['SYNTHETIC'],cycle=[1],capacity_ah=[1.]))
  a,rejected=prepare(x,labels);self.assertFalse(rejected)
  labels.capacity_ah=.5;b,_=prepare(x,labels)
  pd.testing.assert_frame_equal(a.drop(columns='capacity_ah'),b.drop(columns='capacity_ah'))
  for col in ['voltage_v','temperature_c','current_a']:x.loc[x.time_s>900,col]=999
  c,_=prepare(x,labels);pd.testing.assert_frame_equal(b,c)
 def test_missing_temperature_and_short_windows_rejected(self):
  labels=pd.DataFrame(dict(cell=['SYNTHETIC'],cycle=[1],capacity_ah=[1.]))
  with self.assertRaises(ValueError):prepare(self.fixture().drop(columns='temperature_c'),labels)
  x=self.fixture();x.time_s=x.time_s/2
  data,reject=prepare(x,labels);self.assertTrue(data.empty);self.assertTrue(reject)
 def test_offline_archive_inventory(self):
  import uuid
  (ROOT/'work').mkdir(exist_ok=True)
  p=ROOT/'work'/('phase4_fixture_'+uuid.uuid4().hex+'.zip')
  try:
   with zipfile.ZipFile(p,'w') as z:z.writestr('README.txt','Synthetic fixture; no measured external data')
   result=inventory(p);self.assertEqual(result['files'][0]['name'],'README.txt');self.assertEqual(len(result['sha256']),64)
  finally:
   if p.exists():p.unlink()
 @unittest.skipUnless((ROOT/'reports/phase4/status.json').exists(), 'Generate experiment artifacts first; see README')
 def test_status_does_not_invent_metrics(self):
  m=json.loads((ROOT/'reports/phase4/status.json').read_text())
  self.assertFalse(m['external_evaluation_performed']);self.assertIsNone(m['external_metrics'])
 def test_downloaded_calce_thermal_schema_gate(self):
  path=ROOT/'reports/phase4/calce_raw_audit.json'
  if not path.exists():self.skipTest('Optional downloaded CALCE audit not present')
  rows=json.loads(path.read_text());self.assertEqual(len(rows),2)
  for r in rows:
   self.assertFalse(r['direct_transfer_compatible']);self.assertEqual(r['thermal_headers'],[])
   self.assertEqual(r['xlsx_workbooks'],r['telemetry_sheets'])
   self.assertTrue(r['info_temp_mapping_all_zero'])
   self.assertEqual(set(r['missing_features']),{'temp_start','temp_rise','ambient'})
   self.assertGreater(r['representative']['negative_current_rows'],0)
 @unittest.skipUnless((ROOT/'models/phase4/freeze_manifest.json').exists(), 'Generate experiment artifacts first; see README')
 def test_frozen_feature_requirements_include_missing_channels(self):
  m=verify()
  for record in m['models'].values():self.assertTrue({'temp_start','temp_rise','ambient'}<=set(record['features']))
