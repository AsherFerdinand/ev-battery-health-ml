# Hybrid B and visual workbench v1.4–v1.5

Hybrid B adapts available capacity Q and the Thevenin series resistance R₀ referenced to 298.15 K. R₁ and C₁ retain their nominal values. The experiment uses the same EKF and diagnostic outputs as v1.3 and keeps NASA experimental evidence separate. [v1.3 baseline and launch instructions](soc-workbench.md)

## Identification and model selection

The matched voltage Jacobian is rank one at rest and locally full rank under stepped current with the OCV and thermal resistance laws specified. The 180 s and 420 s records differ in both duration and excitation. At 298.15 K, the column-normalized condition number improves from 12.78 to 9.20. In seeded stress trials with triple sensor noise and +60 mA current bias, fitted R₀ median relative error improves from 5.72% to 2.55%. Capacity error rises from 5.01% to 10.08% and RC time-constant error remains above 25%. Recoverability therefore depends on the profile, bias and assumed physics. The RC parameters remain exploratory. [Identifiability analysis and recovery verification](parameter-identifiability.md)

The supervised estimator evaluates 180 s and 420 s. At each cutoff it uses the existing eight causal measurement features and the median of −ΔV/ΔI at observed current steps, normalized using measured temperature. Fewer than two steps of magnitude 0.35 A disable the parameter update. This median is a feature, since the one-second change can include polarisation and SOC dynamics. Q bounds are 3,960–7,200 C and normalized R₀ bounds are 20–80 mΩ. Ridge, Random Forest and HistGradientBoosting reuse the v1.3 hyperparameters. Each target selects the lowest validation MAE within each window. The common window minimizes the mean of the two winning MAEs divided by their respective admissible ranges. Test labels play no role. Independent seeded R₁ and C₁ variation augments Hybrid B training and validation, while Hybrid A retains its original training matrix.

After the correction at the selected sample, Q first changes the following state transition. The new R₀ first changes the following voltage prediction and uses that sample's measured temperature. The shared temperature law is exp(0.018 × (298.15 K − T)), with temperature input limited to 260–335 K for adaptation. The two-state Joseph covariance update and fixed noise settings are retained. This is covariance conditional on the plug-in parameter estimates. It does not propagate ML parameter uncertainty or prove interval calibration.

## Paired experiment protocol

Full mode uses the unchanged 96 held-out Thevenin trajectories and their 96 diffusion counterparts from v1.3. It adds a separate matched stress cohort with independently seeded R₁ and C₁ variations for those same held-out identities. These are paired repeated configurations, so the three cohorts should be read separately. In each trajectory all five eligible estimators see identical measurements and the same initial SOC assumption. The oracle gets model references only when the plant is Thevenin. The diffusion generator defines its own series resistance but does not define Thevenin RC parameters. Voltage RMSE in all cohorts compares the one-step prediction against noise-free simulated voltage. Convergence uses the first 30 consecutive samples within two SOC percentage points of truth.

For continuity, the original 180 s pre/post metrics remain in the export. A second common comparison uses the selected Hybrid B cutoff for every estimator, with pre including the cutoff and post starting at the next sample. Error and convergence definitions otherwise match v1.3. Reference parameters and truth appear only in scoring, diagnostics and eligible oracle inputs.

## Full comparison results

The winning common window was **420 s**, using Ridge for Q and HistGradientBoosting for R₀. Validation MAE is shown in coulombs and milliohms. For scale, 720 C equals 0.20 Ah.

| Window | Ridge Q / R₀ | Random Forest Q / R₀ | HistGradientBoosting Q / R₀ |
|---|---:|---:|---:|
| 180 s | 663.9 C / 2.37 mΩ | 703.0 C / 2.40 mΩ | 680.1 C / 2.29 mΩ |
| 420 s | 630.5 C / 1.77 mΩ | 681.5 C / 1.61 mΩ | 632.7 C / 1.59 mΩ |

On the standard held-out Thevenin families, the unclipped capacity predictions ranged from 7,462 to 13,226 C compared with 4,954–6,679 C on validation. The capacity estimate clipped to 7,200 C on all trajectories in all three full cohorts and equaled the fixed prior. Its test MAE was **0.448 Ah** (22.41 SOH pp) in each cohort. The supervised capacity model failed to generalize across the held-out duty families. The matched SOC gain in this experiment therefore comes from R₀ adaptation. Normalized R₀ MAE was 1.84 mΩ on Thevenin, 1.94 mΩ with RC stress and 9.28 mΩ on diffusion, versus 9.56 mΩ for the fixed prior. A better ohmic estimate alone does not guarantee a better SOC estimate under model mismatch.

The table averages each metric over 96 trajectories per cohort. “Max” averages each run’s maximum absolute error. Pre/post comparison uses the common 420 s cutoff. SOC errors are percentage points and voltage RMSE is millivolts.

| Plant | Estimator | SOC MAE / RMSE | Max / signed bias | Pre / post MAE | Voltage RMSE |
|---|---|---:|---:|---:|---:|
| Thevenin | Coulomb Counting | 16.004 / 16.025 | 16.932 / −11.533 | 16.143 / 15.810 | 215.49 |
| Thevenin | Fixed EKF | 0.892 / 1.177 | 3.113 / −0.615 | 1.095 / 0.606 | 18.26 |
| Thevenin | Hybrid A | 0.906 / 1.181 | 3.110 / −0.633 | 1.087 / 0.651 | 17.78 |
| Thevenin | Hybrid B | 0.764 / 1.130 | 3.133 / −0.418 | 1.095 / 0.300 | 15.87 |
| Thevenin | Oracle EKF | 0.145 / 0.223 | 1.989 / −0.018 | 0.172 / 0.108 | 8.37 |
| Thevenin, RC stress | Coulomb Counting | 16.004 / 16.025 | 16.932 / −11.533 | 16.143 / 15.810 | 215.02 |
| Thevenin, RC stress | Fixed EKF | 1.014 / 1.316 | 3.229 / −0.733 | 1.237 / 0.702 | 19.76 |
| Thevenin, RC stress | Hybrid A | 1.038 / 1.328 | 3.222 / −0.752 | 1.215 / 0.791 | 19.03 |
| Thevenin, RC stress | Hybrid B | 0.870 / 1.254 | 3.240 / −0.534 | 1.237 / 0.355 | 17.52 |
| Thevenin, RC stress | Oracle EKF | 0.155 / 0.240 | 1.987 / −0.019 | 0.187 / 0.110 | 8.37 |
| Diffusion | Coulomb Counting | 16.004 / 16.025 | 16.932 / −11.533 | 16.143 / 15.810 | 270.79 |
| Diffusion | Fixed EKF | 6.949 / 7.065 | 8.194 / +6.946 | 6.667 / 7.345 | 21.71 |
| Diffusion | Hybrid A | 6.933 / 7.053 | 8.270 / +6.930 | 6.765 / 7.170 | 21.52 |
| Diffusion | Hybrid B | 7.330 / 7.478 | 8.745 / +7.327 | 6.667 / 8.261 | 18.40 |

Hybrid B’s post-cutoff SOC MAE increased versus fixed EKF in **29/96** standard Thevenin, **29/96** RC-stress and **96/96** diffusion runs. Versus Hybrid A the counts were **32/96**, **20/96** and **96/96**. The worst increases versus fixed EKF were 0.595 pp for standard Thevenin (family-4-cell-24), 0.420 pp for RC stress (family-4-cell-20) and 2.094 pp for diffusion (family-5-cell-47). In the degraded cold demonstration, post-cutoff MAE rises from 0.056 pp fixed to 0.594 pp Hybrid B. In the warm high-resistance demonstration it drops from 0.747 to 0.378 pp. Under diffusion, Hybrid B improves voltage RMSE while increasing SOC bias. The mismatch makes voltage residuals an unreliable proxy for SOC accuracy.

Coulomb Counting met the convergence criterion on 8/96 runs in each cohort, with median 53.5 s among those runs. All eligible EKFs met it on 96/96 in both matched cohorts, with median 0 s. On diffusion, each available EKF met it on 10/96 with median 41.5 s. The initial voltage correction can place the estimate inside the threshold immediately. These controlled results establish neither field reliability nor parameter identifiability for NASA measurements.

## Visual workbench

The interactive cell cutaway shows electrode layers, ion direction for charging and discharging, and changes in usable capacity and voltage sag. The physics lab retains the verified Python Rint, Thevenin and Dual Polarisation responses. The ML explorer adds fitted Ridge coefficients and a representative residual, sampled decision paths and the full forest prediction, and the first stages of a fitted boosted prediction. The EKF view substitutes measured and predicted values into the active equations and switches between Hybrid A and B diagnostics. The Hybrid laboratory shows the measurement-to-estimate sequence, audit of fixed and estimated parameters, a shared score cutoff and paired voltage and SOC traces. Every view runs offline with procedural SVG and no additional frontend or Python runtime dependency.

## Reproduce

Run from the repository root after installing the existing lockfile. Windows PowerShell uses `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`. The app uses a loopback server and works offline after initial setup.

```sh
.venv/bin/python build_workbench.py
.venv/bin/python parameter_identifiability.py
.venv/bin/python build_workbench.py --full --no-open --refresh
.venv/bin/python -m unittest discover -s tests -v
node tests/workbench_smoke.cjs
node tests/workbench_smoke.cjs reports/workbench-full.html
node tests/dashboard_smoke.cjs
```

For Chromium verification, launch with `--port 8765`, then run `node tests/workbench_browser.cjs`. Use the existing optional Playwright setup described in the v1.3 report. The smoke test restricts access to loopback. [Installation and optional browser check](soc-workbench.md)

## Verification and resources

The completed suite reported **43 passed and 12 skipped**. The skips require existing Phase 2–4 artifacts. The original NASA dashboard passed 672 control combinations plus its replay and history checks. Both Node workbench modes passed checks on 18 paired traces and 63 circuit examples. Chromium exercised all six views with external requests blocked and compared the displayed parameter update with the Python export. Across 672 prior estimator trajectories, all v1.3 scientific metrics reproduced exactly. The quick build reproduced all scientific summary fields, excluding elapsed timing. The four v1.1 default archives reproduced byte for byte.

Measurements used Linux x86-64, Python 3.12.14, Chromium 156 and an Intel Xeon Platinum 8573C with a four-CPU cgroup quota. Windows performance was unmeasured.

| Item | Observation |
|---|---|
| Tracked repository | 2.20 MB across 37 Python, HTML, CJS and PowerShell source files including tests. The pre-commit Git database occupied 2.56 MB. |
| Dependencies | None added. The existing full research environment occupied 480.7 MB. |
| Generated datasets and summaries | The quick and full self-contained HTML exports were 4.96 MB and 4.95 MB. The separate metric summaries were 176 kB and 1.16 MB. Raw inputs, generated exports and environments are ignored. |
| Cached launch | The cache-hit CLI took 0.071 s median across five subprocesses. Chromium reached the first chart in 0.371 s median, 0.558 s on the first navigation. |
| Interaction and idle | Fifty playback input handlers took 1.7 ms median and 2.6 ms p95, excluding paint. Chromium PSS was 375.7 MiB loaded versus 212.5 MiB blank, about 163 MiB attributable. The browser used 0.06 CPU-seconds over 2.5 seconds idle. |
| Rebuild | Quick took 10.7 s wall and 11.5 CPU-seconds. The final full run took 35.5 s wall, 36.4 CPU-seconds and 243 MiB peak child RSS. |
| Estimation | Across cohort medians, Hybrid B filtered each 721-sample trajectory in 19.0–24.1 ms plus 0.95–1.20 ms for feature extraction and inference. Fixed EKF took 19.1–24.5 ms, Hybrid A 19.0–24.5 ms and Coulomb Counting 5.9–7.3 ms. |

Disk footprint uses tracked-file byte totals and GNU `du -sB1`. `perf_counter` measures elapsed time and Linux `resource.getrusage` supplies child CPU time and peak RSS. Browser validation times chart readiness and synchronous input handlers, and reads aggregate PSS from per-process `smaps_rollup`. Results vary with cloud contention.
