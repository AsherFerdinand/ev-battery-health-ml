"""Phase 2: nested cell-separated benchmarking, physics ablation and intervals.
Run: .venv/Scripts/python.exe phase2.py (no new packages/network needed).
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
import json, math, platform
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import loadmat
from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from pipeline import ROOT,CELLS,sha256,ingest
from window_experiment import features,FEATURES as BASE
OUT=ROOT/'reports/phase2'
EXTRA=['v_slope_v_s','v_drop_v','v_curvature_v_s2','i_std_a','i_abs_mean_a','temp_slope_c_s','temp_max_c','temp_above_ambient_c']
SETS={'base':BASE,'physics':BASE+EXTRA}
# Fixed before Phase 2 results. 15 min was selected from Phase 1; exploratory.
WINDOW=900
CONFIGS={'ridge':[{'alpha':1.},{'alpha':100.}],
'random_forest':[{'min_samples_leaf':3},{'min_samples_leaf':10}],
'hist_gradient_boosting':[{'max_leaf_nodes':7},{'max_leaf_nodes':15}]}

def engineered(data,ambient,seconds=WINDOW):
    result=features(data,ambient,seconds)
    t=np.asarray(data.Time,dtype=float).ravel();t=t-t[0];mask=t<=seconds;t=t[mask]
    v=np.asarray(data.Voltage_measured,dtype=float).ravel()[mask]
    i=np.asarray(data.Current_measured,dtype=float).ravel()[mask]
    temp=np.asarray(data.Temperature_measured,dtype=float).ravel()[mask]
    if len(np.unique(t))<3:raise ValueError('Insufficient distinct times')
    linear=np.polyfit(t,v,1);quadratic=np.polyfit(t/t[-1],v,2)
    result.update(dict(zip(EXTRA,[linear[0],v[0]-v[-1],2*quadratic[0]/t[-1]**2,i.std(),np.abs(i).mean(),np.polyfit(t,temp,1)[0],temp.max(),temp.mean()-float(ambient)])))
    # No V/I or delta-V/delta-I resistance: coarse asynchronous load onset,
    # OCV/polarisation/SOC confounding and no controlled pulse support it here.
    return result

def estimator(model,config):
    if model=='ridge': reg=Ridge(**config)
    elif model=='random_forest':reg=RandomForestRegressor(n_estimators=100,random_state=42,n_jobs=1,**config)
    else:reg=HistGradientBoostingRegressor(max_iter=100,learning_rate=.05,l2_regularization=1.,early_stopping=False,random_state=42,**config)
    return make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),reg)

def nested_select(train,cols,model):
    scores=[]
    for config in CONFIGS[model]:
        losses=[]
        for cell in sorted(train.cell.unique()):
            fit=train[train.cell!=cell];val=train[train.cell==cell]
            reg=estimator(model,config);reg.fit(fit[cols],fit.soh_pct)
            losses.append(mean_absolute_error(val.soh_pct,reg.predict(val[cols])))
        scores.append(float(np.mean(losses)))
    best=int(np.argmin(scores))
    return CONFIGS[model][best],scores

def conformal_radius(scores,alpha=.1):
    scores=np.asarray(scores,dtype=float)
    k=math.ceil((len(scores)+1)*(1-alpha))
    return float('inf') if k>len(scores) else float(np.sort(scores)[k-1])

def table_markdown(df):
    return '| '+' | '.join(df.columns)+' |\n|'+'|'.join(['---']*len(df.columns))+'|\n'+'\n'.join('| '+' | '.join(str(v) for v in row)+' |' for row in df.itertuples(index=False,name=None))

def main():
    OUT.mkdir(parents=True,exist_ok=True);ingest(ROOT/'data/raw',offline=True)
    rows=[];reject=[]
    for cell in CELLS:
        battery=loadmat(ROOT/f'data/raw/{cell}.mat',squeeze_me=True,struct_as_record=False)[cell];cycle=0
        for rec in np.atleast_1d(battery.cycle):
            if str(rec.type)!='discharge':continue
            cycle+=1
            try:
                cap=float(rec.data.Capacity)
                if not np.isfinite(cap) or cap<=0:raise ValueError('Invalid capacity')
                rows.append(dict(cell=cell,cycle=cycle,soh_pct=cap/2*100,**engineered(rec.data,rec.ambient_temperature)))
            except ValueError as e:reject.append(dict(cell=cell,cycle=cycle,reason=str(e)))
    df=pd.DataFrame(rows);df.to_csv(OUT/'features.csv',index=False)
    (OUT/'rejections.json').write_text(json.dumps(reject,indent=2))
    predictions=[];audit=[]
    for test_cell in CELLS:
        train=df[df.cell!=test_cell];test=df[df.cell==test_cell]
        for feature_set,cols in SETS.items():
            for model in CONFIGS:
                config,scores=nested_select(train,cols,model)
                audit.append(dict(test_cell=test_cell,training_cells=sorted(train.cell.unique()),feature_set=feature_set,model=model,candidate_configs=CONFIGS[model],inner_macro_cell_mae=scores,selected=config))
                reg=estimator(model,config);reg.fit(train[cols],train.soh_pct);pred=reg.predict(test[cols])
                for r,p in zip(test.itertuples(),pred):predictions.append(dict(cell=test_cell,cycle=r.cycle,feature_set=feature_set,model=model,actual=r.soh_pct,predicted=float(p),temperature=r.temp_start,train_min_soh=float(train.soh_pct.min()),train_max_soh=float(train.soh_pct.max())))
        print('Benchmark completed:',test_cell,flush=True)
    p=pd.DataFrame(predictions);p['residual_pp']=p.predicted-p.actual;p['absolute_error_pp']=abs(p.residual_pp)
    p['outside_train_soh_range']=(p.actual<p.train_min_soh)|(p.actual>p.train_max_soh)
    p.to_csv(OUT/'predictions.csv',index=False);(OUT/'tuning_audit.json').write_text(json.dumps(audit,indent=2))
    def metrics(g):return pd.Series(dict(n=len(g),mae_pp=g.absolute_error_pp.mean(),rmse_pp=np.sqrt(np.mean(g.residual_pp**2)),bias_pp=g.residual_pp.mean(),p95_absolute_error_pp=g.absolute_error_pp.quantile(.95)))
    m=p.groupby(['feature_set','model','cell']).apply(metrics,include_groups=False).reset_index();m.to_csv(OUT/'cell_metrics.csv',index=False)
    overall=m.groupby(['feature_set','model']).agg(macro_cell_mae_pp=('mae_pp','mean'),worst_cell_mae_pp=('mae_pp','max'),macro_cell_rmse_pp=('rmse_pp','mean')).reset_index();overall.to_csv(OUT/'benchmark.csv',index=False)
    p.sort_values('absolute_error_pp',ascending=False).head(40).to_csv(OUT/'failure_cases.csv',index=False)
    p.groupby(['feature_set','model','outside_train_soh_range']).apply(metrics,include_groups=False).to_csv(OUT/'range_errors.csv')
    # Dedicated calibration cell never enters fitting or model selection.
    intervals=[];interval_audit=[]
    for test_cell in CELLS:
        for calibration_cell in [c for c in CELLS if c!=test_cell]:
            fit=df[~df.cell.isin([test_cell,calibration_cell])];cal=df[df.cell==calibration_cell];test=df[df.cell==test_cell]
            for model in CONFIGS:
                reg=estimator(model,CONFIGS[model][0]);reg.fit(fit[SETS['physics']],fit.soh_pct)
                scores=abs(reg.predict(cal[SETS['physics']])-cal.soh_pct.to_numpy());q=conformal_radius(scores)
                pred=reg.predict(test[SETS['physics']])
                interval_audit.append(dict(test_cell=test_cell,calibration_cell=calibration_cell,fit_cells=sorted(fit.cell.unique()),model=model,config=CONFIGS[model][0],radius_pp=q,nominal_coverage=.9,calibration_cycles=len(cal),cell_level_90pct_radius='infinite: only one calibration cell'))
                for r,estimate in zip(test.itertuples(),pred):intervals.append(dict(cell=test_cell,calibration_cell=calibration_cell,model=model,cycle=r.cycle,actual=r.soh_pct,predicted=float(estimate),lower=float(estimate-q),upper=float(estimate+q),covered=bool(abs(estimate-r.soh_pct)<=q),width_pp=2*q))
    ip=pd.DataFrame(intervals);ip.to_csv(OUT/'interval_predictions.csv',index=False)
    im=ip.groupby(['model','cell','calibration_cell']).agg(empirical_coverage=('covered','mean'),mean_width_pp=('width_pp','mean'),n=('cycle','size')).reset_index();im.to_csv(OUT/'interval_metrics.csv',index=False)
    (OUT/'interval_audit.json').write_text(json.dumps(interval_audit,indent=2))
    plot(p,ip)
    manifest=dict(seed=42,window_seconds=WINDOW,feature_sets=SETS,configs=CONFIGS,python=platform.python_version(),raw_sha256={c:sha256(ROOT/f'data/raw/{c}.mat') for c in CELLS},source_sha256=sha256(Path(__file__)),alpha=.1,intervals='cycle-level split conformal; single cell calibration; exploratory, no cross-cell guarantee')
    import importlib.metadata
    manifest['packages']={n:importlib.metadata.version(n) for n in ['numpy','pandas','scipy','scikit-learn','matplotlib']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    generate_report(df,p,m,overall,im)
    print(overall.to_string(index=False));print('Report:',OUT/'engineering_report.md')

def plot(p,ip):
    import matplotlib.pyplot as plt
    for feature_set in SETS:
        fig,axes=plt.subplots(4,4,figsize=(17,13))
        for row,cell in enumerate(CELLS):
            for model in CONFIGS:
                g=p[(p.cell==cell)&(p.model==model)&(p.feature_set==feature_set)]
                for ax,x,label in zip(axes[row,:3],[g.cycle,g.actual,g.temperature],['Cycle','Measured SOH (%)','Starting temperature (C)']):
                    ax.scatter(x,g.residual_pp,s=8,alpha=.5,label=model);ax.axhline(0,color='gray',lw=.6);ax.set(xlabel=label,ylabel=cell+' residual (pp)')
                axes[row,3].hist(g.residual_pp,bins=20,alpha=.4,label=model);axes[row,3].set(xlabel='Residual (predicted - measured, pp)',ylabel='Cycles')
        axes[0,3].legend(fontsize=8);fig.suptitle(feature_set+' features: outer held-out-cell residuals');fig.tight_layout();fig.savefig(OUT/f'residuals_{feature_set}.png',dpi=130);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    for ax,cell in zip(axes.ravel(),CELLS):
        g=ip[(ip.cell==cell)&(ip.model=='hist_gradient_boosting')&(ip.calibration_cell==sorted(set(CELLS)-{cell})[0])]
        ax.plot(g.cycle,g.actual,label='Measured capacity SOH',color='black');ax.plot(g.cycle,g.predicted,label='Estimated SOH')
        ax.fill_between(g.cycle,g.lower,g.upper,alpha=.2,label='90% nominal cycle-calibrated interval')
        ax.set(title=cell+'; calibration '+g.calibration_cell.iloc[0],xlabel='Cycle',ylabel='SOH (%)')
    axes[0,0].legend(fontsize=7);fig.tight_layout();fig.savefig(OUT/'intervals.png',dpi=150);plt.close(fig)

def generate_report(df,p,m,overall,im):
    rounded=overall.round(3);cell_table=m.round(3)
    interval_summary=im.groupby('model').agg(mean_coverage=('empirical_coverage','mean'),min_cell_pair_coverage=('empirical_coverage','min'),mean_width_pp=('mean_width_pp','mean')).reset_index().round(3)
    report='''# Phase 2 engineering report

## Scope and reproducibility

NASA cells B0005/B0006/B0007/B0018 only. Run `python phase2.py` from the existing project environment. No new dependencies or downloads. The manifest records raw-file hashes, source hash, configuration, package versions and random seed. Original dashboard and Phase 1 reports are retained. All new artifacts live in reports/phase2.

The target is NASA measured Capacity/2 Ah ×100. Estimated SOH is an ML output, not a replacement measurement. This work does not explain physical causes, diagnose faults, forecast calendar life or validate EV pack operation.

## Protocol

15-minute measurement window selected during prior exploratory Phase 1, not independently confirmed. No full-cycle duration, integrated capacity, cycle ID or battery ID enters model inputs. Each outer test cell is completely excluded from training, tuning and preprocessing. Within the other three cells, leave-one-cell-out CV selects between two preset candidates per model using mean per-cell validation MAE. Final refit uses the three training cells. Scaling/imputation are inside each fitted pipeline. HistGradientBoosting uses no random early-stopping validation split. Audit JSON preserves every selection and cell membership. Hyperparameter grids are small and not an exhaustive model optimization.

Base uses the existing eight window features (including temperature rise). Physics adds voltage slope (V/s), voltage drop (V), voltage curvature (V/s²), current std and mean magnitude (A), temperature slope (C/s), maximum temperature (C), and mean temperature above ambient (C). All are calculated only within 900 seconds; voltage curvature is twice the quadratic coefficient in physical time. Both sets share identical rows/splits/tuning budgets. This is a feature-group ablation, not attribution to individual added features. Features are engineering summaries, not identified degradation mechanisms.

Resistance is deliberately absent: V/I is not internal resistance; recorded constant-current discharge and coarse load transitions do not isolate ohmic response from OCV, state of charge and polarization. A defensible DCIR estimate needs a characterized current step and synchronized pre/post voltage at a specified timescale. Existing impedance data could be investigated separately, with availability rules.

## Benchmark (macro average across held-out cells)

'''+table_markdown(rounded)+'''

## Per-cell metrics

All MAE, RMSE, bias and residuals use SOH percentage points, not accuracy percentages. Macro RMSE below/above is the average of cell RMSEs, not a pooled RMSE.

'''+table_markdown(cell_table)+'''

## Error and failure analysis

![Base residuals](residuals_base.png)
![Physics residuals](residuals_physics.png)

Each row is a held-out battery; columns show signed residual against cycle, measured SOH, starting temperature, and residual distribution. Failures are preserved in failure_cases.csv; range_errors.csv contrasts labels within/outside the training-cell SOH range. These stratifications use test labels for analysis only, never for fitting. Temperature and SOH co-vary, so residual-temperature associations do not identify temperature as a cause. Only four independent cells underpin the results; hundreds of correlated cycles do not create hundreds of independent batteries. Per-cell differences and bias matter more than a headline pooled score.

## Prediction intervals: calibration experiment

For every test cell, rotate each other cell as a dedicated calibration cell; fit the remaining two cells. These runs use the FIRST preset configuration, with no tuning or fitting on the calibration cell. They are separate models from the tuned benchmark. All runs use physics features. The radius is the ceil((n+1)*0.9)-th ordered absolute calibration residual; intervals are unbounded in SOH units (no clipping to 0–100). All 12 test/calibration combinations per model are retained, not selected by coverage. The figure uses the alphabetically first permitted calibration cell as a fixed display convention.

'''+table_markdown(interval_summary)+'''

![Calibration interval examples](intervals.png)

The nominal target is 90%, not guaranteed held-out-cell coverage. Cycles within a cell are dependent and different cells can shift distributions. Standard cycle-level exchangeability assumptions do not hold automatically. Observed coverage and widths must be read together and per pair in interval_metrics.csv. Repeated uses of the same four cells are correlated; averages across rotations are descriptive.

At battery level there is only ONE calibration cell per split. A finite-sample 90% conformal quantile based on cell-level maximum residuals would require rank ceil(2*0.9)=2 from one score: the valid distribution-free radius is infinite. Therefore these finite cycle-calibrated intervals do NOT establish calibrated 90% generalization to new batteries. At least nine exchangeable calibration cells are needed even to obtain a finite 90% cell-score quantile, plus separate fit/test cells; this is a minimum, not an adequate sample-size recommendation.

## Independent dataset investigation

See [dataset compatibility assessment](second_dataset.md). No CALCE or Oxford measurements were downloaded, parsed, trained on or tested in Phase 2. No external-dataset performance is claimed. Compatibility and file-level sampling/temperature availability must be established before testing a frozen transferable feature subset.

## Conclusions and next decisions

Use the tables to determine whether the physics group actually helps each model/cell. Do not assume added features or gradient boosting are improvements. The four NASA cells have already informed development, so nested separation prevents direct fold leakage but does not erase prior researcher selection. Do not promote the best outer score as an unbiased deployment estimate. Freeze configuration and validate against new cells before any deployment or reliability claim. Obtain more independent batteries before claiming cell-level interval calibration. Preserve measured capacity reference and report unavailability of incompatible features rather than filling missing temperature from labels or future data.
'''
    # Concrete failure cases and direction of ablations, generated rather than hand-picked.
    delta=overall.pivot(index='model',columns='feature_set',values='macro_cell_mae_pp');delta['physics_minus_base_pp']=delta.physics-delta.base
    report+='\n## Observed ablation changes\n\nNegative delta means lower macro-cell MAE for physics features.\n\n'+table_markdown(delta.reset_index().round(3))
    report+='\n\n## Largest observed errors (top 12 of all outer predictions)\n\n'+table_markdown(p.sort_values('absolute_error_pp',ascending=False)[['cell','cycle','feature_set','model','actual','predicted','absolute_error_pp','outside_train_soh_range']].head(12).round(3))
    (OUT/'engineering_report.md').write_text(report,encoding='utf-8')

if __name__=='__main__':main()
