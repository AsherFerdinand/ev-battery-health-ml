"""Causal Coulomb counting and two-state Thevenin SOC filtering."""

from dataclasses import dataclass

import numpy as np

from battery_sim import Cell, lumped_ocv, lumped_ocv_slope, rc_gain


@dataclass(frozen=True)
class Measurements:
    time_s: np.ndarray
    current_a: np.ndarray
    voltage_v: np.ndarray
    temperature_k: np.ndarray

    def __post_init__(self):
        for field in ("time_s", "current_a", "voltage_v", "temperature_k"):
            array = np.array(getattr(self, field), dtype=float, copy=True)
            if array.ndim != 1 or not np.isfinite(array).all():
                raise ValueError("Measurement channels must be finite 1D arrays.")
            array.setflags(write=False)
            object.__setattr__(self, field, array)
        if (len(self.time_s) < 2 or np.any(np.diff(self.time_s) <= 0)
                or any(x.shape != self.time_s.shape for x in
                       (self.current_a, self.voltage_v, self.temperature_k))):
            raise ValueError("Use matching channels and strictly increasing time.")

    @classmethod
    def from_dataset(cls, data):
        return cls(data["time_s"], data["measured_current_a"],
                   data["measured_voltage_v"], data["measured_temperature_k"])


@dataclass(frozen=True)
class Thevenin:
    r0_ohm: float | np.ndarray = Cell.r0_ohm
    r1_ohm: float = Cell.r1_ohm
    c1_f: float = Cell.c1_f

    def series(self, count):
        series = np.broadcast_to(self.r0_ohm, (count,))
        values = np.concatenate((series, [self.r1_ohm, self.c1_f]))
        if not np.isfinite(values).all() or np.any(values <= 0):
            raise ValueError("Resistance and capacitance must be finite and positive.")
        return series


def _validate(initial_soc, capacity_c):
    if not 0 <= initial_soc <= 1 or not np.isfinite(capacity_c) or capacity_c <= 0:
        raise ValueError("Provide a fractional initial SOC and positive capacity in coulombs.")


def transition(state, dt, current, capacity, r1, c1):
    gain = rc_gain(dt, r1, c1)
    return np.array([state[0] - dt * current / capacity,
                     state[1] + gain * (current * r1 - state[1])]), np.diag([1., 1 - gain])


def voltage_observation(state, current, r0):
    return lumped_ocv(state[0]) - state[1] - current * r0, np.array([
        lumped_ocv_slope(state[0]), -1.
    ])


def coulomb_count(measurements, initial_soc, capacity_c, params=Thevenin()):
    _validate(initial_soc, capacity_c)
    r0 = params.series(len(measurements.time_s))
    soc = np.empty(len(r0))
    voltage = np.empty(len(r0))
    state = np.array([initial_soc, 0.])
    for k, amps in enumerate(measurements.current_a):
        if k:
            state, _ = transition(state, measurements.time_s[k] - measurements.time_s[k-1],
                                  measurements.current_a[k-1], capacity_c, params.r1_ohm,
                                  params.c1_f)
            state[0] = np.clip(state[0], 0, 1)
        soc[k] = state[0]
        voltage[k] = voltage_observation(state, amps, r0[k])[0]
    return {"estimated_soc": soc, "predicted_voltage_v": voltage,
            "capacity_c": np.full(len(r0), capacity_c)}


def thevenin_ekf(measurements, initial_soc, capacity_c, params=Thevenin(), *,
                 capacity_update=None):
    """Update capacity once after the voltage correction at the nominated sample.

    The new capacity first affects the transition out of that sample.
    """
    _validate(initial_soc, capacity_c)
    time, amps, volts = (measurements.time_s, measurements.current_a, measurements.voltage_v)
    n = time.size
    r0 = params.series(n)
    if capacity_update is not None:
        index, updated = capacity_update
        if not isinstance(index, (int, np.integer)) or not 0 <= index < n - 1:
            raise ValueError("Capacity update requires a sample with a following interval.")
        _validate(initial_soc, updated)

    state = np.array([initial_soc, 0.])
    covariance = np.diag([0.12**2, 0.020**2])
    process_per_s = np.diag([8e-9, 3e-7])
    voltage_variance = 0.012**2
    identity = np.eye(2)
    predicted = np.empty((n, 2))
    corrected = np.empty_like(predicted)
    posterior = np.empty((n, 2, 2))
    gain_trace = np.empty_like(predicted)
    predicted_v, innovation, capacities = np.empty((3, n))
    for k in range(n):
        if k:
            dt = time[k] - time[k-1]
            state, jacobian = transition(state, dt, amps[k-1], capacity_c, params.r1_ohm,
                                         params.c1_f)
            covariance = jacobian @ covariance @ jacobian.T + dt * process_per_s
        state[0] = np.clip(state[0], 0, 1)
        predicted[k] = state
        predicted_v[k], observation = voltage_observation(state, amps[k], r0[k])
        innovation[k] = volts[k] - predicted_v[k]
        projected = covariance @ observation
        gain = projected / (observation @ projected + voltage_variance)
        state = state + gain * innovation[k]
        state[0] = np.clip(state[0], 0, 1)
        remainder = identity - np.outer(gain, observation)
        covariance = remainder @ covariance @ remainder.T + voltage_variance * np.outer(gain, gain)
        covariance = (covariance + covariance.T) * 0.5
        corrected[k], gain_trace[k], posterior[k] = state, gain, covariance

        if capacity_update is not None and k == index:
            capacity_c = updated
        capacities[k] = capacity_c

    return {
        "estimated_soc": corrected[:, 0], "corrected_state": corrected,
        "predicted_state": predicted, "covariance": posterior, "kalman_gain": gain_trace,
        "predicted_voltage_v": predicted_v, "innovation_v": innovation,
        "capacity_c": capacities,
    }
