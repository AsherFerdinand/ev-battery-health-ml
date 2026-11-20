# v1.4–v1.5 progress

**Branch** `feature/hybrid-b-visual-workbench-v1.5`, based on v1.3 `c33b019`.

- `battery_sim.py` owns Thevenin/diffusion simulation, OCV and RC equations. Positive current discharges. SOC and SOH are fractions, capacity is in coulombs, resistance in ohms, temperature in kelvin.
- `soc_estimation.py` owns the shared EKF, measured-only input and diagnostic traces. `capacity_experiment.py` owns causal feature extraction, identity/family splits and paired scores. `build_workbench.py` exports gzip-compressed Python traces into the offline HTML template. NASA remains a separate data path.
- Preserved v1.3 reference is [the prior report](soc-workbench.md). The full matched post-update SOC MAE was 0.588 pp fixed and 0.607 pp Hybrid A. Diffusion gave 7.394 and 7.373 pp respectively. The 180 s Hybrid A cutoff and prior population are preserved.

| Task and owner | Input → result | Gate |
|---|---|---|
| 1 Physics | Simulator and duty profiles → sensitivity, recovery and supported subset | `python -m unittest discover -s tests -p test_parameter_identifiability.py` |
| 2 Lead | Verified subset → measured-only, bounded ML with grouped validation | Targeted parameter-estimator tests |
| 3 Lead | ML contract → forward-only update in shared EKF | `python -m unittest discover -s tests -p test_soc_estimation.py` |
| 4 Lead | Verified adaptation → paired baseline and parameter-shift comparisons | Full workbench build and export tests |
| 5–7 Visual | Independent UI first, integrated Python results after 4 → six navigable sections and Hybrid B playback | `node tests/workbench_browser.cjs` |
| Delivery Lead | Verified integration → benchmarks, docs, branch push | Full suite and both dashboard/workbench smoke suites |

The target branch includes all v1.3 work. No external blocker. Capacity model saturation and diffusion SOC regressions remain scientific follow-up items.

Checkpoint A passed. Matched analytical sensitivities agree with finite differences. Noiseless recovery, seeded noise/bias and the rest-rank check support bounded Q and temperature-normalized R₀ with the RC branch fixed. Parameter feature causality, excitation guard and grouped model selection are covered by `test_parameter_estimation.py`.

Checkpoint B targeted checks passed. The shared EKF applies Q and R₀ after the cutoff, preserves earlier outputs and maintains valid covariance. Paired integration confirms existing estimator traces are unchanged and diffusion has no oracle. The full comparison preserved 672 original estimator trajectories and scored 288 paired cases across the three current cohorts.


Checkpoint C passed. All six Chromium views worked with external requests blocked. Quick and full exports passed the paired numerical smoke test. UI playback uses compressed, full-precision Python diagnostics.

Checkpoint D passed. The final suite had 43 passed and 12 artifact-dependent skips. The NASA dashboard passed 672 combinations. v1.1 pulse archives were byte-identical and repeated quick builds preserved scientific summaries. Linux performance and caveats are in the [engineering report](hybrid-b-workbench.md). No later milestone started.

Reproduce from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python build_workbench.py --no-open --refresh
.venv/bin/python build_workbench.py --full --no-open --refresh
node tests/workbench_smoke.cjs
node tests/workbench_smoke.cjs reports/workbench-full.html
node tests/dashboard_smoke.cjs
```

For the browser check, serve with `.venv/bin/python build_workbench.py --port 8765` and run `REQUIRE_HYBRID_B=1 node tests/workbench_browser.cjs` using the existing Playwright installation.
