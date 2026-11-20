"""Matched Thevenin local sensitivity and seeded parameter recovery."""

from dataclasses import replace
import json

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import lfilter

from battery_sim import Cell, _r0, lumped_ocv, lumped_ocv_slope, rc_gain
from capacity_experiment import Scenario, signals
from synthetic_battery import SENSOR_STD


PARAMETERS = ("Q", "R0 at 298.15 K", "R1", "tau", "initial SOC")
WINDOWS = (180, 420)
CHECK_CASE = Cell(soh=.76, initial_soc=.77, resistance_scale=1.22, c1_f=880)


def coordinates(cell):
    """Work in relative log coordinates except for the initial SOC fraction."""
    r1 = cell.r1_ohm * cell.resistance_scale
    return np.r_[np.log([cell.capacity_c, cell.r0_ohm * cell.resistance_scale,
                          r1, r1 * cell.c1_f]), cell.initial_soc]


def voltage_jacobian(theta, current, temperature):
    """Predict voltage and its Jacobian at uniformly spaced one-second samples.

    Temperature is a supplied observation. This isolates the electrical model
    with a known temperature coefficient, without using thermal dynamics as
    an additional constraint on parameter recovery.
    """
    capacity, r0, r1, tau = np.exp(theta[:4])
    charge = np.r_[0., np.cumsum(current[:-1])]
    soc = theta[4] - charge / capacity
    slope = lumped_ocv_slope(soc)
    ohmic = current * r0 * (_r0(Cell(), temperature) / Cell.r0_ohm)
    gain = rc_gain(1., 1., tau)
    decay = 1. - gain
    polarisation = np.r_[0., lfilter([gain*r1], [1., -decay], current[:-1])]
    tau_derivative = np.r_[0., lfilter(
        [decay/tau], [1., -decay], polarisation[:-1] - r1*current[:-1])]
    jacobian = np.column_stack((slope*charge/capacity, -ohmic,
                                -polarisation, -tau_derivative, slope))
    return lumped_ocv(soc) - ohmic - polarisation, jacobian


def local_summary(theta, current, temperature):
    _, jac = voltage_jacobian(theta, current, temperature)
    # Report sensitivity to a 10% log perturbation or 0.1 SOC fraction.
    rms = np.sqrt(np.mean(jac**2, axis=0)) * 100
    normalized = jac / np.maximum(np.linalg.norm(jac, axis=0), np.finfo(float).tiny)
    singular = np.linalg.svd(normalized, compute_uv=False)
    full_rank = singular[-1] > 1e-12
    stderr = corr = None
    if full_rank:
        inverse = np.linalg.pinv(jac)
        covariance = inverse @ inverse.T * SENSOR_STD["voltage_v"]**2
        stderr = np.sqrt(np.diag(covariance))
        corr = covariance / np.outer(stderr, stderr)
    return {
        "rank": int(np.linalg.matrix_rank(normalized)),
        "normalized_condition": float(singular[0]/singular[-1]) if full_rank else None,
        "rms_response_mv": rms.tolist(),
        "voltage_only_std_percent": (100*stderr).tolist() if full_rank else None,
        "corr_log_q_log_r1": float(corr[0, 2]) if full_rank else None,
        "corr_log_r1_log_tau": float(corr[2, 3]) if full_rank else None,
    }


def recover(current, temperature, voltage):
    initial = np.r_[np.log([6400, .04, .02, 14]), .72]
    lower = np.r_[np.log([3600, .015, .005, 4]), .35]
    upper = np.r_[np.log([7600, .13, .07, 65]), .98]

    def residual(theta):
        return voltage_jacobian(theta, current, temperature)[0] - voltage

    def jacobian(theta):
        return voltage_jacobian(theta, current, temperature)[1]

    fit = least_squares(residual, initial, jac=jacobian, bounds=(lower, upper),
                        ftol=1e-10, xtol=1e-10, gtol=1e-10)
    if not fit.success:
        raise RuntimeError(f"Parameter recovery failed: {fit.message}")
    return fit.x


def run_study(repeats=12):
    """Compare the same excitation at different temperatures and noise levels."""
    results = {}
    for label, temp, noise, bias in (
        ("cold", 282.15, 1., 0.), ("reference", 298.15, 1., 0.),
        ("warm", 313.15, 1., 0.), ("noisy and biased", 298.15, 3., .06),
    ):
        cell = replace(CHECK_CASE, ambient_k=temp)
        cases = [signals(Scenario(label, 4, cell, seed=9821 + seed,
                                  noise=noise, bias_a=bias), max(WINDOWS))
                 for seed in range(repeats)]
        theta = coordinates(cell)
        rows = {}
        for window in WINDOWS:
            sl = slice(0, window+1)
            first = cases[0]
            values = local_summary(theta, first["truth_current_a"][sl],
                                   first["truth_temperature_k"][sl])
            errors = []
            for data in cases:
                fit = recover(*(data[f"measured_{channel}"][sl] for channel in
                                ("current_a", "temperature_k", "voltage_v")))
                # Include derived C1 = tau / R1. SOC absolute error is in pp.
                logs = fit[:4] - theta[:4]
                errors.append(np.abs(np.r_[np.expm1(logs),
                                           np.expm1(logs[3]-logs[2]), fit[4]-theta[4]])*100)
            values["recovery_median_error"] = np.median(errors, axis=0).tolist()
            values["recovery_max_error"] = np.max(errors, axis=0).tolist()
            rows[window] = values
        results[label] = rows
    theta = coordinates(CHECK_CASE)
    rest = local_summary(theta, np.zeros(181), np.full(181, 298.15))
    baseline = signals(Scenario("reference", 4, CHECK_CASE), 180)
    low_load = local_summary(theta, .25*baseline["truth_current_a"],
                             baseline["truth_temperature_k"])
    return {"parameters": PARAMETERS, "recoveries": repeats, "rest": rest,
            "quarter_load": low_load, "loaded": results}


if __name__ == "__main__":
    print(json.dumps(run_study(), indent=2, allow_nan=False))
