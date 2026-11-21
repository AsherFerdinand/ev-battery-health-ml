# v2.0 release checkpoint

**Branch** `feature/robust-hybrid-validation-v2.0`, based on v1.5 `2cc543b`.

- `battery_sim.py` owns synthetic models and physical conventions. Positive current discharges, SOC and SOH are fractions, and capacity is in coulombs. NASA keeps its original convention in replay.
- `soc_estimation.py` owns the shared EKF and measured-only diagnostics. `capacity_experiment.py` and `parameter_estimation.py` retain legacy policies. `validation_population.py` owns independent cohorts and capacity diagnosis. `robust_validation.py` calibrates on development and freezes configuration before final evaluation.
- `build_workbench.py` exports compressed Python results for six offline views. NASA research and model artifacts remain separate from the synthetic release.

| Gate | Result | Targeted reproduction |
|---|---|---|
| A Capacity investigation | Endpoint-phase shift explained clipping. Diverse Random Forest selected on development. | `python -m unittest discover -s tests -p test_validation_population.py` |
| B Safeguard | Causal evidence, exact fixed fallback, and stable active candidate verified. Risk criterion selected fixed Q and R₀. | `python -m unittest discover -s tests -p test_robust_validation.py` |
| C Independent validation | 48 paired identities per plant. Matched benefits from original adaptation coexist with diffusion degradation. Revised capacity MAE improves with no SOC integration claim. | `python robust_validation.py --full` |
| Historical verification | Phase 2, Phase 3 and NASA-only Phase 4 regenerated. Genuine CALCE archives unavailable. | [Artifact recipe](VERIFICATION.md) |

Known blockers and limitations are CALCE provider HTTP 403, unavailable experimental SOC ground truth, and a safeguarded policy that ties fixed EKF. Gate D passed with 60 Python passes and one CALCE skip, both export modes, six offline Chromium views, the original NASA dashboard, and reproduced independent scores. No later milestone started. [Engineering report and exact reproduction](robust-hybrid-v2.md)
