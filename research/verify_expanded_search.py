"""Audit source-aligned scores and eligibility; does not refit all base variants."""
import sys,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.linear_model import Ridge
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'research'))
import ensemble_benchmark as e
import expanded_search as x


def main():
    path=ROOT/'data/final_accuracy_search.json';r=json.loads(path.read_text())
    assert r['source_sha256']==e.provenance()
    cache=ROOT/'data/final_accuracy_oof_predictions.csv.gz'
    assert hashlib.sha256(cache.read_bytes()).hexdigest()==r['final_cache_sha256']
    p=pd.read_csv(cache,dtype={'facility_id':str})
    folds=[f.reset_index(drop=True) for _,f in p.groupby('target_release',sort=True)]
    original=pd.read_csv(e.CACHE,dtype={'facility_id':str})
    merged=p.merge(original[['facility_id','target_release','target']],on=['facility_id','target_release'],validate='one_to_one',suffixes=('','_source'))
    assert len(merged)==len(original)==len(p)
    assert np.allclose(merged.target,merged.target_source)
    v,t=folds[-2:];base=x.compact(v,v.lag1.to_numpy())
    pass_count=0
    for row in r['all_validation_scores']:
        name=row['candidate']
        if name.startswith('Blend '):
            w=np.array([float(s) for s in name[6:].split(',')])
            assert np.all(w>=0) and np.isclose(w.sum(),1)
            pv=v[e.NAMES].to_numpy()@w;pt=t[e.NAMES].to_numpy()@w
        elif name.startswith('OOF residual stack'):
            alpha=int(name.split()[-1]);pred=[]
            for i in [len(folds)-2,len(folds)-1]:
                earlier=pd.concat(folds[:i],ignore_index=True);current=folds[i]
                model=Ridge(alpha=alpha).fit(earlier[e.NAMES[1:]].to_numpy()-earlier.lag1.to_numpy()[:,None],earlier.target-earlier.lag1)
                pred.append(current.lag1.to_numpy()+model.predict(current[e.NAMES[1:]].to_numpy()-current.lag1.to_numpy()[:,None]))
            pv,pt=pred
        else:pv=v[name].to_numpy();pt=t[name].to_numpy()
        for actual,saved in [(x.compact(v,pv),row['validation']),(x.compact(t,pt),row['later_release'])]:
            for key in saved:assert np.isclose(actual[key],saved[key],rtol=1e-8,atol=1e-8),(name,key)
        assert row['passes_MAE_gate']==(row['validation']['MAE']<=base['MAE']*.98)
        assert row['passes_joint_gate']==x.eligible(row['validation'],base)
        pass_count+=row['passes_MAE_gate']
    assert pass_count==r['passes_MAE_gate_count']==4
    assert r['passes_joint_gate_count']==0
    assert r['selected_using_validation_only']['candidate']=='Persistence baseline'
    for row in r['rolling_selection']:
        assert all(s<row['release'] for s in row['training_releases'])
    assert r['production_changed'] is False
    # The gate rejects a lower-error candidate when regret worsens.
    good={'MAE':9,'county_regret_min':2,'county_shortest_accuracy_tie_aware':.8}
    assert not x.eligible({**good,'MAE':8,'county_regret_min':3},good)
    assert x.eligible({**good,'MAE':8,'county_regret_min':1},good)
    print('PASS: target/source/cache alignment, all 321 candidate validation and later-release scores, 2% and ranking gates, chronological selection and unchanged production decision')

if __name__=='__main__':main()
