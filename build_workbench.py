"""Build or open the offline synthetic SOC workbench."""

import argparse
import base64
import gzip
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
import webbrowser

ROOT = Path(__file__).resolve().parent


def nasa_replay(raw):
    """Display-only samples from the original NASA discharge traces."""
    import numpy as np
    from scipy.io import loadmat

    from pipeline import CELLS

    output = {}
    for cell in CELLS:
        path = raw / f"{cell}.mat"
        if not path.exists():
            continue
        battery = loadmat(path, squeeze_me=True, struct_as_record=False)[cell]
        cycles = []
        for record in np.atleast_1d(battery.cycle):
            if str(record.type) != "discharge":
                continue
            data = record.data
            time = np.asarray(data.Time).ravel()
            indices = np.unique(np.linspace(0, len(time)-1, 40, dtype=int))
            channels = np.column_stack([
                np.asarray(getattr(data, name)).ravel()[indices] for name in
                ("Time", "Voltage_measured", "Current_measured", "Temperature_measured")
            ])
            capacity = float(data.Capacity)
            if not np.isfinite(channels).all() or not np.isfinite(capacity) or capacity <= 0:
                cycles.append(None)
                continue
            channels[:, 0] -= channels[0, 0]
            cycles.append({"capacity_ah": capacity,
                           "trace": channels.round(4).tolist()})
        output[cell] = cycles
    return output


def physics_lab():
    import numpy as np

    from battery_sim import Cell, simulate

    time = np.arange(121.)
    examples = {}
    for model in ("rint", "thevenin", "dual"):
        for amps in (0.8, 1.6, 2.4):
            current = np.where((time >= 10) & (time < 55), amps, 0.)
            for resistance in (0.7, 1., 1.5):
                capacitances = (1.,) if model == "rint" else (0.5, 1., 2.)
                for capacitance in capacitances:
                    cell = replace(Cell(), resistance_scale=resistance,
                                   c1_f=Cell.c1_f*capacitance, c2_f=Cell.c2_f*capacitance)
                    data = simulate(time, current, cell, model)
                    branches = [data[key] for key in
                                ("truth_polarisation_1_v", "truth_polarisation_2_v")
                                if key in data]
                    key = f"{model}:{amps:g}:{resistance:g}:{capacitance:g}"
                    examples[key] = {
                        "terminal": data["truth_voltage_v"].tolist(),
                        "ohmic": (data["ref_r0_ohm"] * current).tolist(),
                        "polarisation": [branch.tolist() for branch in branches],
                        "tau": [r*c*resistance*capacitance for r, c in
                                ((Cell.r1_ohm, Cell.c1_f), (Cell.r2_ohm, Cell.c2_f))
                                ][:len(branches)],
                    }
    return examples


def _cache_key(paths, full):
    digest = hashlib.sha256(str(full).encode())
    for path in paths:
        digest.update(path.name.encode())
        if path.exists():
            stat = path.stat()
            digest.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode())
    return digest.hexdigest()


def _write_text(path, content):
    handle = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def build(full=False, refresh=False):
    reports = ROOT / "reports"
    raw = ROOT / "data/raw"
    output = reports / ("workbench-full.html" if full else "workbench.html")
    summary = output.with_suffix(".json")
    marker = output.with_suffix(".cache")
    sources = [ROOT / name for name in (
        "build_workbench.py", "capacity_experiment.py", "soc_estimation.py", "battery_sim.py",
        "workbench_template.html", "requirements-lock.txt", "synthetic_battery.py",
        "parameter_estimation.py")]
    fingerprint = _cache_key(sources + sorted(raw.glob("B*.mat")), full)
    if not refresh and all(path.exists() for path in (output, summary, marker)):
        if marker.read_text(encoding="utf-8") == fingerprint:
            return output
    started = perf_counter()
    from capacity_experiment import run_experiment

    experiment = run_experiment(full)
    playback = experiment.pop("scenarios")
    surfaces = experiment.pop("surfaces")
    # Corrected SOC already exists in each EKF diagnostic state.
    for case in playback:
        for trial in case["trials"].values():
            for name in ("Hybrid A", "Hybrid B"):
                del trial["soc"][name]
    payload = {
        "scenarios": playback, "surfaces": surfaces, "ml_details": experiment.pop("ml_details"),
        "selected_model": experiment["selected_model"], "window_s": experiment["window_s"],
        "mode": experiment["mode"], "nominal_c": experiment["nominal_c"],
        "nasa": nasa_replay(raw), "physics": physics_lab(),
        "validation": experiment["validation_soh_mae"], "test": experiment["test_soh_mae"],
        "identifiability": experiment["identifiability"], "hybrid_b": experiment["hybrid_b"],
    }
    experiment["demonstrations"] = [
        {key: case[key] for key in ("name", "plant", "truth_soh", "parameter_estimates", "inference_ms")}
        | {"metrics": case["trials"]["Scenario assumption"]["metrics"]} for case in playback
    ]
    reports.mkdir(parents=True, exist_ok=True)
    template = (ROOT / "workbench_template.html").read_text(encoding="utf-8")
    packed = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
    content = base64.b64encode(gzip.compress(packed, compresslevel=5, mtime=0)).decode("ascii")
    _write_text(output, template.replace("__WORKBENCH_DATA__", content))
    experiment["build_seconds"] = perf_counter() - started
    _write_text(summary, json.dumps(experiment, indent=2, allow_nan=False))
    _write_text(marker, fingerprint)
    return output



def serve(output, port):
    files = {"/": output, "/" + output.name: output,
             "/dashboard.html": output.parent / "dashboard.html"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            target = files.get(self.path)
            if target is None or not target.is_file():
                self.send_error(404, "Generated page unavailable")
                return
            content = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Offline workbench: {url} (Ctrl+C stops the server)", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Use the full research population.")
    parser.add_argument("--refresh", action="store_true", help="Rebuild generated files.")
    parser.add_argument("--no-open", action="store_true", help="Generate files without opening a browser.")
    parser.add_argument("--port", type=int, default=0, help="Use this loopback port when serving.")
    args = parser.parse_args()
    output = build(args.full, args.refresh)
    print(f"Workbench: {output.relative_to(ROOT)} ({output.stat().st_size:,} bytes)")
    if not args.no_open:
        serve(output, args.port)


if __name__ == "__main__":
    main()
