import unittest

import numpy as np
from threadpoolctl import threadpool_limits

from capacity_experiment import demonstrations, evaluate, fit_capacity, population, signals
from parameter_estimation import BOUNDS, WINDOWS, adaptive_features, fit_parameters
from soc_estimation import Measurements


class ParameterLearningTests(unittest.TestCase):
    def test_features_are_causal_and_ignore_truth(self):
        case = population(1)["test"][0]
        for window in WINDOWS:
            short = signals(case, window)
            data = signals(case)
            for name, values in data.items():
                if name.startswith("measured_"):
                    values[window+1:] = 100
                elif name.startswith(("ref_", "truth_")):
                    values[:] = np.nan
            k, expected = adaptive_features(Measurements.from_dataset(short), window)
            index, actual = adaptive_features(Measurements.from_dataset(data), window)
            self.assertEqual(k, index)
            np.testing.assert_array_equal(expected, actual)

    def test_no_excitation_does_not_produce_parameters(self):
        samples = Measurements(np.arange(421), np.zeros(421), np.full(421, 4.), np.full(421, 298.))
        self.assertIsNone(adaptive_features(samples, 420)[1])

    def test_training_selection_reproducible_and_bounded(self):
        groups = population(5)
        families = [{case.family for case in cases} for cases in groups.values()]
        self.assertEqual(sum(map(len, families)), len(set.union(*families)))
        with threadpool_limits(limits=1):
            a = fit_parameters(groups["train"], groups["validation"])
            b = fit_parameters(groups["train"], groups["validation"])
            samples = Measurements.from_dataset(signals(groups["test"][0]))
            _, prediction = a.predict(samples)
            self.assertEqual(a.predict(samples), b.predict(samples))
        self.assertEqual(a.details(), b.details())
        self.assertIn(a.window_s, WINDOWS)
        self.assertTrue(np.all((BOUNDS[:, 0] <= prediction) & (prediction <= BOUNDS[:, 1])))


    def test_paired_integration_preserves_baselines_and_gates_oracle(self):
        groups = population(5)
        with threadpool_limits(limits=1):
            models, _, selected, _ = fit_capacity(groups["train"], groups["validation"])
            adaptive = fit_parameters(groups["train"], groups["validation"])
            for case in (demonstrations()[1], demonstrations()[-1]):
                ordinary = evaluate(case, models[selected], playback=True)["trials"]["Scenario assumption"]
                comparison = evaluate(
                    case, models[selected], playback=True, adaptive=adaptive
                )["trials"]["Scenario assumption"]
                for name, trace in ordinary["soc"].items():
                    np.testing.assert_array_equal(trace, comparison["soc"][name])
                k = adaptive.window_s
                np.testing.assert_array_equal(comparison["soc"]["Hybrid B"][:k+1],
                                              comparison["soc"]["Fixed EKF"][:k+1])
                self.assertEqual("Oracle EKF" in comparison["metrics"], case.plant == "thevenin")
                self.assertTrue(comparison["adaptive"]["update_applied"])
