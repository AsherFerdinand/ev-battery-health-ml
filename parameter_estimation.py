"""Causal capacity and reference-temperature R0 estimation for Hybrid B."""

from dataclasses import dataclass, replace

import numpy as np

from battery_sim import resistance_temperature_factor
from capacity_experiment import (NOMINAL_C, SOH_BOUNDS, feature_window, model_candidates,
                                 signals)
from soc_estimation import Measurements

WINDOWS = (180, 420)
PARAMETERS = (
    {"key": "capacity_c", "label": "Available capacity", "unit": "C"},
    {"key": "r0_ref_ohm", "label": "R₀ at 298.15 K", "unit": "Ω"},
)
BOUNDS = np.array([[NOMINAL_C * SOH_BOUNDS[0], NOMINAL_C * SOH_BOUNDS[1]],
                   [0.020, 0.080]])
SPAN = np.diff(BOUNDS).ravel()


def adaptive_features(samples, seconds):
    index, base = feature_window(samples, seconds)
    current = samples.current_a[:index+1]
    volts = samples.voltage_v[:index+1]
    temp = samples.temperature_k[:index+1]
    jumps = np.diff(current)
    steps = np.abs(jumps) >= 0.35
    excited = np.count_nonzero(steps) >= 2
    if not excited:
        return index, None
    edge_resistance = -np.diff(volts)[steps] / jumps[steps]
    normalized = edge_resistance / resistance_temperature_factor(temp[1:][steps])
    return index, np.concatenate((base, [np.median(normalized)]))


def rc_variation(case):
    """Independent, seeded RC variation for augmented training or stress tests."""
    rng = np.random.default_rng(np.random.SeedSequence([145, case.seed]))
    cell = replace(case.cell, r1_ohm=case.cell.r1_ohm * rng.uniform(.65, 1.65),
                   c1_f=case.cell.c1_f * rng.uniform(.55, 2.0))
    return replace(case, cell=cell)


def references(case):
    return np.array([case.cell.capacity_c, case.cell.r0_ohm * case.cell.resistance_scale])


def _matrix(cases, windows):
    features = {seconds: [] for seconds in windows}
    for case in cases:
        samples = Measurements.from_dataset(signals(case, max(windows)))
        for seconds in windows:
            _, x = adaptive_features(samples, seconds)
            if x is None:
                raise ValueError(f"Training scenario {case.name} lacks current excitation.")
            features[seconds].append(x)
    return {seconds: np.stack(rows) for seconds, rows in features.items()}


def _bounded(model, features, parameter):
    low, high = BOUNDS[parameter]
    return np.clip(model.predict(np.atleast_2d(features)), low, high)


@dataclass(frozen=True)
class ParameterEstimator:
    window_s: int
    models: tuple
    names: tuple
    validation: dict

    def predict(self, samples):
        index, features = adaptive_features(samples, self.window_s)
        if features is None:
            return index, None
        return index, tuple(float(_bounded(model, features, j)[0])
                            for j, model in enumerate(self.models))

    def details(self):
        return {
            "window_s": self.window_s,
            "parameters": PARAMETERS,
            "models": {parameter["key"]: name for parameter, name in zip(PARAMETERS, self.names)},
            "validation": self.validation,
        }


def fit_parameters(train, validation):
    train = [rc_variation(case) for case in train]
    validation = [rc_variation(case) for case in validation]
    train_x, val_x = _matrix(train, WINDOWS), _matrix(validation, WINDOWS)
    train_y, val_y = map(lambda cases: np.stack([references(case) for case in cases]),
                         (train, validation))
    selected = {}
    validation_mae = {}
    for seconds in WINDOWS:
        winners = []
        errors = {}
        for j, parameter in enumerate(PARAMETERS):
            candidates = model_candidates()
            for name, model in candidates.items():
                model.fit(train_x[seconds], train_y[:, j])
            mae = {name: float(np.mean(np.abs(_bounded(model, val_x[seconds], j) - val_y[:, j])))
                   for name, model in candidates.items()}
            name = min(mae, key=mae.get)
            winners.append((name, candidates[name], mae[name]))
            errors[parameter["key"]] = mae
        selected[seconds] = winners
        validation_mae[seconds] = errors
    window = min(WINDOWS, key=lambda sec: np.mean([x[2] for x in selected[sec]] / SPAN))
    names, models, _ = zip(*selected[window])
    return ParameterEstimator(window, models, names, validation_mae)
