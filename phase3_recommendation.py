"""Reproducible synthesis of Phase 3 evidence; no fitting or test-based tuning."""
import json
import pandas as pd
from pipeline import ROOT
from phase2 import table_markdown
OUT=ROOT/'reports/phase3'

def main():
 m=pd.read_csv(OUT/'cell_metrics.csv');a=m[m.experiment=='ablation'];rows=[]
 for (protocol,model,cell),g in a.groupby(['protocol','model','cell']):
  vals=dict(zip(g.feature_set,g.mae_pp))
  for name in ['v_drop_v','v_slope_v_s','temp_rise']:
   ds=[]
   for key,value in vals.items():
    parts=key.split('+')
    if name in parts:continue
    other='core'+''.join('+'+n for n in ['v_drop_v','v_slope_v_s','temp_rise'] if n in parts or n==name)
    ds.append(vals[other]-value)
   rows.append(dict(protocol=protocol,model=model,cell=cell,added_feature=name,delta_mae_pp=sum(ds)/len(ds)))
 effects=pd.DataFrame(rows);effects.to_csv(OUT/'ablation_effects.csv',index=False)
 effect_summary=effects.groupby(['protocol','model','added_feature'],as_index=False).delta_mae_pp.mean()
 b=m[(m.experiment=='benchmark')&(m.window=='15min')]
 consistency=b.groupby(['feature_set','model']).agg(combined_macro_mae_pp=('mae_pp','mean'),worst_cell_protocol_mae_pp=('mae_pp','max'),failed_cell_protocols=('flag_mae_gt5','sum')).reset_index()
 primary=b[(b.feature_set=='base')&(b.model=='random_forest')]
 rec=dict(primary_research_candidate=dict(model='random_forest',window='15min',features='base'),universal_acceptance_pass=bool(not primary.flag_mae_gt5.any()),failed_results=json.loads(primary[primary.flag_mae_gt5].to_json(orient='records')),recommendation_type='provisional balanced-task candidate; not deployment approval',external_validation=False,unseen_cell_challenger=dict(model='hist_gradient_boosting',window='15min',features='focused'),known_cell_reference=dict(model='ridge',window='15min',features='base'))
 (OUT/'recommendation.json').write_text(json.dumps(rec,indent=2))
 pi=pd.read_csv(OUT/'permutation_importance.csv')
 ranking=pi[(pi.feature_set=='base')&(pi.kind=='single')].groupby(['protocol','model','feature'],as_index=False).mae_increase_pp.mean()
 ranking=ranking.sort_values(['protocol','model','mae_increase_pp'],ascending=[True,True,False]).groupby(['protocol','model']).head(3)
 text='''# SOH estimator recommendation — Phase 3

## Decision

**Use Random Forest with the existing eight features and a 15-minute measurement window as the provisional balanced-task research baseline. Keep HistGradientBoosting with the focused voltage additions as the unseen-cell challenger. No configuration is accepted as a universally reliable SOH estimator.**

This recommendation is a task-dependent engineering judgment, not an automatic overall-MAE winner or deployment authorization. Four repeatedly studied NASA cells cannot establish external reliability. The independent-dataset step remains necessary.

For the proposed Random Forest baseline, macro-cell MAE is 2.78 pp on unseen cells and 3.07 pp on later cycles; worst unseen-cell MAE is 4.78 pp, while later-cycle B0006 is 5.04646 pp and must remain flagged. Seven of eight cell/protocol results pass the 5 pp screen; the eighth is NOT rounded down or waived. The modest additional focused voltage features barely help transfer and slightly worsen temporal results, so the existing feature set is the more economical baseline.

HistGradientBoosting with focused features gives lower unseen-cell macro MAE (2.64 pp), worst-cell transfer MAE 4.64 pp and no unseen-cell flags. However, later-cycle macro MAE is 3.43 pp and worst-cell MAE 6.37 pp (B0006), worse than Random Forest. It is the stronger transfer-specific candidate, not the universal winner. Ridge with the existing 15-minute features is a compact, interpretable later-cycle reference (2.30 pp macro MAE; worst cell 4.10 pp; no temporal flags), but unseen-cell macro MAE is 5.51 pp with three flagged batteries. It is not the preferred cross-cell estimator.

## Consistency across both prediction tasks (15 minutes)

Each mean below weights each battery/protocol pair equally. The two protocols are distinct tasks, not eight independent batteries.

'''+table_markdown(consistency.round(3))+'''

## Why 15 minutes rather than shorter or longer?

60 seconds and 5 minutes have larger unseen-cell errors and more flagged cells in the matched benchmark. For the base Random Forest, going from 15 to 30 minutes worsens unseen-cell macro MAE from 2.78 to 3.29 pp and temporal macro MAE from 3.07 to 3.29 pp, while doubling measurement time; it still has a temporal flag. The other estimators do not turn 30 minutes into a universally passing option. Thirty-minute Ridge improves known-cell temporal performance but retains transfer failures. Full-cycle features are retrospective and not an early-estimation recommendation; directly measured capacity remains the reference.

All five windows use identical test cycles and outer split memberships. The primary candidate is a trade-off among measurement time, per-cell consistency and both tasks. It is not a claim that 15 minutes is statistically optimal or physically special. Previously inspected data influenced this analysis, so freeze the candidate before external testing.

## Controlled feature effects

The table averages the change in per-cell MAE when adding one feature, across the four combinations of the other two optional features, using fixed model settings. A negative delta means the feature helps; positive means it hurts. See ablation_effects.csv for each battery rather than treating these means as universal effects.

'''+table_markdown(effect_summary.round(3))+'''

Voltage slope improves average cross-cell MAE for all three models here. Temperature rise helps temporal tree-model errors but worsens average cross-cell errors under the fixed ablation settings. This is consistent with a feature capturing within-test progression while also depending on battery/operating conditions; it does not establish that temperature causes model failure. Drop is an algebraic re-expression of existing endpoints and brings no new measured information. Linear regularization and tree partitioning can still respond to that representation.

A longer observation window exposes more voltage trajectory and temperature evolution. The measured improvement is predictive evidence, not proof of an electrochemical mechanism. No resistance is estimated and no causal claims follow from these summaries.

## Held-out feature reliance

Top three single-feature permutation effects per model/task, averaged equally across held-out batteries, are shown below. Joint-group results remain in permutation_importance.csv.

'''+table_markdown(ranking.round(3))+'''

Voltage variability and endpoint voltage dominate many cross-cell models. Temporal tree-model permutation changes can be small despite noticeable errors: later health may lie outside the training response range, so permuting inputs does not repair extrapolation. Single-feature importance is affected by correlations; voltage drop/endpoints can substitute for one another. Row shuffling creates unrealistic feature combinations and breaks time dependence. These are model diagnostics, not causal attributions; no features were selected or refitted using held-out importance.

## Failure cases and acceptance

B0006 is the central difficult battery. Ridge tends to underestimate its late-life SOH in cross-cell testing; tree models can overestimate health on later cycles when degradation extends beyond training targets. See protocol-specific residual plots and signed bias in validation_report.md; associations with SOH/temperature are descriptive. Per-cell MAE and RMSE can hide individual cycle errors above 10 pp, so inspect failure_cases.csv as well.

Use `python phase3_acceptance.py --model random_forest --window 15min --feature-set base --strict` for an explicit gate. It exits 1 because B0006 later-cycle MAE exceeds 5 pp. This is an expected scientific rejection, not broken software. Omit --strict to inspect flags without a failing process exit. Passing any other configuration's screen would still not establish EV deployment readiness.

## Complexity, leakage and next decision

Ridge offers minimal model complexity. Both ensembles add complexity; Random Forest uses 100 trees, while the gradient booster uses 100 bounded-leaf boosting iterations. This report does not measure prediction latency or memory, and does not claim Random Forest is computationally cheaper than the booster. Its advantage for the provisional baseline is the balance across both tasks with the existing features, not computational superiority.

All benchmark preprocessing/tuning excludes outer test data; chronological inner splits remain within training prefixes, and unseen-cell tuning separates entire batteries. Controlled ablations deliberately hold hyperparameters fixed. Neither permutation results nor acceptance flags feed fitting. Nevertheless, prior researcher decisions on the same cells prevent an unbiased claim of population generalization. Hyperparameter search is small; models may respond differently to a larger, equally budgeted search.

Freeze the proposed Random Forest/15-minute baseline and transfer-focused HGB challenger, resolve second-dataset feature compatibility, then compare on untouched cells. Do not silently deploy the lowest score, loosen the 5 pp threshold, modify the dashboard, or claim calibrated uncertainty from this study. The report contains no new-dataset performance claim.
'''
 (OUT/'recommendation.md').write_text(text,encoding='utf-8')
 report=OUT/'validation_report.md'
 report.write_text(report.read_text(encoding='utf-8')+'\n\n## Evidence-based recommendation\n\nSee [recommendation and controlled feature effects](recommendation.md). The recommended balanced-task research candidate is existing-feature Random Forest at 15 minutes, with one remaining temporal battery acceptance failure; no universal or deployment winner is declared.\n',encoding='utf-8')
if __name__=='__main__':main()
