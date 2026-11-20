# Hybrid battery state estimation workbench roadmap

The repository runs battery experiments as Python entry points. The NASA pipeline ingests the public archive, the window and Phase 2–4 scripts produce research artifacts, and the dashboard builder embeds selected results in a standalone HTML/JavaScript page. The workbench builds on this structure. The NASA experiment scripts, model definitions, curated results and dashboard retain their current entry points.

## v1.1 synthetic foundation

`battery_sim.py` owns the numerical circuit and diffusion simulation. `synthetic_battery.py` owns profiles, seeded sensor noise, compressed export and optional static rendering. Each scenario persists one archive per model, with input, labels and provenance together. Presentation code reads the outputs of the simulator. It does not recompute the scientific model. The verification report records assumptions, numerical checks and the performance baseline. [Synthetic modelling report](synthetic-battery.md)

## Estimator experiments after v1.1 review

1. Establish a common input and result contract from the v1.1 measured channels, with explicit uncertainty and rejected-sample diagnostics. Implement Coulomb Counting and a fixed-parameter EKF using the same current convention, capacity units and ECM equations. Verify innovation and covariance behaviour, SOC observability, time-discretisation stability and convergence from perturbed initial SOC.
2. Implement architecture A with an ML capacity/SOH model feeding an SOC EKF. Keep model fitting offline. Use grouped holdouts by cell or independent simulation scenario. Enforce causal feature windows and reserve truth SOC for evaluation.
3. Implement architecture B with ML-assisted age- and temperature-dependent capacity, R0, R1 and C1 feeding the same EKF. Constrain estimates to physically meaningful ranges. Only train against identifiable labels. On experimental data, require excitation, suitable time and temperature coverage, and independent validation before attempting parameter identification. Do not presume NASA has the measurements needed for that study.
4. Compare both architectures with Coulomb Counting, fixed-parameter EKF and a synthetic oracle-parameter EKF. Report the oracle where the generating ECM defines the required parameters. For mismatched plants, use a separately documented projection if justified, or mark the oracle unavailable. Evaluate matched-model diagnostics separately from withheld diffusion and future independently generated PyBaMM trajectories. Vary ambient temperature, initial SOC error, SOH, load, noise, bias and parameter mismatch. Report comparable splits, SOC MAE and bias, worst-case errors, residuals, computational cost and uncertainty diagnostics. Retain regressions and adverse cases in the same comparison.

## Educational interface after estimator verification

| Area | User experience |
|---|---|
| Battery fundamentals | A labelled procedural cutaway explains current collectors, electrodes, separator and ion flow. |
| Dataset explorer | Distinct NASA experimental and synthetic views explain provenance, units, sampling and which signals are available as truth. |
| Battery physics laboratory | Inputs for load, temperature and circuit parameters reveal voltage contributions, RC time constants and bulk versus surface state. |
| ML explorer | Ridge coefficients, Random Forest aggregation and HistGradientBoosting updates explain model assumptions, feature windows and evaluation splits. |
| EKF explorer | A stepped trace exposes prediction, measurement residual, gain, correction and covariance. |
| Hybrid laboratory | Controlled scenarios compare Coulomb Counting, fixed EKF, both hybrids and eligible oracle runs on identical inputs. |
| Results and reports | Reproduction settings, errors, limitations and per-scenario evidence stay inspectable and exportable. |

Prototype these views with the existing offline HTML/JavaScript patterns and an export adapter for selected Python experiment outputs. A lightweight chart renderer is sufficient for the first views. Consider TypeScript and React if shared state and component reuse justify a toolchain. Three.js is a candidate for the cutaway if custom camera controls, picking and accessible inspection justify its asset cost. Keep the illustrative geometry procedural and load the renderer on demand. A Python service is warranted only if interactive simulation cannot use precomputed scenarios or a thin portable bridge. Keep one numerical implementation per model, with explicit parity tests before introducing another runtime.

Use event-driven rendering. Suspend animations on hidden tabs, release old datasets and meshes, and downsample for display only. When solver outputs become expensive, cache bounded scenario results by complete configuration. Retrain models only when training inputs or settings change. Benchmark representative cold and warm launches, idle memory and user interactions after an interface exists. Target a core checkout below 10 MB, frontend assets below 5 MB, startup below 3 s, lightweight interaction below 100 ms and attributable idle memory below 200 MB. Record the actual platform and measurement method.
