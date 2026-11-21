# Battery Engineering Studio v2.2 — Interactive Simulation Lab

## Implementation

The Simulation Lab in Battery Physics sends a bounded JSON configuration to the local standard-library server in `build_workbench.py`. `simulation_api.py` validates it and calls the existing vectorised `battery_sim.Cell` / `battery_sim.simulate` engine. The browser does not duplicate the ECM equations. The server binds to `127.0.0.1`, processes one request at a time, checks request origin and content type, and limits request bodies to 16 KiB. There are no new runtime dependencies.

Three existing-engine model choices are available: Rint, Thevenin (one RC branch), and Dual Polarisation (two RC branches). Model-specific RC controls and outputs are shown only when relevant. Configuration limits are deliberately bounded: duration 30–1,800 integer seconds; current amplitude 0.05–3 A; initial SOC 0.05–0.95; nominal capacity 0.5–10 Ah; ambient temperature −10–50 °C; R₀ 0.005–0.15 Ω; each RC resistance 0.001–0.1 Ω; C₁ 25–20,000 F and C₂ 100–100,000 F. The application labels resistance inputs in mΩ and converts to Ω for the API.

Built-in deterministic profiles are constant discharge, current pulse, pulse/relaxation, charging, and an illustrative drive-style cycle. They are generated locally at 1 Hz, with positive current denoting discharge and negative current denoting charge. The drive-style profile is not sourced from a recorded vehicle. The duration is capped at 1,800 s, yielding 1,801 inclusive time samples.

## Outputs and scientific boundaries

Each result includes configuration, software/schema version, unit metadata, assumptions, and exact time-series channels. All models return current, terminal voltage, SOC, ECM temperature in kelvin, and supported R₀ reference values. Thevenin adds first-branch polarisation voltage; Dual adds the second branch. Energy in/out and R₀ heat are integrated with a left rectangle over the 1-second zero-order-held samples. JSON and CSV downloads retain units, assumptions, model and configuration metadata.

These are user-configured synthetic model outputs. SOH is fixed at 100% during each run; ageing and measurement noise are not simulated. The shared lumped OCV/SOC relation is not calibrated to a cell chemistry, and the temperature is a simple ECM thermal state. These trajectories do not replace NASA experimental records or the separately validated v2.0 research payload. There is no prediction or estimator-improvement claim. In particular, R₀ changes voltage and heating but does not directly change ideal coulomb-counted SOC. Saved baseline comparison is session-local, supports two runs at a common duration, and reports pointwise model differences without asserting which run is more accurate.

The lab includes synchronized voltage/SOC charts, expandable current/temperature/polarisation plots, comparison metrics, playback/seek, and a conceptual battery fill. Animated ions and fill are explanatory visuals, not computed electrochemical concentration fields. The Lab calls the simulation endpoint when hosted by the Python launcher. If the endpoint is unavailable, existing static research views still work and the Lab explains how to start the launcher.

## Reproduction

From the repository root, on Linux:

```sh
.venv/bin/python build_workbench.py --no-open --refresh
.venv/bin/python build_workbench.py --full --no-open --refresh
.venv/bin/python -m unittest tests.test_simulation_api -v
.venv/bin/python -m unittest discover -s tests -v
```

On Windows PowerShell, after creating the project environment:

```powershell
.\.venv\Scripts\python.exe build_workbench.py --no-open --refresh
.\.venv\Scripts\python.exe build_workbench.py --full --no-open --refresh
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Open the generated `reports/workbench.html` (or `reports/workbench-full.html`) to inspect the precomputed offline research views. To use the interactive simulator, keep the local Python launcher serving the page; it starts the same-origin loopback endpoint. The browser verification command used the managed Cloud Chromium/Playwright installation and a bounded local server:

```sh
PLAYWRIGHT_MODULE=/opt/codex/cua_node/lib/node_modules/playwright \
CHROMIUM_PATH=/usr/bin/chromium REQUIRE_ROBUST=1 \
node tests/workbench_browser.cjs http://127.0.0.1:8777/
```

## Verification and measured footprint

Verification on the managed Linux Cloud Codex environment (Python 3.12, Chromium, 2026-11-21):

- Full Python suite: **68 passed, 1 skipped, 0 failed**. The skip is the optional downloaded CALCE audit because its external archive is not present.
- New API suite: **7 passed** (profiles/signs, input bounds and model-specific fields, all three models, charging, endpoint origin/schema/content-type/body-size checks).
- Full and quick offline export checks: each retained 21 paired trace sets and 63 ECM examples; regenerated research outputs were not changed. Existing dashboard smoke passed 288 cell/threshold/cycle/reveal combinations and 384 SOH/RUL combinations.
- Browser flow: all eight destinations, simulation controls for all three models, playback, comparison and downloads, static-view fallback, existing research interactions, and a 390 px responsive viewport passed. Page errors and external network requests were absent.
- Browser page navigation startup: 203–641 ms over five loads (median 388 ms). This is a Cloud browser measurement, not a Windows desktop benchmark.
- 1,800 s Dual Polarisation / drive-style simulation: **0.0116 s** in the measured Python process, 1,801 samples; reported process peak RSS was 20.9 MiB. This is a single Cloud run, not a desktop performance guarantee.
- Browser aggregate idle PSS: 485.3 MiB versus 215.7 MiB blank-browser baseline, a **269.6 MiB attributable delta**. Idle CPU time increased 0.330 CPU-seconds over a 2.5-second sample. This remains above the preliminary 200 MiB target; the measured v2.1 baseline was 284.7 MiB by its recorded method. Do not interpret these multi-process browser figures as application-only Python memory.
- Repository contained 84 tracked files; Git object store was 2.25 MiB and the working repository excluding `.venv`, downloaded data, and generated reports was 6.8 MiB. No raw simulation dataset is saved: simulations are generated on demand. Both generated HTML exports were approximately 5.6 MiB each and ignored by Git.
- Existing `.venv` footprint was 459 MiB. No dependencies were added; this is the inherited environment footprint, not an attributable v2.2 install delta. Core requirements remain NumPy and the existing scientific stack.
- The target remains below the preliminary 10 MB repository target excluding raw data and generated outputs. The HTML exports are 5.78 MB and 5.78 MB (about 5.51 MiB), exceeding the aspirational 5 MB asset target by about 0.78 MB, mainly because the pre-existing research payload is embedded. Scientific precision and existing research data were preserved.

Static Python compilation, Node syntax checks, and `git diff --check` passed. Commands above reproduce the Python and export checks; browser verification additionally requires the indicated managed Chromium/Playwright paths. No Windows measurements are claimed.
