import json
from pathlib import Path
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from build_workbench import create_server
from simulation_api import DEFAULTS, MAX_DURATION_S, current_profile, normalize_config, simulate_configuration


def config_for(model="thevenin", **overrides):
    values = {key: value for key, value in DEFAULTS.items()
              if key not in {"r1_ohm", "c1_f", "r2_ohm", "c2_f"}}
    if model in ("thevenin", "dual"):
        values.update(r1_ohm=DEFAULTS["r1_ohm"], c1_f=DEFAULTS["c1_f"])
    if model == "dual":
        values.update(r2_ohm=DEFAULTS["r2_ohm"], c2_f=DEFAULTS["c2_f"])
    values.update(model=model, **overrides)
    return values


class ProfileTests(unittest.TestCase):
    def test_five_profiles_have_fixed_one_second_samples_and_signs(self):
        expected_sign = {
            "constant_discharge": (1, 1), "current_pulse": (0, 1),
            "pulse_relaxation": (0, 1), "charging": (-1, -1), "drive_style": (-0.35, 1),
        }
        for name, (low, high) in expected_sign.items():
            with self.subTest(profile=name):
                t, current = current_profile(name, 120, 1.0)
                self.assertEqual(len(t), 121)
                self.assertEqual(t[0], 0)
                self.assertEqual(t[-1], 120)
                self.assertAlmostEqual(float(current.min()), low)
                self.assertAlmostEqual(float(current.max()), high)
                np.testing.assert_array_equal(current, current_profile(name, 120, 1.0)[1])

    def test_configuration_ranges_and_model_specific_fields(self):
        self.assertEqual(normalize_config(config_for("rint"))["model"], "rint")
        with self.assertRaisesRegex(ValueError, "Unsupported parameter"):
            normalize_config(config_for("rint", r1_ohm=0.02))
        for bad in (
            {"model": "diffusion"}, {"profile": "external_cycle"},
            {"duration_s": MAX_DURATION_S + 1}, {"duration_s": True},
            {"initial_soc": float("nan")}, {"current_a": 0},
            {"ambient_temperature_c": 51}, {"unknown": 1},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_config(config_for(**bad))


class SimulationTests(unittest.TestCase):
    def test_all_supported_models_call_shared_engine_and_emit_supported_channels(self):
        for model, branches in (("rint", 0), ("thevenin", 1), ("dual", 2)):
            with self.subTest(model=model):
                result = simulate_configuration(config_for(model, duration_s=60))
                channels = result["channels"]
                self.assertEqual(len(channels["time_s"]), 61)
                self.assertEqual(channels["time_s"][-1], 60)
                self.assertEqual(channels["current_a"][0], 1.4)
                self.assertEqual(result["configuration"]["model"], model)
                self.assertEqual(result["units"]["channels"]["time_s"], "s")
                self.assertEqual(result["units"]["configuration"]["nominal_capacity_ah"], "Ah")
                self.assertEqual("polarisation_1_v" in channels, branches >= 1)
                self.assertEqual("polarisation_2_v" in channels, branches == 2)
                self.assertTrue(all(len(values) == 61 for values in channels.values()))
                self.assertGreater(result["energy"]["terminal_energy_out_wh"], 0)
                self.assertGreater(result["energy"]["ohmic_heat_wh"], 0)
                expected_out = np.sum(np.maximum(
                    np.asarray(channels["terminal_voltage_v"][:-1]) * channels["current_a"][:-1], 0
                )) / 3600
                self.assertAlmostEqual(result["energy"]["terminal_energy_out_wh"], expected_out)
                self.assertEqual(result["assumptions"]["current_sign"],
                                 "positive discharges; negative charges")

    def test_charging_sign_energy_and_increasing_soc(self):
        result = simulate_configuration(config_for("rint", profile="charging", duration_s=60))
        self.assertLess(result["channels"]["current_a"][0], 0)
        self.assertGreater(result["channels"]["soc"][-1], result["channels"]["soc"][0])
        self.assertGreater(result["energy"]["terminal_energy_in_wh"], 0)
        self.assertEqual(result["energy"]["terminal_energy_out_wh"], 0)

    def test_duration_cap_and_soc_bounds_are_enforced(self):
        longest = simulate_configuration(config_for("rint", duration_s=MAX_DURATION_S))
        self.assertEqual(len(longest["channels"]["time_s"]), MAX_DURATION_S + 1)
        with self.assertRaisesRegex(ValueError, r"left \[0, 1\]"):
            simulate_configuration(config_for("rint", profile="constant_discharge",
                                               initial_soc=0.05, nominal_capacity_ah=0.5,
                                               current_a=3.0, duration_s=1800))


class LocalEndpointTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(Path("missing-workbench.html"), 0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, body, *, origin=True, content_type="application/json"):
        headers = {"Content-Type": content_type}
        if origin:
            headers["Origin"] = self.base
        req = Request(self.base + "/api/simulate", data=body, headers=headers, method="POST")
        try:
            return urlopen(req, timeout=2)
        except HTTPError as error:
            return error

    def test_local_post_returns_python_simulation_and_origin_guard(self):
        body = json.dumps(config_for("dual", duration_s=30)).encode()
        response = self.request(body)
        self.assertEqual(response.status, 200)
        output = json.loads(response.read())
        self.assertEqual(output["software_version"], "2.2")
        self.assertEqual(len(output["channels"]["time_s"]), 31)
        self.assertIn("polarisation_2_v", output["channels"])
        self.assertEqual(self.request(body, origin=False).status, 403)

    def test_endpoint_rejects_invalid_content_type_schema_and_oversize_body(self):
        valid = json.dumps(config_for("rint", duration_s=30)).encode()
        self.assertEqual(self.request(valid, content_type="text/plain").status, 415)
        self.assertEqual(self.request(b"not json").status, 400)
        self.assertEqual(self.request(b" " * 16_385).status, 413)
