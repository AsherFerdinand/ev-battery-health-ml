# v2.0 release checkpoint

**Branch** `feature/robust-hybrid-validation-v2.0`, based on v1.5 `2cc543b`.

- `battery_sim.py` owns synthetic models and physical conventions. Positive current discharges, SOC and SOH are fractions, and capacity is in coulombs. NASA keeps its original convention in replay.
- `soc_estimation.py` owns the shared EKF and measured-only diagnostics. `capacity_experiment.py` and `parameter_estimation.py` retain legacy policies. `validation_population.py` owns independent cohorts and capacity diagnosis. `robust_validation.py` calibrates on development and freezes configuration before final evaluation.
- `build_workbench.py` exports compressed Python results for six offline views. NASA research and model artifacts remain separate from the synthetic release.

| Gate | Result | Targeted reproduction |
|---|---|---|
| A Capacity investigation | Endpoint-phase shift explained clipping. Diverse Random Forest selected on development. | `python -m unittest discover -s tests -p test_validation_population.py` |
| B Safeguard | Causal evidence, exact fixed fallback, and stable active candidate verified. Risk criterion selected fixed Q and R₀. | `python -m unittest discover -s tests -p test_robust_validation.py` |
| C Independent validation | 48 paired identities per plant. Matched benefits from original adaptation coexist with diffusion degradation. Revised capacity MAE improves with no SOC integration claim. | `python robust_validation.py --full` |
| Historical verification | Phase 2, Phase 3 and NASA-only Phase 4 regenerated. Genuine CALCE archives unavailable. | [Artifact recipe](VERIFICATION.md) |

Known blockers and limitations are CALCE provider HTTP 403, unavailable experimental SOC ground truth, and a safeguarded policy that ties fixed EKF. Gate D passed with 60 Python passes and one CALCE skip, both export modes, six offline Chromium views, the original NASA dashboard, and reproduced independent scores. No later milestone started. [Engineering report and exact reproduction](robust-hybrid-v2.md)

# v2.1 Battery Engineering Studio checkpoint

**Branch** `feature/battery-engineering-studio-v2.1`, based on `565d657`.

- The prior uncommitted `workbench_template.html` redesign was recovered and retained.
- Overview is the landing view and synchronises scenario measurements with the existing Python payload. Navigation has eight destinations while the existing NASA and synthetic workbench functions remain in the shared page.
- Reports surface existing v2.0 cohort values; local routes expose the existing engineering reports. The independent diffusion synthetic trace has a distinct explanation and view.
- No estimator equations, model outputs, training or dependencies were changed.
- Quick and full export checks passed (21 paired trace sets and 63 circuit examples each); full export rebuilt successfully. The offline Chromium test passed all eight destinations, local report serving, theme, scenario/estimator controls, NASA replay and 390 px responsive layout. The original dashboard smoke passed, and `robust_validation.py --full` reproduced the published v2.0 results.
- Full Python suite: 60 passed, 1 optional CALCE audit skipped, 0 failed. Browser startup median 0.307 s; playback chart-update median/p95 1.5/2.5 ms. Aggregate browser PSS delta was 284.7 MiB, above the preliminary 200 MiB target. See [v2.1 report](battery-engineering-studio-v2.1.md) for the platform, methods, artifact sizes and limitations.

# v2.2 Interactive Simulation Lab checkpoint

**Branch** `feature/interactive-battery-studio-v2.2`, based on v2.1 `0b35dc8`.

- Recovered in-progress edits without resetting the branch. v2.2 adds `simulation_api.py` over the shared `battery_sim.simulate` engine and extends the standard-library launcher with a sequential `127.0.0.1`-bound simulation endpoint.
- Battery Physics contains configurable Rint, Thevenin and Dual Polarisation simulations; five deterministic profiles; 1-second samples capped at 1,800 seconds; dynamic ECM temperature, RC outputs when applicable, energy summaries, synchronized visualization and charts, two-result session baseline comparison and JSON/CSV export.
- Custom simulations are separated from the precomputed research results. The standalone research UI remains usable without the endpoint. Navigation clears inactive chart/cutaway SVG DOM without altering numerical data.
- Verification complete: full Python suite 68 passed / 1 optional CALCE skip; API suite 7/7; quick/full workbench exports preserved 21 paired trace sets and 63 circuit examples; dashboard smoke passed. Managed Chromium exercised all eight views, all ECM choices, export/comparison/playback, static fallback, no external requests, and 390 px responsive layout.
- Full-export browser page startup median 388 ms. Maximum 1,800-s dual-model simulation ran in 0.0116 s. Aggregate browser PSS delta measured 269.6 MiB, down from v2.1's 284.7 MiB but still above the preliminary 200 MiB target. See [v2.2 engineering report](battery-engineering-studio-v2.2.md) for platform, measurement limits, sizes, assumptions, and reproduction commands.

# v2.3 Interactive Battery Explorer checkpoint

**Branch** `feature/battery-explorer-educational-v2.3`, based on v2.2 `ad33b41`.

- Overview and Battery Design are merged into a seven-destination Battery Explorer. Four synthetic Thevenin presets use the Python API: normal, high load, cold ambient and explicitly configured SOH/R₀. The API's additive `soh` input defaults to 1.0 and passes through existing cell-capacity math; no ECM equations changed.
- The generic cylindrical cutaway supports six selectable layers, representative materials, pointer/keyboard controls and charge/discharge ion direction. The separate SOC/SOH illustration retains casing size and shows capacity arithmetic; a 30-second-window thermometer follows modelled temperature. Battery Physics retains Simulation Lab with selectable circuit/parameter focus. NASA is the default dataset view with generic cell illustration, test workflow and capacity/SOH histories derived only from existing discharge measurements.
- No estimator, research result or NASA measurement changed; no dependencies were added. Regression: 69 passed, 1 optional CALCE audit skipped. Simulation API: 8 passed. Workbench structural checks preserve 21 paired trace sets/63 circuit examples; NASA dashboard smoke passed. Full browser flow passes all seven destinations, four scenario runs, keyboard and reduced-motion checks, offline/API fallback, themes and 390 px layout.
- Full-export browser page navigation median 357 ms, playback render median/p95 2.5/3.5 ms. Cloud browser idle PSS delta 262.9 MiB, 6.7 MiB below v2.2's 269.6 MiB reading but still above the preliminary 200 MiB target. See [v2.3 engineering report](battery-explorer-educational-v2.3.md), including screenshots and exact reproduction commands.

# v2.4 Interactive Engineering Visualisation checkpoint

**Branch** `feature/engineering-visualization-ux-v2.4`, based on v2.3 `ab90427`.

- A single shared playback clock now drives research, NASA, Explorer, ECM and simulation chart cursors; renderers retain full scientific arrays and move display cursors during playback. Expandable chart panels improve smaller-screen inspection.
- Battery Explorer synchronizes voltage/current/SOC with an initial-SOC ghost and conceptual current-flow schematic. Battery Physics explains model levels and compares Rint, Thevenin and Dual Polarisation responses under common inputs. NASA charts explain measurements and annotate phases inferred from sampled current; ML and SOC views explain assumptions; Investigation Lab surfaces failure evidence and limitations.
- Existing estimator outputs and Phase 1–4 research are unchanged. The only Python export addition is the already simulated current profile (`current_a`) required to compare ECM responses under identical input. No dependencies added.
- Full regression, browser interactions, performance methods and screenshots: [v2.4 engineering report](engineering-visualization-ux-v2.4.md).
