# Hybrid battery state estimation workbench roadmap

The repository runs battery experiments as Python entry points. The NASA pipeline ingests the public archive, the window and Phase 2–4 scripts produce research artifacts, and the dashboard builder embeds selected results in a standalone HTML/JavaScript page. The workbench builds on this structure. The NASA experiment scripts, model definitions, curated results and dashboard retain their current entry points.

## v1.1 synthetic foundation

`battery_sim.py` owns the numerical circuit and diffusion simulation. `synthetic_battery.py` owns profiles, seeded sensor noise, compressed export and optional static rendering. Each scenario persists one archive per model, with input, labels and provenance together. Presentation code reads the outputs of the simulator. It does not recompute the scientific model. The verification report records assumptions, numerical checks and the performance baseline. [Synthetic modelling report](synthetic-battery.md)

## v1.2–v1.3 checkpoint

The successor branch adds the standalone Thevenin EKF, Coulomb Counting, a matched synthetic oracle and Hybrid A. Training and validation use disjoint simulated battery identities and load-profile families. Test reporting separates matched Thevenin and structurally mismatched diffusion plants. The workbench reads compressed Python playback output and serves it on loopback with no frontend dependencies. [Architecture, experiments and reproduction](soc-workbench.md)

## v1.4–v1.5 checkpoint

Hybrid B learns available capacity and reference-temperature series resistance with a causal update in the shared EKF. The branch keeps the v1.3 cohorts and scores and adds a separate RC stress cohort. The workbench shows actual model paths and updates, an interactive cell cutaway and paired Hybrid B traces. [Hybrid B engineering report](hybrid-b-workbench.md)

## Future estimator experiments

- Compare longer or designed excitation windows with the 180 s capacity baseline. Investigate uncertainty when SOC, resistance and capacity have similar voltage effects.
- Assess RC adaptation with independently designed excitation, known sensor bias and defensible parameter references. Experimental identification requires appropriate thermal measurements and independent validation.
- Extend structural-mismatch validation with separately pinned PyBaMM trajectories and document the chemistry and reference definitions. Report an oracle only when the plant defines the needed parameters or a documented projection is defensible.

## Educational workbench and extension points

| Area | User experience |
|---|---|
| Battery fundamentals | A labelled procedural cutaway explains current collectors, electrodes, separator and ion flow. |
| Dataset explorer | Distinct NASA experimental and synthetic views explain provenance, units, sampling and which signals are available as truth. |
| Battery physics laboratory | Inputs for load, temperature and circuit parameters reveal voltage contributions, RC time constants and bulk versus surface state. |
| ML explorer | Ridge coefficients, Random Forest aggregation and HistGradientBoosting updates explain model assumptions, feature windows and evaluation splits. |
| EKF explorer | A stepped trace exposes prediction, measurement residual, gain, correction and covariance. |
| Hybrid laboratory | Controlled scenarios compare Coulomb Counting, fixed EKF, Hybrid A, Hybrid B and eligible oracle runs on identical inputs. |
| Results and reports | Reproduction settings, errors, limitations and per-scenario evidence stay inspectable and exportable. |

The current views use plain HTML, CSS and JavaScript, SVG rendering and one compressed export of Python experiment outputs. Consider TypeScript and React if shared state and component reuse justify a toolchain. Three.js is a candidate for the cutaway if custom camera controls, picking and accessible inspection justify its asset cost. Keep the illustrative geometry procedural and load the renderer on demand. A Python service is warranted only if interactive simulation cannot use precomputed scenarios or a thin portable bridge. Keep one numerical implementation per model, with explicit parity tests before introducing another runtime.

Use event-driven rendering. Suspend animations on hidden tabs, release old datasets and meshes, and downsample for display only. When solver outputs become expensive, cache bounded scenario results by complete configuration. Retrain models only when training inputs or settings change. Benchmark representative cold and warm launches, idle memory and user interactions after an interface exists. Target a core checkout below 10 MB, frontend assets below 5 MB, startup below 3 s, lightweight interaction below 100 ms and attributable idle memory below 200 MB. Record the actual platform and measurement method.

## v2.0 release checkpoint

The final milestone investigates capacity generalisation, evaluates a causal adaptation safeguard on independent profile families, and extends the offline Hybrid lab with reproducible decision and failure audits. The report distinguishes synthetic results, NASA compatibility and the remaining CALCE audit prerequisite. [v2.0 engineering release](robust-hybrid-v2.md)

## v2.1 Battery Engineering Studio

The existing six-view offline page is reorganised into eight destinations: Overview, Battery Design, Battery Physics, Dataset Explorer, Machine Learning, SOC Estimation, Investigation Lab and Reports. The Overview synchronises its measurement cards with a selected precomputed synthetic trajectory. Battery Physics teaches the three equivalent-circuit views and presents the independent diffusion plant's exported trajectory separately. Reports show v2.0 paired cohort summaries and link to local methodology and capacity reports. The studio continues to use the existing Python numerical engines and compressed experiment export. It adds no package dependency and does not change model training, estimator equations or published research results. [v2.1 implementation report](battery-engineering-studio-v2.1.md)

The four future investigations above remain future work: this redesign does not implement or claim a new estimator, experimental SOC validation or chemistry-calibrated electrochemical model.

## v2.2 Interactive Simulation Lab

The eighth-destination layout remains unchanged. Battery Physics now hosts a configurable ECM simulation UI that calls the existing Python engine through a strict loopback-only standard-library HTTP route. It supports Rint, Thevenin and Dual Polarisation, five deterministic locally defined profiles, 1 Hz samples up to 1,800 s, synchronized SOC/voltage plots and a conceptual cell visualization, session-only baseline comparison, and JSON/CSV export. No external drive-cycle data is used. Custom simulations are not passed into or scored by the trained estimators. When launched as `reports/workbench.html` without the Python server, the existing research views continue to work and the simulation panel explains how to enable runs. [v2.2 engineering report](battery-engineering-studio-v2.2.md)

The loopback endpoint handles one request at a time and rejects cross-origin submissions, unknown fields, model-inapplicable RC parameters, invalid ranges, oversized bodies and simulations above the sample cap. Inactive view SVGs are cleared on navigation and recreated from unchanged source results when needed. This reduces browser DOM retention without dropping or downsampling scientific data. No frontend or backend package dependency is added.
