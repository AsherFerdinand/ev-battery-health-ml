# Phase 4 — CALCE raw-data compatibility verdict

## Outcome

**Both downloaded archives were acquired and inspected. Direct transfer of the unchanged frozen models is not scientifically compatible with the supplied measurement channels. No external SOH predictions or error scores were generated.** The compatibility gate concerns missing required measurements, not a failed model score.

## Provenance and inspection scope

CS2_35.zip and CS2_36.zip were inspected locally under data/external/calce. Per-archive SHA-256, complete member inventories and XLSX header/metadata previews are saved in the inventory JSONs. Every workbook's telemetry headers were checked. The audit is reproducible without extra packages using ZIP/XML readers.

- **CS2_35**: 25 XLSX workbooks, 25 raw telemetry sheets; archive SHA-256 `84d88cb98a43c02049f16c78806a78ec19084776ea5df8a4b7c2f8f7ba4589e5`. All 25 Info-sheet Temp mapping fields are zero: `True`.
- **CS2_36**: 26 XLSX workbooks, 26 raw telemetry sheets; archive SHA-256 `2e674f58bb6dc005c73bef10e87edbbd97afd041dde77a1d461a3c4ecac1b027`. All 26 Info-sheet Temp mapping fields are zero: `True`.

## Dataset metadata

[CALCE provider documentation](https://calce.umd.edu/data) identifies CS2 as 1.1 Ah prismatic cells with an LCO cathode. CS2_35/36 use 1C discharge. Charging is CC/CV to 4.2 V, with usual discharge cutoff 2.7 V. Exact chamber temperature is not established by the supplied telemetry. See original provider experiment papers before publication. These are laboratory cells, not EV pack data.

## What the actual files contain

Every raw telemetry sheet has 17 columns: Data_Point, Test_Time(s), Date_Time, Step_Time(s), Step_Index, Cycle_Index, Current(A), Voltage(V), Charge_Capacity(Ah), Discharge_Capacity(Ah), Charge_Energy(Wh), Discharge_Energy(Wh), dV/dt(V/s), Internal_Resistance(Ohm), Is_FC_Data, AC_Impedance(Ohm), ACI_Phase_Angle(Deg). Some workbooks additionally contain cycle-summary sheets. There are no temperature or ambient channels in these headers, and no separate temperature file in either ZIP.

The Info worksheet DOES contain the label **Temp**, but it sits under **Mapped_Aux_Number** and its value is **0** in every inspected workbook. That is auxiliary-channel configuration metadata, not measured 0°C or a constant-temperature experiment. It must not be used to create temperature features. Likewise, resistance/impedance column names do not establish valid resistance measurements; those columns are unused here.

## Sampling and discharge evidence (representative files only)

The first XLSX archive member of each ZIP was parsed numerically to inspect sign, cadence and window availability. These are representative raw-file checks, NOT full lifecycle parsing, selected best-performing cycles or ML evaluation. Discharge segments are grouped by the file's Cycle_Index and Step_Index with negative current; boundary/counter semantics would need further validation before constructing measured-capacity SOH labels.

- **CS2_35**, `CS2_35/CS2_35_10_15_10.xlsx`: 17139 total rows; 5607 negative-current rows; median discharge current -1.0996 A. Positive within-segment sample intervals have median 30.015 s (range 0.250–30.019 s). 50 of 50 observed segments span at least 900 s.
- **CS2_36**, `CS2_36/CS2_36_10_04_10.xlsx`: 2709 total rows; 822 negative-current rows; median discharge current -1.0999 A. Positive within-segment sample intervals have median 30.015 s (range 0.484–31.218 s). 7 of 8 observed segments span at least 900 s.

## Feature compatibility

| Frozen input | Raw compatibility |
|---|---|
| Voltage start/end/mean/std | Voltage and time are present; use only samples at/before 900 s after verified discharge onset |
| Mean current | A units and negative-discharge samples verified in representative files; no C-rate substitution |
| Voltage drop/slope (HGB challenger) | Potentially computable from voltage/time once cycle/step segmentation is validated |
| Starting cell temperature | **Unavailable: no cell-temperature series** |
| Temperature rise | **Unavailable: no cell-temperature series** |
| Ambient temperature | **Unavailable: no ambient series or justified supplied chamber setpoint** |
| Measured SOH reference | Discharge-capacity counter exists; complete-discharge boundary/reference semantics still need validation. CALCE nominal divisor would be 1.1 Ah, not NASA's 2 Ah |

Both frozen models require all three missing thermal features. Compatibility of voltage/current subsets does not make the full model input compatible. Constant temperatures, external median fills, mapping a channel count of zero to 0°C, dropping thermal inputs, or training replacement pipelines would change the experiment and must not be presented as direct transfer.

## Frozen models and results

The existing freeze was verified without retraining. It predates raw-file inspection and records final NASA-only fits of the Phase 3 recipes: RF uses the eight existing 15-minute features; HGB uses those plus voltage drop/slope. Settings, preprocessing, training/raw/source hashes and artifact hashes remain in models/phase4/freeze_manifest.json. No CALCE labels or features were used to choose model settings.

| Cell | Frozen model | External MAE/RMSE/bias | Acceptance |
|---|---|---|---|
| CS2_35 | Random Forest | Not evaluated: required inputs absent | Not evaluated |
| CS2_35 | HistGradientBoosting | Not evaluated: required inputs absent | Not evaluated |
| CS2_36 | Random Forest | Not evaluated: required inputs absent | Not evaluated |
| CS2_36 | HistGradientBoosting | Not evaluated: required inputs absent | Not evaluated |

Not evaluated is neither a pass nor a failure of the >5 pp error rule. No external prediction failures, residual plots or numerical feature-shift conclusions are asserted. Measured capacity remains a reference, not an independent ML prediction.

## Potential dataset shift and defensible next experiment

Different nominal rating, cell construction, discharge current/C-rate, chemistry/protocol, voltage/capacity reference and sampling may affect transfer. The actual header incompatibility is established; these other factors remain domain-shift hypotheses, not observed causes of prediction error. Sampling summaries describe only the representative files.

A separate voltage/current-only model trained and selected on NASA could be frozen before inspecting CALCE target-performance outcomes, then tested on fully parsed CALCE cycles. That would be **new NASA-trained reduced-feature transfer**, not validation of the original thermal-feature models. Alternatively obtain a public dataset supplying compatible temperature/ambient measurements. No replacement or adapted model has been trained in this phase.

## Reproduce

```
python phase4_freeze.py
python phase4_inspect.py data/external/calce/CS2_35.zip --output reports/phase4/CS2_35_inventory.json
python phase4_inspect.py data/external/calce/CS2_36.zip --output reports/phase4/CS2_36_inventory.json
python phase4_calce_audit.py
python -m unittest discover -s tests
```

`python phase4_report.py` now dispatches to the local raw-data audit when these inventories exist, instead of regenerating the obsolete network-blocked status. The guarded inference runner remains available for future genuinely compatible data; no CALCE parser or inference run is claimed. The original dashboard, all prior experiment results, RUL models and anomaly detection are preserved. No automotive deployment claim follows from this compatibility investigation.
