"""Audit locally supplied CALCE archives; never fit or predict with missing channels."""
import io,json,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
import pandas as pd
from pipeline import ROOT,sha256
from phase4_freeze import verify,MODEL_DIR
OUT=ROOT/'reports/phase4'
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def representative(path):
 with zipfile.ZipFile(path) as a:
  name=next(n for n in a.namelist() if n.endswith('.xlsx'))
  with zipfile.ZipFile(io.BytesIO(a.read(name))) as z:
   strings=[''.join(t.itertext()) for t in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
   for part in z.namelist():
    if not(part.startswith('xl/worksheets/sheet') and part.endswith('.xml')):continue
    root=ET.fromstring(z.read(part));rows=root.findall('s:sheetData/s:row',NS)
    def values(row):
     out={}
     for c in row.findall('s:c',NS):
      v=c.find('s:v',NS)
      if v is None:continue
      out[''.join(ch for ch in c.get('r') if ch.isalpha())]=strings[int(v.text)] if c.get('t')=='s' else v.text
     return out
    if not rows:continue
    header=values(rows[0])
    if 'Data_Point' not in header.values():continue
    records=[{header[k]:v for k,v in values(r).items() if k in header} for r in rows[1:]]
    df=pd.DataFrame(records).apply(pd.to_numeric,errors='coerce');dis=df[df['Current(A)']<-.05]
    dt=[];dur=[]
    for _,g in dis.groupby(['Cycle_Index','Step_Index']):
     t=g['Test_Time(s)'].to_numpy();delta=np.diff(t);dt.extend(delta[delta>0]);dur.append(float(t[-1]-t[0]))
    return dict(member=name,selection='first XLSX archive member; representative only, not all cycles',rows=len(df),negative_current_rows=len(dis),median_discharge_current_a=float(dis['Current(A)'].median()),observed_voltage_min_v=float(dis['Voltage(V)'].min()),observed_voltage_max_v=float(dis['Voltage(V)'].max()),median_positive_discharge_sample_delta_s=float(np.median(dt)),min_positive_discharge_sample_delta_s=float(np.min(dt)),max_positive_discharge_sample_delta_s=float(np.max(dt)),negative_current_cycle_step_segments=len(dur),segments_spanning_at_least_900s=sum(d>=900 for d in dur),max_segment_span_s=max(dur),capacity_field='Discharge_Capacity(Ah) exists; counter/reset/reference interpretation not validated as cycle-level SOH labels')
 raise ValueError('No telemetry sheet found')

def main():
 frozen=verify();results=[];counts=[]
 for cell in ['CS2_35','CS2_36']:
  path=ROOT/f'data/external/calce/{cell}.zip';invpath=OUT/f'{cell}_inventory.json'
  if not invpath.exists():raise ValueError('Run phase4_inspect.py for '+cell+' first')
  inv=json.loads(invpath.read_text())
  if sha256(path)!=inv['sha256']:raise ValueError('Archive differs from inspected hash')
  files=[f for f in inv['files'] if f['name'].endswith('.xlsx')];telemetry=[];maps=[];all_headers=[]
  for f in files:
   for sheet in f['sheets']:
    rows=sheet['preview_rows'];headers=[v['value'] for v in rows[0]] if rows else []
    if 'Data_Point' in headers:telemetry.append(dict(workbook=f['name'],sheet=sheet['part'],headers=headers));all_headers.extend(headers)
    # Info worksheet uses Temp under Mapped_Aux_Number, NOT degrees C.
    if any(c['column']=='I4' and c['value']=='Temp' for row in rows for c in row):
     values=[c['value'] for row in rows for c in row if c['column']=='I5'];maps.extend(values)
  thermal_headers=[h for h in all_headers if any(s in h.lower() for s in ['temp','thermocouple','ambient'])]
  if thermal_headers:raise ValueError('Thermal headers found: compatibility requires renewed channel review')
  if len(telemetry)!=len(files):raise ValueError('Unexpected workbook schema; cannot infer complete archive coverage')
  record=dict(cell=cell,archive_sha256=inv['sha256'],xlsx_workbooks=len(files),telemetry_sheets=len(telemetry),telemetry_headers=sorted(set(all_headers)),thermal_headers=thermal_headers,info_temp_mapped_aux_numbers=maps,info_temp_mapping_all_zero=bool(len(maps)==len(files) and all(float(v)==0 for v in maps)),representative=representative(path),direct_transfer_compatible=False,missing_features=['temp_start','temp_rise','ambient'],reason='No recorded cell/ambient temperature channels in telemetry; Info Temp is an auxiliary-channel mapping field, not a temperature measurement')
  results.append(record)
  for t in telemetry:counts.append(dict(cell=cell,workbook=t['workbook'],sheet=t['sheet'],header_count=len(t['headers']),has_measured_temperature=False,has_ambient_temperature=False))
 (OUT/'calce_raw_audit.json').write_text(json.dumps(results,indent=2));pd.DataFrame(counts).to_csv(OUT/'calce_workbook_schema.csv',index=False)
 status=dict(phase='4',freeze_complete=True,raw_external_data_acquired=True,raw_schema_verified=True,feature_compatibility='incompatible with unchanged frozen feature requirements: missing cell temperature and ambient temperature',external_evaluation_performed=False,external_metrics=None,external_retraining_performed=False,cells=[r['cell'] for r in results],scientific_blocker='Required temperature_start, temperature_rise and ambient features are not supplied; no values were invented or imputed',previous_network_blocker_resolved='User downloaded both archives; copies inspected locally',frozen_manifest_sha256=sha256(MODEL_DIR/'freeze_manifest.json'))
 (OUT/'status.json').write_text(json.dumps(status,indent=2))
 report='''# Phase 4 — CALCE raw-data compatibility verdict

## Outcome

**Both downloaded archives were acquired and inspected. Direct transfer of the unchanged frozen models is not scientifically compatible with the supplied measurement channels. No external SOH predictions or error scores were generated.** The earlier network-access blocker is resolved by the user's downloads. The current blocker is missing required measurements, not network access or a failed model score.

## Provenance and inspection scope

Copies of CS2_35.zip and CS2_36.zip were read from the user's Downloads into data/external/calce; originals were preserved. Per-archive SHA-256, complete member inventories and XLSX header/metadata previews are saved in the inventory JSONs. Every workbook's telemetry headers were checked. The audit is reproducible without extra packages using ZIP/XML readers.

'''
 for r in results:
  report+=f"- **{r['cell']}**: {r['xlsx_workbooks']} XLSX workbooks, {r['telemetry_sheets']} raw telemetry sheets; archive SHA-256 `{r['archive_sha256']}`. All {len(r['info_temp_mapped_aux_numbers'])} Info-sheet Temp mapping fields are zero: `{r['info_temp_mapping_all_zero']}`.\n"
 report+='''
## Dataset metadata

[CALCE provider documentation](https://calce.umd.edu/data) identifies CS2 as 1.1 Ah prismatic cells with an LCO cathode. CS2_35/36 use 1C discharge. Charging is CC/CV to 4.2 V, with usual discharge cutoff 2.7 V. Exact chamber temperature is not established by the supplied telemetry. See original provider experiment papers before publication. These are laboratory cells, not EV pack data.

## What the actual files contain

Every raw telemetry sheet has 17 columns: Data_Point, Test_Time(s), Date_Time, Step_Time(s), Step_Index, Cycle_Index, Current(A), Voltage(V), Charge_Capacity(Ah), Discharge_Capacity(Ah), Charge_Energy(Wh), Discharge_Energy(Wh), dV/dt(V/s), Internal_Resistance(Ohm), Is_FC_Data, AC_Impedance(Ohm), ACI_Phase_Angle(Deg). Some workbooks additionally contain cycle-summary sheets. There are no temperature or ambient channels in these headers, and no separate temperature file in either ZIP.

The Info worksheet DOES contain the label **Temp**, but it sits under **Mapped_Aux_Number** and its value is **0** in every inspected workbook. That is auxiliary-channel configuration metadata, not measured 0°C or a constant-temperature experiment. It must not be used to create temperature features. Likewise, resistance/impedance column names do not establish valid resistance measurements; those columns are unused here.

## Sampling and discharge evidence (representative files only)

The first XLSX archive member of each ZIP was parsed numerically to inspect sign, cadence and window availability. These are representative raw-file checks, NOT full lifecycle parsing, selected best-performing cycles or ML evaluation. Discharge segments are grouped by the file's Cycle_Index and Step_Index with negative current; boundary/counter semantics would need further validation before constructing measured-capacity SOH labels.

'''
 for r in results:
  v=r['representative'];report+=f"- **{r['cell']}**, `{v['member']}`: {v['rows']} total rows; {v['negative_current_rows']} negative-current rows; median discharge current {v['median_discharge_current_a']:.4f} A. Positive within-segment sample intervals have median {v['median_positive_discharge_sample_delta_s']:.3f} s (range {v['min_positive_discharge_sample_delta_s']:.3f}–{v['max_positive_discharge_sample_delta_s']:.3f} s). {v['segments_spanning_at_least_900s']} of {v['negative_current_cycle_step_segments']} observed segments span at least 900 s.\n"
 report+='''
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
'''
 (OUT/'external_validation_report.md').write_text(report,encoding='utf-8');verify();print(json.dumps(status,indent=2))
if __name__=='__main__':main()
