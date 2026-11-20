from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from battery_sim import Cell, MODELS, simulate
from synthetic_battery import dataset, profile


class BatteryModelTests(unittest.TestCase):
    def test_rest_equilibrium_for_all_models(self):
        time = np.array([0, 1, 15, 100])
        cell = Cell(ambient_k=287, initial_soc=0.6)
        for model in MODELS:
            with self.subTest(model=model):
                result = simulate(time, np.zeros_like(time), cell, model)
                np.testing.assert_allclose(result["truth_soc"], 0.6, atol=1e-12)
                np.testing.assert_allclose(result["truth_temperature_k"], 287)
                voltage = result["truth_voltage_v"]
                np.testing.assert_allclose(voltage, voltage[0], atol=1e-12)

    def test_charge_sign_units_ageing_and_irregular_steps(self):
        time = [0, 2, 11, 18]
        current = [1.2, -0.9, 1.1, 9.0]
        consumed_c = np.array([0.0, 2.4, -5.7, 2.0])
        for model in MODELS:
            with self.subTest(model=model):
                for soh in [1.0, 0.7]:
                    cell = Cell(soh=soh)
                    result = simulate(time, current, cell, model)
                    capacity = 7200 * soh
                    np.testing.assert_allclose(result["ref_available_capacity_c"], capacity)
                    np.testing.assert_allclose(result["truth_soh"], soh)
                    np.testing.assert_allclose(
                        result["truth_soc"], 0.8 - consumed_c / capacity, atol=1e-12
                    )

    def test_instantaneous_resistance_sign_and_scaling(self):
        for amps in [-1.2, 1.2]:
            cell = Cell(ambient_k=288.15, resistance_scale=1.5)
            for model in ("rint", "thevenin", "dual"):
                with self.subTest(amps=amps, model=model):
                    rest = simulate([0, 1], [0, 0], cell, model)
                    loaded = simulate([0, 1], [amps, 0], cell, model)
                    resistance = 0.035 * 1.5 * np.exp(0.18)
                    self.assertAlmostEqual(loaded["ref_r0_ohm"][0], resistance)
                    self.assertAlmostEqual(
                        rest["truth_voltage_v"][0] - loaded["truth_voltage_v"][0],
                        amps * resistance,
                    )

    def test_rc_step_and_relaxation_closed_form(self):
        time = np.array([0, 3, 17, 42, 67, 160])
        current = np.array([1.4, 1.4, 1.4, 0, 0, 0])
        for model, branches in (("thevenin", 1), ("dual", 2)):
            with self.subTest(model=model):
                result = simulate(time, current, model=model)
                for branch in range(1, branches + 1):
                    r = result[f"ref_r{branch}_ohm"][0]
                    c = result[f"ref_c{branch}_f"][0]
                    charge = 1.4 * r * (1 - np.exp(-np.minimum(time, 42) / (r * c)))
                    expected = charge * np.exp(-np.maximum(time - 42, 0) / (r * c))
                    np.testing.assert_allclose(
                        result[f"truth_polarisation_{branch}_v"], expected,
                        rtol=1e-12, atol=1e-14,
                    )
        rint = simulate(time, current, model="rint")
        self.assertNotIn("ref_r1_ohm", rint)

    def test_temperature_step_and_rest_cooling(self):
        cell = Cell()
        rint = simulate([0, 20, 220], [1.5, 0, 0], cell, "rint")
        tau = cell.thermal_capacity_j_per_k / cell.cooling_w_per_k
        rise = 1.5**2 * cell.r0_ohm / cell.cooling_w_per_k * (1 - np.exp(-20 / tau))
        expected = cell.ambient_k + np.array([0, rise, rise * np.exp(-200 / tau)])
        np.testing.assert_allclose(rint["truth_temperature_k"], expected, atol=1e-12)

    def test_diffusion_mesh_refinement_and_relaxation(self):
        t, i = profile("pulse")
        surface = {}
        for mesh in (12, 24, 48, 96):
            cell = replace(Cell(), diffusion_cells=mesh)
            result = simulate(t, i, cell, "diffusion")
            surface[mesh] = result["truth_surface_fraction"]
            bulk = result["truth_soc"]
            self.assertLess(surface[mesh][109], bulk[109])
            self.assertLess(abs(surface[mesh][180] - bulk[180]),
                            abs(surface[mesh][110] - bulk[110]))
            self.assertNotIn("ref_r1_ohm", result)
            self.assertNotIn("ref_c1_f", result)
        errors = [np.max(np.abs(surface[n] - surface[96])) for n in (12, 24, 48)]
        self.assertLess(errors[2], errors[1])
        self.assertLess(errors[1], errors[0])
        self.assertLess(errors[1], 0.001)

    def test_reject_invalid_inputs_and_infeasible_profiles(self):
        with self.assertRaises(ValueError):
            Cell(soh=0)
        with self.assertRaises(ValueError):
            Cell(diffusion_cells=3)
        for time, current in [([0, 0], [0, 0]), ([0, 1], [0]), ([0, 1], [np.nan, 0])]:
            with self.subTest(time=time, current=current), self.assertRaises(ValueError):
                simulate(time, current)
        for model in MODELS:
            with self.subTest(model=model), self.assertRaisesRegex(ValueError, "left"):
                simulate([0, 8000], [1.5, 0], model=model)


class SyntheticDatasetTests(unittest.TestCase):
    def test_seed_reproducibility_and_truth_isolation(self):
        baseline = dataset("diffusion", "mixed", Cell(), 41, 1)
        same = dataset("diffusion", "mixed", Cell(), 41, 1)
        changed = dataset("diffusion", "mixed", Cell(), 42, 1)
        clean = dataset("diffusion", "mixed", Cell(), 41, 0)
        for channel in baseline:
            np.testing.assert_array_equal(baseline[channel], same[channel])
            if channel.startswith(("truth_", "ref_")):
                np.testing.assert_array_equal(baseline[channel], changed[channel])
            if channel.startswith("measured_"):
                self.assertFalse(np.array_equal(baseline[channel], changed[channel]))
                truth = channel.replace("measured_", "truth_", 1)
                np.testing.assert_array_equal(clean[channel], clean[truth])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.npz"
            np.savez_compressed(path, **baseline)
            with np.load(path, allow_pickle=False) as loaded:
                metadata = json.loads(loaded["metadata_json"].item())
                self.assertEqual(metadata["provenance"], "synthetic")
                self.assertEqual(metadata["seed"], 41)
                self.assertEqual(metadata["model"], "diffusion")
                np.testing.assert_array_equal(loaded["truth_soc"], baseline["truth_soc"])
