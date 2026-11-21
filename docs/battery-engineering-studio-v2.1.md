# Battery Engineering Studio v2.1

## Scope and architecture

v2.1 redesigns the existing offline workbench as eight destinations: Overview, Battery Design, Battery Physics, Dataset Explorer, Machine Learning, SOC Estimation, Investigation Lab and Reports. The NASA research dashboard remains separately available. The HTML/JavaScript front end reads the same compressed Python result export; it does not recompute the battery simulator, fit estimators, or modify the v2.0 research outputs. The navigation, theme and scenarios use ordinary DOM events. Charts and cutaways remain SVG, and the battery diagrams are procedural.

Overview synchronises voltage, current, temperature, reference SOC/SOH and fixed-EKF SOC with the selected exported synthetic scenario. Its cross-section is explicitly conceptual. Battery Physics retains the existing interactive Rint, Thevenin and Dual Polarisation circuit response. The Diffusion tab displays a separately generated finite-volume plant trajectory and identifies it as synthetic ground truth rather than an equivalent-circuit response. Dataset Explorer preserves the NASA replay and synthetic channels. Machine Learning and SOC Estimation keep the existing teaching views. Investigation Lab preserves Hybrid A, Hybrid B, the fixed estimator, Coulomb Counting, eligible oracle, safeguards, diagnostics and per-run controls. Reports expose the v2.0 paired SOC/voltage outcomes, capacity generalisation, policy description and locally served methodology documents.

NASA recordings and their recorded current convention remain in the NASA-only view. Synthetic truth is labelled as a simulation reference. NASA capacity-derived SOH does not become SOC ground truth. No NASA ECM identification or experimental SOC accuracy claim is introduced. The v2.0 result interpretation and limitations remain in [the scientific report](robust-hybrid-v2.md) and [capacity study](capacity-generalisation.md).

## Dependencies, storage and operation

No Python, JavaScript, UI framework, chart library or 3D library dependency was added. Python remains the numerical source of truth. The full standalone HTML embeds its compressed experiment payload, so the browser requires no network connection or backend process. Launch it with:

```sh
.venv/bin/python build_workbench.py                 # quick demonstration, served offline on loopback
.venv/bin/python build_workbench.py --full           # full research export
.venv/bin/python build_workbench.py --full --no-open --refresh
```

In Windows PowerShell, substitute `\.venv\Scripts\python.exe`. Generated HTML and experiment payloads remain under ignored `reports/`; raw NASA and synthetic datasets, caches, model binaries and environments are not committed. Reports links resolve to checked-in local Markdown files both from the generated reports path and the loopback server.

## Verification

The v2.0 backend and its numerical tests are unchanged. The quick and full export smoke checks verify 21 paired trace sets and all 63 exported circuit examples. The Playwright browser check runs with outbound requests blocked. It exercises all eight views, the local result tables, theme toggle, estimator cutoffs, NASA replay, model selection, ML teaching controls, battery cutaway controls and 390 px layout. See the delivery record in [PROGRESS](PROGRESS.md) for the final test counts and any environment-dependent skip.

## Linux cloud measurements

Measurements describe the managed Linux cloud only; they are not Windows desktop estimates. The host reported an AMD EPYC 9V74 processor with five available CPUs, Python 3.12.14 and Chromium 156.0.8078.79. The checkout contains 84 tracked files, 41 source files (`.py`, HTML, JS/CJS, CSS and PowerShell), and about 2.29 MB of tracked content. The existing `.venv` occupies 459 MiB; no dependencies were added. Browser startup is navigation-to-rendered-workbench over five launches. Playback interaction is synchronous DOM/chart update time for 50 slider events. Browser PSS is aggregate Chrome process memory and its delta from a blank page, not application-only heap.

| Measurement | v2.1 result |
|---|---:|
| Quick/full HTML export | 5,754,758 / 5,751,105 bytes |
| Full compressed experiment JSON | 1,700,547 bytes embedded by the HTML builder; no separate dataset was added |
| Exporter build timing | 22.93 s quick / 52.07 s full, from the builder's monotonic timer |
| Browser startup | 0.307 s median, 0.491 s maximum across five full-export launches |
| Playback chart update | 1.5 ms median, 2.5 ms p95, 2.6 ms maximum across 50 synchronous updates |
| Browser idle memory | 489.3 MiB aggregate Chrome PSS; 204.6 MiB blank page; 284.7 MiB delta |
| Idle browser CPU | 0.25 aggregate CPU-seconds over 2.5 seconds |
| Synthetic trajectory simulation | No new simulation was added. In the reproduced v2.0 cohort, per-trajectory median was 3.06 ms for Thevenin and 10.69 ms for diffusion (721 samples) |

Browser memory exceeds the preliminary 200 MiB attributable idle target in this Linux run. CPU and memory include the aggregate browser process tree. The browser check blocks outbound requests and confirms the rendered workbench and report routes work offline. The repository remains below the preliminary 10 MB target; generated exports remain ignored. The full Python suite tests the preserved scientific implementation, which v2.1 did not modify. Windows startup, memory, CPU and performance were not measured.
