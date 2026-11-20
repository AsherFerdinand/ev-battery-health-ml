import unittest

import numpy as np

from battery_sim import Cell, simulate
from soc_estimation import (Measurements, Thevenin, coulomb_count, thevenin_ekf,
                            transition, voltage_observation)


def matched_measurements():
    t = np.arange(201.)
    amps = np.where(t < 70, 1.5, np.where(t < 155, -0.8, 0.))
    cell = Cell(soh=0.8)
    truth = simulate(t, amps, cell)
    return cell, truth, Measurements(t, amps, truth["truth_voltage_v"],
                                     truth["truth_temperature_k"])


class SOCTests(unittest.TestCase):
    def test_charge_counting_with_irregular_intervals_and_last_current(self):
        samples = Measurements([0, 2, 5, 9], [1, -2, 0.5, 999], [4]*4, [298]*4)
        result = coulomb_count(samples, 0.7, 100)
        np.testing.assert_allclose(result["estimated_soc"], [0.7, 0.68, 0.74, 0.72])

    def test_analytical_jacobians(self):
        state = np.array([0.51, 0.02])
        basis = np.eye(2) * 1e-6
        for function in (lambda x: transition(x, 4, 1.7, 6300, 0.03, 800),
                         lambda x: voltage_observation(x, 1.7, 0.05)):
            _, analytical = function(state)
            numeric = np.stack([(function(state + d)[0] - function(state - d)[0]) / 2e-6
                                for d in basis], axis=-1)
            np.testing.assert_allclose(analytical, numeric, atol=1e-9)

    def test_matched_filter_and_covariance(self):
        cell, truth, samples = matched_measurements()
        params = Thevenin(truth["ref_r0_ohm"], cell.r1_ohm, cell.c1_f)
        exact = thevenin_ekf(samples, cell.initial_soc, cell.capacity_c, params)
        np.testing.assert_allclose(exact["estimated_soc"], truth["truth_soc"], atol=1e-13)
        result = thevenin_ekf(samples, 0.4, cell.capacity_c, params)
        error = np.abs(result["estimated_soc"] - truth["truth_soc"])
        self.assertLess(np.max(error[30:]), 0.015)
        covariance = result["covariance"]
        np.testing.assert_array_equal(covariance, covariance.transpose(0, 2, 1))
        self.assertGreaterEqual(np.linalg.eigvalsh(covariance).min(), 0)
        self.assertTrue(np.all((result["estimated_soc"] >= 0) & (result["estimated_soc"] <= 1)))

    def test_capacity_update_is_forward_only(self):
        cell, _, samples = matched_measurements()
        base = thevenin_ekf(samples, 0.65, 7200)
        hybrid = thevenin_ekf(samples, 0.65, 7200, capacity_update=(50, cell.capacity_c))
        np.testing.assert_array_equal(base["estimated_soc"][:51], hybrid["estimated_soc"][:51])
        self.assertNotEqual(base["predicted_state"][51, 0], hybrid["predicted_state"][51, 0])
        np.testing.assert_array_equal(hybrid["capacity_c"][:50], 7200)
        np.testing.assert_array_equal(hybrid["capacity_c"][50:], cell.capacity_c)
