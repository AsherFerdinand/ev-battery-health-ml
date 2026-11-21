"""Measured-only adaptation audit and independent paired comparison."""

from dataclasses import asdict, dataclass
from time import perf_counter

import numpy as np

from battery_sim import Cell
from capacity_experiment import NOMINAL_C
from parameter_estimation import BOUNDS, adaptive_features
from soc_estimation import AdaptiveUpdate, thevenin_ekf


@dataclass(frozen=True)
class Evidence:
    index: int
    raw_capacity_c: float | None
    clipped_capacity_c: float | None
    raw_r0_ref_ohm: float | None
    features_distance: float | None
    current_steps: int
    innovation_ratio: float


@dataclass(frozen=True)
class Policy:
    max_innovation: float | None
    blend: float

    def decide(self, evidence):
        reasons = ["Capacity held at the nominal prior under the safeguarded policy."]
        r0 = evidence.raw_r0_ref_ohm
        bounded = None if r0 is None else float(np.clip(r0, *BOUNDS[1]))
        audit = asdict(evidence) | {"clipped_r0_ref_ohm": bounded}
        if evidence.current_steps < 2:
            reasons.append("Fewer than two informative current steps.")
        elif r0 is None or not np.isfinite(r0) or not BOUNDS[1, 0] <= r0 <= BOUNDS[1, 1]:
            reasons.append("Unbounded resistance prediction outside the admissible range.")
        elif self.blend == 0:
            reasons.append("Development selected the fixed fallback.")
        elif self.max_innovation is not None and evidence.innovation_ratio > self.max_innovation:
            reasons.append("Pre-update normalized innovation exceeds the calibrated threshold.")
        else:
            applied = Cell.r0_ohm + self.blend * (r0 - Cell.r0_ohm)
            reasons.append(f"Resistance accepted with {self.blend:.0%} weight on the ML prediction.")
            return audit | {
                "accepted": True, "reasons": reasons, "applied_capacity_c": NOMINAL_C,
                "applied_r0_ref_ohm": applied,
            }
        return audit | {
            "accepted": False, "reasons": reasons, "applied_capacity_c": NOMINAL_C,
            "applied_r0_ref_ohm": Cell.r0_ohm,
        }


def evidence_from_samples(samples, fixed, original, center, scale):
    """Read measured features and fixed EKF diagnostics through the cutoff only."""
    index, features = adaptive_features(samples, original.window_s)
    steps = int(np.count_nonzero(np.abs(np.diff(samples.current_a[:index+1])) >= 0.35))
    start = int(np.searchsorted(samples.time_s, samples.time_s[0]+30))
    residual = fixed["innovation_v"][start:index+1]
    variance = fixed["innovation_variance_v2"][start:index+1]
    ratio = float(np.sqrt(np.mean(residual**2 / variance)))
    if features is None:
        return Evidence(index, None, None, None, None, steps, ratio)
    q, r0 = (float(model.predict(features[None])[0]) for model in original.models)
    distance = float(np.max(np.abs((features-center)/scale)))
    return Evidence(index, q, float(np.clip(q, *BOUNDS[0])), r0, distance, steps, ratio)


def guarded_run(samples, initial_guess, fixed, evidence, policy):
    decision = policy.decide(evidence)
    if not decision["accepted"]:
        return fixed, decision
    update = AdaptiveUpdate(evidence.index, decision["applied_capacity_c"],
                            decision["applied_r0_ref_ohm"])
    return thevenin_ekf(samples, initial_guess, NOMINAL_C, adaptive_update=update), decision


def candidate_policies():
    # Fixed fallback competes with blending and with explicitly innovation-gated updates.
    return (Policy(None, 0.),) + tuple(
        Policy(limit, blend) for blend in (.5, 1.) for limit in (.65, 1., 1.5, None)
    )


def _post_error(result, truth, index):
    tail = slice(index+1, None)
    return float(100*np.mean(np.abs(result["estimated_soc"][tail] - truth[tail])))


def calibrate(cases, original, center, scale):
    from soc_estimation import Measurements
    from validation_population import validation_signals

    policies = candidate_policies()
    losses = [[] for _ in policies]
    for case in cases:
        data = validation_signals(case)
        samples = Measurements.from_dataset(data)
        fixed = thevenin_ekf(samples, case.initial_guess, NOMINAL_C)
        e = evidence_from_samples(samples, fixed, original, center, scale)
        truth = data["truth_soc"]
        baseline = _post_error(fixed, truth, e.index)
        for policy, risks in zip(policies, losses):
            guarded, _ = guarded_run(samples, case.initial_guess, fixed, e, policy)
            delta = _post_error(guarded, truth, e.index) - baseline
            # Penalize a loss twice as much as a same-sized gain.
            risks.append(delta + max(0., delta))
    scores = [float(np.mean(loss)) for loss in losses]
    winner = int(np.argmin(scores))
    return policies[winner], [asdict(p) | {"development_risk_pp": value}
                              for p, value in zip(policies, scores)]


def _capacity_scores(rows, label):
    estimates = np.array([row[label] for row in rows], dtype=float)
    truth = np.array([row["truth_capacity_c"] for row in rows])
    present = np.isfinite(estimates)
    inside = present & (estimates >= BOUNDS[0, 0]) & (estimates <= BOUNDS[0, 1])
    bounded = np.where(present, np.clip(estimates, *BOUNDS[0]), NOMINAL_C)
    return {"mae_ah": float(np.mean(np.abs(bounded - truth))/3600),
            "clip_rate": float(np.mean(present & ~inside)),
            "in_range_rate": float(inside.mean()), "unavailable_rate": float((~present).mean())}


def _compare(case, models, policy, center, scale, playback=False):
    from capacity_experiment import benchmark, score
    from parameter_estimation import references
    from soc_estimation import Measurements
    from validation_population import validation_signals

    hybrid_a, original, revised = models
    started = perf_counter()
    data = validation_signals(case)
    simulation_ms = (perf_counter() - started)*1000
    samples = Measurements.from_dataset(data)
    index, prediction = original.predict(samples)
    update = None if prediction is None else AdaptiveUpdate(index, *prediction)
    results = benchmark(case, data, samples, hybrid_a, adaptive_update=update)
    fixed, fixed_ms = results["Fixed EKF"]
    if update is None:
        results["Hybrid B"] = (fixed, fixed_ms)
    started = perf_counter()
    evidence = evidence_from_samples(samples, fixed, original, center, scale)
    guarded, decision = guarded_run(samples, case.initial_guess, fixed, evidence, policy)
    guard_ms = (perf_counter() - started)*1000
    elapsed = fixed_ms + guard_ms
    results["Safeguarded Hybrid B"] = guarded, elapsed
    _, revised_raw = revised.predict_raw(samples)
    capacity, reference_r0 = map(float, references(case))
    original_r0 = Cell.r0_ohm if update is None else update.r0_ref_ohm
    applied = {"Hybrid B": original_r0, "Safeguarded Hybrid B": decision["applied_r0_ref_ohm"],
               "Oracle EKF": reference_r0}
    metrics = {}
    for name, run in results.items():
        metrics[name] = score(data, samples, *run, index)
        metrics[name]["r0_error_mohm"] = 1000*(applied.get(name, Cell.r0_ohm) - reference_r0)
    row = {
        "name": case.name, "family": case.family, "plant": case.plant, "metrics": metrics,
        "decision": decision, "simulation_ms": simulation_ms, "truth_capacity_c": capacity,
        "original_capacity_c": evidence.raw_capacity_c, "revised_capacity_c": revised_raw,
        "fixed_capacity_c": NOMINAL_C,
    }
    if playback:
        trace_fields = ("predicted_state", "corrected_state", "predicted_voltage_v", "innovation_v",
                        "kalman_gain", "covariance", "capacity_c")
        traces = {name: {key: results[name][0][key].tolist() for key in trace_fields}
                  for name in ("Hybrid A", "Hybrid B")}
        adaptive_parameters = {
            "capacity_c": {"fixed": NOMINAL_C,
                           "estimated": NOMINAL_C if update is None else update.capacity_c,
                           "reference": capacity},
            "r0_ref_ohm": {"fixed": Cell.r0_ohm, "estimated": original_r0, "reference": reference_r0},
        }
        row["playback"] = {
            "name": f"Independent · {case.plant} · {case.name}", "plant": case.plant,
            "truth_soh": case.cell.soh, "time": samples.time_s.tolist(),
            "current": samples.current_a.tolist(), "temperature": samples.temperature_k.tolist(),
            "voltage": samples.voltage_v.tolist(), "truth": data["truth_soc"].tolist(),
            "trials": {"Scenario assumption": {
                "initial_soc": case.initial_guess, "metrics": metrics,
                "soc": {name: run[0]["estimated_soc"].tolist() for name, run in results.items()
                        if name not in ("Hybrid A", "Hybrid B", "Safeguarded Hybrid B")},
                "diagnostics": traces["Hybrid A"],
                "adaptive": {"parameters": adaptive_parameters, "update_applied": update is not None,
                             "window_s": original.window_s, "models": original.details()["models"],
                             "fixed_voltage_v": fixed["predicted_voltage_v"].tolist(),
                             "diagnostics": traces["Hybrid B"]},
                "robust": {"decision": decision | {"window_s": original.window_s,
                                                   "revised_capacity_c": revised_raw},
                           "soc": guarded["estimated_soc"].tolist() if decision["accepted"] else None,
                           "predicted_voltage_v": guarded["predicted_voltage_v"].tolist()
                           if decision["accepted"] else None},
            }},
        }
    return row


def _summarize(label, rows):
    fields = ("mae_pp", "rmse_pp", "bias_pp", "max_pp", "voltage_rmse_mv")
    metrics = {}
    for name in rows[0]["metrics"]:
        scores = [row["metrics"][name] for row in rows]
        converged = [score["convergence_s"] is not None for score in scores]
        metrics[name] = {key: float(np.mean([score[key] for score in scores])) for key in fields}
        metrics[name].update({
            "post_mae_pp": float(np.mean([s["adaptive_post_mae_pp"] for s in scores])),
            "capacity_mae_ah": float(np.mean([abs(s["capacity_error_ah"]) for s in scores])),
            "r0_mae_mohm": float(np.mean([abs(s["r0_error_mohm"]) for s in scores])),
            "median_ms": float(np.median([s["execution_ms"] for s in scores])),
            "convergence_rate": float(np.mean(converged)),
        })
    fixed = np.array([row["metrics"]["Fixed EKF"]["adaptive_post_mae_pp"] for row in rows])
    original = np.array([row["metrics"]["Hybrid B"]["adaptive_post_mae_pp"] for row in rows])
    guarded = np.array([row["metrics"]["Safeguarded Hybrid B"]["adaptive_post_mae_pp"] for row in rows])
    accepted = np.array([row["decision"]["accepted"] for row in rows])
    harm_margin = .02
    harmful = original - fixed > harm_margin
    beneficial = fixed - original > harm_margin
    families = sorted({row["family"] for row in rows})
    group_means = [float(np.mean([(guarded-fixed)[i] for i, row in enumerate(rows)
                                  if row["family"] == family])) for family in families]
    worst = int(np.argmax(guarded-fixed))
    return {
        "name": label, "plant": rows[0]["plant"], "cases": len(rows), "metrics": metrics,
        "rejection_rate": float(np.mean(~accepted)), "harmful_original": float(harmful.mean()),
        "harmful_guarded": float(np.mean(guarded-fixed > harm_margin)),
        "false_accept": int(np.count_nonzero(accepted & harmful)),
        "false_reject": int(np.count_nonzero(~accepted & beneficial)),
        "family_mean_delta_pp_range": [min(group_means), max(group_means)],
        "median_simulation_ms": float(np.median([row["simulation_ms"] for row in rows])),
        "worst_guarded": {"case": rows[worst]["name"], "increase_pp": float((guarded-fixed)[worst])},
    }


def run_validation(full=False):
    from capacity_experiment import fit_capacity, population
    from parameter_estimation import _matrix, fit_parameters, rc_variation
    from threadpoolctl import threadpool_limits
    from validation_population import fit_revised_capacity, paired, provenance

    old = population(48)
    with threadpool_limits(limits=1):
        a, _, winner, _ = fit_capacity(old["train"], old["validation"])
        original = fit_parameters(old["train"], old["validation"])
        revised = fit_revised_capacity(48)
        x = _matrix([rc_variation(case) for case in old["train"]], [original.window_s])[original.window_s]
        center, scale = x.mean(axis=0), x.std(axis=0).clip(min=1e-8)
        development = paired("development", 5)
        policy, calibration = calibrate([case for group in development.values() for case in group],
                                        original, center, scale)
        # Only access final families after models and policy have been selected.
        count = 12 if full else 3
        final = paired("final", count)
        models = a[winner], original, revised
        cohorts, capacity, details, playback = [], [], {}, []
        represented = set()
        for plant, cases in final.items():
            rows = []
            for case in cases:
                row = _compare(case, models, policy, center, scale)
                rows.append(row)
                label = plant, row["decision"]["accepted"], row["decision"]["current_steps"] < 2
                if label not in represented and len(playback) < 3:
                    represented.add(label)
                    example = _compare(case, models, policy, center, scale, playback=True)
                    playback.append(example["playback"])
            cohorts.append(_summarize(f"Final · {plant}", rows))
            for name, key in (("v1.5 model", "original_capacity_c"),
                              ("Revised candidate", "revised_capacity_c"),
                              ("Fixed prior", "fixed_capacity_c")):
                capacity.append({"name": f"Final {plant} · {name}"} | _capacity_scores(rows, key))
            details[plant] = rows
        formatted = "fixed fallback" if policy.blend == 0 else f"{policy.blend:.0%} resistance blend"
        limit = "without an innovation limit" if policy.max_innovation is None else (
            f"with normalized innovation at most {policy.max_innovation:g}")
        return {
            "cohorts": cohorts, "capacity": capacity, "window_s": original.window_s,
            "policy": f"Development selected {formatted}, {limit}. Capacity stays at the nominal prior.",
            "configuration": asdict(policy), "calibration": calibration,
            "capacity_candidate": {"model": revised.name, "window_s": revised.window_s,
                                   "validation": revised.validation},
            "provenance": {"development": provenance("development", 5),
                           "final": provenance("final", count)},
            "details": details, "scenarios": playback,
        }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true")
    report = run_validation(parser.parse_args().full)
    report.pop("scenarios")
    print(json.dumps(report, indent=2, allow_nan=False))
