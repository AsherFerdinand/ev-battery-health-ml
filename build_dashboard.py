import json
import pandas as pd
from pipeline import ROOT
from forecast import forecast_model, MODELS, plot_forecasts, main as backtest

def main():
    backtest()
    df=pd.read_csv(ROOT/'data/processed/cycles.csv')
    plot_forecasts(df)
    flags=pd.read_csv(ROOT/'reports/anomaly_flags.csv')
    df=df.merge(flags[['cell','cycle','flag']],on=['cell','cycle'],validate='one_to_one')
    pred=pd.read_csv(ROOT/'reports/predictions.csv')
    pred=pred[(pred.split=='temporal_70_30')&(pred.model=='ridge')]
    df=df.merge(pred[['cell','cycle','predicted_soh_pct']],on=['cell','cycle'],how='left',validate='one_to_one')
    forecasts={cell:{str(int(c)):{str(t):{m:forecast_model(g[g.cycle<=c],t,m) for m in MODELS} for t in (70,80)} for c in g.cycle if c>=30} for cell,g in df.groupby('cell')}
    payload=dict(rows=json.loads(df.to_json(orient='records')),forecasts=forecasts,metrics=json.loads((ROOT/'reports/rul_metrics.json').read_text()))
    payload['soh_predictions']=json.loads(pd.read_csv(ROOT/'reports/window_predictions.csv').to_json(orient='records'))
    payload['soh_metrics']=json.loads(pd.read_csv(ROOT/'reports/window_metrics.csv').to_json(orient='records'))
    template=(ROOT/'dashboard_template.html').read_text(encoding='utf-8-sig')
    (ROOT/'reports/dashboard.html').write_text(template.replace('__DATA__',json.dumps(payload,allow_nan=False)),encoding='utf-8')
    print('Dashboard ready: reports/dashboard.html')
if __name__=='__main__': main()

