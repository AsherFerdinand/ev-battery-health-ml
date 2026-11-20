"""Synthetic cell physics. See docs/synthetic-battery.md for conventions."""

from dataclasses import dataclass

import numpy as np


ECM_BRANCHES = {"rint": 0, "thevenin": 1, "dual": 2}
MODELS = (*ECM_BRANCHES, "diffusion")
GAS_CONSTANT = 8.314462618  # J/(mol K)
FARADAY_CONSTANT = 96485.33212  # C/mol


@dataclass(frozen=True)
class Cell:
    nominal_ah: float = 2.0
    soh: float = 0.85
    initial_soc: float = 0.80
    ambient_k: float = 298.15
    resistance_scale: float = 1.0
    r0_ohm: float = 0.035
    r1_ohm: float = 0.018
    c1_f: float = 650.0
    r2_ohm: float = 0.012
    c2_f: float = 5000.0
    thermal_capacity_j_per_k: float = 65.0
    cooling_w_per_k: float = 0.18
    diffusion_rate_per_s: float = 0.006
    diffusion_cells: int = 24
    exchange_current_a: float = 1.8

    def __post_init__(self):
        positive = (
            self.nominal_ah, self.ambient_k, self.resistance_scale,
            self.r0_ohm, self.r1_ohm, self.c1_f, self.r2_ohm, self.c2_f,
            self.thermal_capacity_j_per_k, self.cooling_w_per_k,
            self.diffusion_rate_per_s, self.exchange_current_a,
        )
        if not all(np.isfinite(v) and v > 0 for v in positive):
            raise ValueError("Cell parameters must be finite and positive.")
        if not 0 < self.soh <= 1 or not 0 <= self.initial_soc <= 1:
            raise ValueError("SOH must be in (0, 1] and initial SOC in [0, 1].")
        if type(self.diffusion_cells) is not int or not 4 <= self.diffusion_cells <= 128:
            raise ValueError("Diffusion mesh must have 4 to 128 cells.")

    @property
    def capacity_c(self):
        return self.nominal_ah * self.soh * 3600.0


def lumped_ocv(soc):
    return 3.05 + 1.05 * soc + 0.08 * np.tanh((soc - 0.52) / 0.15)


def lumped_ocv_slope(soc):
    return 1.05 + (0.08 / 0.15) * (1 - np.tanh((soc - 0.52) / 0.15)**2)


def rc_gain(dt, resistance, capacitance):
    return -np.expm1(-dt / (resistance * capacitance))


def _surface_ocv(surface):
    return 3.15 + 0.95 * surface + 0.14 * np.tanh((surface - 0.41) / 0.18)


def resistance_temperature_factor(temp_k):
    return np.exp(0.018 * (298.15 - temp_k))


def _r0(cell, temp):
    return cell.r0_ohm * cell.resistance_scale * resistance_temperature_factor(temp)


def _temperature(cell, temp, heat_w, dt):
    gain = -np.expm1(-cell.cooling_w_per_k * dt / cell.thermal_capacity_j_per_k)
    return temp + gain * (cell.ambient_k + heat_w / cell.cooling_w_per_k - temp)


def _check_fraction(values, label):
    if np.any(~np.isfinite(values)) or np.any((values < -1e-12) | (values > 1 + 1e-12)):
        raise ValueError(f"{label} left [0, 1]; shorten or reduce the current profile.")


def _diffusion_modes(cells, rate):
    # Unit-length slab with reflecting boundaries. Current enters as a
    # boundary flux in the last control volume; the first face is insulated.
    laplacian = np.diag(np.full(cells, -2.0))
    laplacian += np.diag(np.ones(cells - 1), 1) + np.diag(np.ones(cells - 1), -1)
    laplacian[0, 0] = laplacian[-1, -1] = -1.0
    eigenvalues, basis = np.linalg.eigh(rate * cells**2 * laplacian)
    eigenvalues[-1] = 0.0  # exact conservation mode
    return eigenvalues, basis, basis[-1, :] * cells


def _simulate_diffusion(time, current, cell):
    eigenvalues, basis, flux = _diffusion_modes(
        cell.diffusion_cells, cell.diffusion_rate_per_s
    )
    modes = basis.T @ np.full(cell.diffusion_cells, cell.initial_soc)
    dt = np.diff(time)
    rates = eigenvalues[:-1]
    previous_step = None
    activation_per_k = (2 * GAS_CONSTANT / FARADAY_CONSTANT) * np.arcsinh(
        current / (2 * cell.exchange_current_a)
    )
    temp_k = np.full(time.size, cell.ambient_k)
    surface = np.empty(time.size)
    bulk = np.empty(time.size)
    kinetic = np.empty(time.size)
    series = np.empty(time.size)
    for k, amps in enumerate(current):
        fractions = basis @ modes
        _check_fraction(fractions, "Diffusion filling at a sample time")
        bulk[k] = fractions.mean()
        surface[k] = fractions[-1]
        series[k] = _r0(cell, temp_k[k])
        # Symmetric Butler–Volmer activation, with 2R/F in V/K.
        kinetic[k] = temp_k[k] * activation_per_k[k]
        if k < dt.size:
            step = dt[k]
            if step != previous_step:
                z = step * rates
                decay = np.exp(z)
                integrated_flux = np.append(np.expm1(z) / rates, step) * flux
                previous_step = step
            modes[:-1] *= decay
            modes -= integrated_flux * (amps / cell.capacity_c)
            heat = amps**2 * series[k] + amps * kinetic[k]
            temp_k[k + 1] = _temperature(cell, temp_k[k], heat, step)
    return {
        "truth_soc": bulk,
        "truth_temperature_k": temp_k,
        "truth_voltage_v": _surface_ocv(surface) - current * series - kinetic,
        "truth_surface_fraction": surface,
        "truth_activation_drop_v": kinetic,
        "ref_r0_ohm": series,
    }


def _simulate_ecm(time, current, cell, branches):
    dt = np.diff(time)
    total_charge = np.concatenate(([0.0], np.cumsum(current[:-1] * dt)))
    soc = cell.initial_soc - total_charge / cell.capacity_c
    _check_fraction(soc, "SOC")

    resistance = cell.resistance_scale * np.array([cell.r1_ohm, cell.r2_ohm])[:branches]
    capacitance = np.array([cell.c1_f, cell.c2_f])[:branches]
    branch_v = np.zeros((time.size, branches))
    if branches:
        gain = rc_gain(dt[:, None], resistance, capacitance)
        targets = current[:-1, None] * resistance
        for k, interval_gain in enumerate(gain):
            branch_v[k + 1] = branch_v[k] + interval_gain * (targets[k] - branch_v[k])

    temp_k = np.full(time.size, cell.ambient_k)
    if np.any(current):
        for k, step in enumerate(dt):
            heat = current[k] ** 2 * _r0(cell, temp_k[k])
            temp_k[k + 1] = _temperature(cell, temp_k[k], heat, step)
    r0 = _r0(cell, temp_k)
    result = {
        "truth_soc": soc,
        "truth_temperature_k": temp_k,
        "truth_voltage_v": lumped_ocv(soc) - current * r0 - branch_v.sum(axis=1),
        "ref_r0_ohm": r0,
    }
    for index in range(branches):
        branch = index + 1
        result[f"truth_polarisation_{branch}_v"] = branch_v[:, index].copy()
        result[f"ref_r{branch}_ohm"] = np.full(time.size, resistance[index])
        result[f"ref_c{branch}_f"] = np.full(time.size, capacitance[index])
    return result


def simulate(time_s, current_a, cell=Cell(), model="thevenin"):
    """Return sampled truth and reference channels as float64 NumPy arrays."""
    time = np.asarray(time_s, dtype=np.float64)
    current = np.asarray(current_a, dtype=np.float64)
    if model not in MODELS:
        raise ValueError(f"Unknown battery model: {model}")
    if (
        time.ndim != 1 or time.size < 2 or current.shape != time.shape
        or not np.all(np.isfinite(time)) or not np.all(np.isfinite(current))
        or time[0] != 0 or np.any(np.diff(time) <= 0)
    ):
        raise ValueError("Use matching finite 1D arrays and strictly increasing time starting at zero.")

    if model == "diffusion":
        result = _simulate_diffusion(time, current, cell)
    else:
        result = _simulate_ecm(time, current, cell, ECM_BRANCHES[model])
    result.update(
        time_s=time.copy(),
        truth_current_a=current.copy(),
        truth_soh=np.full(time.size, cell.soh),
        ref_available_capacity_c=np.full(time.size, cell.capacity_c),
    )
    return result
