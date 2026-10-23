"""Historical-capacity trend baseline; no future measurements in each fit."""
import json
import numpy as np
import pandas as pd
from pipeline import ROOT

def forecast(history, threshold=70, window=30):
    h = history.sort_values('cycle').tail(window)
    if len(h) < 10: return None
    slope, intercept = np.polyfit(h.cycle, h.soh_pct, 1)
    now = float(h.cycle.iloc[-1])
    if slope >= -1e-6: return None
    remaining = max(0., float((threshold-intercept)/slope-now))
    return dict(kind='linear', slope=float(slope), intercept=float(intercept), fitted_soh=float(slope*now+intercept), predicted_rul_cycles=remaining, predicted_crossing_cycle=now+remaining)


def power_forecast(history, threshold=70):
    """Robust bounded power-law fit; all supplied history, fixed parameters."""
    from scipy.optimize import least_squares
    h = history.sort_values('cycle')
    if len(h) < 10 or np.polyfit(h.cycle, h.soh_pct, 1)[0] >= -1e-6:
        return None
    x = h.cycle.to_numpy(dtype=float)/100
    y = h.soh_pct.to_numpy(dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        return None
    # Fixed bounds and robust loss, not selected on backtest scores.
    initial = [float(np.clip(np.median(y[:5]),60.01,119.99)),10.,1.3]
    fit = least_squares(lambda p: p[0]-p[1]*x**p[2]-y, initial,
                        bounds=([60,1e-6,.5],[120,150,3]),
                        loss='soft_l1', f_scale=.8, max_nfev=2000)
    if not fit.success:
        return None
    q0,a,b = map(float,fit.x)
    now = float(h.cycle.iloc[-1])
    crossing = 0. if threshold>=q0 else 100*((q0-threshold)/a)**(1/b)
    remaining = max(0.,crossing-now)
    return dict(kind='power',q0=q0,a=a,b=b,fitted_soh=q0-a*(now/100)**b,
                predicted_rul_cycles=remaining,predicted_crossing_cycle=now+remaining,
                parameter_at_bound=bool(np.any(fit.active_mask)))

MODELS = ('recent_30','all_history','power_law')

def forecast_model(history, threshold, model):
    if model == 'power_law':
        return power_forecast(history,threshold)
    if model not in MODELS:
        raise ValueError('Unknown forecast model')
    return forecast(history,threshold,30 if model=='recent_30' else 10000)

def forecast_value(f, x):
    x = np.asarray(x)
    return f['q0']-f['a']*(x/100)**f['b'] if f['kind']=='power' else f['slope']*x+f['intercept']

def first_crossing(group, threshold):
    hits = group[group.soh_pct <= threshold]
    return None if hits.empty else int(hits.cycle.iloc[0])

def main():
    df = pd.read_csv(ROOT/'data/processed/cycles.csv')
    rows=[]
    for cell,g in df.groupby('cell'):
        for threshold in (70,80):
            actual=first_crossing(g,threshold)
            for origin in (40,60,80):
                if actual is not None and origin>=actual: continue
                for model in MODELS:
                    f=forecast_model(g[g.cycle<=origin],threshold,model)
                    rows.append(dict(cell=cell,threshold_pct=threshold,origin_cycle=origin,model=model,observed_crossing_cycle=actual,censored=actual is None,actual_rul_cycles=None if actual is None else actual-origin,observed_rul_lower_bound=int(g.cycle.max())-origin if actual is None else None,absolute_error_cycles=None if actual is None or f is None else abs(f['predicted_rul_cycles']-(actual-origin)),**(f or {})))
    out=pd.DataFrame(rows)
    out.to_csv(ROOT/'reports/rul_backtests.csv',index=False)
    out.groupby(['threshold_pct','model','cell'],as_index=False).agg(mae_cycles=('absolute_error_cycles','mean'),scored_origins=('absolute_error_cycles','count')).to_csv(ROOT/'reports/rul_by_cell.csv',index=False)
    metrics=[]
    for (threshold,model),g in out.groupby(['threshold_pct','model']):
        valid=g.absolute_error_cycles.dropna()
        metrics.append(dict(threshold_pct=int(threshold),model=model,scored_origins=len(valid),unscored_origins=int(g.absolute_error_cycles.isna().sum()),mae_cycles=float(valid.mean()) if len(valid) else None,median_error_cycles=float(valid.median()) if len(valid) else None,scored_cells=int(g.loc[g.absolute_error_cycles.notna(),'cell'].nunique())))
    (ROOT/'reports/rul_metrics.json').write_text(json.dumps(metrics,indent=2))
    print(json.dumps(metrics,indent=2))


# A static comparison figure supplements the interactive dashboard.
def plot_forecasts(df):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (cell,g) in zip(axes.ravel(),df.groupby('cell')):
        origin=60
        h=g[g.cycle<=origin]
        f=forecast(h,70)
        ax.plot(g.cycle,g.soh_pct,color='gray',alpha=.6,label='Future actual (comparison)')
        ax.plot(h.cycle,h.soh_pct,color='teal',label='Observed through cycle 60')
        if f:
            end=min(400,f['predicted_crossing_cycle'])
            x=np.array([origin,end])
            ax.plot(x,f['slope']*x+f['intercept'],'--',color='darkorange',label='Recent-trend forecast')
        nonlinear=power_forecast(h,70)
        if nonlinear:
            x=np.linspace(origin,min(400,nonlinear['predicted_crossing_cycle']),100)
            ax.plot(x,forecast_value(nonlinear,x),'--',color='purple',label='Robust power-law forecast')
        ax.axhline(70,color='gray',linestyle=':')
        ax.set(title=cell,xlabel='Discharge cycle',ylabel='SOH (%)',ylim=(45,110))
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Forecast at cycle 60: compare linear and nonlinear aging')
    fig.tight_layout()
    fig.savefig(ROOT/'reports/forecast.png',dpi=150)
    plt.close(fig)

if __name__=='__main__': main()
