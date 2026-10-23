# Verification and reproduction notes

## Evidence behind the published results

The original completed Windows research workspace passed **32 Python tests** with its NASA data and generated Phase 1–4 artifacts available. Dashboard logic checks covered **672 control combinations**, replay start/pause, retained prediction history, hidden future predictions and forecast-history visibility. Phase 3 complete reruns produced byte-identical predictions, metrics, permutation importance and acceptance flags; the retained summary is in results/phase3/repeat_check.json.

These are recorded local checks, not a GitHub Actions status, live badge, certified system, independent fleet test or code-coverage claim. The CALCE finding is a real raw-schema audit, not external prediction accuracy.

## Publication-folder check

The publication copy was tested without raw datasets, generated reports or model binaries: **18 tests passed and 14 integration checks explicitly skipped** (32 discovered). No skipped check is counted as passed. Artifact-free checks cover cutoff independence, physical feature units, forecast mechanics, conformal quantiles, acceptance boundaries, feature-set definitions and strict transfer input gates.

Artifact-dependent checks become available after their respective experiment outputs exist. For all 32 checks, run the NASA baseline/window/Phase 2/Phase 3 scripts, create the NASA-only Phase 4 freeze, and inspect/audit the separately obtained CALCE archives. See README for commands. Node-based dashboard checks require generating reports/dashboard.html first. Optional external data is not downloaded during unit tests.

## Publication-only portability changes

Scientific model factories, hyperparameter grids, feature formulas and evaluation logic are preserved. The publication copy adds explicit skip conditions when optional experiment artifacts are absent, uses repository-local test scratch files, and records preservation hashes at the start of Phase 3 so a fresh reproduction can verify unchanged application sources. Phase 4's no-input status now says files are absent rather than attributing a new user's missing files to the original session's network issue.

The original workspace and its recorded experiments remain unchanged. Full model experiments were not rerun from the publication folder; the curated result files are exact copies of the completed original results. A separate review checks their values against the README. Generated runtime data belongs under ignored data/, reports/, models/ and work/; selected immutable study evidence is under docs/results/.

## Practical limitations

Reproduction requires obtaining the provider's raw data and the pinned Python dependencies. Python 3.12 on Windows was tested; other platforms are not claimed verified. Integration results depend on generated artifact availability, not only installation. Pipeline outputs include complete training/split/provenance audits that are regenerated locally rather than bundled into the public snapshot.

The 5 pp screen is a research acceptance criterion, not an automotive standard. Its Random Forest/15-minute failure on later-cycle B0006 remains visible and the strict gate intentionally returns a nonzero exit status. No CALCE SOH estimate was generated after the incompatible-channel finding.

## Regenerating integration artifacts

Run these commands from the repository root using the project's environment. They do not change the documented scientific configuration:

```powershell
.\.venv\Scripts\python.exe pipeline.py
.\.venv\Scripts\python.exe window_experiment.py
.\.venv\Scripts\python.exe build_dashboard.py
.\.venv\Scripts\python.exe phase2.py
.\.venv\Scripts\python.exe phase3.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

With NASA artifacts generated, 28 checks are available and four Phase 4 checks remain dependent on model-freeze/status/CALCE-audit artifacts. To enable those, obtain CS2_35.zip and CS2_36.zip separately, put them under data/external/calce/, then run:

```powershell
.\.venv\Scripts\python.exe phase4_freeze.py
.\.venv\Scripts\python.exe phase4_inspect.py data/external/calce/CS2_35.zip --output reports/phase4/CS2_35_inventory.json
.\.venv\Scripts\python.exe phase4_inspect.py data/external/calce/CS2_36.zip --output reports/phase4/CS2_36_inventory.json
.\.venv\Scripts\python.exe phase4_calce_audit.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Those four checks validate freeze integrity and the incompatible-channel finding. They do not validate CALCE prediction performance. Missing artifacts must produce explicit skips rather than implied passes. Run `node tests/dashboard_smoke.cjs` separately after dashboard generation to check the interactive rendering logic.

## Documentation-only final review

The README revision changes presentation, explanations, FAQ markup and licensing scope only. Source files, model settings, dependency locks, dashboard code and the curated experiment results are checked byte-for-byte against their pre-revision hashes. The B0006 MAE 5.04646 pp acceptance failure and the CALCE thermal-channel incompatibility remain explicit.

The MIT grant covers original software/documentation rights only; third-party data and materials are excluded as described in LICENSE_NOTES.md. The standard MIT text is unchanged apart from the copyright year/holder.
