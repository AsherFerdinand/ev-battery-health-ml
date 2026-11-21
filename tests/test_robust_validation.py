from dataclasses import replace
from types import SimpleNamespace
import unittest

import numpy as np

from capacity_experiment import NOMINAL_C, population, signals
from robust_validation import Evidence, Policy, evidence_from_samples, guarded_run
from soc_estimation import Measurements, thevenin_ekf


class GuardTests(unittest.TestCase):
    def test_rejected_update_is_exact_fallback(self):
        case = population(1)["test"][0]
        samples = Measurements.from_dataset(signals(case))
        fixed = thevenin_ekf(samples, .6, NOMINAL_C)
        e = Evidence(420, 8000, NOMINAL_C, .045, 8., 4, 2.)
        result, decision = guarded_run(samples, .6, fixed, e, Policy(.75, .5))
        self.assertFalse(decision["accepted"])
        self.assertIs(result, fixed)
        self.assertEqual(decision["applied_capacity_c"], NOMINAL_C)
        accepted, decision = guarded_run(samples, .6, fixed, e, Policy(3., .5))
        self.assertTrue(decision["accepted"])
        self.assertAlmostEqual(decision["applied_r0_ref_ohm"], .040)
        np.testing.assert_array_equal(accepted["estimated_soc"][:421], fixed["estimated_soc"][:421])
        self.assertGreaterEqual(np.linalg.eigvalsh(accepted["covariance"]).min(), 0)
        self.assertFalse(Policy(3., .5).decide(replace(e, raw_r0_ref_ohm=.1))["accepted"])

    def test_evidence_is_prefix_only(self):
        class Constant:
            def __init__(self, result):
                self.result = result
            def predict(self, features):
                return [self.result]

        original = SimpleNamespace(window_s=420, models=(Constant(8000), Constant(.04)))
        case = population(1)["test"][0]
        data = signals(case)
        samples = Measurements.from_dataset(data)
        fixed = thevenin_ekf(samples, .6, NOMINAL_C)
        result = evidence_from_samples(samples, fixed, original, np.zeros(9), np.ones(9))
        for name in ("current_a", "temperature_k", "voltage_v"):
            data[f"measured_{name}"][421:] += 12
        future = Measurements.from_dataset(data)
        changed = evidence_from_samples(future, thevenin_ekf(future, .6, NOMINAL_C),
                                        original, np.zeros(9), np.ones(9))
        self.assertEqual(result, changed)
        self.assertEqual(result.clipped_capacity_c, NOMINAL_C)
