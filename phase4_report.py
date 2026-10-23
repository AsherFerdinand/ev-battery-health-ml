"""Generate Phase 4 status report from frozen artifacts and acquisition evidence."""
import json
from pipeline import ROOT,sha256
from phase4_freeze import verify,MODEL_DIR
OUT=ROOT/'reports/phase4'

def main():
 if all((OUT/f'{cell}_inventory.json').exists() for cell in ['CS2_35','CS2_36']):
  from phase4_calce_audit import main as audit
  audit();return
 if (OUT/'direct_transfer/evaluation_manifest.json').exists():raise RuntimeError('Actual transfer results exist; refusing to overwrite them with a pending-status report')
 frozen=verify();OUT.mkdir(parents=True,exist_ok=True)
 status=dict(phase='4',freeze_complete=True,raw_external_data_acquired=False,raw_schema_verified=False,feature_compatibility='unverified, not proven incompatible',external_evaluation_performed=False,external_metrics=None,external_retraining_performed=False,blocker='External archive/inventory not supplied locally; compatibility is unverified',sources=['https://calce.umd.edu/data','https://web.calce.umd.edu/batteries/data/CS2_35.zip','https://web.calce.umd.edu/batteries/data/CS2_36.zip'],frozen_manifest_sha256=sha256(MODEL_DIR/'freeze_manifest.json'))
 (OUT/'status.json').write_text(json.dumps(status,indent=2))
 report='''# Phase 4 — independent dataset validation status

## Outcome

**Model freeze completed. External dataset acquisition and validation have NOT completed. There are no external MAE/RMSE/bias scores or pass/fail results.**

The required raw archive inventories are not available locally. Obtain the provider archives separately and inspect them before making a compatibility or performance claim. Missing local files are not evidence of scientific incompatibility.

## Candidate dataset and documented conditions

Source: [CALCE Battery Research Data](https://calce.umd.edu/data). Candidate archives: [CS2_35](https://web.calce.umd.edu/batteries/data/CS2_35.zip), [CS2_36](https://web.calce.umd.edu/batteries/data/CS2_36.zip). The provider identifies CS2 as prismatic LCO-cathode cells rated 1.1 Ah. It describes CC/CV charging at 0.5C to 4.2 V, with CV ending below 0.05 A; usual discharge cutoff is 2.7 V. CS2_35/36 use 1C discharge. Files are dated Excel logs. Raw voltage/current/capacity/temperature column availability and units still require file inspection. The documentation does not establish CS2 thermocouple or ambient channels; temperature files mentioned for CX2_4 cannot be assumed to exist for CS2. Consult the provider's linked experiment papers for use/publication attribution.

Metadata is a starting point, not raw-file validation. No statement about actual missing CS2 channels is made. CS2 protocol temperature and native sampling interval remain unverified.

## What was frozen before external evaluation

Phase 3 stored cross-validation fold results, not a single final estimator. Phase 4 therefore follows a declared NASA-only final-fit step: retain the selected Phase 3 model recipes and exact feature lists; choose between the same two hyperparameter candidates by leave-one-NASA-cell-out CV over all four NASA cells; fit final preprocessing and model on all four NASA cells. This final NASA training is NOT external adaptation or a new test result.

'''
 for model,record in frozen['models'].items():
  report+=f"- **{model}**: settings `{record['selected_config']}`, features `{record['features']}`, artifact SHA-256 `{record['artifact_sha256']}`.\n"
 report+='''
Both models use the original 900-second sampling cutoff, NASA-fitted median imputation and scaler, unchanged raw-unit features, and the same estimator factory/seed. External missing measurements are rejected BEFORE the pipeline, so the imputer cannot silently supply absent temperature/ambient channels. Frozen joblib artifacts, training-data/raw hashes, source hashes, versions, NASA-only CV scores and freeze timestamp are in models/phase4/freeze_manifest.json. Only these own hash-verified serialized artifacts may be loaded. Subsequent freeze commands verify and reuse rather than retrain.

## Compatibility gate

| Item | Required for unchanged direct transfer | Current status |
|---|---|---|
| Voltage and time | Volts and elapsed seconds from matched discharge onset; first 900 s only | Native headers, cadence, gaps and operation start unverified |
| Current | Amperes with the same negative-discharge convention | Provider sign/units must be inspected; documented physical unit/sign conversion is allowed, C-rate feature replacement is not |
| Cell temperature | Actual recorded temperature, degrees Celsius, within the feature window | Not confirmed for CS2; ambient must never be substituted for cell temperature |
| Ambient | Recorded metadata or independently documented chamber setpoint matching NASA scalar ambient semantics | Unknown; no invented 24/25C constants |
| Capacity target | Full-discharge measured Ah with known reference protocol; SOH=100*capacity/1.1 Ah | Column meaning and complete-discharge status unverified. Never divide CALCE by NASA's 2 Ah |
| Window | >=900 s of valid discharge measurement | Must check from native time records; exclude shorter cycles and report exclusions |
| Voltage drop/slope | Same original cutoff-limited calculation, no future interpolation | Potentially supported by voltage/time, not yet tested |
| Chemistry/conditions | Document shift, do not silently correct it with target-dependent transforms | Different rating/form factor/protocol may create shift; compatibility is not the same as in-distribution behavior |

If required temperature or ambient is absent, unchanged transfer of these frozen pipelines is not admissible. Dropping features, using constant temperatures without evidence, replacing current with C-rate, aligning labels by inferred offsets, recalibrating on external targets or fitting again would define a NEW adapted model, not this direct-transfer test. No adapted model was created.

## Direct-transfer results

| Candidate | Model | Evaluated cycles | MAE | RMSE | Signed bias | MAE >5 acceptance |
|---|---|---|---|---|---|---|
| CS2_35/36 | Frozen RF | Not evaluated | Not available | Not available | Not available | Not evaluated |
| CS2_35/36 | Frozen HGB | Not evaluated | Not available | Not available | Not available | Not evaluated |

Missing scores are not zero, and not a pass. No direct-transfer inference was run even as a demonstration with imputed channels. The original NASA metrics remain Phase 3 development evidence, not CALCE results.

## Dataset shift and failure investigation plan

Potential shifts include different chemistry/form factor/rating, discharge current and C-rate, voltage/capacity cutoff definitions, ambient/thermal conditions, timestamp cadence, measurement noise and the observed health range. These are hypotheses from protocol comparison, not observed external prediction failures. No external residual plot or numerical shift estimate can be produced without measurements.

The prepared evaluation runner records feature-wise external ranges and fractions outside frozen NASA ranges, per-cell MAE/RMSE/signed bias, strict MAE >5 flags, and large residual cases. A feature outside the NASA range is a diagnostic, not proof of a causal mechanism; matching ranges also does not prove distribution compatibility. Both model results must be reported, without selecting cells or changing preprocessing based on external labels. Raw capacity is a reference measurement; predicted SOH is a separate model output.

## Reproduction and continuation

1. `python phase4_freeze.py` verifies/reuses the frozen final NASA-only models. No external input is read.
2. Once the provider ZIP exists locally, run `python phase4_inspect.py data/external/calce/CS2_35.zip`. The offline inventory records SHA-256, archive members, XLSX sheet/header previews and text metadata. Legacy XLS is explicitly unsupported until a parser is selected. This does not establish scientific compatibility automatically.
3. Inspect actual units, cycle/step boundaries, sensor channels, sampling and full-discharge capacity definition. A vendor-specific parser must be implemented and tested against those actual files; none is claimed to exist yet.
4. Only after review, prepare a canonical directory containing samples.csv (cell,cycle,time_s,voltage_v,current_a,temperature_c,ambient_c), capacities.csv (cell,cycle,capacity_ah), and metadata.json. This is a schema contract, NOT a CALCE parser or evidence of data availability. Metadata must include dataset, chemistry, nominal_capacity_ah, discharge_protocol, capacity_reference_protocol, sampling_description, temperature_source, ambient_source, provenance, units, and compatibility_review='verified_without_feature_changes'. Units must be {'time':'s','voltage':'V','current':'A_negative_discharge','temperature':'degC','capacity':'Ah'}. Ambient source must be 'recorded' or 'documented_test_setpoint'. Carry raw hashes, unit/sign mappings, and parser provenance; never mark verified without evidence.
5. `python phase4_evaluate.py <reviewed-canonical-directory>` loads only frozen models and predicts; it never fits or tunes. It validates channels/metadata, records exclusions and hashes, and writes results separately under reports/phase4/direct_transfer. `python phase4_report.py` describes the current pending state; a completed external report must be generated from actual direct_transfer results after data acquisition. Do not mistake this status report for completed external validation.
6. `python -m unittest discover -s tests` verifies original tests plus freeze integrity, rejection gates and synthetic adapter behavior. Synthetic test fixtures are NOT external dataset evaluation.

## Conclusion

The models are ready for a controlled direct-transfer experiment, but the primary external-validation objective remains pending raw-file access and compatibility verification. Preserve this blocked status rather than inventing performance or declaring incompatibility. The next concrete requirement is a locally supplied CALCE archive and verified raw-file compatibility. The original dashboard, RUL, anomaly detection and Phase 1–3 experiments are unchanged. No automotive deployment readiness is claimed.
'''
 (OUT/'external_validation_report.md').write_text(report,encoding='utf-8');print(OUT/'external_validation_report.md')
if __name__=='__main__':main()
