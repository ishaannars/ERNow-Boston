"""Check that saved model forecasts reach actual Streamlit consumer cards.

Uses deterministic seven-minute routes and offline context; no external requests.
Run: python scripts/verify_consumer_outputs.py
"""
import html
import json
import re
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
fixture = '''
import runpy
from unittest.mock import patch
import requests
import streamlit as st
class Route:
    def raise_for_status(self): pass
    def json(self): return {"routes": [{"duration": 420, "distance": 3218.688}]}
def offline_get(url, **kwargs):
    if "project-osrm.org" in url and st.session_state.get("routes_available", True):
        return Route()
    raise requests.RequestException("offline verification")
if "initialized" not in st.session_state:
    st.session_state["origin"] = (42.3555, -71.0605, "Verification location")
    st.session_state["initialized"] = True
with patch("requests.get", side_effect=offline_get):
    runpy.run_path(APP_PATH, run_name="__main__")
'''.replace('APP_PATH', repr(str(ROOT / 'app.py')))


def minutes(value):
    value = int(round(value))
    return f'{value} min' if value < 60 else f'{value // 60}h {value % 60}m'


def check(at, forecast):
    assert not at.exception, [e.message for e in at.exception]
    card_markup = next(m.value for m in at.markdown if m.value.startswith('<div class="er-list">'))
    cards = card_markup.split('<div class="er-card')[1:]
    assert len(cards) == len(forecast)
    for row in forecast.itertuples():
        card = next(c for c in cards if f'<span class="er-title">{html.escape(row.hospital)}</span>' in c)
        text = html.unescape(re.sub(r'<[^>]*>', ' ', card))
        assert f'Forecast median {minutes(row.forecast_op18b)}' in text, row.hospital
        assert f'{minutes(row.lo80)}–{minutes(row.hi80)}' in text, row.hospital
        assert f'~{minutes(row.forecast_op18b + 7)}' in text, row.hospital
        assert 'Fastest in simulation' in text
        if row.ed_type == 'general':
            assert f'{minutes(abs(row.vs_peers_min))} ' in text
    winner = forecast.loc[forecast.forecast_op18b.idxmin(), 'hospital']
    winning_card = next(c for c in cards if f'<span class="er-title">{html.escape(winner)}</span>' in c)
    assert 'Lowest estimated total' in winning_card
    model = json.loads((ROOT / 'data/national_results.json').read_text())['selected_model']
    assert any(f'Selected: {model}' in m.value for m in at.markdown)


def main():
    forecast = pd.read_csv(ROOT / 'data/boston_forecast.csv')
    at = AppTest.from_string(fixture, default_timeout=30).run()
    check(at, forecast[forecast.ed_type == 'general'])
    at.radio(key='emergency_type').set_value('Eye, ear, nose, or throat').run()
    check(at, forecast)
    at.session_state['routes_available'] = False
    at.session_state['origin'] = (42.36, -71.06, 'Missing-route verification')
    at.run()
    assert not at.exception
    assert any('comparison is unavailable' in i.value for i in at.info)
    cards = next(m.value for m in at.markdown if m.value.startswith('<div class="er-list">'))
    assert 'Lowest estimated total' not in cards
    assert not any('answer-one' in m.value for m in at.markdown if not m.value.startswith('<style>'))
    print('Consumer wiring: all eight forecast medians/ranges, totals, peer values, selected-model label, winner and missing-route behavior PASS')


if __name__ == '__main__':
    main()
