"""Retrospective chronological blend benchmark; never changes production/UI.

OOF base fits use only earlier releases. Blend weights use only prior OOF folds.
Existing releases have already been inspected; results need future confirmation.
"""
import sys,json,itertools,argparse,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import national_model as n
OUTPUT=ROOT/'data/ensemble_benchmark.json'
CACHE=ROOT/'data/ensemble_oof_predictions.csv.gz'
MANIFEST=ROOT/'data/ensemble_oof_manifest.json'
NAMES=list(n.candidate_models())


def weights():
    # Predeclared bounded search: convex weights in 25-percentage-point increments.
    return np.array([w for w in itertools.product(range(5),repeat=4) if sum(w)==4],dtype=float)/4


def groups(frame):
    return [g.index.to_numpy() for _,g in frame.groupby(['state','county']) if len(g)>=3]


def metrics(frame,prediction):
    y=frame.target.to_numpy()
    regret=[];hits=[]
    for idx in groups(frame):
        pick=idx[np.argmin(prediction[idx])]
        loss=float(y[pick]-y[idx].min())
        regret.append(loss);hits.append(float(loss==0))
    return {'MAE':float(mean_absolute_error(y,prediction)),
            'county_regret_min':float(np.mean(regret)),
            'county_shortest_accuracy_tie_aware':float(np.mean(hits)),
            'counties':len(regret),'county_regrets':regret}


def score(folds,w):
    values=[metrics(f,f[NAMES].to_numpy()@w) for f in folds]
    # Equal release weighting prevents populous years dominating selection.
    return {k:float(np.mean([v[k] for v in values])) for k in
            ['MAE','county_regret_min','county_shortest_accuracy_tie_aware']}


def select(prior):
    base=score(prior,np.array([1,0,0,0]))
    candidates=[]
    for w in weights():
        result=score(prior,w)
        # Ranking is primary; retain the existing 2% error-improvement requirement.
        # Otherwise leave production-eligible selection at Persistence.
        if result['MAE']<=base['MAE']*(1-n.PROMOTION_MARGIN) and result['county_regret_min']<base['county_regret_min'] and result['county_shortest_accuracy_tie_aware']>=base['county_shortest_accuracy_tie_aware']:
            candidates.append((result['county_regret_min'],result['MAE'],w,result))
    if not candidates:
        return np.array([1,0,0,0]),base
    best=min(candidates,key=lambda x:(x[0],x[1]))
    return best[2],best[3]


def build_predictions():
    panel=n.load_panel();df,snaps=n.make_transitions(panel)
    labeled=df[df.target.notna()];folds=[]
    for k in range(2,int(labeled.t.max())+1):
        train,test=labeled[labeled.t<k],labeled[labeled.t==k]
        if len(train)<1000 or len(test)<500:continue
        fold=test[['facility_id','state','county','target','lag1']].copy()
        fold['target_release']=str(pd.Timestamp(snaps[k+1]).date())
        for name,model in n.candidate_models().items():
            model.fit(train);fold[name]=model.predict(test)
        folds.append(fold)
        print('Out-of-time predictions: '+fold.target_release.iloc[0],flush=True)
    data=pd.concat(folds,ignore_index=True)
    data.to_csv(CACHE,index=False,compression='gzip')
    return data


def provenance():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [n.PANEL_PATH,ROOT/'national_model.py',CACHE]}


def boston_metrics(frame,prediction):
    hospitals=pd.read_csv(n.BOSTON_CSV,dtype={'cms_provider_id':str})
    hospitals=hospitals[hospitals.ed_type=='general'].merge(frame,left_on='cms_provider_id',right_on='facility_id').reset_index(drop=True)
    if len(hospitals)<3:return None
    pred_map=dict(zip(frame.facility_id,prediction))
    lat,lon=np.meshgrid(np.linspace(42.28,42.39,45),np.linspace(-71.16,-71.02,45))
    lat,lon=lat.ravel()[:,None],lon.ravel()[:,None]
    distances=2*3958.8*np.arcsin(np.sqrt(np.sin(np.radians(hospitals.latitude.to_numpy()-lat)/2)**2+
        np.cos(np.radians(lat))*np.cos(np.radians(hospitals.latitude.to_numpy()))*
        np.sin(np.radians(hospitals.longitude.to_numpy()-lon)/2)**2))
    drive=distances[distances.min(axis=1)<=4]*1.35/18*60+3
    observed=drive+hospitals.target.to_numpy()
    prediction=np.array([pred_map[i] for i in hospitals.facility_id])
    options={'selected':drive+prediction,'persistence':drive+hospitals.lag1.to_numpy(),'closest':drive}
    out={}
    for name,estimates in options.items():
        pick=estimates.argmin(axis=1)
        regret=observed[np.arange(len(observed)),pick]-observed.min(axis=1)
        out[name]={'mean_regret_min':float(regret.mean()),'p90_regret_min':float(np.percentile(regret,90)),
            'shortest_total_accuracy':float(np.mean(regret<=1e-8))}
    out['selected']['hospital_median_MAE']=float(mean_absolute_error(hospitals.target,prediction))
    out['persistence']['hospital_median_MAE']=float(mean_absolute_error(hospitals.target,hospitals.lag1))
    return {'points':len(drive),'hospitals':len(hospitals),
        'observed_shortest_hospitals':hospitals.iloc[np.unique(observed.argmin(axis=1))].hospital.tolist(),'metrics':out,
        'scope':'Current seven-general-ER ID/coordinate set applied retrospectively; grid extends outside Boston; distance-based drive assumptions, not observed trips or patient outcomes'}


def main(reuse=False):
    if reuse:
        assert json.loads(MANIFEST.read_text())==provenance(),'OOF source changed; rebuild without --reuse'
        data=pd.read_csv(CACHE,dtype={'facility_id':str})
    else:
        data=build_predictions()
        MANIFEST.write_text(json.dumps(provenance(),indent=2)+'\n')
    folds=[f.reset_index(drop=True) for _,f in data.groupby('target_release',sort=True)]
    evaluations=[]
    # First two releases are historical weight-training burn-in, not evaluation.
    for i in range(2,len(folds)):
        earlier=folds[:i];current=folds[i]
        chosen,training=select(earlier)
        pred=current[NAMES].to_numpy()@chosen
        evaluation=metrics(current,pred)
        baseline=metrics(current,current.lag1.to_numpy())
        evaluations.append({'release':current.target_release.iloc[0],
            'training_releases':[f.target_release.iloc[0] for f in earlier],
            'weights':dict(zip(NAMES,chosen.tolist())),'training_score':training,
            'selected':evaluation,'persistence':baseline,'boston_assumed_drive':boston_metrics(current,pred)})
        print('Chronological selection evaluated: '+current.target_release.iloc[0],flush=True)
    # All folds can be used to nominate a FUTURE research candidate; not an unseen test.
    future_w,future_training=select(folds)
    all_candidates=[]
    for w in weights():
        all_candidates.append({'weights':dict(zip(NAMES,w.tolist())),'historical_score':score(folds,w)})
    all_candidates.sort(key=lambda x:(x['historical_score']['county_regret_min'],x['historical_score']['MAE']))
    summary={}
    for key in ['MAE','county_regret_min','county_shortest_accuracy_tie_aware']:
        summary[key]={method:float(np.mean([r[method][key] for r in evaluations])) for method in ['selected','persistence']}
    # Paired county bootstrap within each release; no claims of independent years.
    rng=np.random.default_rng(n.SEED)
    draws=[]
    for r in evaluations:
        difference=np.array(r['persistence']['county_regrets'])-np.array(r['selected']['county_regrets'])
        draws.append(difference[rng.integers(0,len(difference),(2000,len(difference)))].mean(axis=1))
    gain=np.mean(draws,axis=0)
    result={'scope':'Retrospective saved-panel hospital-median county decision benchmark; excludes driving, clinical suitability and patient outcomes',
            'protocol':{'candidate_count':len(weights()),'weight_increment':0.25,'burn_in_releases':2,
                'primary_metric':'Equal-release mean county median regret',
                'promotion_gate':'Prior-fold MAE improves >=2%, county regret improves, tie-aware shortest selection does not worsen',
                'future_validation_required':True},
            'model_order':NAMES,'chronological_evaluations':evaluations,'summary':summary,
            'paired_county_bootstrap_regret_gain_ci95':np.percentile(gain,[2.5,97.5]).tolist(),
            'future_research_weights':dict(zip(NAMES,future_w.tolist())),
            'future_research_training_score':future_training,
            'retrospective_candidates_best_to_worst':all_candidates,
            'source_sha256':provenance(),'production_changed':False}
    OUTPUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'summary':summary,'future_weights':result['future_research_weights'],'regret_gain_ci95':result['paired_county_bootstrap_regret_gain_ci95']},indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reuse',action='store_true')
    main(parser.parse_args().reuse)
