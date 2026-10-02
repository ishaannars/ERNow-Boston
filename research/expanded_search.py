"""Bounded retrospective search. No production or UI mutations.

Protocol: seven base OOF folds, first two burn-in, choose using strictly prior
OOF rows with the SAME 2%-MAE + regret + tie-aware ranking gate. Compare five
later releases. Confirmation requires new future outcomes.
"""
import sys,json,itertools,hashlib
from pathlib import Path
import sklearn,scipy
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge,HuberRegressor
from sklearn.pipeline import Pipeline

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'research'))
import national_model as n
import ensemble_benchmark as e

OUT=ROOT/'data/expanded_model_search.json'
CACHE=ROOT/'data/expanded_oof_predictions.csv.gz'


class Variant:
    def __init__(self,cols,kind='boost',alpha=10,loss='squared_error',leaves=15,decay=False):
        self.cols,self.kind,self.alpha,self.loss,self.leaves,self.decay=cols,kind,alpha,loss,leaves,decay
    def fit(self,df):
        if self.kind=='boost':
            self.pipe=n._gbm_pipe(self.cols)
            self.pipe['m'].set_params(loss=self.loss,max_leaf_nodes=self.leaves,max_iter=250,l2_regularization=5.)
        else:
            model=Ridge(alpha=self.alpha) if self.kind=='ridge' else HuberRegressor(epsilon=1.35,alpha=1.,max_iter=500)
            self.pipe=Pipeline([('pre',n._pre(self.cols)),('m',model)])
        kw={}
        if self.decay:kw['m__sample_weight']=np.power(0.5,(df.t.max()-df.t.to_numpy())/2)
        self.pipe.fit(df[self.cols],df.target-df.lag1,**kw)
        return self
    def predict(self,df):return df.lag1.to_numpy()+self.pipe.predict(df[self.cols])


def variants():
    full=n.FEATURE_GROUPS['+ geography & peers (full)']
    history=n.FEATURE_GROUPS['History only']
    for alpha in [1,100,1000]:
        yield f'Ridge alpha {alpha}',Variant(full,'ridge',alpha=alpha)
    yield 'Recency-weighted ridge',Variant(full,'ridge',alpha=100,decay=True)
    yield 'Robust Huber history',Variant(history,'huber')
    for cols,label in [(history,'history'),(full,'full')]:
        for loss in ['squared_error','absolute_error']:
            for leaves in [7,15]:
                yield f'Boost {label} {loss} leaves {leaves}',Variant(cols,loss=loss,leaves=leaves)
    yield 'Recency-weighted absolute boost',Variant(full,loss='absolute_error',leaves=15,decay=True)


def compact(f,p):
    v=e.metrics(f,p)
    return {k:v[k] for k in ['MAE','county_regret_min','county_shortest_accuracy_tie_aware']}


def eligible(candidate,baseline):
    return (candidate['MAE']<=baseline['MAE']*(1-n.PROMOTION_MARGIN)
            and candidate['county_regret_min']<baseline['county_regret_min']
            and candidate['county_shortest_accuracy_tie_aware']>=baseline['county_shortest_accuracy_tie_aware'])


def main():
    assert json.loads(e.MANIFEST.read_text())==e.provenance()
    df,snaps=n.make_transitions(n.load_panel());labeled=df[df.target.notna()]
    base=pd.read_csv(e.CACHE,dtype={'facility_id':str})
    folds=[];variant_names=[name for name,_ in variants()]
    for release,old in base.groupby('target_release',sort=True):
        k=next(k for k in range(2,len(snaps)-1) if str(pd.Timestamp(snaps[k+1]).date())==release)
        train=labeled[labeled.t<k];test=labeled[labeled.t==k].copy()
        old=old.set_index('facility_id')
        test=test.set_index('facility_id').loc[old.index].reset_index()
        fold=old.reset_index().copy()
        for name,model in variants():
            model.fit(train);fold[name]=model.predict(test)
        # Learned offset/trend coefficients: actual older transitions only.
        delta=train.delta.fillna(0).to_numpy();change=(train.target-train.lag1).to_numpy()
        for damp in [-.2,-.1,0,.1,.2,.3]:
            bias=float(np.median(change-damp*delta))
            name=f'Robust offset trend {damp}'
            fold[name]=test.lag1.to_numpy()+damp*test.delta.fillna(0).to_numpy()+bias
            if name not in variant_names:variant_names.append(name)
        folds.append(fold.reset_index(drop=True))
        print(release+' expanded OOF fits done',flush=True)
    pd.concat(folds,ignore_index=True).to_csv(CACHE,index=False,compression='gzip')
    names=e.NAMES+variant_names
    # 286 10%-increment convex blends of the existing four base models.
    blend_weights=[np.array(w)/10 for w in itertools.product(range(11),repeat=4) if sum(w)==10]
    predictions={}
    for name in names:predictions[name]=[f[name].to_numpy() for f in folds]
    for w in blend_weights:
        name='Blend '+','.join(f'{x:.1f}' for x in w)
        predictions[name]=[f[e.NAMES].to_numpy()@w for f in folds]
    # Regularized stacking fitted only to strictly earlier OOF forecasts.
    # Base residuals relative to Persistence avoid hospital-level intercept confounding.
    for alpha in [10,100,1000]:
        name=f'OOF residual stack ridge {alpha}';predictions[name]=[]
        for i,f in enumerate(folds):
            if i<2:
                predictions[name].append(f.lag1.to_numpy());continue
            prior=pd.concat(folds[:i],ignore_index=True)
            x=prior[e.NAMES[1:]].to_numpy()-prior.lag1.to_numpy()[:,None]
            y=prior.target.to_numpy()-prior.lag1.to_numpy()
            stack=Ridge(alpha=alpha).fit(x,y)
            current=f[e.NAMES[1:]].to_numpy()-f.lag1.to_numpy()[:,None]
            predictions[name].append(f.lag1.to_numpy()+stack.predict(current))
    scores={name:[compact(f,p) for f,p in zip(folds,ps)] for name,ps in predictions.items()}
    evaluations=[]
    baseline='Persistence baseline'
    for i in range(2,len(folds)):
        mean=lambda name:{key:float(np.mean([s[key] for s in scores[name][:i]])) for key in scores[name][0]}
        base_score=mean(baseline)
        allowed=[name for name in predictions if name!=baseline and eligible(mean(name),base_score)]
        best=min(allowed,key=lambda name:(mean(name)['county_regret_min'],mean(name)['MAE'])) if allowed else baseline
        evaluations.append({'release':folds[i].target_release.iloc[0],
            'training_releases':[f.target_release.iloc[0] for f in folds[:i]],'selected_candidate':best,
            'training_score':mean(best),'training_baseline':base_score,
            'evaluation':scores[best][i],'baseline':scores[baseline][i],
            'boston_assumed_drive':e.boston_metrics(folds[i],predictions[best][i])})
        print(evaluations[-1]['release']+' selected '+best,flush=True)
    avg=lambda name,start=0:{key:float(np.mean([s[key] for s in scores[name][start:]])) for key in scores[name][0]}
    retrospective=sorted([{'candidate':name,'score':avg(name),'later_folds_score':avg(name,2)} for name in predictions],key=lambda row:(row['score']['MAE'],row['score']['county_regret_min']))
    future_allowed=[r for r in retrospective if r['candidate']!=baseline and eligible(r['score'],avg(baseline))]
    nominee=min(future_allowed,key=lambda r:(r['score']['county_regret_min'],r['score']['MAE'])) if future_allowed else next(r for r in retrospective if r['candidate']==baseline)
    summary={key:{method:float(np.mean([row[method][key] for row in evaluations])) for method in ['evaluation','baseline']} for key in scores[baseline][0]}
    final={'protocol':{'candidate_count':len(predictions),'new_base_variant_count':len(variant_names),'convex_blends':len(blend_weights),
            'gate':'Strictly prior OOF folds: MAE >=2% better, regret better, tie-aware shortest accuracy not worse',
            'burn_in':2,'evaluation_folds':5,'retrospective':True,'new_future_confirmation_required':True},
        'chronological_evaluations':evaluations,'summary':summary,'future_research_nominee':nominee,
        'all_candidate_scores':retrospective,'production_changed':False,
        'source_sha256':e.provenance(),'expanded_cache_sha256':hashlib.sha256(CACHE.read_bytes()).hexdigest(),
        'environment':{'python':sys.version.split()[0],'scikit_learn':sklearn.__version__,'pandas':pd.__version__,'numpy':np.__version__,'scipy':scipy.__version__}}
    OUT.write_text(json.dumps(final,indent=2)+'\n')
    print(json.dumps({'protocol':final['protocol'],'summary':summary,'nominee':nominee},indent=2),flush=True)

if __name__=='__main__':main()
