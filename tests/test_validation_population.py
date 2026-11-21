import unittest

import numpy as np

from parameter_estimation import BOUNDS
from soc_estimation import Measurements
from validation_population import (paired, population, provenance, run_capacity_study,
                                   validation_signals)


class ValidationPopulationTests(unittest.TestCase):
    def test_frozen_split_manifests_and_distinct_duty_structures(self):
        development = provenance("development", 3)
        final = provenance("final", 3)
        self.assertNotEqual(development["root_seed"], final["root_seed"])
        self.assertTrue(set(development["profile_and_case_ids"]).isdisjoint(
            final["profile_and_case_ids"]))
        self.assertTrue(set(development["profiles_end_s_a"].values()).isdisjoint(
            final["profiles_end_s_a"].values()))
        self.assertEqual(development, provenance("development", 3))
        self.assertEqual(population("development", 3)[0], population("development", 4)[0])

    def test_paired_current_noise_and_causal_prefix(self):
        groups = paired("development", 1)
        for first, second in zip(groups["thevenin"], groups["diffusion"]):
            self.assertEqual(first.name, second.name)
            self.assertEqual(first.cell, second.cell)
            self.assertEqual(first.initial_guess, second.initial_guess)
            leading = validation_signals(first, 180)
            full = validation_signals(first, 420)
            mismatch = validation_signals(second, 420)
            for channel in ("current_a", "voltage_v", "temperature_k"):
                key = "measured_" + channel
                np.testing.assert_array_equal(full[key][:181], leading[key])
            np.testing.assert_array_equal(full["measured_current_a"],
                                          mismatch["measured_current_a"])
            self.assertFalse(np.array_equal(full["truth_voltage_v"],
                                            mismatch["truth_voltage_v"]))

    def test_diverse_model_reproducibility_and_future_independence(self):
        from validation_population import fit_revised_capacity

        first = fit_revised_capacity(5)
        second = fit_revised_capacity(5)
        self.assertEqual((first.name, first.window_s, first.validation),
                         (second.name, second.window_s, second.validation))
        case = population("development", 1)[0]
        short = Measurements.from_dataset(validation_signals(case, first.window_s))
        full = Measurements.from_dataset(validation_signals(case))
        self.assertEqual(first.predict_raw(short), second.predict_raw(full))
        self.assertTrue(BOUNDS[0, 0] <= first.predict(full)[1] <= BOUNDS[0, 1])
        weak = Measurements.from_dataset(validation_signals(population("development", 1)[-1]))
        self.assertIsNone(first.predict(weak)[1])

    def test_old_capacity_diagnosis_has_explicit_clipping_counts_and_fixed_prior(self):
        report = run_capacity_study(6)
        self.assertEqual(report["status"], "development evidence only")
        self.assertEqual(set(report["feature_target_distributions"]), {180, 420})
        for cohort in report["old_cohort_scores"].values():
            for metrics in cohort.values():
                self.assertEqual(metrics["in_range"] + metrics["below_bound"] +
                                 metrics["above_bound"], metrics["eligible"])
            self.assertEqual(cohort["prior"]["at_prior"], cohort["prior"]["count"])
