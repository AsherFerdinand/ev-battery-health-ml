"""Generate reproducible synthetic datasets and optional verification plots."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path

import numpy as np

from battery_sim import Cell, MODELS, simulate


PROFILES = {
    # (duration in seconds, held current in amperes)
    "pulse": ((30, 0), (80, 1.4), (90, 0), (45, -0.65), (115, 0)),
    "mixed": ((25, 0), (65, 1.1), (25, -0.6), (40, 2), (45, 0.4), (40, 0),
              (55, 1.4), (30, -0.75), (35, 0)),
    "rest": ((360, 0),),
}


def profile(name):
    segments = np.asarray(PROFILES[name])
    ends = np.cumsum(segments[:, 0])
    time = np.arange(ends[-1] + 1, dtype=np.float64)
    current = segments[np.minimum(np.searchsorted(ends, time, side="right"),
                                  len(ends) - 1), 1]
    return time, current


def dataset(model, profile_name, cell, seed, noise_scale):
    if not np.isfinite(noise_scale) or noise_scale < 0:
        raise ValueError("Noise scale must be finite and nonnegative.")
    time, current = profile(profile_name)
    result = simulate(time, current, cell, model)
    sigmas = {"current_a": 0.015, "voltage_v": 0.003, "temperature_k": 0.12}
    rng = np.random.Generator(np.random.PCG64(seed))
    for channel, sigma in sigmas.items():
        noise = rng.normal(0, noise_scale * sigma, time.size)
        result[f"measured_{channel}"] = result[f"truth_{channel}"] + noise
    result["metadata_json"] = np.array(json.dumps({
        "schema_version": 1,
        "provenance": "synthetic",
        "model": model,
        "cell": asdict(cell),
        "profile": profile_name,
        "profile_segments_s_a": PROFILES[profile_name],
        "seed": seed,
        "rng": "NumPy PCG64",
        "numpy_version": np.__version__,
        "measurement_noise_std": {
            channel: noise_scale * sigma for channel, sigma in sigmas.items()
        },
    }, sort_keys=True))
    return result


def figure(path, datasets, profile_name, cell):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(10, 6), layout="constrained")
    current_ax, voltage_ax, soc_ax, residual_ax = axes.flat
    diffusion = datasets["diffusion"]
    time = diffusion["time_s"]
    current_ax.step(time, diffusion["truth_current_a"], where="post", color="#253451")
    current_ax.set(ylabel="Current (A)", title="Applied load")
    for model, series in datasets.items():
        voltage_ax.plot(time, series["truth_voltage_v"], label=model, linewidth=1.4)
    voltage_ax.set(ylabel="Terminal voltage (V)", title="Model response")
    voltage_ax.legend(frameon=False)
    soc_ax.plot(time, diffusion["truth_soc"] * 100, label="Bulk SOC")
    soc_ax.plot(time, diffusion["truth_surface_fraction"] * 100, label="Surface filling")
    soc_ax.set(ylabel="Fraction (%)", title="Diffusion state")
    soc_ax.legend(frameon=False)
    for model in ("rint", "thevenin", "dual"):
        delta_mv = (datasets[model]["truth_voltage_v"] - diffusion["truth_voltage_v"]) * 1000
        residual_ax.plot(time, delta_mv, label=model, linewidth=1.4)
    residual_ax.axhline(0, color="0.4", linewidth=0.8)
    residual_ax.set(ylabel="Voltage difference (mV)", title="ECM minus diffusion")
    for ax in axes.flat:
        ax.set_xlabel("Time (s)")
        ax.grid(alpha=0.2)
    fig.suptitle(
        f"Synthetic {profile_name} verification · {cell.soh:.0%} SOH · "
        f"{cell.ambient_k:g} K ambient"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=(*MODELS, "all"), default="all")
    parser.add_argument("--profile", choices=PROFILES, default="pulse")
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--soh", type=float, default=Cell.soh)
    parser.add_argument("--initial-soc", type=float, default=Cell.initial_soc)
    parser.add_argument("--ambient-k", type=float, default=Cell.ambient_k)
    parser.add_argument("--resistance-scale", type=float, default=Cell.resistance_scale)
    parser.add_argument("--noise-scale", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--figure", type=Path, help="Plot the selected scenario with all four models.")
    args = parser.parse_args()
    if args.figure and args.model != "all":
        parser.error("--figure requires --model all")
    if args.seed < 0:
        parser.error("--seed must be nonnegative")
    try:
        cell = replace(Cell(), soh=args.soh, initial_soc=args.initial_soc,
                       ambient_k=args.ambient_k, resistance_scale=args.resistance_scale)
        models = MODELS if args.model == "all" else (args.model,)
        datasets = {
            model: dataset(model, args.profile, cell, args.seed, args.noise_scale)
            for model in models
        }
    except ValueError as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    for model, channels in datasets.items():
        path = args.output / f"{args.profile}_{model}.npz"
        np.savez_compressed(path, **channels)
        print(f"{path} ({channels['time_s'].size} samples, {path.stat().st_size} bytes)")
    if args.figure:
        figure(args.figure, datasets, args.profile, cell)


if __name__ == "__main__":
    main()
