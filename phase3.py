"""Phase 3 validation. Reuse raw NASA data, feature extraction and model factories.
Run .venv/Scripts/python.exe phase3.py. No network or new dependencies.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
import json,platform
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import loadmat
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error
from pipeline import ROOT,CELLS,ingest,sha256
from window_experiment import memberships,WINDOWS
from phase2 import BASE,engineered,estimator,CONFIGS,table_markdown
OUT=ROOT/'reports/phase3'
FOCUSED=BASE+['v_drop_v','v_slope_v_s']
CORE=[c for c in BASE if c!='temp_rise']
ABLATIONS={}
for mask in range(8):
    names=[name for bit,name in enumerate(['v_drop_v','v_slope_v_s','temp_rise']) if mask&(1<<bit)]
    ABLATIONS['core'+('+'+'+'.join(names) if names else '')]=CORE+names

def select_config(train,cols,model,protocol):
    # Fit/preprocess only inside inner folds. Temporal tuning uses prefix-to-tail
    # validation within the OUTER training prefixes, never the final outer tail.
    folds=[]
    if protocol=='temporal_70_30':
        a=[];b=[]
        for _,g in train.groupby('cell'):
            g=g.sort_values('cycle');cut=int(len(g)*.7);a.extend(g.index[:cut]);b.extend(g.index[cut:])
        folds=[(a,b)]
    else:
        for cell in sorted(train.cell.unique()):folds.append((list(train.index[train.cell!=cell]),list(train.index[train.cell==cell])))
    losses=[];audit=[]
    for config in CONFIGS[model]:
        cell_errors=[]
        for tr,va in folds:
            fit=train.loc[tr];val=train.loc[va];reg=estimator(model,config);reg.fit(fit[cols],fit.soh_pct)
            val=val.assign(pred=reg.predict(val[cols]))
            cell_errors.extend(float(abs(g.pred-g.soh_pct).mean()) for _,g in val.groupby('cell'))
        losses.append(float(np.mean(cell_errors)))
    for tr,va in folds:
        audit.append(dict(fit_keys=[str(k) for k in train.loc[tr,'key']],validation_keys=[str(k) for k in train.loc[va,'key']]))
    return CONFIGS[model][int(np.argmin(losses))],losses,audit

def flag_mae(value):return bool(value>5.)

def extract():
    frames=[];unavailable=[]
    for cell in CELLS:
        battery=loadmat(ROOT/f'data/raw/{cell}.mat',squeeze_me=True,struct_as_record=False)[cell];cycle=0
        for rec in np.atleast_1d(battery.cycle):
            if str(rec.type)!='discharge':continue
            cycle+=1
            for window,seconds in WINDOWS.items():
                # engine needs a numeric cutoff; full recording is retrospective.
                cutoff=float(np.max(rec.data.Time)-np.min(rec.data.Time)) if seconds is None else seconds
                try:
                    f=engineered(rec.data,rec.ambient_temperature,cutoff)
                    frames.append(dict(key=f'{cell}_{cycle}',cell=cell,cycle=cycle,window=window,soh_pct=float(rec.data.Capacity)/2*100,**f))
                except ValueError as e:unavailable.append(dict(cell=cell,cycle=cycle,window=window,reason=str(e)))
    data=pd.DataFrame(frames)
    common=set.intersection(*(set(data.loc[data.window==w,'key']) for w in WINDOWS))
    return data[data.key.isin(common)].copy(),unavailable

def importance(reg,test,cols,model,feature_set,protocol,rows):
    for cell,g in test.groupby('cell'):
        result=permutation_importance(reg,g[cols],g.soh_pct,scoring='neg_mean_absolute_error',n_repeats=10,random_state=42,n_jobs=1)
        for name,mean,std in zip(cols,result.importances_mean,result.importances_std):rows.append(dict(cell=cell,protocol=protocol,model=model,feature_set=feature_set,feature=name,kind='single',mae_increase_pp=float(mean),repeat_std_pp=float(std)))
        base_error=mean_absolute_error(g.soh_pct,reg.predict(g[cols]))
        for name,group in [('voltage_joint',[c for c in cols if c.startswith('v_')]),('temperature_joint',[c for c in cols if c.startswith('temp') or c=='ambient'])]:
            rng=np.random.default_rng(42);effects=[]
            for _ in range(10):
                x=g[cols].copy();order=rng.permutation(len(x));x[group]=x[group].to_numpy()[order]
                effects.append(mean_absolute_error(g.soh_pct,reg.predict(x))-base_error)
            rows.append(dict(cell=cell,protocol=protocol,model=model,feature_set=feature_set,feature=name,kind='joint',mae_increase_pp=float(np.mean(effects)),repeat_std_pp=float(np.std(effects))))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'preserved_files.json').write_text(json.dumps({name:sha256(ROOT/name) for name in ['pipeline.py','forecast.py','dashboard_template.html','build_dashboard.py']},indent=2))
    ingest(ROOT/'data/raw',offline=True)
    raw,unavailable=extract();raw.to_csv(OUT/'features.csv',index=False)
    (OUT/'unavailable.json').write_text(json.dumps(unavailable,indent=2))
    base=pd.read_csv(ROOT/'data/processed/cycles.csv');base['key']=base.cell+'_'+base.cycle.astype(str)
    predictions=[];audits=[];permutations=[]
    for window in WINDOWS:
        data=raw[raw.window==window].set_index('key',drop=False)
        for split,(tr,te) in memberships(base).items():
            train=data.loc[[k for k in base.loc[tr,'key'] if k in data.index]].copy();test=data.loc[[k for k in base.loc[te,'key'] if k in data.index]].copy()
            protocol='temporal_70_30' if split=='temporal_70_30' else 'leave_one_cell_out'
            sets={'base':BASE,'focused':FOCUSED} if window=='15min' else {'base':BASE}
            experiments=[('benchmark',name,cols,None) for name,cols in sets.items()]
            if window=='15min':experiments += [('ablation',name,cols,'fixed') for name,cols in ABLATIONS.items()]
            for experiment,feature_set,cols,fixed in experiments:
                for model in CONFIGS:
                    if fixed:config=CONFIGS[model][0];scores=[];inner=[]
                    else:config,scores,inner=select_config(train,cols,model,protocol)
                    audits.append(dict(experiment=experiment,window=window,split=split,protocol=protocol,model=model,feature_set=feature_set,features=cols,selected=config,inner_scores=scores,inner_folds=inner,fit_keys=list(train.key),test_keys=list(test.key),fit_cells=sorted(train.cell.unique()),test_cells=sorted(test.cell.unique())))
                    reg=estimator(model,config);reg.fit(train[cols],train.soh_pct);pred=reg.predict(test[cols])
                    for r,y in zip(test.itertuples(),pred):predictions.append(dict(experiment=experiment,window=window,split=split,protocol=protocol,feature_set=feature_set,model=model,cell=r.cell,cycle=r.cycle,actual=r.soh_pct,predicted=float(y),temperature=r.temp_start,train_min_soh=float(train.soh_pct.min()),train_max_soh=float(train.soh_pct.max())))
                    if experiment=='benchmark' and window=='15min':importance(reg,test,cols,model,feature_set,protocol,permutations)
            print('Completed',window,split,flush=True)
    p=pd.DataFrame(predictions);p['residual_pp']=p.predicted-p.actual;p['absolute_error_pp']=abs(p.residual_pp)
    p.to_csv(OUT/'predictions.csv',index=False);(OUT/'split_tuning_audit.json').write_text(json.dumps(audits,indent=2))
    pi=pd.DataFrame(permutations);pi.to_csv(OUT/'permutation_importance.csv',index=False)
    keys=['experiment','window','protocol','feature_set','model','cell']
    m=p.groupby(keys).agg(n=('cycle','size'),mae_pp=('absolute_error_pp','mean'),bias_pp=('residual_pp','mean'),rmse_pp=('residual_pp',lambda x:float(np.sqrt(np.mean(x*x)))),max_error_pp=('absolute_error_pp','max')).reset_index()
    m['flag_mae_gt5']=m.mae_pp.map(flag_mae);m.to_csv(OUT/'cell_metrics.csv',index=False)
    summary=m.groupby(keys[:-1]).agg(macro_cell_mae_pp=('mae_pp','mean'),worst_cell_mae_pp=('mae_pp','max'),macro_cell_rmse_pp=('rmse_pp','mean'),flagged_cells=('flag_mae_gt5','sum')).reset_index();summary.to_csv(OUT/'comparison.csv',index=False)
    (OUT/'acceptance_flags.json').write_text(json.dumps(dict(rule='Flag every evaluated battery/protocol/model/window/feature set with MAE > 5 SOH percentage points. A flag is not a unit-test failure.',flagged_results=json.loads(m[m.flag_mae_gt5].to_json(orient='records')),total_evaluated_results=len(m),flagged_count=int(m.flag_mae_gt5.sum())),indent=2))
    p.sort_values('absolute_error_pp',ascending=False).head(100).to_csv(OUT/'failure_cases.csv',index=False)
    generate_plots(p,pi);write_report(p,m,summary,pi)
    from phase3_recommendation import main as recommendation
    recommendation()
    manifest=dict(seed=42,configs=CONFIGS,windows=WINDOWS,ablation_sets=ABLATIONS,importance_repeats=10,raw_hashes={c:sha256(ROOT/f'data/raw/{c}.mat') for c in CELLS},source_hash=sha256(Path(__file__)),python=platform.python_version(),common_cycles=int(len(raw[raw.window=='15min'])))
    import importlib.metadata
    manifest['supporting_source_hashes']={name:sha256(ROOT/name) for name in ['phase2.py','window_experiment.py','pipeline.py','phase3_recommendation.py','phase3_acceptance.py']}
    manifest['versions']={k:importlib.metadata.version(k) for k in ['numpy','pandas','scipy','scikit-learn','matplotlib']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(summary.query("experiment=='benchmark'").to_string(index=False))

def generate_plots(p,pi):
    import matplotlib.pyplot as plt
    for window,protocol in [(w,p) for w in WINDOWS for p in ['temporal_70_30','leave_one_cell_out']]:
        fig,axes=plt.subplots(4,4,figsize=(17,13))
        for row,cell in enumerate(CELLS):
            for model in CONFIGS:
                g=p[(p.experiment=='benchmark')&(p.window==window)&(p.feature_set=='base')&(p.protocol==protocol)&(p.cell==cell)&(p.model==model)]
                for ax,x,label in zip(axes[row,:3],[g.cycle,g.actual,g.temperature],['Cycle','Measured SOH (%)','Starting temperature (C)']):
                    ax.scatter(x,g.residual_pp,s=8,alpha=.6,label=model);ax.axhline(0,color='gray',lw=.7);ax.set(xlabel=label,ylabel=cell+' residual (pp)')
                axes[row,3].hist(g.residual_pp,bins=18,alpha=.4,label=model);axes[row,3].set(xlabel='Residual (predicted - measured, pp)',ylabel='Cycles')
        axes[0,3].legend(fontsize=7);fig.suptitle(window+' existing features: '+protocol);fig.tight_layout();fig.savefig(OUT/f'residuals_{window}_{protocol}.png',dpi=130);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,protocol in zip(axes,['temporal_70_30','leave_one_cell_out']):
        for model in CONFIGS:
            means=[]
            for w in WINDOWS:
                g=p[(p.experiment=='benchmark')&(p.feature_set=='base')&(p.protocol==protocol)&(p.model==model)&(p.window==w)]
                means.append(g.groupby('cell').absolute_error_pp.mean().mean())
            ax.plot(['60s','5min','15min','30min','full (retro.)'],means,'o-',label=model)
        ax.set(title=protocol,ylabel='Macro-cell MAE (SOH pp)',xlabel='Measurement window');ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(OUT/'window_comparison.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,6))
    for ax,protocol in zip(axes,['temporal_70_30','leave_one_cell_out']):
        g=pi[(pi.protocol==protocol)&(pi.feature_set=='base')&(pi.kind=='single')]
        pivot=g.groupby(['feature','model']).mae_increase_pp.mean().unstack().reindex(BASE)
        pivot.plot.barh(ax=ax);ax.set(title=protocol,xlabel='Held-out permutation increase in MAE (pp)')
    fig.tight_layout();fig.savefig(OUT/'permutation_importance.png',dpi=150);plt.close(fig)

def write_report(p,m,s,pi):
    benchmark=s[s.experiment=='benchmark'];ablation=s[s.experiment=='ablation']
    report='''# Phase 3 engineering validation report

## Reproduce and scope

Run `python phase3.py` in the existing environment, then `python -m unittest discover -s tests`. No new dependencies, network or UI changes. Seeds/configurations/raw hashes/software versions are in manifest.json; exact fit, test and inner-validation keys are in split_tuning_audit.json. Existing dashboard, RUL, anomaly detection and previous experiments are preserved.

This is continued exploratory analysis of the same four NASA cells, not independent dataset confirmation. Target SOH is measured Capacity / nominal 2 Ah ×100; ML outputs estimate this label. Full-cycle ML is retrospective and not a replacement for directly measuring capacity; it is excluded from early-window recommendations.

## Matched evaluation and tuning

Original 70/30 chronological per-cell membership and four leave-one-cell-out folds are reused identically for all models/windows. Common complete-case cycles across all windows are selected before fitting and count is saved in the manifest. All recorded selected cells span the requested windows here; changing this filter can bias another dataset toward longer-lasting discharges.

For later-cycle evaluation, tuning splits only the outer training prefixes into first 70%/last 30% per cell. For unseen-cell evaluation, tuning uses inner leave-one-cell-out on the three outer training cells, optimizing macro-cell MAE. Every imputer/scaler is fitted inside its training pipeline. Two preset candidates per model, no test-driven early stopping, no target/cycle/cell/duration in inputs. Different protocol-specific tuning is appropriate to the intended prediction task, so a deployed model needs its intended protocol stated. The small tuning grid is not exhaustive optimization.

## Model and window comparison

MAE/RMSE are SOH percentage points, not percentage accuracy. Macro means weight each battery equally. Worst-cell error and acceptance failures are primary checks alongside the mean. No confidence interval for population performance is claimed from four cells.

'''+table_markdown(benchmark.round(3))+'''

![Window comparison](window_comparison.png)

## Per-cell results (benchmark)

'''+table_markdown(m[m.experiment=='benchmark'].round(3))+'''

## Controlled 15-minute ablation: why does the window help?

The seven-feature core is the existing feature set WITHOUT temperature rise. A 2³ factorial adds voltage drop, voltage slope and temperature rise independently and jointly, on identical 15-minute rows and outer splits. These ablations use the first preset configuration for each model, fixed across feature sets, so an observed effect is not confounded with retuning. The separately tuned base/focused benchmark is not the controlled factorial comparison. Voltage drop is exactly v_start minus v_end: it adds representation, not new information. Both endpoints already exist in the core. Permutation effects for these correlated variables may be diluted or unstable.

'''+table_markdown(ablation.round(3))+'''

The graphs and tables compare 60 s/5/15/30 minutes with the same features and splits. A longer window observes a larger part of discharge voltage evolution and temperature change. That is a plausible interpretation of improved predictive information, not evidence of a causal mechanism. Improvement is neither monotone nor universal across cells/models. Endpoint voltage, slope and temperature can also proxy discharge conditions and state of charge; four cells cannot disentangle those effects. Do not claim that 15 minutes uniquely captures an electrochemical process.

## Held-out permutation importance

![Importance](permutation_importance.png)

Importance is the increase in held-out MAE after shuffling one input, with 10 fixed-seed repetitions, separately on each held-out battery and protocol, and only at 15 minutes. Joint voltage and joint temperature permutations are also in permutation_importance.csv. Models are NOT refitted, tuned or feature-selected using this diagnostic. Negative values are retained. Repeat standard deviation describes permutation randomness, not a confidence interval across batteries.

Correlated inputs, redundant endpoints/drop, off-manifold combinations and temporal autocorrelation limit ordinary row-shuffle interpretation. Joint permutations partially address within-group redundancy but not between-group confounding. Importance describes model reliance under a perturbation; it is not proof of physical causation or a ranking of intrinsic battery mechanisms.

## Residuals and failure cases

![Later-cycle residuals](residuals_15min_temporal_70_30.png)
![Unseen-cell residuals](residuals_15min_leave_one_cell_out.png)

Positive residual means overestimated health. Per-cell cycle/SOH/temperature plots and failure_cases.csv identify where errors concentrate. In particular target-range differences and late-life extrapolation can affect B0006; tree models cannot extrapolate arbitrarily outside their training targets. Temperature associations remain confounded by cell/health. The failure table below is descriptive and never feeds fitting.

'''+table_markdown(p[p.experiment=='benchmark'].sort_values('absolute_error_pp',ascending=False)[['window','protocol','feature_set','model','cell','cycle','actual','predicted','absolute_error_pp']].head(20).round(3))+'''

## Automated acceptance

Every battery/protocol/window/model/feature-set result with MAE >5 pp is flagged in acceptance_flags.json and cell_metrics.csv. Exactly 5 is not flagged. Scientific acceptance failures are preserved as results, not hidden or converted into software-test failures. The report includes flagged counts per configuration; a pooled mean under 5 cannot override a failing battery. Passing this screen does not establish fleet-level reliability.

## Recommendation criteria and limitations

A defensible choice must consider both protocols, all per-cell failures, worst-cell MAE, window cost and model complexity, not merely the smallest pooled mean. Ridge is the simplest linear reference; Random Forest uses 100 trees and HistGradientBoosting uses 100 boosting iterations with bounded leaves. These size settings are not a measured latency/memory benchmark. There is no external validation, and previous analysis influenced the windows/features under study. Compare recommendations as candidates to freeze and independently test, never validated deployment winners.
'''
    (OUT/'validation_report.md').write_text(report,encoding='utf-8')

if __name__=='__main__':main()
