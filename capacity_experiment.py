"""Synthetic capacity learning, scenario evaluation and workbench data export."""

from dataclasses import dataclass, replace
from time import perf_counter

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from battery_sim import Cell, simulate
from soc_estimation import Measurements, Thevenin, coulomb_count, thevenin_ekf
from synthetic_battery import SENSOR_STD


SEED = 1307
WINDOW_S = 180
NOMINAL_C = Cell.nominal_ah * 3600
SOH_BOUNDS = (0.55, 1.0)
FEATURES = ("Start voltage (V)", "Voltage change (V)", "Voltage spread (V)",
            "Mean current (A)", "Current spread (A)", "Net charge (C)",
            "Mean temperature (K)", "Temperature change (K)")
FAMILIES = {
    "train": (0, 1, 2), "validation": (3,), "test": (4, 5),
}


@dataclass(frozen=True)
class Scenario:
    name: str
    family: int
    cell: Cell = Cell()
    plant: str = "thevenin"
    noise: float = 1.0
    bias_a: float = 0.0
    initial_guess: float = 0.65
    seed: int = SEED


def signals(case, duration=720):
    time = np.arange(duration + 1, dtype=float)
    family = case.family
    # Distinct duty schedules by family, with a shared early discharge challenge.
    current = np.select(
        [time < 18 + 2*family, time < 100 + 7*family, time <= WINDOW_S,
         time < 300 + 9*family, time < 385 + 9*family, time < 520 + 7*family,
         time < 585 + 4*family],
        [0., 1.75 + 0.10*family, 1.25 - 0.06*family,
         -0.75 - 0.04*family, 0., 1.45 + 0.08*family, -0.85], default=0.35)
    data = simulate(time, current, case.cell, case.plant)
    streams = np.random.SeedSequence(case.seed).spawn(len(SENSOR_STD))
    for (name, std), stream in zip(SENSOR_STD.items(), streams):
        bias = case.bias_a if name == "current_a" else 0.
        rng = np.random.default_rng(stream)
        data[f"measured_{name}"] = data[f"truth_{name}"] + bias + rng.normal(
            0, std * case.noise, time.size)
    return data


def feature_window(samples):
    elapsed = samples.time_s - samples.time_s[0]
    end = int(np.searchsorted(elapsed, WINDOW_S))
    if end >= elapsed.size or end < 2 or elapsed[end] != WINDOW_S:
        raise ValueError("Features require the sample at 180 s and its causal prefix.")
    voltage = samples.voltage_v[:end+1]
    current = samples.current_a[:end+1]
    temp = samples.temperature_k[:end+1]
    features = [voltage[0], voltage[-1] - voltage[0], voltage.std(),
                current.mean(), current.std(), current[:-1] @ np.diff(elapsed[:end+1]),
                temp.mean(), temp[-1] - temp[0]]
    return end, np.array(features)


def population(cells_per_family):
    def sample(family, index):
        rng = np.random.default_rng(np.random.SeedSequence([SEED, family, index]))
        return Scenario(
            name=f"family-{family}-cell-{index}", family=family,
            cell=Cell(soh=rng.uniform(0.58, 1.0), initial_soc=rng.uniform(0.58, 0.90),
                      ambient_k=rng.uniform(280, 315),
                      resistance_scale=rng.uniform(0.8, 1.7)),
            noise=rng.uniform(0.5, 2.0), bias_a=rng.uniform(-0.065, 0.065),
            initial_guess=rng.uniform(0.42, 0.85), seed=SEED + 100*family + index,
        )

    return {
        split: [sample(family, index) for family in families
                for index in range(cells_per_family)]
        for split, families in FAMILIES.items()
    }


def training_matrix(cases):
    pairs = [(feature_window(Measurements.from_dataset(signals(case, WINDOW_S)))[1],
              case.cell.soh) for case in cases]
    features, labels = zip(*pairs)
    return np.stack(features), np.array(labels)


def predict_soh(model, features):
    return np.clip(model.predict(np.atleast_2d(features)), *SOH_BOUNDS)


def fit_capacity(train, validation):
    train_x, train_y = training_matrix(train)
    val_x, val_y = training_matrix(validation)
    models = {
        "Ridge": make_pipeline(StandardScaler(), Ridge(alpha=3)),
        "Random Forest": RandomForestRegressor(
            n_estimators=64, min_samples_leaf=3, n_jobs=1, random_state=SEED),
        "HistGradientBoosting": HistGradientBoostingRegressor(
            max_iter=70, max_leaf_nodes=9, min_samples_leaf=8, random_state=SEED),
    }
    metrics = {}
    for name, model in models.items():
        model.fit(train_x, train_y)
        metrics[name] = float(np.mean(np.abs(predict_soh(model, val_x) - val_y)))
    winner = min(metrics, key=metrics.get)
    return models, metrics, winner, train_x


def _run(label, method, *args, **kwargs):
    started = perf_counter()
    result = method(*args, **kwargs)
    return label, (result, (perf_counter() - started) * 1000)


def benchmark(case, data, samples, model, initial_guess=None):
    guess = case.initial_guess if initial_guess is None else initial_guess
    index, features = feature_window(samples)
    updated = float(predict_soh(model, features)[0]) * NOMINAL_C
    results = dict([
        _run("Coulomb Counting", coulomb_count, samples, guess, NOMINAL_C),
        _run("Fixed EKF", thevenin_ekf, samples, guess, NOMINAL_C),
        _run("Hybrid A", thevenin_ekf, samples, guess, NOMINAL_C,
             capacity_update=(index, updated)),
    ])
    if case.plant == "thevenin":
        oracle = Thevenin(data["ref_r0_ohm"], data["ref_r1_ohm"][0], data["ref_c1_f"][0])
        results.update([_run("Oracle EKF", thevenin_ekf, samples, guess,
                             data["ref_available_capacity_c"][0], oracle)])
    return results


def score(data, samples, result, elapsed_ms):
    k = int(np.searchsorted(samples.time_s, WINDOW_S))
    error = 100*(result["estimated_soc"] - data["truth_soc"])
    absolute = np.abs(error)
    within = np.convolve((absolute <= 2.).astype(int), np.ones(30, dtype=int), mode="valid")
    converged = np.flatnonzero(within == 30)
    capacity_error = result["capacity_c"][-1] - data["ref_available_capacity_c"][0]
    voltage_error = result["predicted_voltage_v"] - data["truth_voltage_v"]
    return {
        "mae_pp": absolute.mean(), "rmse_pp": np.sqrt(np.mean(error**2)),
        "max_pp": absolute.max(), "bias_pp": error.mean(),
        "capacity_error_ah": capacity_error / 3600, "soh_error_pp": 100*capacity_error/NOMINAL_C,
        "voltage_rmse_mv": 1000*np.sqrt(np.mean(voltage_error**2)),
        "convergence_s": float(samples.time_s[converged[0]]) if converged.size else None,
        "pre_mae_pp": absolute[:k+1].mean(), "post_mae_pp": absolute[k+1:].mean(),
        "execution_ms": elapsed_ms,
    }


def demonstrations():
    normal = Scenario("Fresh · incorrect initial SOC", 4, Cell(soh=.98), initial_guess=.42)
    return [
        normal,
        replace(normal, name="Degraded · cold", family=5,
                cell=Cell(soh=.64, ambient_k=282.15), initial_guess=.64),
        replace(normal, name="Warm · increased resistance", family=5,
                cell=Cell(soh=.84, ambient_k=313.15, resistance_scale=1.65), initial_guess=.74),
        replace(normal, name="Biased current · noisy measurements", family=4,
                cell=Cell(soh=.76), bias_a=.075, noise=2.4, initial_guess=.74),
        replace(normal, name="Diffusion · structural mismatch", family=5, plant="diffusion",
                cell=Cell(soh=.73, ambient_k=291.15, initial_soc=.74), initial_guess=.50),
    ]


def identifiability_example():
    baseline = Scenario("Identifiability", 4, cell=Cell(soh=1.0, initial_soc=.80))
    degraded = replace(baseline, cell=Cell(soh=.68, initial_soc=.807,
                                          resistance_scale=1.08))
    a, b = (signals(case, WINDOW_S) for case in (baseline, degraded))
    difference = 1000*(a["truth_voltage_v"] - b["truth_voltage_v"])
    return {"delta_soh_pp": 32, "first_30_s_rms_mv": float(np.sqrt(np.mean(difference[:31]**2))),
            "window_rms_mv": float(np.sqrt(np.mean(difference**2))),
            "nominal_voltage_noise_mv": 3}


def prediction_surfaces(models, train_x):
    axes = (1, 6)
    xs, ys = [np.linspace(*np.quantile(train_x[:, j], [.05, .95]), 10) for j in axes]
    grid = np.tile(np.median(train_x, axis=0), (len(xs)*len(ys), 1))
    grid[:, axes[0]], grid[:, axes[1]] = np.tile(xs, len(ys)), np.repeat(ys, len(xs))
    return {"x": xs.tolist(), "y": ys.tolist(), "features": [FEATURES[j] for j in axes],
            "models": {name: predict_soh(model, grid).reshape(10, 10).tolist()
                       for name, model in models.items()}}


def evaluate(case, model, *, playback=False):
    data = signals(case)
    samples = Measurements.from_dataset(data)
    trials = {}
    for guess, label in ((case.initial_guess, "Scenario assumption"), (.5, "50% initial SOC"),
                         (.9, "90% initial SOC")) if playback else ((None, "Scenario assumption"),):
        results = benchmark(case, data, samples, model, guess)
        trials[label] = {
            "metrics": {name: score(data, samples, *run) for name, run in results.items()},
        }
        if playback:
            hybrid = results["Hybrid A"][0]
            trials[label].update({
                "initial_soc": guess,
                "soc": {name: run[0]["estimated_soc"].tolist() for name, run in results.items()},
                "diagnostics": {name: hybrid[name].tolist() for name in (
                    "predicted_state", "corrected_state", "predicted_voltage_v", "innovation_v",
                    "kalman_gain", "covariance", "capacity_c")},
            })
    return {
        "name": case.name, "plant": case.plant, "family": case.family,
        "truth_soh": case.cell.soh, "trials": trials,
        **({"time": samples.time_s.tolist(), "current": samples.current_a.tolist(),
            "voltage": samples.voltage_v.tolist(), "temperature": samples.temperature_k.tolist(),
            "truth": data["truth_soc"].tolist()} if playback else {}),
    }


def run_experiment(full=False):
    groups = population(48 if full else 10)
    with threadpool_limits(limits=1):
        models, validation, winner, train_x = fit_capacity(groups["train"], groups["validation"])
        model = models[winner]
        capacity_tests = {}
        comparison = {}
        for plant in ("thevenin", "diffusion"):
            cases = [replace(case, plant=plant) for case in groups["test"]]
            x, y = training_matrix(cases)
            capacity_tests[plant] = {
                name: float(np.mean(np.abs(predict_soh(fitted, x) - y)))
                for name, fitted in models.items()
            }
            comparison[plant] = [evaluate(case, model) for case in cases]
        return {
            "seed": SEED, "mode": "full" if full else "quick", "selected_model": winner,
            "splits": {key: [case.name for case in cases] for key, cases in groups.items()},
            "validation_soh_mae": validation, "test_soh_mae": capacity_tests,
            "holdout": comparison, "identifiability": identifiability_example(),
            "surfaces": prediction_surfaces(models, train_x),
            "scenarios": [evaluate(case, model, playback=True) for case in demonstrations()],
            "window_s": WINDOW_S, "nominal_c": NOMINAL_C,
        }
