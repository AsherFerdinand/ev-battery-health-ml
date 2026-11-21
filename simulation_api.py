"""Validated user-configurable simulations using the shared battery physics engine."""

from __future__ import annotations

import math

import numpy as np

from battery_sim import Cell, simulate

SCHEMA_VERSION = 1
SOFTWARE_VERSION = "2.2"
MAX_DURATION_S = 1800
PROFILES = (
    "constant_discharge", "current_pulse", "pulse_relaxation", "charging", "drive_style",
)
MODELS = ("rint", "thevenin", "dual")
BASE_FIELDS = {
    "model", "profile", "duration_s", "current_a", "initial_soc",
    "nominal_capacity_ah", "ambient_temperature_c", "r0_ohm",
}
BRANCH_FIELDS = {
    "thevenin": {"r1_ohm", "c1_f"},
    "dual": {"r1_ohm", "c1_f", "r2_ohm", "c2_f"},
    "rint": set(),
}
DEFAULTS = {
    "model": "thevenin", "profile": "pulse_relaxation", "duration_s": 600,
    "current_a": 1.4, "initial_soc": 0.8, "nominal_capacity_ah": 2.0,
    "ambient_temperature_c": 25.0, "r0_ohm": 0.035,
    "r1_ohm": 0.018, "c1_f": 650.0, "r2_ohm": 0.012, "c2_f": 5000.0,
}


def _number(config: dict, key: str, low: float, high: float) -> float:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{key} must be a number from {low:g} to {high:g}.")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{key} must be a finite value from {low:g} to {high:g}.")
    return value


def normalize_config(values: dict) -> dict:
    """Validate a strict public configuration and fill documented defaults."""
    if not isinstance(values, dict):
        raise ValueError("Simulation configuration must be a JSON object.")
    model = values.get("model", DEFAULTS["model"])
    profile = values.get("profile", DEFAULTS["profile"])
    if model not in MODELS:
        raise ValueError("Choose Rint, Thevenin or Dual Polarisation.")
    if profile not in PROFILES:
        raise ValueError("Choose one of the supported built-in current profiles.")
    allowed = BASE_FIELDS | BRANCH_FIELDS[model]
    unknown = set(values) - allowed
    if unknown:
        raise ValueError("Unsupported parameter(s) for this model: " + ", ".join(sorted(unknown)))
    duration = values.get("duration_s", DEFAULTS["duration_s"])
    if isinstance(duration, bool) or not isinstance(duration, int) or not 30 <= duration <= MAX_DURATION_S:
        raise ValueError(f"duration_s must be an integer from 30 to {MAX_DURATION_S}.")
    def number(name, low, high):
        return _number({name: values.get(name, DEFAULTS[name])}, name, low, high)
    result = {
        "model": model, "profile": profile, "duration_s": duration,
        "current_a": number("current_a", 0.05, 3.0),
        "initial_soc": number("initial_soc", 0.05, 0.95),
        "nominal_capacity_ah": number("nominal_capacity_ah", 0.5, 10.0),
        "ambient_temperature_c": number("ambient_temperature_c", -10.0, 50.0),
        "r0_ohm": number("r0_ohm", 0.005, 0.15),
    }
    for key, bounds in (("r1_ohm", (0.001, 0.1)), ("c1_f", (25.0, 20000.0)),
                        ("r2_ohm", (0.001, 0.1)), ("c2_f", (100.0, 100000.0))):
        if key in BRANCH_FIELDS[model]:
            result[key] = number(key, *bounds)
    return result


def current_profile(name: str, duration_s: int, amplitude_a: float) -> tuple[np.ndarray, np.ndarray]:
    """Build reproducible, locally defined 1 Hz profiles; positive current discharges."""
    if name not in PROFILES:
        raise ValueError("Unknown current profile.")
    time_s = np.arange(duration_s + 1, dtype=np.float64)
    phase = time_s[:-1] % 120
    current = np.zeros(time_s.size, dtype=np.float64)
    if name == "constant_discharge":
        current[:-1] = amplitude_a
    elif name == "charging":
        current[:-1] = -amplitude_a
    elif name == "current_pulse":
        current[:-1][(time_s[:-1] >= duration_s * 0.2) & (time_s[:-1] < duration_s * 0.5)] = amplitude_a
    elif name == "pulse_relaxation":
        current[:-1][phase < 30] = amplitude_a
    else:
        current[:-1][phase < 20] = amplitude_a * 0.25
        current[:-1][(phase >= 20) & (phase < 45)] = amplitude_a * 0.8
        current[:-1][(phase >= 55) & (phase < 70)] = -amplitude_a * 0.35
        current[:-1][(phase >= 70) & (phase < 90)] = amplitude_a
    current[-1] = current[-2]
    return time_s, current


def simulate_configuration(values: dict) -> dict:
    """Run the shared NumPy simulator and return JSON-ready exact 1 Hz outputs."""
    config = normalize_config(values)
    time_s, current_a = current_profile(config["profile"], config["duration_s"], config["current_a"])
    cell_values = {
        "nominal_ah": config["nominal_capacity_ah"], "soh": 1.0,
        "initial_soc": config["initial_soc"],
        "ambient_k": config["ambient_temperature_c"] + 273.15,
        "r0_ohm": config["r0_ohm"],
    }
    for key in BRANCH_FIELDS[config["model"]]:
        cell_values[key] = config[key]
    cell = Cell(**cell_values)
    result = simulate(time_s, current_a, cell, config["model"])
    voltage = result["truth_voltage_v"]
    power_w = voltage * current_a
    dt_h = np.diff(time_s) / 3600.0
    # The profile is zero-order-held between 1 s samples, matching battery_sim.
    energy_out_wh = float(np.sum(np.maximum(power_w[:-1], 0) * dt_h))
    energy_in_wh = float(np.sum(np.maximum(-power_w[:-1], 0) * dt_h))
    ohmic_heat_wh = float(np.sum(
        current_a[:-1] ** 2 * result["ref_r0_ohm"][:-1] * dt_h
    ))
    channels = {
        "time_s": time_s,
        "current_a": current_a,
        "terminal_voltage_v": voltage,
        "soc": result["truth_soc"],
        "temperature_k": result["truth_temperature_k"],
        "r0_ohm": result["ref_r0_ohm"],
    }
    if config["model"] in ("thevenin", "dual"):
        channels["polarisation_1_v"] = result["truth_polarisation_1_v"]
    if config["model"] == "dual":
        channels["polarisation_2_v"] = result["truth_polarisation_2_v"]
    config_units = {
        "model": "name", "profile": "name",
        "duration_s": "s", "current_a": "A", "initial_soc": "fraction",
        "nominal_capacity_ah": "Ah", "ambient_temperature_c": "°C", "r0_ohm": "Ω",
        "r1_ohm": "Ω", "c1_f": "F", "r2_ohm": "Ω", "c2_f": "F",
    }
    channel_units = {
        "time_s": "s", "current_a": "A", "terminal_voltage_v": "V", "soc": "fraction",
        "temperature_k": "K", "r0_ohm": "Ω", "polarisation_1_v": "V", "polarisation_2_v": "V",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "software_version": SOFTWARE_VERSION,
        "configuration": config,
        "units": {
            "configuration": {key: config_units[key] for key in config},
            "channels": {key: channel_units[key] for key in channels},
            "energy": {"terminal_energy_out_wh": "Wh", "terminal_energy_in_wh": "Wh",
                       "ohmic_heat_wh": "Wh"},
        },
        "assumptions": {
            "provenance": "user-configured synthetic simulation",
            "current_sign": "positive discharges; negative charges",
            "time_step_s": 1,
            "temperature": "ECM heat and cooling state, reported in kelvin",
            "model_scope": "lumped ECM voltage response; not an electrochemical chemistry model",
            "drive_style": "deterministic illustrative profile, not recorded vehicle data",
            "energy_integration": "left rectangle for the 1 s zero-order-held current profile",
            "state_of_health": "fixed at 1.0 for this run; no ageing update",
            "measurement_noise": "none; returned channels are modelled values",
            "ocv": "shared lumped SOC curve; not fitted to a specific cell chemistry",
        },
        "energy": {
            "terminal_energy_out_wh": energy_out_wh,
            "terminal_energy_in_wh": energy_in_wh,
            "ohmic_heat_wh": ohmic_heat_wh,
        },
        "channels": {name: array.tolist() for name, array in channels.items()},
    }
