"""Additional retrospective pooling/correction variants and production-gate audit.
No production mutation. All labels and feature windows follow existing source.
"""
import sys,json,hashlib,itertools
from pathlib import Path
import sklearn,scipy
import numpy as np,pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import HuberRegressor,Ridge
from sklearn.preprocessing import PolynomialFeatures,StandardScaler
from sklearn.pipeline import Pipeline
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'research'))
import national_model as n
import ensemble_benchmark as e
import expanded_search as x


class ContinuousPooling:
    def __init__(self,decay=False,intercept=False):self.decay,self.intercept=decay,intercept
    def fit(self,df):
        a=df[['delta','state_mean_gap','peer_mean_gap']].fillna(0).to_numpy()
        if self.intercept:a=np.column_stack([a,np.ones(len(a))])
        y=(df.target-df.lag1).to_numpy()
        w=np.power(.5,(df.t.max()-df.t.to_numpy())/2) if self.decay else np.ones(len(a))
        bounds=[(-.3,.3),(0,.5),(0,.5)]+([(-20,20)] if self.intercept else [])
        loss=lambda b:np.average(np.abs(y-a@b),weights=w)
        opt=minimize(loss,np.zeros(a.shape[1]),method='Powell',bounds=bounds,options={'maxiter':300,'xtol':1e-5,'ftol':1e-7})
        if not opt.success:raise RuntimeError(opt.message)
        self.coef=opt.x
        return self
    def predict(self,df):
        a=df[['delta','state_mean_gap','peer_mean_gap']].fillna(0).to_numpy()
        if self.intercept:a=np.column_stack([a,np.ones(len(a))])
        return df.lag1.to_numpy()+a@self.coef


class PolyCorrection:
    def __init__(self,alpha):self.alpha=alpha
    def fit(self,df):
        self.pipe=Pipeline([('poly',PolynomialFeatures(2,include_bias=False)),('scale',StandardScaler()),('ridge',Ridge(alpha=self.alpha))])
        self.pipe.fit(df[['delta','state_mean_gap','peer_mean_gap']].fillna(0),df.target-df.lag1)
        return self
    def predict(self,df):return df.lag1.to_numpy()+self.pipe.predict(df[['delta','state_mean_gap','peer_mean_gap']].fillna(0))


def variants():
    for decay,intercept in itertools.product([False,True],repeat=2):
        yield f'Continuous pooling recency={decay} offset={intercept}',ContinuousPooling(decay,intercept)
    yield 'Robust Huber full',x.Variant(n.FEATURE_GROUPS['+ geography & peers (full)'],'huber')
    for alpha in [100,1000,10000]:yield f'Polynomial correction ridge {alpha}',PolyCorrection(alpha)


def mean_score(folds,predictions):
    return {key:float(np.mean([x.compact(f,p)[key] for f,p in zip(folds,predictions)])) for key in x.compact(folds[0],predictions[0])}


def main():
    prior=json.loads((ROOT/'data/expanded_model_search.json').read_text())
    assert prior['source_sha256']==e.provenance()
    cache=ROOT/'data/expanded_oof_predictions.csv.gz'
    assert hashlib.sha256(cache.read_bytes()).hexdigest()==prior['expanded_cache_sha256']
    data=pd.read_csv(cache,dtype={'facility_id':str})
    df,snaps=n.make_transitions(n.load_panel());labeled=df[df.target.notna()]
    folds=[]
    for release,old in data.groupby('target_release',sort=True):
        k=next(k for k in range(2,len(snaps)-1) if str(pd.Timestamp(snaps[k+1]).date())==release)
        train=labeled[labeled.t<k];test=labeled[labeled.t==k].set_index('facility_id').loc[old.facility_id].reset_index()
        fold=old.reset_index(drop=True).copy()
        for name,model in variants():model.fit(train);fold[name]=np.maximum(1,model.predict(test))
        folds.append(fold)
        print(release+' continuous pooling and corrections complete',flush=True)
    pd.concat(folds,ignore_index=True).to_csv(ROOT/'data/final_accuracy_oof_predictions.csv.gz',index=False,compression='gzip')
    names=[c for c in folds[0].columns if c not in ['facility_id','state','county','target','lag1','target_release']]
    predictions={name:[f[name].to_numpy() for f in folds] for name in names}
    # Fixed finer convex blend grid, preserving the previous candidate definitions.
    for w in [np.array(w)/10 for w in itertools.product(range(11),repeat=4) if sum(w)==10]:
        predictions['Blend '+','.join(f'{v:.1f}' for v in w)]=[f[e.NAMES].to_numpy()@w for f in folds]
    for alpha in [10,100,1000]:
        name=f'OOF residual stack ridge {alpha}';predictions[name]=[]
        for i,f in enumerate(folds):
            if i<2:predictions[name].append(f.lag1.to_numpy());continue
            old=pd.concat(folds[:i],ignore_index=True)
            model=Ridge(alpha=alpha).fit(old[e.NAMES[1:]].to_numpy()-old.lag1.to_numpy()[:,None],old.target-old.lag1)
            predictions[name].append(f.lag1.to_numpy()+model.predict(f[e.NAMES[1:]].to_numpy()-f.lag1.to_numpy()[:,None]))
    scores={name:[x.compact(f,p) for f,p in zip(folds,ps)] for name,ps in predictions.items()}
    baseline='Persistence baseline';vi=len(folds)-2;ti=len(folds)-1
    base=scores[baseline][vi]
    rows=[]
    for name in predictions:
        v,t=scores[name][vi],scores[name][ti]
        rows.append({'candidate':name,'validation':v,'later_release':t,
            'validation_MAE_gain':1-v['MAE']/base['MAE'],
            'passes_MAE_gate':bool(v['MAE']<=base['MAE']*(1-n.PROMOTION_MARGIN)),
            'passes_joint_gate':bool(x.eligible(v,base))})
    rows.sort(key=lambda r:r['validation']['MAE'])
    # Selection uses validation ONLY; later release already inspected, label retrospective.
    eligible=[r for r in rows if r['passes_joint_gate']]
    selected=min(eligible,key=lambda r:(r['validation']['county_regret_min'],r['validation']['MAE'])) if eligible else next(r for r in rows if r['candidate']==baseline)
    rolling=[]
    for i in range(2,len(folds)):
        mean=lambda name:{key:float(np.mean([s[key] for s in scores[name][:i]])) for key in base}
        candidates=[name for name in predictions if x.eligible(mean(name),mean(baseline))]
        choice=min(candidates,key=lambda name:(mean(name)['county_regret_min'],mean(name)['MAE'])) if candidates else baseline
        rolling.append({'release':folds[i].target_release.iloc[0],'training_releases':[f.target_release.iloc[0] for f in folds[:i]],
            'candidate':choice,'score':scores[choice][i],'baseline':scores[baseline][i],
            'boston_assumed_drive':e.boston_metrics(folds[i],predictions[choice][i])})
    result={'scope':'Retrospective public hospital-median prediction/decision research; future confirmation required',
            'candidate_configurations':len(predictions),'new_variants':8,'validation_release':folds[vi].target_release.iloc[0],
            'later_release':folds[ti].target_release.iloc[0],
            'joint_gate':'Validation MAE improves at least 2%, county regret improves, tie-aware shortest accuracy does not worsen',
            'passes_MAE_gate_count':sum(r['passes_MAE_gate'] for r in rows),'passes_joint_gate_count':len(eligible),
            'selected_using_validation_only':selected,'all_validation_scores':rows,'rolling_selection':rolling,
            'source_sha256':e.provenance(),'final_cache_sha256':hashlib.sha256((ROOT/'data/final_accuracy_oof_predictions.csv.gz').read_bytes()).hexdigest(),
            'production_changed':False,
            'environment':{'python':sys.version.split()[0],'scikit_learn':sklearn.__version__,'pandas':pd.__version__,'numpy':np.__version__,'scipy':scipy.__version__}}
    (ROOT/'data/final_accuracy_search.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['candidate_configurations','passes_MAE_gate_count','passes_joint_gate_count','selected_using_validation_only']},indent=2),flush=True)

if __name__=='__main__':main()
