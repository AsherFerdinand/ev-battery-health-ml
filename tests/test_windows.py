import unittest
from types import SimpleNamespace
import numpy as np
import pandas as pd
from window_experiment import features,memberships
from pipeline import ROOT
class WindowTests(unittest.TestCase):
 def data(self):
  return SimpleNamespace(Time=np.arange(0,2001,10),Voltage_measured=np.linspace(4.2,2.7,201),Current_measured=np.full(201,-2.),Temperature_measured=np.linspace(24,35,201))
 def test_cutoff_independence(self):
  for cutoff in (60,300,900,1800):
   d=self.data();before=features(d,24,cutoff)
   d.Voltage_measured[d.Time>cutoff]=999;d.Temperature_measured[d.Time>cutoff]=999
   self.assertEqual(before,features(d,24,cutoff))
 def test_short_cycle_not_silently_truncated(self):
  d=self.data();d.Time=d.Time/10
  with self.assertRaises(ValueError):features(d,24,300)
 @unittest.skipUnless((ROOT/'data/processed/cycles.csv').exists(), 'Generate experiment artifacts first; see README')
 def test_splits_are_disjoint_and_chronological(self):
  base=pd.read_csv(ROOT/'data/processed/cycles.csv')
  for split,(tr,te) in memberships(base).items():
   self.assertFalse(set(tr)&set(te))
   if split.startswith('unseen'):self.assertFalse(set(base.loc[tr,'cell'])&set(base.loc[te,'cell']))
   else:
    for cell in base.cell.unique():self.assertLess(base.loc[tr].query('cell==@cell').cycle.max(),base.loc[te].query('cell==@cell').cycle.min())
 @unittest.skipUnless((ROOT/'reports/window_predictions.csv').exists(), 'Generate experiment artifacts first; see README')
 def test_saved_predictions_respect_membership_and_common_cohort(self):
  base=pd.read_csv(ROOT/'data/processed/cycles.csv');p=pd.read_csv(ROOT/'reports/window_predictions.csv')
  for split,(_,te) in memberships(base).items():
   allowed=set(zip(base.loc[te,'cell'],base.loc[te,'cycle']))
   group=p[p.split==split]
   self.assertTrue(set(zip(group.cell,group.cycle))<=allowed)
   sets=[set(zip(g.cell,g.cycle)) for _,g in group.query("cohort=='common' and model=='ridge'").groupby('window')]
   self.assertTrue(all(s==sets[0] for s in sets))
