# EV Battery Health ML

- Use Python 3.12 and install from `requirements-lock.txt`.
- Run `python -m unittest discover -s tests -v`. Artifact-dependent NASA and CALCE checks explicitly skip when their outputs are absent.
- Run `python build_workbench.py --no-open` and `node tests/workbench_smoke.cjs` for the synthetic SOC workbench. The NASA dashboard retains its own build and smoke commands.
- Keep NASA and synthetic evidence separate. Ordinary estimators receive measured channels only. Restrict synthetic truth to scoring and eligible oracle experiments.
- Keep data, generated HTML, models and caches in ignored directories. Preserve published Phase 1–4 outputs and their original reproduction workflow.
- Resume milestone work from [docs/PROGRESS.md](docs/PROGRESS.md). Use targeted checks for each change and the full suite for delivery.
- Hybrid B adapts capacity and reference-temperature R₀ after a causal observation window. Keep R₁/C₁ fixed unless a new identifiability study supports changes.
- For v2 release verification run `python robust_validation.py --full`, both workbench export checks, and the browser check with `REQUIRE_ROBUST=1`. Keep final duty families separate from model and safeguard selection.
- v2.2 user simulations must call `simulation_api.py`, which delegates to `battery_sim.py`; do not duplicate model equations in JavaScript or feed custom runs into validated estimator claims.
- Launch the interactive Python service with `python build_workbench.py` (PowerShell: `.\.venv\Scripts\python.exe build_workbench.py`). The service binds to 127.0.0.1, serializes simulation requests and enforces the 1,800 s / 1 Hz request cap. Opening generated HTML without the service must retain the precomputed research views and explain that custom runs need the launcher.
- Run `python -m unittest tests.test_simulation_api -v` for the user-simulation schema, profile and endpoint checks. The service accepts only same-origin JSON, whitelisted model/profile values and supported model parameters.
- Retain at most two user simulation results for baseline comparison. Clear SVGs from inactive views; preserve all scientific payloads and full precision.
