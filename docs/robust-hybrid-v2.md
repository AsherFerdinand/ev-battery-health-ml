# Robust hybrid battery estimation v2.0

## Architecture and evidence

The existing Thevenin and diffusion plants generate paired synthetic signals. The shared two-state EKF combines current integration, RC polarisation and nonlinear OCV with voltage correction. Coulomb Counting, fixed EKF, Hybrid A at 180 s, the original Hybrid B at 420 s and the matched oracle retain their v1.5 definitions. The v2 investigator adds a measured-only adaptation audit, development policy selection and a separate final comparison. R₁ and C₁ remain fixed in both hybrids. The oracle uses generating parameters only in matched Thevenin scenarios. [v1.5 baseline](hybrid-b-workbench.md) · [Identifiability study](parameter-identifiability.md)

## Capacity diagnosis

At 420 s, the old training and validation families had entered a positive-current segment while old holdouts were still at rest. The old matched holdout median ΔV was −0.029 V versus −0.134 V in training. All 96 held-out ΔV values were outside the training range. The frozen Ridge attributed 1.419 Ah of mean upward raw shift to this feature. Every old holdout capacity prediction clipped at 2 Ah. The equal fixed and clipped MAEs of 0.448 Ah explain why v1.5 matched gains came from R₀.

Random Forest trained with diverse excitation and selected on development data at 420 s reduced old-cohort error to 0.210–0.215 Ah. On the independent final cohorts it achieved 0.251 Ah on Thevenin and 0.250 Ah on diffusion, including the 2 Ah fallback where observations were too weak. The original model and fixed prior both gave 0.400 Ah. The original clipped on all 36 eligible trajectories per plant and the revised candidate stayed in range on all 36. Each plant also had 12 cases with no eligible update. The revised candidate remains a capacity prediction experiment. Its MAE does not establish an SOC benefit from feeding it to an EKF. [Feature distributions, perturbations and capacity study](capacity-generalisation.md)

## Safeguard selection and independent test

The decision uses measurements and fixed-filter diagnostics through 420 s only. It counts current changes of at least 0.35 A, logs maximum standardized feature distance from the old training mean, and audits the raw and physically bounded Q and reference-temperature R₀. The innovation metric is the RMS of the pre-update residual divided by its EKF standard deviation over 30–420 s. The first 30 s are excluded to reduce sensitivity to initial-state correction. Innovation is a consistency signal under assumed measurement and process covariance. It does not identify model mismatch or measure SOC error.

Candidate policies retained nominal capacity. An update required two current steps and a raw R₀ prediction within [20, 80] mΩ. Candidates compared 50% or 100% weight on the predicted R₀, innovation RMS limits 0.65, 1 and 1.5, or no limit. A fixed fallback competed directly. The objective on the separate development cohort was mean post-cutoff ΔMAE versus fixed plus an additional copy of its positive part. Equal numbers of Thevenin and diffusion cases were scored. The best active option, half weight and a 0.65 innovation limit, scored +0.0184 pp versus 0 for fixed. The fixed fallback won before the final cohort was scored. Feature distance and capacity saturation are audit signals and do not override that policy. Covariance and the fixed and Hybrid A estimator traces retain their existing update equations.

The new development seed is 8429 and the final seed is 9629. Development profiles are pulse bursts, staircase loads, short reversals and weak observations. Final profiles are charge-first, long load-release, delayed transients and regenerative bursts. Identity, seed, profile family and per-sensor random streams are reproducible. The full final cohort is 12 identities per profile, each evaluated on both plants. SOC, SOH, ambient temperature, current offset, channel noise, resistances and capacitance vary. The final inputs are created only after model and policy selection. The two plants reuse the same underlying identity and noise streams, so their results are paired. Four duty families give limited evidence for population uncertainty. The release reports family-level ranges rather than treating individual trajectory samples as independent. Full provenance is in the generated JSON.

## Final paired results

Each plant has 48 cases. SOC errors are in percentage points (pp). Maximum error is averaged across per-run maxima. Post is the common interval after 420 s. Voltage RMSE is in mV against the noise-free synthetic terminal voltage.

| Plant | Method | MAE / RMSE | Signed bias / Max | Post MAE | Voltage RMSE |
|---|---|---:|---:|---:|---:|
| Thevenin | Coulomb Counting | 11.009 / 11.018 | −3.353 / 11.552 | 10.979 | 152.28 |
| Thevenin | Fixed EKF | 0.708 / 0.861 | −0.358 / 2.121 | 0.478 | 14.54 |
| Thevenin | Hybrid A | 0.736 / 0.890 | −0.410 / 2.160 | 0.514 | 14.41 |
| Thevenin | Original Hybrid B | 0.663 / 0.838 | −0.284 / 2.121 | 0.371 | 14.05 |
| Thevenin | Safeguarded Hybrid B | 0.708 / 0.861 | −0.358 / 2.121 | 0.478 | 14.54 |
| Thevenin | Oracle EKF | 0.318 / 0.342 | −0.047 / 1.330 | 0.264 | 6.21 |
| Diffusion | Coulomb Counting | 11.009 / 11.018 | −3.353 / 11.552 | 10.979 | 187.02 |
| Diffusion | Fixed EKF | 7.527 / 7.589 | +7.525 / 9.479 | 7.582 | 17.72 |
| Diffusion | Hybrid A | 7.471 / 7.537 | +7.469 / 9.479 | 7.521 | 17.77 |
| Diffusion | Original Hybrid B | 7.639 / 7.707 | +7.638 / 9.518 | 7.853 | 17.07 |
| Diffusion | Safeguarded Hybrid B | 7.527 / 7.589 | +7.525 / 9.479 | 7.582 | 17.72 |

Original Hybrid B harmed post-cutoff SOC by more than 0.02 pp on 6/48 Thevenin and 36/48 diffusion cases. The safeguard rejected every update, so it matches fixed EKF on both plants. Using the original update as the retrospective counterfactual, it accepted zero harmful updates and rejected 27 beneficial matched updates and zero beneficial diffusion updates. The guarded family-level ΔMAE range is [0, 0] in each plant. This shows the cost of rejecting every update. It provides no evidence that the guard can selectively identify harmful adaptation or that it outperforms fixed EKF. The lower diffusion voltage RMSE with original Hybrid B coincided with worse SOC.

Coulomb Counting converged in 3/48 per plant, using the first 30 consecutive samples within ±2 pp. All eligible EKFs converged in 48/48 matched and 1/48 diffusion cases. Applied reference-temperature R₀ MAE was 13.87 mΩ for fixed, Hybrid A and the safeguard, 7.62 mΩ for original Hybrid B on Thevenin and 10.97 mΩ on diffusion. Applied capacity MAE was 0.400 Ah for the same fixed-capacity methods and original Hybrid B. Hybrid A gave 0.370 Ah on Thevenin and 0.382 Ah on diffusion. The Thevenin oracle had zero parameter error by construction.

## NASA measurement compatibility and historical artifacts

The hash-verified local NASA archive contains 636 discharges from B0005, B0006, B0007 and B0018, plus charge and impedance records. Discharge telemetry includes terminal and load voltage (V), terminal and load current (A), elapsed time (s), cell temperature (°C), ambient metadata (°C) and discharge capacity (Ah). Typical loaded terminal current is about −2 A in the archive. To use it with the synthetic EKF sign convention, negate the recorded terminal current and convert cell temperature to kelvin. The workbench replay preserves the original recorded sign. Native sampling is irregular, with median 9.375 s in B0005–B0007 and 11.562 s in B0018. The observed interval range across the four cells is about 9.27–20.50 s. Near-zero-current records and separate charge records are present. Their presence does not establish a validated equilibrium OCV curve or an independently known initial SOC.

Measured voltage permits replay and a residual comparison for a separately calibrated electrical model. Its cadence and load protocol limit immediate-step and RC identification relative to the one-second synthetic study. Capacity is a measured discharge outcome and supports capacity-derived SOH; it is neither an independent SOC trajectory nor a prospective estimator input. The available measurements do not independently establish OCV–SOC calibration, initial SOC, internal temperature or ground-truth SOC. Reconstructing SOC with assumed initial charge and Coulomb Counting would produce a derived trajectory with accumulated uncertainty. No experimental SOC accuracy or calibrated voltage-residual performance is reported.

The local research outputs were regenerated for Phases 2 and 3 with the existing scripts, followed by the NASA-only Phase 4 freeze and status report. The CALCE provider page and both documented archive URLs returned HTTP 403. No CS2_35 or CS2_36 archive was local. The single remaining skip is `test_downloaded_calce_thermal_schema_gate`, which requires both genuine archives, their inventories and `reports/phase4/calce_raw_audit.json`. The current run did not re-audit those files or perform external transfer inference. Prior curated CALCE schema evidence remains unchanged. [Historical verification steps](VERIFICATION.md)

## Reproduce offline

Use Python 3.12 and the existing lockfile. On Linux create the environment with `python3.12 -m venv .venv`; in PowerShell use `py -3.12 -m venv .venv`. The commands below use the Linux interpreter path. In PowerShell substitute `.\.venv\Scripts\python.exe`.

```sh
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python pipeline.py
.venv/bin/python window_experiment.py
.venv/bin/python build_dashboard.py
.venv/bin/python phase2.py
.venv/bin/python phase3.py
.venv/bin/python phase4_freeze.py
.venv/bin/python phase4_report.py
.venv/bin/python validation_population.py
.venv/bin/python robust_validation.py --full
.venv/bin/python build_workbench.py
.venv/bin/python build_workbench.py --full --no-open --refresh
.venv/bin/python -m unittest discover -s tests -v
node tests/dashboard_smoke.cjs
node tests/workbench_smoke.cjs
node tests/workbench_smoke.cjs reports/workbench-full.html
```

The NASA ingestion command acquires the provider archive when needed and checks the local manifest on subsequent runs. Use `pipeline.py --offline` once cached. Use `phase4_inspect.py` and `phase4_calce_audit.py` as documented when the genuine CALCE archives are available. To verify the browser, run the workbench with `--port 8765` and use the optional Playwright setup for `REQUIRE_ROBUST=1 node tests/workbench_browser.cjs`. The application runs in a current browser with no external connections after installation.

The six existing views remain available. The Hybrid lab adds decision-time diagnostics, original and guarded playback, rejected-update reasons, clipping and revised capacity comparisons, and independently labelled aggregate results. All trace and metric values come from the Python export. No production reliability, field SOC accuracy or robustness under uncontrolled operating conditions has been established.

## Verification and Linux cloud performance

The full Python run discovered 61 tests, with **60 passed, zero failed and one CALCE skip**. Both workbench exports passed 21 trace sets and 63 circuit examples. The original NASA dashboard passed 672 control combinations and its replay/history tests. The original Phase 3 strict 5 pp gate still exits 1 for its previously documented B0006 failure, independently of passing Python tests. The full v2 build reproduced final scientific scores from the standalone run, and the recorded v1.5 results reproduced exactly for 1,344 estimator trajectories, excluding elapsed timings.

| Item | Linux cloud measurement |
|---|---|
| Tracked source and dependencies | 2.27 MB tracked and 41 Python, HTML, CJS and PowerShell source files. No new dependencies. The existing environment occupied 480.7 MB. |
| Generated artifacts | Quick and full HTML are about 5.74 MB each. The full JSON report is 1.70 MB. The HTML grew from about 4.95 MB in v1.5 because it adds independent playback and decision tables. It omits duplicate guarded traces on fixed fallback. |
| Startup | Cached CLI median 0.083 s over five launches. Chromium median 0.36–0.46 s across offline runs to first chart. |
| Interaction and browser idle | Safeguard playback handler p95 2.8 ms, excluding paint. Attributable idle PSS varied between about 172 and 206 MiB versus a blank Chromium page. |
| Build | Quick 24.5 s wall and 25.3 CPU-seconds. Full 52.4 s wall and 53.3 CPU-seconds, with about 255 MiB peak child RSS. Additional offline fitting, calibration and independent cases account for the build growth. |
| Simulation and estimation | Median generation 2.95 ms on Thevenin and 10.66 ms on diffusion per 721 samples. Fixed EKF took 19.9–20.2 ms, original Hybrid B 20.0–20.4 ms and safeguarded Hybrid B 20.8–21.1 ms, including fixed filtering and the decision audit. Original Hybrid B timing covers filtering only. |

Measurements used Python 3.12.14 and Chromium 156 on the Linux cloud Xeon with a four-CPU quota. Wall and CPU times used `perf_counter` and `resource.getrusage`. Browser results use navigation-to-chart, synchronous interaction timing and aggregate PSS from Linux `smaps_rollup`. Windows commands are supplied and Windows performance was unmeasured.
