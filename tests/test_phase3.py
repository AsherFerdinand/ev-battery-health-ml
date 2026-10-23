from pipeline import ROOT
import unittest,json
import numpy as np
import pandas as pd
from phase3 import OUT,ABLATIONS,CORE,BASE,flag_mae
class Phase3Tests(unittest.TestCase):
 def test_acceptance_threshold(self):
  self.assertFalse(flag_mae(5.));self.assertTrue(flag_mae(5.000001));self.assertFalse(flag_mae(4.99))
 def test_factorial_controls(self):
  self.assertEqual(len(ABLATIONS),8)
  self.assertNotIn('temp_rise',CORE)
  self.assertEqual(set(ABLATIONS['core+temp_rise']),set(BASE))
  for cols in ABLATIONS.values():self.assertTrue(set(CORE)<=set(cols))
 @unittest.skipUnless((ROOT/'reports/phase3/split_tuning_audit.json').exists(), 'Generate experiment artifacts first; see README')
 def test_outer_and_inner_no_leakage(self):
  rows=json.loads((OUT/'split_tuning_audit.json').read_text())
  for r in rows:
   self.assertFalse(set(r['fit_keys'])&set(r['test_keys']))
   if r['protocol']=='leave_one_cell_out':self.assertFalse(set(r['fit_cells'])&set(r['test_cells']))
   else:
    for c in r['fit_cells']:
     fit=[int(k.split('_')[1]) for k in r['fit_keys'] if k.startswith(c+'_')]
     test=[int(k.split('_')[1]) for k in r['test_keys'] if k.startswith(c+'_')]
     self.assertLess(max(fit),min(test))
   for inner in r['inner_folds']:
    a=set(inner['fit_keys']);b=set(inner['validation_keys'])
    self.assertFalse(a&b);self.assertTrue((a|b)<=set(r['fit_keys']))
    if r['protocol']=='leave_one_cell_out':self.assertFalse({k.split('_')[0] for k in a}&{k.split('_')[0] for k in b})
    else:
     for c in r['fit_cells']:
      self.assertLess(max(int(k.split('_')[1]) for k in a if k.startswith(c+'_')),min(int(k.split('_')[1]) for k in b if k.startswith(c+'_')))
 @unittest.skipUnless((ROOT/'reports/phase3/predictions.csv').exists(), 'Generate experiment artifacts first; see README')
 def test_identical_benchmark_test_keys(self):
  p=pd.read_csv(OUT/'predictions.csv').query("experiment=='benchmark'")
  sets=[set(zip(g.cell,g.cycle)) for _,g in p.groupby(['window','split','feature_set','model'])]
  # Compare within split (not across inherently different tests).
  for split,g in p.groupby('split'):
   sets=[set(zip(h.cell,h.cycle)) for _,h in g.groupby(['window','feature_set','model'])]
   self.assertTrue(all(s==sets[0] for s in sets))
 @unittest.skipUnless((ROOT/'reports/phase3/predictions.csv').exists(), 'Generate experiment artifacts first; see README')
 def test_metrics_and_flags_recomputed(self):
  p=pd.read_csv(OUT/'predictions.csv');m=pd.read_csv(OUT/'cell_metrics.csv')
  for r in m.itertuples():
   g=p[(p.experiment==r.experiment)&(p.window==r.window)&(p.protocol==r.protocol)&(p.feature_set==r.feature_set)&(p.model==r.model)&(p.cell==r.cell)]
   self.assertAlmostEqual(r.mae_pp,abs(g.predicted-g.actual).mean())
   self.assertAlmostEqual(r.rmse_pp,np.sqrt(np.mean((g.predicted-g.actual)**2)))
   self.assertEqual(r.flag_mae_gt5,flag_mae(r.mae_pp))
  flags=json.loads((OUT/'acceptance_flags.json').read_text())
  self.assertEqual(flags['flagged_count'],int(m.flag_mae_gt5.sum()))
 @unittest.skipUnless((ROOT/'reports/phase3/permutation_importance.csv').exists(), 'Generate experiment artifacts first; see README')
 def test_importance_complete_and_finite(self):
  p=pd.read_csv(OUT/'permutation_importance.csv')
  self.assertEqual(set(p.protocol),{'temporal_70_30','leave_one_cell_out'})
  self.assertTrue(np.isfinite(p.mae_increase_pp).all())
  self.assertTrue((p.repeat_std_pp>=0).all())
  self.assertEqual(set(p.cell),{'B0005','B0006','B0007','B0018'})
 @unittest.skipUnless((ROOT/'reports/phase3/preserved_files.json').exists(), 'Generate experiment artifacts first; see README')
 def test_preserved_application(self):
  import hashlib
  from pipeline import ROOT
  expected=json.loads((OUT/'preserved_files.json').read_text())
  for name,value in expected.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),value)
 @unittest.skipUnless((ROOT/'reports/phase3/cell_metrics.csv').exists(), 'Generate experiment artifacts first; see README')
 def test_explicit_gate_matches_saved_results(self):
  from phase3_acceptance import check
  for model in ['ridge','random_forest','hist_gradient_boosting']:
   result=check(model)
   self.assertEqual(result['passed_all'],len(result['failures'])==0)
   self.assertTrue(all(f['mae_pp']>5 for f in result['failures']))

