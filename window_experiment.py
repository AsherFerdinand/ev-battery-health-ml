"""Window ablation with fixed original split memberships and common test cohorts."""
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from pipeline import ROOT,CELLS,models,ingest
from sklearn.metrics import mean_absolute_error
WINDOWS={'60s':60,'5min':300,'15min':900,'30min':1800,'full':None}
FEATURES=['v_start','v_end','v_mean','v_std','i_mean','temp_start','temp_rise','ambient']

def features(data,ambient,seconds):
    t=np.asarray(data.Time,dtype=float).ravel()
    arrays=[np.asarray(getattr(data,k),dtype=float).ravel() for k in ('Voltage_measured','Current_measured','Temperature_measured')]
    if len(t)<3 or any(len(a)!=len(t) for a in arrays) or not np.isfinite(t).all() or np.any(np.diff(t)<0): raise ValueError('Invalid arrays/time')
    t=t-t[0]
    if seconds is not None and t[-1]<seconds: raise ValueError('Discharge shorter than window')
    mask=np.ones(len(t),dtype=bool) if seconds is None else t<=seconds
    if mask.sum()<3: raise ValueError('Insufficient samples')
    v,i,temp=[a[mask] for a in arrays]
    if not all(np.isfinite(a).all() for a in (v,i,temp)): raise ValueError('Invalid samples')
    return dict(zip(FEATURES,[v[0],v[-1],v.mean(),v.std(),i.mean(),temp[0],temp[-1]-temp[0],float(ambient)]))

def memberships(base):
    splits={}
    train=[];test=[]
    for _,g in base.groupby('cell'):
        cut=int(len(g)*.7);train+=list(g.index[:cut]);test+=list(g.index[cut:])
    splits['temporal_70_30']=(train,test)
    for c in CELLS: splits['unseen_'+c]=(list(base.index[base.cell!=c]),list(base.index[base.cell==c]))
    return splits

def main():
    ingest(ROOT/'data/raw',offline=True)
    base=pd.read_csv(ROOT/'data/processed/cycles.csv')
    base['key']=base.cell+'_'+base.cycle.astype(str)
    rows=[];coverage=[]
    for cell in CELLS:
        battery=loadmat(ROOT/f'data/raw/{cell}.mat',squeeze_me=True,struct_as_record=False)[cell];cycle=0
        for rec in np.atleast_1d(battery.cycle):
            if str(rec.type)!='discharge':continue
            cycle+=1
            for window,seconds in WINDOWS.items():
                try: rows.append(dict(key=f'{cell}_{cycle}',window=window,**features(rec.data,rec.ambient_temperature,seconds)))
                except ValueError as e:coverage.append(dict(cell=cell,cycle=cycle,window=window,reason=str(e)))
    table=pd.DataFrame(rows).merge(base[['key','cell','cycle','soh_pct']],on='key',validate='many_to_one')
    table.to_csv(ROOT/'data/processed/window_features.csv',index=False)
    pd.DataFrame(coverage).to_csv(ROOT/'reports/window_unavailable.csv',index=False)
    common=set.intersection(*(set(table.loc[table.window==w,'key']) for w in WINDOWS))
    metrics=[];predictions=[]
    for cohort in ('common','available'):
        for window in WINDOWS:
            data=table[table.window==window].set_index('key')
            if cohort=='common':data=data.loc[data.index.isin(common)]
            for split,(tr,te) in memberships(base).items():
                train=data.reindex(base.loc[tr,'key']).dropna();test=data.reindex(base.loc[te,'key']).dropna()
                if len(train)<10 or len(test)==0:continue
                for model,estimator in models().items():
                    estimator.fit(train[FEATURES],train.soh_pct);pred=estimator.predict(test[FEATURES])
                    for cell,g in test.assign(pred=pred).groupby('cell'):
                        metrics.append(dict(cohort=cohort,window=window,split=split,model=model,cell=cell,train_n=len(train),test_n=len(g),mae_pp=mean_absolute_error(g.soh_pct,g.pred)))
                    for r,p in zip(test.itertuples(),pred):predictions.append(dict(cohort=cohort,window=window,split=split,model=model,cell=r.cell,cycle=r.cycle,actual=r.soh_pct,predicted=float(p)))
    m=pd.DataFrame(metrics);p=pd.DataFrame(predictions)
    m.to_csv(ROOT/'reports/window_metrics.csv',index=False);p.to_csv(ROOT/'reports/window_predictions.csv',index=False)
    summary=p.groupby(['cohort','window','split','model']).apply(lambda g:pd.Series(dict(mae_pp=float(abs(g.actual-g.predicted).mean()),test_n=len(g))),include_groups=False).reset_index()
    summary.to_csv(ROOT/'reports/window_summary.csv',index=False)
    # Predeclared practical criterion; not a claim of statistical reliability.
    candidates=[]
    for w in list(WINDOWS)[:-1]:
        for model in ('ridge','random_forest'):
            checks=m[(m.cohort=='common')&(m.window==w)&(m.model==model)]
            passed=len(checks)==8 and (checks.mae_pp<=5).all() and (checks.test_n>=20).all()
            candidates.append(dict(window=w,model=model,passes_practical_criterion=bool(passed)))
    (ROOT/'reports/window_criterion.json').write_text(json.dumps(dict(criterion='MAE <=5 SOH percentage points and >=20 test cycles in each cell, temporal and unseen-cell tests; exploratory, no statistical guarantee',common_cycles=len(common),total_cycles=len(base),results=candidates),indent=2))
    diagnostics=table.groupby(['window','cell']).agg(n=('cycle','size'),soh_min=('soh_pct','min'),soh_max=('soh_pct','max'),voltage_mean=('v_end','mean'),current_mean=('i_mean','mean'),temperature_mean=('temp_start','mean'))
    diagnostics.to_csv(ROOT/'reports/window_cell_diagnostics.csv')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for ax,split in zip(axes,['temporal_70_30','unseen']):
        for model in ('ridge','random_forest'):
            g=p[(p.cohort=='common')&(p.model==model)&(p.split.str.startswith(split))]
            vals=[abs(g[g.window==w].actual-g[g.window==w].predicted).mean() for w in WINDOWS]
            ax.plot(list(WINDOWS),vals,'o-',label=model)
        ax.set(title=split,ylabel='MAE (SOH percentage points)',xlabel='Measurement window');ax.legend()
    fig.tight_layout();fig.savefig(ROOT/'reports/window_comparison.png',dpi=150);plt.close(fig)
    print(summary.to_string(index=False));print('Common cohort:',len(common),'of',len(base))
if __name__=='__main__':main()
