# Capacity generalisation and independent cohort design

## Why the v1.5 capacity estimate saturated

Reproduce the full development diagnosis with `python validation_population.py`. The script reconstructs the original training and validation splits at 48 cell identities per duty family, replays the old v1.5 holdouts, and reports feature and target quantiles, range exceedances, raw and clipped predictions, and one-at-a-time sensor perturbations. All three old holdouts are **development evidence** in v2.0.

The source of the largest shift is the voltage endpoint used at the selected 420 s cutoff. The original training families 0–2 and validation family 3 had started the next discharge step by 420 s. Old holdout families 4 and 5 were still at rest. Consequently, the same feature compared loaded terminal voltage with initial rest voltage during training and near-rest voltage with initial rest voltage in the holdout. The voltage change at 180 s remained within the original training range on the old matched cohort. Some current features already extrapolated at 180 s.

| Matched 420 s diagnostic | Original train (144) | Original validation (48) | Old Thevenin holdout (96) |
|---|---:|---:|---:|
| Target capacity, min / median / max (Ah) | 1.162 / 1.592 / 1.999 | 1.161 / 1.598 / 1.977 | 1.162 / 1.569 / 1.979 |
| Voltage change, median (V) | −0.134 | −0.127 | −0.029 |
| Voltage change, 5th–95th percentile (V) | −0.179 to −0.103 | −0.181 to −0.083 | −0.042 to −0.018 |
| Voltage change outside train min–max | 0% | 0% | 100% |
| Current spread, median (A) | 1.046 | 1.152 | 1.244 |
| Current spread outside train min–max | 0% | 100% | 100% |
| Net charge, median (C) | 189 | 147 | 127 |
| Net charge outside train min–max | 0% | 42% | 74% |

Capacity was drawn independently of family. The target range barely changed. Nevertheless, duty families share a generator whose timing and current levels move together. The held-out samples combine lower net discharge charge with greater current variation and a different endpoint phase. Finite-sample associations also shift. The Pearson correlation of target capacity with voltage change was +0.20, +0.43 and +0.49 in train, validation and old matched holdout respectively. The correlation with mean temperature changed from −0.13 to +0.34 and back to −0.17. Mean current and integrated charge are nearly redundant for a fixed window. These properties make a single held-out validation family a weak check of endpoint extrapolation.

The original Ridge assigns +1.419 Ah of its mean holdout-vs-train shift to standardized voltage change alone. The contributions from voltage spread and current spread are +0.144 and −0.347 Ah respectively. This is an exact linear attribution of the shift in the fitted model, with correlated features and no causal interpretation. On the old matched cases, independently adding +60 mA to measured current, +10 mV to voltage or +2 K to temperature changed the median absolute **raw** prediction by 0.032, 0.007 and 0.008 Ah respectively. Median clipped change was zero in each perturbation. Those offsets probe model response near the replayed cases. A sensor fault can interact with duration or affect other measurements. In the separate matched-physics recovery experiment, a longer window improved local conditioning while worsening capacity under joint current bias and sensor noise. [Identifiability study](parameter-identifiability.md)

## Diverse capacity comparator

The revised candidate retains the existing Ridge, Random Forest and HistGradientBoosting families, causal nine-feature contract and capacity bounds of 1.10–2.00 Ah. Training combines 144 original training cases with 288 varied synthetic pulse sequences from a separate seed and broader parameter ranges. It uses original validation and the new development families for selection. Ineligible traces count as fixed-prior errors when selecting window and model. No original holdout or new final measurement enters fit or selection. The selection-only cohort has 240 cases, including 48 with insufficient observed excitation.

At 180 s the best all-case validation error was 883 C (Ridge, 0.245 Ah). The 420 s Random Forest won at 846 C (0.235 Ah), versus 0.427 Ah for the fixed prior. The selected estimator's MAE was 726 C across 192 eligible traces. This score credits a 2 Ah fallback on the remaining 48 and gives no evidence about an SOC benefit. An additional physically constrained estimator was deferred. The matched fit assumes a known OCV relationship and distinguishable Q, resistance and initial SOC. Those assumptions do not establish a robust capacity estimate in a biased or mismatched setting.

| Old v1.5 development cohort | Original Ridge raw min / median / max (Ah) | Original high clips / in range | Revised high clips / in range | Revised MAE / signed error (Ah) |
|---|---:|---:|---:|---:|
| Thevenin | 2.073 / 2.736 / 3.674 | 96 / 0 | 0 / 96 | 0.215 / +0.042 |
| Diffusion | 2.332 / 2.893 / 3.665 | 96 / 0 | 0 / 96 | 0.210 / +0.037 |
| Thevenin RC stress | 2.068 / 2.768 / 3.664 | 96 / 0 | 0 / 96 | 0.215 / +0.042 |

Neither model clipped low in these cases. The original clipped capacity equals 2 Ah throughout, so both its MAE and positive signed error equal the fixed 2 Ah comparator's 0.448 Ah. Diverse training avoids the endpoint extrapolation seen in the original fit. Its matched predictions still span just 1.484–1.732 Ah against targets spanning 1.162–1.979 Ah. Prediction compression near the population centre is consistent with weak individual capacity evidence. A bounded prediction or smaller capacity error does not establish better SOC.

## Independent operating cohorts

`validation_population.py` defines deterministic 721-sample, 1 Hz records and records profile breakpoints, seeds, identities and configuration ranges. The release protocol uses separate roots for varied training (8021), development (8429) and final (9629). Development profiles include pulse bursts, a staircase, short reversals and weak initial excitation. Final profiles use independent families with charge-first operation, long load release, delayed transients and regenerative bursts. These change sequencing and load geometry, as well as random draws. Fixed family membership is established before scoring. Weak profiles exercise the option to keep prior parameters.

Each sampled identity has matched Thevenin and mismatched diffusion trajectories with the same applied current, initial SOC guess, temperature conditions and random streams. Each identity samples capacity SOH, initial SOC and SOC guess error, ambient temperature, reference resistance scale, RC multipliers, current bias and independent sensor noise scales. The trajectories are paired by name. The matched plant supplies comparator-only parameter references. Diffusion supplies no Thevenin RC oracle. Candidate features read only measured time, current, voltage and temperature through the selected cutoff. Exact ranges and profiles are exported by `provenance()`. Final predictions and release comparisons are reported separately from this development investigation.
