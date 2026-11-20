from dataclasses import replace
import unittest

import numpy as np
from threadpoolctl import threadpool_limits

from capacity_experiment import (NOMINAL_C, WINDOW_S, benchmark, demonstrations,
                                 feature_window, fit_capacity, population, signals)
from soc_estimation import Measurements


class CapacityTests(unittest.TestCase):
    def test_splits_keep_both_identity_and_family_disjoint(self):
        groups = population(3)
        ids, families = set(), set()
        for cases in groups.values():
            next_ids = {case.name for case in cases}
            next_families = {case.family for case in cases}
            self.assertTrue(ids.isdisjoint(next_ids))
            self.assertTrue(families.isdisjoint(next_families))
            ids.update(next_ids)
            families.update(next_families)
        self.assertEqual(groups["test"][0], population(4)["test"][0])

    def test_features_ignore_future_and_truth(self):
        for case in (demonstrations()[0], demonstrations()[-1]):
            with self.subTest(plant=case.plant):
                complete = signals(case)
                short = signals(case, WINDOW_S)
                _, expected = feature_window(Measurements.from_dataset(short))
                for name, channel in complete.items():
                    if name.startswith("measured_"):
                        np.testing.assert_array_equal(channel[:WINDOW_S+1], short[name])
                        channel[WINDOW_S+1:] += 25
                    if name.startswith(("truth_", "ref_")):
                        channel[:] = np.nan
                k, actual = feature_window(Measurements.from_dataset(complete))
                self.assertEqual(k, WINDOW_S)
                np.testing.assert_array_equal(actual, expected)

    def test_model_selection_reproducibility_and_hybrid_integration(self):
        groups = population(5)
        case = demonstrations()[-1]
        data = signals(case)
        measured = Measurements.from_dataset(data)
        with threadpool_limits(limits=1):
            models, validation, winner, _ = fit_capacity(groups["train"], groups["validation"])
            _, repeat, _, _ = fit_capacity(groups["train"], groups["validation"])
            self.assertEqual(validation, repeat)
            self.assertEqual(winner, min(validation, key=validation.get))
            with_truth = benchmark(case, data, measured, models[winner])
            no_truth = benchmark(case, {}, measured, models[winner])
            matched = replace(case, plant="thevenin")
            matched_data = signals(matched)
            eligible = benchmark(matched, matched_data, Measurements.from_dataset(matched_data),
                                 models[winner])
        self.assertNotIn("Oracle EKF", with_truth)
        self.assertIn("Oracle EKF", eligible)
        for name in with_truth:
            np.testing.assert_array_equal(with_truth[name][0]["estimated_soc"],
                                          no_truth[name][0]["estimated_soc"])
        fixed = with_truth["Fixed EKF"][0]
        hybrid = with_truth["Hybrid A"][0]
        k = WINDOW_S
        np.testing.assert_array_equal(fixed["estimated_soc"][:k+1], hybrid["estimated_soc"][:k+1])
        self.assertNotEqual(fixed["estimated_soc"][k+1], hybrid["estimated_soc"][k+1])
        np.testing.assert_array_equal(hybrid["capacity_c"][:k], NOMINAL_C)
        self.assertGreaterEqual(hybrid["capacity_c"][k], .55*NOMINAL_C)
        self.assertLessEqual(hybrid["capacity_c"][k], NOMINAL_C)
