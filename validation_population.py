"""Independent v2 validation cohorts and capacity diagnosis on v1.5 development evidence."""

from dataclasses import dataclass, replace
import json

import numpy as np
from threadpoolctl import threadpool_limits

from battery_sim import Cell, simulate
from capacity_experiment import (FEATURES, NOMINAL_C, Scenario, model_candidates,
                                 population as legacy_population, signals)
from parameter_estimation import BOUNDS, WINDOWS, adaptive_features, fit_parameters, rc_variation
from soc_estimation import Measurements
from synthetic_battery import SENSOR_STD


ROOT_SEEDS = {"diverse-train": 8021, "development": 8429, "final": 9629}
PLANTS = ("thevenin", "diffusion")
# Each tuple is (exclusive end time in seconds, held current in A).
PROFILES = {
    "development": {
        "pulse-bursts": ((35, 0), (62, 1.8), (82, 0), (124, 1.05), (168, -.55),
                         (202, 0), (235, 1.6), (315, .48), (425, -.72), (720, .65)),
        "staircase-load": ((20, 0), (67, .45), (123, .94), (164, 1.42), (225, 1.86),
                           (301, -.49), (379, -.96), (459, .15), (561, 1.10), (720, .35)),
        "short-reversals": ((18, 0), (45, 1.4), (72, -.8), (115, 1.55), (145, -.60),
                            (203, 1.1), (244, -.8), (291, 1.3), (388, .25), (720, -.05)),
        "weak-observation": ((90, .12), (170, .05), (250, .22), (330, 0), (480, .17),
                             (535, .9), (610, -.45), (720, .3)),
    },
    "final": {
        "charge-first": ((31, 0), (132, -1.17), (155, 0), (239, .74), (272, 0),
                         (348, 1.63), (435, -.57), (489, .93), (572, .24), (720, -.23)),
        "long-load-release": ((9, 0), (151, 1.5), (268, .68), (337, 0), (398, -1.12),
                              (483, 0), (612, 1.04), (720, .12)),
        "delayed-transients": ((220, .17), (272, 0), (312, .25), (410, .08), (435, 0),
                               (462, 1.75), (509, -.91), (581, .51), (720, -.19)),
        "regenerative-bursts": ((36, -.55), (74, .96), (92, -.97), (109, .82),
                                (146, -1.17), (162, .65), (206, -.60), (242, 1.28),
                                (293, -.79), (318, 0), (355, 1.32), (720, .29)),
    },
}
RANGES = {
    "soh": (.57, 1.0), "initial_soc": (.44, .86), "ambient_k": (274., 320.),
    "resistance_scale": (.72, 1.85), "r1_scale": (.55, 1.8),
    "c1_scale": (.53, 2.11), "current_bias_a": (-.12, .12),
    "current_noise_multiplier": (.45, 2.4), "voltage_noise_multiplier": (.55, 3.2),
    "temperature_noise_multiplier": (.5, 3.),
    "initial_soc_error_pp": (-23., 23.),
}
DIAGNOSTIC_FEATURES = (*FEATURES, "Median edge resistance (Ω)")


@dataclass(frozen=True)
class ValidationCase(Scenario):
    segments: tuple = ()
    profile: str = ""
    voltage_noise: float = 1.
    temperature_noise: float = 1.


def _case(split, family, index, profile, segments):
    seed = np.random.SeedSequence([ROOT_SEEDS[split], family, index])
    rng = np.random.default_rng(seed)
    values = {key: rng.uniform(*interval) for key, interval in RANGES.items()}
    cell = Cell(soh=values["soh"], initial_soc=values["initial_soc"],
                ambient_k=values["ambient_k"], resistance_scale=values["resistance_scale"],
                r1_ohm=Cell.r1_ohm * values["r1_scale"],
                c1_f=Cell.c1_f * values["c1_scale"])
    return ValidationCase(
        name=f"{split}/{profile}/{index:03d}", family=family, cell=cell,
        seed=int(seed.generate_state(1)[0]), noise=values["current_noise_multiplier"],
        bias_a=values["current_bias_a"],
        initial_guess=float(np.clip(cell.initial_soc + values["initial_soc_error_pp"]/100,
                                    .15, .95)), segments=segments, profile=profile,
        voltage_noise=values["voltage_noise_multiplier"],
        temperature_noise=values["temperature_noise_multiplier"],
    )


def population(split, cases_per_family):
    """Materialize an independent split. Family IDs are separated across splits."""
    if cases_per_family < 1:
        raise ValueError("At least one case per family is required.")
    offset = {"development": 100, "final": 200}[split]
    return [_case(split, family, index, profile, segments)
            for family, (profile, segments) in enumerate(PROFILES[split].items(), offset)
            for index in range(cases_per_family)]


def paired(split, cases_per_family):
    cases = population(split, cases_per_family)
    return {plant: [replace(case, plant=plant) for case in cases] for plant in PLANTS}


def provenance(split, cases_per_family):
    return {
        "root_seed": ROOT_SEEDS[split], "cases_per_family": cases_per_family,
        "profiles_end_s_a": PROFILES[split], "ranges_uniform": RANGES,
        "profile_and_case_ids": [case.name for case in population(split, cases_per_family)],
        "plant_pairing": PLANTS, "duration_s": 720, "sample_period_s": 1,
        "streams": "PCG64 per identity and per sensor, including paired Thevenin/diffusion",
        "terminal_current": "Final segment current is held through the last sample.",
    }


def validation_signals(case, duration=720):
    time = np.arange(duration + 1, dtype=float)
    ends, levels = np.asarray(case.segments).T
    current = levels[np.minimum(np.searchsorted(ends, time, side="right"), levels.size - 1)]
    data = simulate(time, current, case.cell, case.plant)
    streams = np.random.SeedSequence(case.seed).spawn(len(SENSOR_STD))
    scales = (case.noise, case.voltage_noise, case.temperature_noise)
    for (name, std), stream, scale in zip(SENSOR_STD.items(), streams, scales):
        bias = case.bias_a if name == "current_a" else 0.
        rng = np.random.default_rng(stream)
        data[f"measured_{name}"] = data[f"truth_{name}"] + bias + rng.normal(
            0, std * scale, time.size)
    return data


def diverse_training(cases_per_family):
    """Train on new load shapes. Neither development nor final families are reused."""
    for family in range(6):
        rng = np.random.default_rng(np.random.SeedSequence([ROOT_SEEDS["diverse-train"], family]))
        for index in range(cases_per_family):
            ends = (15, *np.cumsum(rng.integers(16, 47, size=15)) + 15, 720)
            levels = (0., *rng.uniform(-1.15, 1.9, len(ends)-2), .10)
            # Supply two physically informative transitions before 180 s.
            levels = (*levels[:1], rng.uniform(.7, 1.8), rng.uniform(-.8, -.2), *levels[3:])
            segments = tuple(zip(ends, levels))
            yield _case("diverse-train", family + 300, index, f"random-segments-{family}",
                        segments)


def _rows(cases, windows):
    observations = {}
    for case in cases:
        generator = validation_signals if isinstance(case, ValidationCase) else signals
        observations[case.name] = (
            Measurements.from_dataset(generator(case, max(windows))), case.cell.capacity_c)
    return observations


def _matrix(observations, window):
    rows, labels, names = [], [], []
    for name, (samples, target) in observations.items():
        _, feature = adaptive_features(samples, window)
        if feature is not None:
            rows.append(feature)
            labels.append(target)
            names.append(name)
    return np.asarray(rows), np.asarray(labels), names


@dataclass(frozen=True)
class CapacityCandidate:
    window_s: int
    model: object
    name: str
    validation: dict

    def predict_raw(self, samples):
        index, feature = adaptive_features(samples, self.window_s)
        return index, None if feature is None else float(self.model.predict(feature[None])[0])

    def predict(self, samples):
        index, capacity = self.predict_raw(samples)
        return index, None if capacity is None else float(np.clip(capacity, *BOUNDS[0]))


def fit_revised_capacity(cases_per_family=48):
    legacy = legacy_population(cases_per_family)
    train = _rows([*map(rc_variation, legacy["train"]), *diverse_training(cases_per_family)],
                  WINDOWS)
    development = [*map(rc_variation, legacy["validation"]),
                   *population("development", cases_per_family)]
    valid = _rows(development, WINDOWS)
    scores, fitted = {}, {}
    with threadpool_limits(limits=1):
        for window in WINDOWS:
            x, y, _ = _matrix(train, window)
            val_x, val_y, eligible = _matrix(valid, window)
            skipped = valid.keys() - set(eligible)
            default_error = sum(abs(NOMINAL_C - valid[case][1]) for case in skipped)
            scores[window] = {}
            for name, model in model_candidates().items():
                model.fit(x, y)
                raw = model.predict(val_x)
                error = np.abs(np.clip(raw, *BOUNDS[0]) - val_y)
                scores[window][name] = {
                    "mae_c": float(error.mean()), "eligible": len(val_y), "total": len(valid),
                    "fallback_mae_c": float((error.sum() + default_error) / len(valid)),
                }
                fitted[window, name] = model
    # Compare substantive policies on all cases, charging skipped updates the prior error.
    window, name = min(fitted, key=lambda key: scores[key[0]][key[1]]["fallback_mae_c"])
    return CapacityCandidate(window, fitted[window, name], name, scores)


def _fit_metrics(raw, labels, total):
    bounded = np.clip(raw, *BOUNDS[0])
    error = (bounded-labels)/3600
    return {
        "count": int(total),
        "eligible": int(len(raw)),
        "below_bound": int(np.count_nonzero(raw < BOUNDS[0, 0])),
        "above_bound": int(np.count_nonzero(raw > BOUNDS[0, 1])),
        "in_range": int(np.count_nonzero((raw >= BOUNDS[0, 0]) & (raw <= BOUNDS[0, 1]))),
        "at_prior": int(np.count_nonzero(bounded == NOMINAL_C)),
        "raw_range_ah": (np.quantile(raw / 3600, [0, .5, 1])).tolist(),
        "mae_ah": float(np.mean(np.abs(error))),
        "signed_error_ah": float(np.mean(error)),
    }


def _describe(x, target, reference):
    target_in_ah = target / 3600
    feature_stats = {}
    for i, name in enumerate(DIAGNOSTIC_FEATURES):
        column, baseline = x[:, i], reference[:, i]
        feature_stats[name] = {
            "median": float(np.median(column)),
            "range_5_95": np.quantile(column, [.05, .95]).tolist(),
            "out_of_train_range_fraction": float(
                np.mean((column < baseline.min()) | (column > baseline.max()))),
            "capacity_correlation": float(np.corrcoef(column, target_in_ah)[0, 1]),
        }
    return {
        "target_range_ah": np.quantile(target_in_ah, [0, .5, 1]).tolist(),
        "features": feature_stats,
    }


def _observed_perturbations(model, window, observations):
    """One-at-a-time sensor offsets. Compare unbounded and clipped predictions."""
    baseline, _, selected = _matrix(observations, window)
    baseline_raw = model.predict(baseline)
    results = {}
    for channel, delta in (("current_a", .06), ("voltage_v", .010), ("temperature_k", 2.)):
        shifted = []
        for name in selected:
            samples, _ = observations[name]
            changed = replace(samples, **{channel: getattr(samples, channel) + delta})
            _, row = adaptive_features(changed, window)
            shifted.append(row)
        raw = model.predict(np.stack(shifted))
        bounded = np.clip(raw, *BOUNDS[0])-np.clip(baseline_raw, *BOUNDS[0])
        results[channel] = {
            "offset": delta,
            "median_abs_raw_change_ah": float(np.median(np.abs(raw-baseline_raw))/3600),
            "median_abs_bounded_change_ah": float(np.median(np.abs(bounded))/3600),
        }
    return results


def run_capacity_study(cases_per_family=48):
    """Revisit old v1.5 holdouts as development diagnostics, never a final test."""
    legacy = legacy_population(cases_per_family)
    old_train = _rows(map(rc_variation, legacy["train"]), WINDOWS)
    old_validation = _rows(map(rc_variation, legacy["validation"]), WINDOWS)
    old_tests = {
        "thevenin": legacy["test"],
        "diffusion": [replace(case, plant="diffusion") for case in legacy["test"]],
        "thevenin_rc_stress": [rc_variation(case) for case in legacy["test"]],
    }
    observations = {name: _rows(cases, WINDOWS) for name, cases in old_tests.items()}
    revised = fit_revised_capacity(cases_per_family)
    with threadpool_limits(limits=1):
        original = fit_parameters(legacy["train"], legacy["validation"])
        original_results = {name: _matrix(rows, original.window_s)
                            for name, rows in observations.items()}
        scores = {}
        for name, rows in observations.items():
            x, y, _ = original_results[name]
            revised_x, revised_y, _ = _matrix(rows, revised.window_s)
            scores[name] = {
                "original": _fit_metrics(original.models[0].predict(x), y, len(rows)),
                "revised": _fit_metrics(revised.model.predict(revised_x), revised_y, len(rows)),
                "prior": _fit_metrics(np.full(len(y), NOMINAL_C), y, len(rows)),
            }
        distributions = {}
        for window in WINDOWS:
            train_x, train_y, _ = _matrix(old_train, window)
            val_x, val_y, _ = _matrix(old_validation, window)
            distributions[window] = {
                "train": _describe(train_x, train_y, train_x),
                "validation": _describe(val_x, val_y, train_x),
                **{name: _describe(*_matrix(rows, window)[:2], train_x)
                   for name, rows in observations.items()},
            }
        explanations = _observed_perturbations(
            original.models[0], original.window_s, observations["thevenin"])
        ridge = original.models[0]
        if original.names[0] == "Ridge":
            scaler, linear = ridge.steps[0][1], ridge.steps[-1][1]
            train_x = _matrix(old_train, original.window_s)[0]
            test_x = original_results["thevenin"][0]
            shift = (scaler.transform(test_x).mean(axis=0)
                     - scaler.transform(train_x).mean(axis=0))
            contributions = dict(zip(DIAGNOSTIC_FEATURES, shift * linear.coef_ / 3600))
        else:
            contributions = {}
    return {
        "status": "development evidence only", "cases_per_family": cases_per_family,
        "old_winner": {"name": original.names[0], "window": original.window_s,
                       "validation": {k: v["capacity_c"] for k, v in original.validation.items()}},
        "revised_winner": {"name": revised.name, "window": revised.window_s,
                           "validation": revised.validation},
        "old_cohort_scores": scores, "feature_target_distributions": distributions,
        "old_model_sensor_perturbations": explanations,
        "ridge_mean_shift_contributions_ah": contributions,
    }


if __name__ == "__main__":
    print(json.dumps(run_capacity_study(), indent=2, allow_nan=False))
