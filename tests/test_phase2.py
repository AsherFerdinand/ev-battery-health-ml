from pipeline import ROOT
import json,unittest
import numpy as np
import pandas as pd
from types import SimpleNamespace
from phase2 import engineered,conformal_radius,BASE,EXTRA,OUT
class Phase2Tests(unittest.TestCase):
 def data(self):
  t=np.arange(0,1201,10,dtype=float)
  return SimpleNamespace(Time=t,Voltage_measured=4.2-.0002*t,Current_measured=np.full(len(t),-2.),Temperature_measured=24+.002*t)
 def test_physical_units_and_cutoff(self):
  d=self.data();f=engineered(d,24)
  self.assertAlmostEqual(f['v_slope_v_s'],-.0002)
  self.assertAlmostEqual(f['temp_slope_c_s'],.002)
  self.assertAlmostEqual(f['temp_rise'],1.8)
  self.assertAlmostEqual(f['v_curvature_v_s2'],0.,places=10)
  for key in ['Voltage_measured','Current_measured','Temperature_measured']:getattr(d,key)[d.Time>900]=999
  self.assertEqual(f,engineered(d,24))
  self.assertFalse(set(BASE+EXTRA)&{'Capacity','capacity','soh_pct','cycle','cell','resistance'})
 def test_conformal_order_statistic(self):
  self.assertEqual(conformal_radius(np.arange(1,10),.1),9)
  self.assertTrue(np.isinf(conformal_radius([3.],.1)))
 @unittest.skipUnless((ROOT/'reports/phase2/interval_audit.json').exists(), 'Generate experiment artifacts first; see README')
 def test_nested_and_calibration_separation(self):
  for row in json.loads((OUT/'tuning_audit.json').read_text()):
   self.assertNotIn(row['test_cell'],row['training_cells']);self.assertEqual(len(row['training_cells']),3)
   self.assertEqual(row['selected'],row['candidate_configs'][int(np.argmin(row['inner_macro_cell_mae']))])
  for row in json.loads((OUT/'interval_audit.json').read_text()):
   self.assertNotIn(row['test_cell'],row['fit_cells']);self.assertNotIn(row['calibration_cell'],row['fit_cells'])
   self.assertNotEqual(row['test_cell'],row['calibration_cell']);self.assertEqual(len(row['fit_cells']),2)
 @unittest.skipUnless((ROOT/'reports/phase2/interval_predictions.csv').exists(), 'Generate experiment artifacts first; see README')
 def test_metrics_and_interval_consistency(self):
  p=pd.read_csv(OUT/'predictions.csv');m=pd.read_csv(OUT/'cell_metrics.csv')
  self.assertEqual(len(m),24)
  for row in m.itertuples():
   g=p[(p.cell==row.cell)&(p.feature_set==row.feature_set)&(p.model==row.model)]
   self.assertAlmostEqual(row.mae_pp,abs(g.predicted-g.actual).mean())
   self.assertAlmostEqual(row.rmse_pp,np.sqrt(np.mean((g.predicted-g.actual)**2)))
  q=pd.read_csv(OUT/'interval_predictions.csv')
  self.assertTrue((q.lower<=q.upper).all())
  self.assertTrue((q.covered==((q.actual>=q.lower)&(q.actual<=q.upper))).all())
