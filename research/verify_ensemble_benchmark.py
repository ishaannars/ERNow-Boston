"""Verify benchmark provenance, target alignment and chronological blend selection."""
import json
import numpy as np
import pandas as pd
import ensemble_benchmark as e


def main():
    assert len(e.weights())==35
    assert np.all(e.weights()>=0) and np.allclose(e.weights().sum(axis=1),1)
    assert e.NAMES[0]=='Persistence baseline'
    assert json.loads(e.MANIFEST.read_text())==e.provenance()
    result=json.loads(e.OUTPUT.read_text())
    assert result['source_sha256']==e.provenance()
    data=pd.read_csv(e.CACHE,dtype={'facility_id':str})
    assert np.isfinite(data[e.NAMES].to_numpy()).all()
    assert np.allclose(data[e.NAMES[0]],data.lag1)
    df,snaps=e.n.make_transitions(e.n.load_panel())
    folds=[f.reset_index(drop=True) for _,f in data.groupby('target_release',sort=True)]
    saved=json.loads(e.n.RESULTS_PATH.read_text())
    for fold in folds:
        release=fold.target_release.iloc[0]
        k=next(k for k in range(2,len(snaps)-1) if str(pd.Timestamp(snaps[k+1]).date())==release)
        target=df[(df.t==k)&df.target.notna()]
        assert len(fold)==len(target)
        aligned=fold.merge(target[['facility_id','target']],on='facility_id',validate='one_to_one',suffixes=('','_source'))
        assert np.allclose(aligned.target,aligned.target_source)
        old=next(r for r in saved['rolling'] if r['target_release']==release)
        for name in e.NAMES:
            actual=np.mean(np.abs(fold.target-fold[name]))
            assert np.isclose(actual,old['maes'][name],rtol=1e-4,atol=1e-4)
    for i,row in enumerate(result['chronological_evaluations'],start=2):
        assert all(d<row['release'] for d in row['training_releases'])
        chosen,_=e.select(folds[:i])
        assert np.allclose(chosen,[row['weights'][name] for name in e.NAMES])
        assert row['selected']['county_regret_min']>=0
        assert row['boston_assumed_drive']['points']==2001
    # Exercise ranking semantics independently: a ten-minute wrong-choice regret;
    # choosing either truly tied minimum is a correct decision.
    toy=pd.DataFrame({'state':['MA']*3,'county':['x']*3,'target':[10,20,30]})
    assert e.metrics(toy,np.array([30,10,20]))['county_regret_min']==10
    toy['target']=[10,10,30]
    assert e.metrics(toy,np.array([30,10,20]))['county_shortest_accuracy_tie_aware']==1
    assert result['production_changed'] is False
    print('PASS: source/cache hashes, all seven target alignments/base fits, chronological weights, 35 convex candidates, regret/tie semantics and Boston coverage')

if __name__=='__main__':main()
