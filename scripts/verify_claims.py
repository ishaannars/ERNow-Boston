"""Reproduce quantitative claims from the saved panel; optional model refits.

Run `python scripts/verify_claims.py --refit` for the full statistical check.
Raw CMS archive verification is separate: the original zip files are not in Git.
"""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import national_model as n
import record_decision_time as timing


def close(actual, expected, name, tolerance=1e-6):
    if not np.isclose(actual, expected, atol=tolerance, rtol=tolerance):
        raise AssertionError(f"{name}: recomputed {actual}, saved {expected}")


def main(refit=False, rolling=False):
    results = json.loads((ROOT / 'data/national_results.json').read_text())
    panel = n.load_panel()
    df, snaps = n.make_transitions(panel)
    labeled = df[df.target.notna()]
    last = int(labeled.t.max())
    train, valid, test = (labeled[labeled.t <= last - 2], labeled[labeled.t == last - 1], labeled[labeled.t == last])
    for key, value in [('total_rows', len(labeled)), ('hospitals', labeled.facility_id.nunique()), ('train_rows', len(train)), ('validation_rows', len(valid)), ('test_rows', len(test))]:
        close(value, results['split'][key], key)
    models = {r['model']: r for r in results['models']}
    baseline = models['Persistence baseline']
    close(mean_absolute_error(test.target, test.lag1), baseline['MAE'], 'persistence test MAE')
    close(r2_score(test.target, test.lag1), baseline['R2'], 'persistence test R2')
    rank = n.ranking_eval(test.assign(pred=test.lag1), 'pred')
    for key, value in rank.items():
        close(value, results['ranking']['persistence'][key], 'ranking ' + key)
    gain = 1 - models[results['best_learned_model']]['validation_MAE'] / baseline['validation_MAE']
    assert (gain >= results['promotion_margin']) == results['learned_model_promoted']
    latest = panel[panel.snapshot == panel.snapshot.max()]
    close(latest.op18b.notna().sum(), results['evidence']['hospitals_with_op18b_latest'], 'latest reporting hospitals')
    close(latest[['op18b','op22']].corr(method='spearman').iloc[0,1], results['structure']['spearman_op18b_vs_left_without_being_seen'], 'ED-time / OP22 association')
    lag = panel.dropna(subset=['op18b_period_end']).groupby('snapshot').op18b_period_end.max()
    months = (lag.index.to_series() - lag).dt.days / 30.44
    close(months.min(), results['evidence']['data_lag_months_min'], 'minimum archive lag')
    close(months.max(), results['evidence']['data_lag_months_max'], 'maximum archive lag')
    forecast = pd.read_csv(ROOT / 'data/boston_forecast.csv', dtype={'cms_provider_id':str})
    saved = forecast.merge(latest, left_on='cms_provider_id', right_on='facility_id')
    assert len(saved) == len(forecast)
    assert np.allclose(saved.latest_op18b, saved.op18b)
    assert np.allclose(saved.left_without_seen_pct, saved.op22)
    assert (forecast.lo80 <= forecast.forecast_op18b).all() and (forecast.hi80 >= forecast.forecast_op18b).all()
    if results['selected_model'] == 'Persistence baseline':
        assert np.allclose(forecast.forecast_op18b, forecast.latest_op18b)
    assert timing.summary()['ernow'] == {'median_seconds':9.0,'participants':5}
    assert timing.summary()['quick'] == {'median_seconds':20.0,'participants':5}
    assert timing.summary()['full'] == {'median_seconds':381.0,'participants':1}
    print('Counts, baseline MAE/R², county ranking, promotion rule, data lag, Boston medians/OP22, range containment, association and timing: PASS', flush=True)
    if refit:
        fitted = {}
        for name, model in n.candidate_models().items():
            model.fit(train)
            fitted[name] = model
            close(mean_absolute_error(valid.target, model.predict(valid)), models[name]['validation_MAE'], name + ' validation MAE')
            close(mean_absolute_error(test.target, model.predict(test)), models[name]['MAE'], name + ' test MAE')
            close(r2_score(test.target, model.predict(test)), models[name]['R2'], name + ' test R2')
            print(name + ' refit: PASS', flush=True)
        cols = n.FEATURE_GROUPS['+ geography & peers (full)']
        intervals = n.CQR(cols).fit(train, valid)
        lo, hi = intervals.predict(test)
        close(np.mean((test.target.to_numpy() >= lo) & (test.target.to_numpy() <= hi)), results['intervals']['test_coverage'], 'interval coverage')
        close(np.median(hi - lo), results['intervals']['median_width_min'], 'interval width')
        y = test.target.to_numpy()
        hits = ((y >= lo) & (y <= hi)).astype(float)
        cov_ci = np.percentile(np.random.default_rng(n.SEED).choice(hits, (2000,len(hits))).mean(1),[2.5,97.5])
        assert np.allclose(cov_ci,results['intervals']['test_coverage_ci95'])
        rng = np.random.default_rng(n.SEED)
        idx = rng.integers(0,len(test),(2000,len(test)))
        gain = np.abs(y-test.lag1.to_numpy())[idx].mean(1) - np.abs(y-fitted[results['best_learned_model']].predict(test))[idx].mean(1)
        close(gain.mean(),results['confidence']['mae_gain_vs_best_challenger_min'],'bootstrap mean gain')
        assert np.allclose(np.percentile(gain,[2.5,97.5]),results['confidence']['mae_gain_ci95'])
        groups = [g for _,g in test.groupby(['state','county']) if len(g)>=3]
        hits = np.array([float(g.lag1.idxmin()==g.target.idxmin()) for g in groups])
        pick = hits[rng.integers(0,len(hits),(2000,len(hits)))].mean(1)
        assert np.allclose(np.percentile(pick,[2.5,97.5]),results['confidence']['fastest_pick_ci95'])
        print('All three bootstrap confidence intervals: PASS',flush=True)
        deploy = n.CQR(cols).fit(labeled[labeled.t <= last - 1], test)
        now = df[df.t == df.t.max()]
        lo,hi = deploy.predict(now)
        deployed = now.assign(lo=np.minimum(lo, now.lag1),hi=np.maximum(hi,now.lag1)).merge(forecast,left_on='facility_id',right_on='cms_provider_id')
        assert np.allclose(deployed.lo,deployed.lo80) and np.allclose(deployed.hi,deployed.hi80)
        print('Held-out interval coverage/width and all eight deployed forecast bounds: PASS', flush=True)


    if rolling:
        checked = []
        for saved in results['rolling']:
            k = next(k for k in range(2,last+1) if str(pd.Timestamp(snaps[k+1]).date()) == saved['target_release'])
            earlier, heldout = labeled[labeled.t < k], labeled[labeled.t == k]
            close(len(heldout),saved['hospitals'],'rolling hospital count')
            maes = {}
            for name, model in n.candidate_models().items():
                model.fit(earlier)
                maes[name] = mean_absolute_error(heldout.target,model.predict(heldout))
                # Linear-solver reductions can differ slightly across BLAS platforms.
                # Tolerance is well below the displayed 0.01-minute precision.
                close(maes[name],saved['maes'][name],saved['target_release']+' '+name,tolerance=1e-4)
            best = min((name for name in maes if name != 'Persistence baseline'),key=maes.get)
            assert best == saved['best_challenger']
            close(maes[best],saved['best_challenger_MAE'],'rolling challenger',tolerance=1e-4)
            close(n.ranking_eval(heldout.assign(pred=heldout.lag1),'pred')['fastest_pick_accuracy'],saved['fastest_pick_accuracy'],'rolling county ranking')
            if saved.get('coverage') is not None:
                interval = n.CQR(n.FEATURE_GROUPS['+ geography & peers (full)']).fit(labeled[labeled.t<=k-2],labeled[labeled.t==k-1])
                lower,upper = interval.predict(heldout)
                y = heldout.target.to_numpy()
                close(np.mean((y>=lower)&(y<=upper)),saved['coverage'],'rolling median coverage')
            checked.append(saved)
            print(saved['target_release']+' all four models, ranges and ranking: PASS',flush=True)
        ruled = []
        for prior,current in zip(checked,checked[1:]):
            candidate = min((name for name in prior['maes'] if name != 'Persistence baseline'),key=prior['maes'].get)
            chosen = candidate if prior['maes'][candidate] <= prior['persistence_MAE']*(1-results['promotion_margin']) else 'Persistence baseline'
            assert chosen == current['rule_model']
            close(current['maes'][chosen],current['rule_MAE'],'rolling selected error')
            ruled.append(current)
        close(np.mean([r['rule_MAE'] for r in ruled]),results['walk_forward']['rule_MAE'],'walk-forward MAE')
        close(np.mean([r['persistence_MAE'] for r in ruled]),results['walk_forward']['always_persistence_MAE'],'walk-forward baseline MAE')
        print('All seven historical folds and walk-forward selection: PASS',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--refit',action='store_true')
    parser.add_argument('--rolling',action='store_true')
    args = parser.parse_args()
    main(args.refit,args.rolling)
