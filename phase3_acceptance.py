"""Explicit acceptance gate for a configuration (independent of unit tests)."""
import argparse,json
import pandas as pd
from phase3 import OUT,flag_mae

def check(model,window='15min',feature_set='base'):
    m=pd.read_csv(OUT/'cell_metrics.csv')
    selected=m[(m.experiment=='benchmark')&(m.model==model)&(m.window==window)&(m.feature_set==feature_set)]
    if len(selected)!=8:raise ValueError('Expected four battery results per protocol, eight total')
    failures=selected[selected.mae_pp.map(flag_mae)]
    return {'model':model,'window':window,'feature_set':feature_set,'evaluated_cell_protocol_results':len(selected),'passed_all':failures.empty,'failures':json.loads(failures.to_json(orient='records'))}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',required=True,choices=['ridge','random_forest','hist_gradient_boosting']);p.add_argument('--window',default='15min');p.add_argument('--feature-set',default='base');p.add_argument('--strict',action='store_true',help='Exit 1 when any selected battery MAE exceeds 5 pp')
    args=p.parse_args();result=check(args.model,args.window,args.feature_set);print(json.dumps(result,indent=2))
    if args.strict and not result['passed_all']:raise SystemExit(1)
if __name__=='__main__':main()
