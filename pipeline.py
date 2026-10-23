"""NASA battery aging: first-minute SOH estimation and exploratory novelty detection."""
import argparse
import hashlib
import io
import json
import platform
import os
import zipfile
from pathlib import Path
from urllib.request import urlopen

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mpl-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.io import loadmat
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
URL = "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
CELLS = ("B0005", "B0006", "B0007", "B0018")
FEATURES = ["voltage_start", "voltage_60s", "voltage_mean", "voltage_std",
            "current_mean", "temperature_start", "temperature_rise", "ambient_c"]


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ingest(raw, offline=False):
    """Extract only selected MAT/README files, including nested ZIP archives."""
    raw.mkdir(parents=True, exist_ok=True)
    manifest = raw / "manifest.json"
    if all((raw / f"{cell}.mat").exists() for cell in CELLS):
        if not manifest.exists():
            raise ValueError("Missing provenance manifest; rerun with a fresh raw directory.")
        metadata = json.loads(manifest.read_text())
        for name, expected in metadata["files"].items():
            if sha256(raw / name) != expected:
                raise ValueError(f"Checksum mismatch: {name}")
        return
    archive = raw / "nasa-batteries.zip"
    if not archive.exists():
        if offline:
            raise FileNotFoundError("Offline mode requires cached NASA archive or extracted MAT files.")
        print("Downloading NASA archive...", flush=True)
        temporary = archive.with_suffix(".part")
        with urlopen(URL, timeout=180) as response, temporary.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        temporary.replace(archive)

    def extract(source, depth=0):
        if depth > 5:
            raise ValueError("Unexpected archive nesting")
        with zipfile.ZipFile(source) as z:
            for item in z.infolist():
                name = Path(item.filename).name
                if name in {f"{c}.mat" for c in CELLS}:
                    (raw / name).write_bytes(z.read(item))
                elif name.lower().endswith(".zip"):
                    extract(io.BytesIO(z.read(item)), depth + 1)
                elif "readme" in name.lower() and name.lower().endswith(".txt"):
                    (raw / ("source_" + str(depth) + "_" + name)).write_bytes(z.read(item))
    extract(archive)
    missing = [c for c in CELLS if not (raw / f"{c}.mat").exists()]
    if missing:
        raise ValueError(f"NASA archive missing selected cells: {missing}")
    manifest.write_text(json.dumps({"url": URL, "archive_sha256": sha256(archive),
        "files": {f"{c}.mat": sha256(raw / f"{c}.mat") for c in CELLS}}, indent=2))


def early_features(data, ambient):
    t = np.asarray(data.Time, dtype=float).ravel()
    arrays = [np.asarray(getattr(data, key), dtype=float).ravel() for key in
              ("Voltage_measured", "Current_measured", "Temperature_measured")]
    if len(t) < 3 or any(len(a) != len(t) for a in arrays):
        raise ValueError("Inconsistent discharge arrays")
    if not np.isfinite(t).all() or np.any(np.diff(t) < 0):
        raise ValueError("Invalid time axis")
    elapsed = t - t[0]
    # Never interpolate using samples after the 60-second prediction cutoff.
    mask = elapsed <= 60
    if mask.sum() < 3 or elapsed[mask][-1] < 40:
        raise ValueError("Insufficient first-minute measurements")
    v, i, temp = [a[mask] for a in arrays]
    if not all(np.isfinite(a).all() for a in (v, i, temp)):
        raise ValueError("Nonfinite first-minute measurement")
    return dict(zip(FEATURES, [v[0], v[-1], v.mean(), v.std(), i.mean(),
                               temp[0], temp[-1] - temp[0], float(ambient)]))


def build_table(raw):
    rows, rejected = [], []
    for cell in CELLS:
        battery = loadmat(raw / f"{cell}.mat", squeeze_me=True, struct_as_record=False)[cell]
        cycle = 0
        for record in np.atleast_1d(battery.cycle):
            if str(record.type) != "discharge":
                continue
            cycle += 1
            try:
                capacity = float(record.data.Capacity)
                if not np.isfinite(capacity) or capacity <= 0:
                    raise ValueError("Invalid capacity")
                rows.append({"cell": cell, "cycle": cycle, "capacity_ah": capacity,
                    "soh_pct": 100 * capacity / 2.0,
                    **early_features(record.data, record.ambient_temperature)})
            except (ValueError, AttributeError, TypeError) as error:
                rejected.append({"cell": cell, "cycle": cycle, "reason": str(error)})
    df = pd.DataFrame(rows).sort_values(["cell", "cycle"]).reset_index(drop=True)
    if df.empty or set(df.cell) != set(CELLS) or df.duplicated(["cell", "cycle"]).any():
        raise ValueError("Invalid cycle table")
    return df, rejected


def models():
    return {"mean": DummyRegressor(),
        "ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=10)),
        "random_forest": make_pipeline(SimpleImputer(strategy="median"),
            RandomForestRegressor(n_estimators=300, min_samples_leaf=5, random_state=42, n_jobs=1))}


def evaluate(df, reports):
    splits = []
    train_idx, test_idx = [], []
    for _, group in df.groupby("cell"):
        cut = int(len(group) * .7)
        train_idx.extend(group.index[:cut]); test_idx.extend(group.index[cut:])
    splits.append(("temporal_70_30", train_idx, test_idx))
    for cell in CELLS:
        splits.append((f"unseen_{cell}", df.index[df.cell != cell], df.index[df.cell == cell]))
    metrics, predictions = [], []
    for split, tr, te in splits:
        train, test = df.loc[tr], df.loc[te]
        for name, model in models().items():
            model.fit(train[FEATURES], train.soh_pct)
            pred = model.predict(test[FEATURES])
            metrics.append({"split": split, "model": name, "train_n": len(train), "test_n": len(test),
                "mae_percentage_points": mean_absolute_error(test.soh_pct, pred),
                "rmse_percentage_points": float(np.sqrt(mean_squared_error(test.soh_pct, pred)))})
            predictions.extend({"split": split, "model": name, "cell": row.cell,
                "cycle": row.cycle, "actual_soh_pct": row.soh_pct, "predicted_soh_pct": float(p)}
                for row, p in zip(test.itertuples(), pred))
    pd.DataFrame(metrics).to_csv(reports / "metrics.csv", index=False)
    pd.DataFrame(predictions).to_csv(reports / "predictions.csv", index=False)
    # Exploratory detector: fit early training cycles only; later aging may itself look novel.
    reference = df.loc[train_idx].groupby("cell", group_keys=False).head(30)
    detector = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
        IsolationForest(n_estimators=300, contamination=.05, random_state=42))
    detector.fit(reference[FEATURES])
    flags = df[["cell", "cycle", "soh_pct"]].copy()
    flags["novelty_score"] = -detector.decision_function(df[FEATURES])
    flags["flag"] = detector.predict(df[FEATURES]) == -1
    flags["used_for_detector_fit"] = flags.index.isin(reference.index)
    flags.to_csv(reports / "anomaly_flags.csv", index=False)
    return metrics, flags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    raw, processed, reports = ROOT / "data/raw", ROOT / "data/processed", ROOT / "reports"
    processed.mkdir(parents=True, exist_ok=True); reports.mkdir(parents=True, exist_ok=True)
    ingest(raw, args.offline)
    df, rejected = build_table(raw)
    df.to_csv(processed / "cycles.csv", index=False)
    (reports / "rejected_cycles.json").write_text(json.dumps(rejected, indent=2))
    df.groupby("cell").agg(cycles=("cycle", "count"), first_soh=("soh_pct", "first"),
        last_soh=("soh_pct", "last"), min_capacity=("capacity_ah", "min")).to_csv(reports / "summary.csv")
    df[FEATURES + ["capacity_ah", "soh_pct"]].describe().to_csv(reports / "eda_statistics.csv")
    metrics, flags = evaluate(df, reports)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for cell, group in df.groupby("cell"):
        axes[0].plot(group.cycle, group.soh_pct, label=cell)
        axes[1].scatter(group.voltage_60s, group.soh_pct, s=9, label=cell)
    axes[0].set(xlabel="Discharge cycle", ylabel="SOH (% of nominal 2 Ah)")
    axes[0].axhline(70, color="gray", linestyle="--"); axes[0].legend()
    axes[1].set(xlabel="Last voltage sampled within first 60 seconds (V)", ylabel="SOH (%)")
    fig.tight_layout(); fig.savefig(reports / "eda.png", dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4))
    for cell, group in flags.groupby("cell"):
        ax.plot(group.cycle, group.novelty_score, label=cell)
    ax.axhline(0, color="gray", linestyle="--")
    ax.set(xlabel="Discharge cycle", ylabel="Novelty score (>0 flagged)")
    ax.legend(); fig.tight_layout(); fig.savefig(reports / "novelty.png", dpi=160); plt.close(fig)
    import importlib.metadata
    (reports / "environment.json").write_text(json.dumps({"python": platform.python_version(),
        "packages": {p: importlib.metadata.version(p) for p in
        ("numpy", "pandas", "scipy", "scikit-learn", "matplotlib")}}, indent=2))
    print(f"Processed {len(df)} discharge cycles; rejected {len(rejected)}.")
    print(pd.DataFrame(metrics).to_string(index=False))


if __name__ == "__main__":
    main()
