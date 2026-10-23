import unittest
from types import SimpleNamespace
import numpy as np
from pipeline import early_features, FEATURES


class FeatureTests(unittest.TestCase):
    def test_future_samples_cannot_change_features(self):
        data = SimpleNamespace(Time=np.array([0, 20, 40, 60, 80]),
            Voltage_measured=np.array([4.2, 4.0, 3.9, 3.8, 3.7]),
            Current_measured=np.ones(5) * -2, Temperature_measured=np.arange(5.) + 24)
        before = early_features(data, 24)
        data.Voltage_measured[-1] = 999
        data.Temperature_measured[-1] = 999
        self.assertEqual(before, early_features(data, 24))
        self.assertNotIn("capacity_ah", FEATURES)

    def test_bad_time_is_rejected(self):
        data = SimpleNamespace(Time=[0, 50, 40], Voltage_measured=[4, 3, 2],
            Current_measured=[-2]*3, Temperature_measured=[24]*3)
        with self.assertRaises(ValueError):
            early_features(data, 24)


if __name__ == "__main__":
    unittest.main()
