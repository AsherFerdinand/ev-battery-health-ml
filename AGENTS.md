# EV Battery Health ML

- Use Python 3.12 and install from `requirements-lock.txt`.
- Run `python -m unittest discover -s tests -v`. Artifact-dependent NASA and CALCE checks explicitly skip when their outputs are absent.
- Run `python build_workbench.py --no-open` and `node tests/workbench_smoke.cjs` for the synthetic SOC workbench. The NASA dashboard retains its own build and smoke commands.
- Keep NASA and synthetic evidence separate. Ordinary estimators receive measured channels only. Restrict synthetic truth to scoring and eligible oracle experiments.
- Keep data, generated HTML, models and caches in ignored directories. Preserve published Phase 1–4 outputs and their original reproduction workflow.
- Resume milestone work from [docs/PROGRESS.md](docs/PROGRESS.md). Use targeted checks for each change and the full suite for delivery.
- Hybrid B adapts capacity and reference-temperature R₀ after a causal observation window. Keep R₁/C₁ fixed unless a new identifiability study supports changes.
