import unittest
import pandas as pd
from forecast import forecast,first_crossing
class ForecastTests(unittest.TestCase):
    def test_linear_crossing(self):
        df=pd.DataFrame(dict(cycle=range(1,61),soh_pct=[100-.5*c for c in range(1,61)]))
        self.assertAlmostEqual(forecast(df[df.cycle<=40])['predicted_rul_cycles'],20)
        self.assertEqual(first_crossing(df,70),60)
        self.assertIsNone(first_crossing(df,60))
    def test_future_independence(self):
        df=pd.DataFrame(dict(cycle=range(1,81),soh_pct=[100-.4*c for c in range(1,81)]))
        before=forecast(df[df.cycle<=40])
        df.loc[df.cycle>40,'soh_pct']=-999
        self.assertEqual(before,forecast(df[df.cycle<=40]))
    def test_non_declining(self):
        df=pd.DataFrame(dict(cycle=range(20),soh_pct=range(80,100)))
        self.assertIsNone(forecast(df))

class PowerForecastTests(unittest.TestCase):
    def test_known_power_law(self):
        from forecast import power_forecast
        df=pd.DataFrame(dict(cycle=range(1,81),soh_pct=[100-20*(c/100)**1.7 for c in range(1,81)]))
        f=power_forecast(df,70)
        expected=100*(30/20)**(1/1.7)-80
        self.assertAlmostEqual(f['predicted_rul_cycles'],expected,places=2)
    def test_power_ignores_future(self):
        from forecast import power_forecast
        df=pd.DataFrame(dict(cycle=range(1,101),soh_pct=[100-20*(c/100)**1.7 for c in range(1,101)]))
        f=power_forecast(df[df.cycle<=60])
        df.loc[df.cycle>60,'soh_pct']=-500
        self.assertEqual(f,power_forecast(df[df.cycle<=60]))
    def test_power_rejects_flat_or_short_history(self):
        from forecast import power_forecast
        df=pd.DataFrame(dict(cycle=range(1,21),soh_pct=[95.]*20))
        self.assertIsNone(power_forecast(df))
        self.assertIsNone(power_forecast(df.head(5)))
