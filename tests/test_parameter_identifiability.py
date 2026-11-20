import unittest

import numpy as np

from capacity_experiment import Scenario, signals
from parameter_identifiability import (CHECK_CASE, coordinates, local_summary,
                                       recover, run_study, voltage_jacobian)


class ParameterIdentifiabilityTests(unittest.TestCase):
    def setUp(self):
        self.theta = coordinates(CHECK_CASE)
        self.data = signals(Scenario("verification", 4, CHECK_CASE), 420)
        self.current = self.data["truth_current_a"]
        self.temperature = self.data["truth_temperature_k"]

    def test_projection_matches_thevenin_plant_and_jacobian(self):
        voltage, jacobian = voltage_jacobian(self.theta, self.current, self.temperature)
        np.testing.assert_allclose(voltage, self.data["truth_voltage_v"], atol=1e-13)
        for delta in np.eye(5) * 1e-5:
            plus = voltage_jacobian(self.theta + delta, self.current, self.temperature)[0]
            minus = voltage_jacobian(self.theta - delta, self.current, self.temperature)[0]
            np.testing.assert_allclose((plus-minus)/2e-5,
                                       jacobian[:, np.argmax(delta)], atol=2e-9, rtol=2e-8)

    def test_rest_rank_and_loaded_local_recovery(self):
        rest = local_summary(self.theta, np.zeros_like(self.current), self.temperature)
        self.assertEqual(rest["rank"], 1)
        self.assertIsNone(rest["normalized_condition"])
        self.assertEqual(local_summary(self.theta, self.current, self.temperature)["rank"], 5)
        recovered = recover(self.current, self.temperature, self.data["truth_voltage_v"])
        np.testing.assert_allclose(recovered, self.theta, atol=1e-7)

    def test_seeded_study_compares_window_excitation_temperature_and_noise(self):
        study = run_study(repeats=4)
        self.assertEqual(study, run_study(repeats=4))
        nominal = study["loaded"]["reference"]
        stressed = study["loaded"]["noisy and biased"]
        self.assertLess(nominal[420]["normalized_condition"],
                        nominal[180]["normalized_condition"])
        self.assertLess(study["quarter_load"]["rms_response_mv"][3],
                        nominal[180]["rms_response_mv"][3] / 3)
        self.assertGreater(study["loaded"]["cold"][180]["rms_response_mv"][1],
                           study["loaded"]["warm"][180]["rms_response_mv"][1])
        for window in nominal:
            self.assertGreater(stressed[window]["recovery_median_error"][3],
                               nominal[window]["recovery_median_error"][3])
