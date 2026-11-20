# SOC workbench v1.2–v1.3

The workbench compares Coulomb Counting, a fixed Thevenin EKF, an eligible oracle EKF and Hybrid A on identical synthetic sensor traces. The offline application reads precomputed Python outputs. Its NASA explorer presents separately labelled experimental telemetry and links to the original dashboard.

## Install and launch

Use Python 3.12 from the repository root. After installation, launch with one command and stop the loopback server with Ctrl+C. Browser requests stay local. A current browser with gzip stream support is required.

| Action | Linux | Windows PowerShell |
|---|---|---|
| Create environment | `python3.12 -m venv .venv` | `py -3.12 -m venv .venv` |
| Install pinned packages | `.venv/bin/python -m pip install -r requirements-lock.txt` | `.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt` |
| Launch quick workbench | `.venv/bin/python build_workbench.py` | `.\.venv\Scripts\python.exe build_workbench.py` |

Append `--full` for the larger research population, `--no-open` to build without starting the server, or `--refresh` to regenerate an existing export. The app prints its URL if automatic browser opening is unavailable. `--port 8765` selects a fixed loopback port. Generated pages and summaries are ignored under `reports/`. Normal launches reuse an up-to-date export. Synthetic generation needs no network after installation. If the browser permits file access, the generated standalone page also opens directly.

For NASA playback, run the original `pipeline.py` to acquire or validate the local files. Rebuild the workbench to embed a display-only sample of up to 40 points per discharge cycle. The workbench preserves recorded NASA current polarity. NASA capacity comes from the recorded discharge and is divided by 2 Ah for derived SOH. The NASA recordings provide no independent SOC truth and do not train or test the synthetic estimators. [Original research reproduction guide](VERIFICATION.md)

## Numerical design

`battery_sim.py` supplies the existing open-circuit voltage and RC response functions. `soc_estimation.py` implements the filter and defines a measured-only input record. `capacity_experiment.py` generates labelled scenarios, extracts causal features, fits models and compares the estimators. `build_workbench.py` exports gzip-compressed playback and an independent compact metric summary. The HTML uses event-driven SVG and procedural cutaway geometry. Playback stops when the user changes views or hides the tab. The browser interpolates no estimator states and trains no models.

The EKF uses state **x = [SOC, polarisation voltage]ᵀ**, with positive current for discharge. For held current I, capacity Q in coulombs and step Δt, the predicted SOC decreases by IΔt/Q. The RC branch uses the exact held-current transition with decay a = exp(−Δt/(R₁C₁)). The transition Jacobian is diag(1, a). The observation is OCV(SOC) − v₁ − I·R₀, with Jacobian [OCV′(SOC), −1]. Interval k−1 drives the transition into k. Current and voltage at k drive the observation update at k. The EKF computes the innovation and gain from the prior covariance, then uses the Joseph covariance update and symmetrisation. SOC is projected into [0, 1]. The resulting covariance is an internal linearised diagnostic near that bound.

The fixed and hybrid filters start with 2 Ah and fixed R₀ = 35 mΩ, R₁ = 18 mΩ, C₁ = 650 F. Initial covariance standard deviations are 0.12 SOC fraction and 20 mV, with independent process variances of 8×10⁻⁹ fraction²/s and 3×10⁻⁷ V²/s and a 12 mV observation standard deviation. Coulomb Counting uses the same initial SOC and capacity, ignores voltage, and uses a nominal Thevenin voltage reconstruction for voltage scoring. The Thevenin oracle receives the generating capacity, R₀ trace, R₁ and C₁ with the same noisy current and voltage and initial SOC guess. Diffusion has no physically defined Thevenin RC parameters, so the oracle is unavailable there.

Standalone checks passed before ML integration. They cover analytical irregular-step counting, numerical differentiation of both Jacobians, exact matched-state tracking, recovery from a wrong initial SOC, covariance symmetry and positive semidefiniteness, SOC bounds and forward-only parameter changes.

## Capacity experiment and comparison criteria

The simulation root seed is 1307. Six disjoint duty-schedule families vary pulse durations and load levels. Train uses families 0–2, validation family 3 and test families 4–5. Stable cell identities sample SOH uniformly in [0.58, 1.0], initial SOC in [0.58, 0.90], ambient temperature in [280, 315] K, resistance scale in [0.8, 1.7], noise scale in [0.5, 2.0] and current bias in [−0.065, 0.065] A. Each sensor has its own deterministic noise stream. A full trajectory and its short counterpart yield identical measurements through the cutoff. The quick run uses 10 cells per family and the full run 48. The withheld cohorts are evaluated as paired Thevenin and diffusion realizations of the same test identities. Named playback scenarios are separate illustrative configurations outside model selection.

The eight input features summarize voltage, current and temperature through the sample at 180 s. Inputs exclude cell identity, plant parameters, reference and future values. The capacity label is the generating capacity divided by nominal capacity. Ridge uses training-only standardisation and α = 3. Random Forest uses 64 trees and at least 3 samples per leaf. HistGradientBoosting uses 70 iterations, at most 9 leaves and at least 8 samples per leaf. Validation MAE in SOH fraction selects the model. Test errors are reported for all three without changing the selection.

Hybrid A clips SOH to [0.55, 1.00], converts it to capacity, and updates once after the voltage correction at 180 s. It first uses the new capacity to propagate from 180 to 181 s and never revises earlier predictions. Fixed and hybrid SOC estimates agree exactly through 180 s.

The comparison uses per-trajectory SOC MAE, RMSE, maximum absolute error and signed bias in percentage points (pp). Terminal voltage RMSE uses one-step predicted voltage against noise-free synthetic terminal voltage. Convergence is the start of the first sequence of 30 consecutive samples within ±2 pp of reference SOC. Pre-update scoring includes t = 180 s. Post-update scoring starts at t = 181 s. Capacity errors compare final assumed or estimated capacity with the known reference. The comparison reports cases where Hybrid A increases post-update MAE.

## Full research results

Ridge was selected with 8.85 pp validation MAE. Random Forest and HistGradientBoosting gave 9.72 and 9.19 pp respectively.

| Capacity model | Thevenin test MAE (pp) | Diffusion test MAE (pp) |
|---|---:|---:|
| Ridge | 8.32 | 9.27 |
| Random Forest | 9.90 | 10.30 |
| HistGradientBoosting | 10.02 | 10.36 |

The table reports averages across 96 trajectories per plant. “Max” is the mean of the per-trajectory maximum absolute errors. Convergence gives the number of converged runs and the median starting time among those runs.

| Plant | Estimator | SOC MAE / RMSE (pp) | Max / signed bias (pp) | Pre / post MAE (pp) | Voltage RMSE (mV) | Convergence |
|---|---|---:|---:|---:|---:|---|
| Thevenin | Coulomb Counting | 16.004 / 16.025 | 16.932 / −11.533 | 16.206 / 15.936 | 215.49 | 8/96, 53.5 s |
| Thevenin | Fixed EKF | 0.892 / 1.177 | 3.113 / −0.615 | 1.797 / 0.588 | 18.26 | 96/96, 0 s |
| Thevenin | Hybrid A | 0.906 / 1.181 | 3.110 / −0.633 | 1.797 / 0.607 | 17.78 | 96/96, 0 s |
| Thevenin | Oracle EKF | 0.145 / 0.223 | 1.989 / −0.018 | 0.234 / 0.116 | 8.37 | 96/96, 0 s |
| Diffusion | Coulomb Counting | 16.004 / 16.025 | 16.932 / −11.533 | 16.206 / 15.936 | 270.79 | 8/96, 53.5 s |
| Diffusion | Fixed EKF | 6.949 / 7.065 | 8.194 / +6.946 | 5.620 / 7.394 | 21.71 | 10/96, 41.5 s |
| Diffusion | Hybrid A | 6.933 / 7.053 | 8.270 / +6.930 | 5.620 / 7.373 | 21.52 | 10/96, 41.5 s |

The fixed 2 Ah assumption had a mean absolute capacity error of 0.448 Ah in both cohorts. Hybrid A reduced it to 0.166 Ah on Thevenin and 0.185 Ah on diffusion. Despite this, post-update SOC MAE increased in **66/96 Thevenin cases** and **1/96 diffusion cases**. In the fresh Thevenin demonstration it rises from about 0.030 to 0.146 pp. With biased current in the noisy demonstration it falls from 0.347 to 0.278 pp. Capacity changes the input-driven SOC prediction, while the voltage correction still uses fixed impedances and the nominal OCV relation. The diffusion runs retain about +6.93 pp Hybrid A bias. Differences in the diffusion OCV curve and dynamics both contribute to this structurally mismatched case. These findings describe the selected simulations.

In the illustrative identifiability pair, a 32 pp capacity difference with small changes in initial SOC and resistance produced 7.05 mV RMS voltage separation in the first 30 s and 11.55 mV over 180 s, versus a 3 mV nominal single-sensor noise standard deviation. This shows that early responses can be close across very different capacities. It does not establish statistical indistinguishability over the full window. The held-out 8–10 pp capacity errors and fresh-cell regressions indicate limited reliability with these features and loads. [Simulation assumptions](synthetic-battery.md)

## Verification and performance

Linux cloud measurements used Python 3.12.14, Node 24.22.1 and Chromium 156, with an Intel Xeon Platinum 8573C, five visible logical CPUs and a four-CPU cgroup quota. Windows PowerShell commands are provided for reproduction. Windows performance was unmeasured.

| Item | Linux cloud observation |
|---|---|
| Repository | 2.14 MB of tracked files and 33 Python, HTML, CJS and PowerShell source files, including tests. The local Git database used 2.36 MB before this commit. |
| Dependencies | No application dependencies added. The full existing research environment occupied 480.7 MB on disk. Chromium and preinstalled Playwright 1.57 were used only for the optional browser check. |
| Generated outputs | About 2.71 MB per HTML playback export, including compressed synthetic traces, 63 precomputed circuit cases and the NASA display subset. Summary JSON was 104 kB quick and 459 kB full. No generated outputs are tracked. |
| Cached startup | The CLI's cached build-only check took 0.14 s median across five timed child processes. Browser navigation through the rendered first chart took 0.55 s median across five navigations, with 1.02 s on the first. First-time generation is a separate step. |
| Interaction and idle | Fifty SOC playback changes took 0.8 ms median and 4.5 ms p95 for the synchronous DOM handler, excluding browser paint. Aggregate Chromium PSS rose from 211.6 MiB on a blank page to 397.6 MiB with the workbench, about 186 MiB attributable to the loaded app in that run. Browser processes used 0.09 CPU-seconds over 2.5 seconds idle. |
| Experiment rebuild | A sequential quick build took 6.9 s wall, 7.7 CPU-seconds and 222 MiB peak child RSS. The full build took 16.8 s wall, 17.6 CPU-seconds and 223 MiB peak child RSS. This includes simulation, model fit and export. |
| Full-run estimator cost | Median wall time per 721-sample trajectory was 5.9–6.1 ms for Coulomb Counting and 19.4–20.1 ms for the EKFs. Filter timing excludes signal simulation and the shared capacity feature/prediction step. |

Disk footprint uses tracked-file byte totals and GNU `du -sB1`. Rebuild wall time is measured around the complete child command and CPU and peak RSS use Linux `resource.getrusage`. The optional browser check measures navigation and interaction wall time and obtains per-process PSS from Linux `smaps_rollup`. Measurements vary with cloud contention.

Run the following from the repo root on Linux. On Windows use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python build_workbench.py --no-open --refresh
node tests/workbench_smoke.cjs
.venv/bin/python build_workbench.py --no-open --full --refresh
node tests/workbench_smoke.cjs reports/workbench-full.html
node tests/dashboard_smoke.cjs
```

The optional real-browser check uses an existing Playwright installation. Launch the app with `--port 8765`, then run `node tests/workbench_browser.cjs`. Set `PLAYWRIGHT_MODULE` or `CHROMIUM_PATH` if the test tools are installed in custom locations. It blocks external browser requests and exercises all six views, including play, pause, reset, step, the oracle eligibility display, model examples and NASA cycle selection when local data is present.

The full Python suite had **35 passing and 12 skipped tests**. All new estimator and capacity tests passed. The skipped checks depend on Phase 2–4 research artifacts. The NASA offline pipeline processed 636 cycles, the common window cohort retained all 636, and the original dashboard passed 672 control combinations and its replay and history checks. The Node workbench check validated 15 exported diagnostics sets per mode, including innovations, SOC error and the capacity change boundary. No Phase 1–4 source, curated results or original dashboard files were modified.
