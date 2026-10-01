from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from html import unescape
import html
import os
import re
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st
from streamlit_geolocation import streamlit_geolocation
import json
import numpy as np

st.set_page_config(page_title="ERNow Boston", page_icon="✚", layout="wide")
DATA_PATH = Path(__file__).parent / "data" / "boston_er_data.csv"
HOSPITAL_DATA = DATA_PATH
NATIONAL_RESULTS = Path(__file__).resolve().parent / "data" / "national_results.json"
BOSTON_FORECAST = Path(__file__).resolve().parent / "data" / "boston_forecast.csv"
URGENT_GUARDRAIL = ("For urgent but not life-threatening needs. In an emergency, call 911 or go to "
                    "the nearest emergency department. Never pass a closer ER because of an ERNow estimate.")


@st.cache_data(show_spinner=False)
def load_national():
    """Small outputs of national_model.py: trained on every U.S. hospital in the CMS archives."""
    if not NATIONAL_RESULTS.exists() or not BOSTON_FORECAST.exists():
        return None, None
    res = json.loads(NATIONAL_RESULTS.read_text())
    fc = pd.read_csv(BOSTON_FORECAST, dtype={"cms_provider_id": str})
    fc["cms_provider_id"] = fc["cms_provider_id"].str.zfill(6)
    return res, fc


def chance_fastest(drive, mid, lo, hi, n=4000, seed=11):
    """Probability each hospital has the shortest drive + ED visit, by simulation.

    Each visit time is drawn from a lognormal matched to that hospital's tested 80% range;
    hospitals without a route are excluded (shown as unavailable)."""
    drive_a, mid_a = np.asarray(drive, dtype=float), np.asarray(mid, dtype=float)
    ok = ~(np.isnan(drive_a) | np.isnan(mid_a))
    probs = np.full(len(mid), np.nan)
    if ok.sum() < 2:
        return probs
    rng = np.random.default_rng(seed)
    m, l, h, d = (np.asarray(x, dtype=float)[ok] for x in (mid, lo, hi, drive))
    sigma = np.maximum(np.log(np.maximum(h, m + 1) / np.maximum(l, 1)) / (2 * 1.2816), 0.01)
    draws = d + np.exp(np.log(np.maximum(m, 1)) + sigma * rng.standard_normal((n, len(m))))
    wins = np.bincount(draws.argmin(axis=1), minlength=len(m)) / n
    probs[np.where(ok)[0]] = wins
    return probs
EASTERN = ZoneInfo("America/New_York")

FALLBACK_ORIGINS = {
    "Northeastern University": (42.3398, -71.0892),
    "Downtown Boston": (42.3555, -71.0605),
    "Back Bay": (42.3503, -71.0810),
    "Fenway": (42.3458, -71.0985),
    "South Boston": (42.3381, -71.0476),
    "East Boston": (42.3751, -71.0392),
    "Jamaica Plain": (42.3097, -71.1151),
    "Charlestown": (42.3782, -71.0602),
}

URLS = {
    "cms": "https://data.cms.gov/data-api/v1/dataset/yv7e-xc69/data",
    "cdc": "https://data.cdc.gov/resource/f3zz-zga5.json",
    "nws_points": "https://api.weather.gov/points/{lat},{lon}",
    "nws_alerts": "https://api.weather.gov/alerts/active",
    "boston_events": "https://www.boston.gov/rss/events",
    "td_garden": "https://www.tdgarden.com/events",
    "mlb_schedule": "https://statsapi.mlb.com/api/v1/schedule",
    "boston_local_rss": "https://www.boston.com/tag/local-news/?feed=rss",
    "boston_traffic_rss": "https://www.boston.com/tag/traffic/feed/",
    "ticketmaster": "https://app.ticketmaster.com/discovery/v2/events.json",
    "osrm": "https://router.project-osrm.org/route/v1/driving/{olon},{olat};{dlon},{dlat}",
}

HEADERS = {
    "User-Agent": "ERNow-Boston/1.1 portfolio-project contact=ernow-boston",
    "Accept": "application/json, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
}

MAJOR_CITY_EVENT_KEYWORDS = {
    "marathon", "parade", "fireworks", "championship", "road closure", "road closures",
    "street closure", "street closures", "head of the charles", "first night",
    "boston calling", "major festival", "large festival", "race day", "celebration",
    "demonstration", "rally", "protest", "citywide", "major event",
}

MAJOR_TICKETMASTER_VENUES = {
    "td garden", "fenway park", "mgm music hall at fenway", "leader bank pavilion",
    "aggannis arena", "agganis arena", "house of blues boston",
}

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&display=swap');
:root{--ivory:#F8F4E6;--shell:#FFFDF5;--ink:#1C1B19;--soft-ink:#403A32;--tea:#B9AD91;--moss:#48513C;--beni:#8C2F2F;--kakishibu:#A85B45;--kakishibu-wash:rgba(168,91,69,.10)}
html,body,[class*="css"],.stApp{font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif}
.stApp{background:var(--ivory);color:var(--ink)}
.block-container{padding-top:5.4rem!important;padding-bottom:2rem;max-width:960px}
[data-testid="stSidebar"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
button[kind="header"] {
    display: none !important;
}
.safety-banner{display:block;width:100%;box-sizing:border-box;overflow:visible;background:var(--beni);color:#fff!important;border-radius:16px;padding:16px 19px;font-size:1rem;line-height:1.5;font-weight:650;margin:0 0 .9rem 0}
.safety-banner,.safety-banner *{color:#fff!important;opacity:1!important}
.nav-wrap{border-bottom:1px solid var(--tea);padding-bottom:.55rem;margin-bottom:1.15rem}
[data-testid="stPageLink-NavLink"]{background:var(--shell)!important;border:1px solid var(--tea)!important;border-radius:10px!important;color:var(--ink)!important;font-weight:650!important;white-space:nowrap!important;overflow:visible!important;min-width:max-content!important}
[data-testid="stPageLink-NavLink"] *{color:var(--ink)!important;white-space:nowrap!important;overflow:visible!important}
[data-testid="stPageLink-NavLink"]:hover{border-color:var(--kakishibu)!important;background:var(--kakishibu-wash)!important}
[data-testid="stPageLink-NavLink"] .material-symbols-rounded{color:var(--beni)!important}
.location-confirm{background:var(--kakishibu-wash);border-bottom:2px solid var(--kakishibu);border-radius:10px 10px 4px 4px;padding:.72rem .9rem;margin:.35rem 0 .75rem 0;color:var(--ink);font-weight:600}
.location-confirm .sub{color:var(--soft-ink);font-size:.84rem;font-weight:500;margin-left:.35rem}
.brand-sub{color:var(--soft-ink);margin-top:-.35rem;margin-bottom:1.1rem;font-size:.98rem}
.model-bar{background:var(--shell);border:1px solid var(--tea);border-left:4px solid var(--moss);border-radius:14px;padding:.82rem 1rem;margin:.35rem 0 1.05rem 0}
.model-line-1{display:flex;align-items:center;gap:.5rem;color:var(--ink);font-size:.96rem;font-weight:700}
.model-line-2{color:var(--soft-ink);font-size:.86rem;font-weight:600;margin-top:.28rem;line-height:1.4}
.model-meta{display:flex;flex-wrap:wrap;gap:.42rem .55rem;margin-top:.55rem}
.model-chip{font-size:.73rem;color:var(--soft-ink);background:var(--ivory);border:1px solid rgba(185,173,145,.72);border-radius:999px;padding:.24rem .5rem;font-weight:600}
.model-dot{width:9px;height:9px;border-radius:50%;background:var(--moss);display:inline-block;box-shadow:0 0 0 rgba(72,81,60,.45);animation:modelPulse 1.65s infinite}
@keyframes modelPulse{0%{box-shadow:0 0 0 0 rgba(72,81,60,.45);opacity:1}70%{box-shadow:0 0 0 7px rgba(72,81,60,0);opacity:.72}100%{box-shadow:0 0 0 0 rgba(72,81,60,0);opacity:1}}
.er-card{background:var(--shell);border:1px solid var(--tea);border-radius:16px;padding:1.05rem 1.1rem;margin-bottom:.8rem}
.er-best{border:2px solid var(--moss)}
.best-label{color:var(--moss);font-size:.76rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.25rem}
.er-title{font-size:1.15rem;font-weight:650;color:var(--ink)}
.er-rank{font-size:1.12rem;font-weight:700;margin-right:.4rem;color:var(--moss)}
.er-wait-label{font-size:.82rem;color:var(--soft-ink);margin-top:.6rem}
.er-wait{font-size:1.65rem;font-weight:700;letter-spacing:-.02em;margin:.08rem 0 .45rem 0;color:var(--ink)}
.er-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.38rem 1.1rem;margin-top:.15rem}
.er-metric{font-size:.93rem;color:var(--soft-ink)}
.er-metric b{color:var(--ink);font-weight:600}
.er-reason{font-size:.82rem;color:var(--moss);font-weight:600;margin-top:.5rem}
.er-flag{display:inline-block;margin-left:.55rem;vertical-align:middle;font-size:.68rem;font-weight:650;color:var(--kakishibu);border:1px solid var(--kakishibu);border-radius:999px;padding:.08rem .45rem}
.evidence-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem;margin:.45rem 0 1rem}
.evidence-card{background:var(--shell);border:1px solid var(--tea);border-radius:12px;padding:.8rem .9rem}
.evidence-value{font-size:1.25rem;font-weight:700;letter-spacing:-.01em;color:var(--ink);line-height:1.2}
.evidence-copy{font-size:.84rem;color:var(--soft-ink);line-height:1.45;margin-top:.25rem}
.evidence-source{font-size:.7rem;color:var(--soft-ink);opacity:.8;margin-top:.4rem;text-transform:uppercase;letter-spacing:.04em;font-weight:600}
.stMarkdown table{width:100%;border-collapse:collapse;font-size:.86rem;margin:.35rem 0 .9rem}
.stMarkdown th{text-align:left;font-weight:650;color:var(--ink);border-bottom:1px solid var(--tea);padding:.42rem .6rem}
.stMarkdown td{color:var(--soft-ink);border-bottom:1px solid rgba(185,173,145,.45);padding:.4rem .6rem;vertical-align:top}
[data-testid="stTable"]{margin:.45rem 0 .9rem !important}
[data-testid="stTable"] table{font-size:.86rem}
[data-testid="stTable"] th,[data-testid="stTable"] td{padding:.42rem .6rem !important;vertical-align:top}
@media(max-width:720px){.evidence-grid{grid-template-columns:1fr}}
@media(max-width:650px){.block-container{padding-top:4.8rem!important}.er-grid{grid-template-columns:1fr}.er-wait{font-size:1.5rem}.model-line-2{font-size:.8rem}.model-chip{font-size:.69rem}}

[data-testid="stAppViewContainer"], [data-testid="stAppViewBlockContainer"], section.main, .stApp, html, body {background:var(--ivory) !important;}
[data-testid="stStatusWidget"], .stDeployButton {display:none !important;}
[data-testid="stSpinner"] [role="status"] {display:none !important;}
.ernow-loading-wrap{display:flex;align-items:center;justify-content:center;padding:.8rem 0 1rem 0;}
.ernow-loading{width:30px;height:30px;border:3px solid #DDD4BE;border-top-color:var(--moss);border-radius:50%;animation:ernow-spin .8s linear infinite;}
@keyframes ernow-spin{to{transform:rotate(360deg)}}


.er-card{padding:.92rem 1.05rem!important;margin-bottom:.7rem!important}
.er-grid{gap:.26rem 1.05rem!important;margin-top:.1rem!important}
.er-wait{margin:.04rem 0 .35rem 0!important}
.er-reason{font-size:.72rem!important;line-height:1.42!important;margin-top:.38rem!important;font-weight:550!important}
.er-actions{margin-top:.5rem}
.er-directions{
  display:inline-block;
  text-decoration:none!important;
  background:var(--moss);
  border:1px solid var(--moss);
  border-radius:9px;
  padding:.42rem .68rem;
  color:#fff!important;
  font-size:.78rem;
  font-weight:650;
}
.er-directions:hover{
  background:#3E4735;
  border-color:#3E4735;
  color:#fff!important;
}


/* Final spacing pass */
.model-bar{padding:.82rem 1rem!important;margin:.35rem 0 1.15rem!important}
.model-meta{gap:.38rem .46rem!important;margin-top:.48rem!important}
.model-chip{padding:.22rem .48rem!important;font-size:.72rem!important;font-weight:600!important}
.er-card{padding:1.02rem 1.08rem .92rem!important;margin-bottom:.82rem!important}
.er-best{padding-top:1.05rem!important}
.best-label{margin-bottom:.32rem!important}
.er-title{line-height:1.25!important}
.er-wait-label{margin-top:.62rem!important;margin-bottom:.02rem!important}
.er-wait{margin:.04rem 0 .5rem!important}
.er-grid{gap:.34rem 1.25rem!important;margin-top:.08rem!important;margin-bottom:.12rem!important}
.er-metric{line-height:1.45!important}
.er-metric b{font-weight:600!important}
.er-reason{font-size:.69rem!important;line-height:1.42!important;font-weight:400!important;margin-top:.42rem!important;color:var(--soft-ink)!important}
.er-actions{margin-top:.42rem!important}
.er-directions{padding:.31rem .54rem!important;font-size:.70rem!important;line-height:1.2!important;border-radius:7px!important;font-weight:600!important}

</style>
""",
    unsafe_allow_html=True,
)


def secret_or_env(name):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name)


def safe_get(url, *, params=None, headers=None, timeout=8):
    try:
        r = requests.get(url, params=params, headers=headers or HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except requests.RequestException:
        return None


def clean_text(value):
    text = unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", text).strip()


@st.cache_data(ttl=3600)
def load_fallback_data():
    df = pd.read_csv(DATA_PATH, dtype={"cms_provider_id": str})
    for col in ["typical_ed_minutes", "legacy_wait_to_provider_min", "recent_ed_visits", "recent_occupancy_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_cms_metrics(provider_ids):
    rows = []
    for provider_id in provider_ids:
        r = safe_get(URLS["cms"], params={"size": 100, "offset": 0, "filter[Facility ID]": provider_id}, timeout=10)
        if not r:
            continue
        try:
            payload = r.json()
        except ValueError:
            continue
        if isinstance(payload, dict):
            payload = payload.get("data", payload.get("results", []))
        record = {"cms_provider_id": str(provider_id)}
        for item in payload if isinstance(payload, list) else []:
            if str(item.get("Facility ID", "")) != str(provider_id):
                continue
            try:
                score = float(item.get("Score"))
            except (TypeError, ValueError):
                continue
            if item.get("Measure ID") == "OP_18b":
                record["cms_current_baseline"] = score
            elif item.get("Measure ID") == "OP_22":
                record["left_before_seen_pct"] = score
        rows.append(record)
    return pd.DataFrame(rows)


@st.cache_data(ttl=600, show_spinner=False)
def fetch_current_weather(lat, lon):
    point = safe_get(URLS["nws_points"].format(lat=f"{lat:.4f}", lon=f"{lon:.4f}"), timeout=8)
    if not point:
        return None
    try:
        stations_url = point.json().get("properties", {}).get("observationStations")
    except ValueError:
        return None
    stations = safe_get(stations_url, timeout=8) if stations_url else None
    if not stations:
        return None
    try:
        features = stations.json().get("features", [])
    except ValueError:
        return None
    for station in features[:5]:
        station_url = station.get("id") or station.get("properties", {}).get("@id")
        obs = safe_get(f"{station_url}/observations/latest", timeout=8) if station_url else None
        if not obs:
            continue
        try:
            p = obs.json().get("properties", {})
        except ValueError:
            continue
        if p:
            return {
                "description": p.get("textDescription") or "Current NWS observation",
                "timestamp": p.get("timestamp"),
                "temperature_c": (p.get("temperature") or {}).get("value"),
                "wind_kmh": (p.get("windSpeed") or {}).get("value"),
            }
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_location_name(lat, lon):
    r = safe_get(URLS["nws_points"].format(lat=f"{lat:.4f}", lon=f"{lon:.4f}"), timeout=8)
    if not r:
        return "Current location"
    try:
        rel = (r.json().get("properties", {}).get("relativeLocation") or {}).get("properties", {})
        city, state = rel.get("city"), rel.get("state")
        return f"{city}, {state}" if city and state else (city or "Current location")
    except (ValueError, AttributeError):
        return "Current location"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_nws_alerts(lat, lon):
    r = safe_get(URLS["nws_alerts"], params={"point": f"{lat:.4f},{lon:.4f}"}, timeout=8)
    if not r:
        return []
    try:
        return r.json().get("features", [])
    except ValueError:
        return []


def current_weather_factor(obs, alerts):
    factor = 1.0
    if obs:
        text = (obs.get("description") or "").lower()
        temp_c, wind = obs.get("temperature_c"), obs.get("wind_kmh")
        if any(k in text for k in ["snow", "ice", "sleet", "freezing"]):
            factor *= 1.08
        elif any(k in text for k in ["thunder", "heavy rain", "rain", "showers"]):
            factor *= 1.03
        if isinstance(temp_c, (int, float)) and (temp_c >= 35 or temp_c <= -7):
            factor *= 1.04
        if isinstance(wind, (int, float)) and wind >= 50:
            factor *= 1.03
    if any(str(a.get("properties", {}).get("severity", "")).lower() in {"severe", "extreme"} for a in alerts):
        factor *= 1.05
    return min(factor, 1.15)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cdc_ari():
    params = {"$select": "week_end,geography,label", "$where": "geography='Massachusetts'", "$order": "week_end DESC", "$limit": 1}
    r = safe_get(URLS["cdc"], params=params, timeout=8)
    if not r:
        return None
    try:
        rows = r.json()
    except ValueError:
        return None
    return rows[0] if rows else None


def illness_factor(ari):
    label = ((ari or {}).get("label") or "").strip().lower()
    mapping = {"minimal": 0.99, "very low": 0.99, "low": 1.00, "moderate": 1.02, "high": 1.04, "very high": 1.06}
    return mapping.get(label, 1.0), (label.title() if label else "Unavailable")


def nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    return d + timedelta(days=((weekday - d.weekday()) % 7) + 7 * (n - 1))


def last_weekday(year, month, weekday):
    d = date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def observed_fixed(d):
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


def holiday_name(d):
    y = d.year
    holidays = {
        observed_fixed(date(y, 1, 1)): "New Year's Day",
        nth_weekday(y, 1, 0, 3): "Martin Luther King Jr. Day",
        nth_weekday(y, 2, 0, 3): "Presidents Day",
        nth_weekday(y, 4, 0, 3): "Patriots' Day / Boston Marathon",
        last_weekday(y, 5, 0): "Memorial Day",
        observed_fixed(date(y, 6, 19)): "Juneteenth",
        observed_fixed(date(y, 7, 4)): "Independence Day",
        nth_weekday(y, 9, 0, 1): "Labor Day",
        nth_weekday(y, 10, 0, 2): "Indigenous Peoples' / Columbus Day",
        observed_fixed(date(y, 11, 11)): "Veterans Day",
        nth_weekday(y, 11, 3, 4): "Thanksgiving",
        observed_fixed(date(y, 12, 25)): "Christmas Day",
    }
    # Match the actual date as well as the observed weekday (July 4 on a Saturday is still July 4).
    actual = {date(y, 1, 1): "New Year's Day", date(y, 6, 19): "Juneteenth", date(y, 7, 4): "Independence Day",
              date(y, 11, 11): "Veterans Day", date(y, 12, 25): "Christmas Day"}
    return holidays.get(d) or actual.get(d)


def temporal_factor(now_dt):
    factor = 1.0
    h, wd = now_dt.hour, now_dt.weekday()
    if 16 <= h < 23:
        factor *= 1.08
    elif 0 <= h < 6:
        factor *= 0.96
    if wd == 0:
        factor *= 1.04
    elif wd >= 5:
        factor *= 1.02
    hname = holiday_name(now_dt.date())
    if hname:
        factor *= 1.07 if "Marathon" in hname else 1.04
    return factor


def is_major_city_event(title, text=""):
    haystack = clean_text(f"{title} {text}").lower()
    return any(keyword in haystack for keyword in MAJOR_CITY_EVENT_KEYWORDS)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_city_events(today_iso):
    r = safe_get(URLS["boston_events"], timeout=8)
    if not r:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    target = datetime.fromisoformat(today_iso)
    tokens = {target.strftime("%B %d, %Y").replace(" 0", " "), target.strftime("%Y-%m-%d")}
    out = []
    for item in root.findall(".//item"):
        text = " ".join((c.text or "") for c in list(item))
        title = (item.findtext("title") or "").strip()
        if title and any(tok.lower() in text.lower() for tok in tokens) and is_major_city_event(title, text):
            out.append(title)
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_tdgarden_events(today_iso):
    target = datetime.fromisoformat(today_iso)
    r = safe_get(URLS["td_garden"], headers={"User-Agent": HEADERS["User-Agent"], "Accept": "text/html"}, timeout=10)
    if not r:
        return []
    html = r.text
    month, day, year = target.strftime("%B"), target.day, target.year
    events = []
    for match in re.findall(rf"{month}\s+{day},\s+{year}.*?<h3[^>]*>(.*?)</h3>", html, flags=re.I | re.S):
        title = clean_text(match)
        if title:
            events.append(f"{title} — TD Garden")
    for start_day, end_day, match in re.findall(rf"{month}\s+(\d{{1,2}})\s*[–—-]\s*(\d{{1,2}}),\s*{year}.*?<h3[^>]*>(.*?)</h3>", html, flags=re.I | re.S):
        if int(start_day) <= day <= int(end_day):
            title = clean_text(match)
            if title:
                events.append(f"{title} — TD Garden")
    return list(dict.fromkeys(events))


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_red_sox_home_games(today_iso):
    r = safe_get(URLS["mlb_schedule"], params={"sportId": 1, "teamId": 111, "date": today_iso, "hydrate": "venue"}, timeout=8)
    if not r:
        return []
    try:
        dates = r.json().get("dates", [])
    except ValueError:
        return []
    events = []
    for d in dates:
        for game in d.get("games", []):
            if game.get("teams", {}).get("home", {}).get("team", {}).get("id") == 111:
                away = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "opponent")
                events.append(f"Red Sox vs. {away} — Fenway Park")
    return events


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_boston_news_event_layer(now_iso):
    now_dt = datetime.fromisoformat(now_iso)
    keywords = [
        "parade", "marathon", "festival", "fireworks", "street closure", "street closures",
        "road closure", "road closures", "concert", "championship", "rally", "demonstration",
        "head of the charles", "first night", "boston calling", "large event", "major event",
    ]
    time_terms = {"today", "tonight", "this weekend", now_dt.strftime("%A").lower(), now_dt.strftime("%B %-d").lower()}
    events = []
    for url in [URLS["boston_local_rss"], URLS["boston_traffic_rss"]]:
        r = safe_get(url, headers={"User-Agent": HEADERS["User-Agent"], "Accept": "application/rss+xml, application/xml, text/xml"}, timeout=8)
        if not r:
            continue
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            continue
        for item in root.findall(".//item"):
            title = clean_text(item.findtext("title") or "")
            desc = clean_text(item.findtext("description") or "")
            published = item.findtext("pubDate") or ""
            try:
                pub_dt = parsedate_to_datetime(published).astimezone(EASTERN)
            except Exception:
                pub_dt = None
            if pub_dt and now_dt - pub_dt > timedelta(days=7):
                continue
            text = f"{title} {desc}".lower()
            if any(k in text for k in keywords) and (any(t in text for t in time_terms) or (pub_dt and now_dt - pub_dt <= timedelta(hours=36))):
                events.append(title)
    return list(dict.fromkeys(events))[:4]


@st.cache_data(ttl=900, show_spinner=False)
def fetch_ticketmaster_events(now_iso, end_iso, api_key):
    if not api_key:
        return []
    params = {
        "apikey": api_key,
        "city": "Boston",
        "stateCode": "MA",
        "countryCode": "US",
        "startDateTime": now_iso,
        "endDateTime": end_iso,
        "size": 50,
        "sort": "date,asc",
    }
    r = safe_get(URLS["ticketmaster"], params=params, timeout=10)
    if not r:
        return []
    try:
        source_events = r.json().get("_embedded", {}).get("events", [])
    except ValueError:
        return []
    events = []
    for event in source_events:
        name = clean_text(event.get("name", ""))
        venues = event.get("_embedded", {}).get("venues", [])
        venue = clean_text(venues[0].get("name", "")) if venues else ""
        if name and venue.lower() in MAJOR_TICKETMASTER_VENUES:
            events.append(f"{name} — {venue}")
    return events


def major_event_titles(now_dt):
    day = now_dt.date().isoformat()
    events = []
    events.extend(fetch_city_events(day))
    events.extend(fetch_tdgarden_events(day))
    events.extend(fetch_red_sox_home_games(day))
    events.extend(fetch_boston_news_event_layer(now_dt.isoformat()))
    tm_key = secret_or_env("TICKETMASTER_API_KEY")
    if tm_key:
        events.extend(fetch_ticketmaster_events(
            now_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            (now_dt + timedelta(hours=8)).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            tm_key,
        ))
    cleaned = []
    seen = set()
    for event in events:
        event = clean_text(event)
        key = re.sub(r"[^a-z0-9]+", " ", event.lower()).strip()
        if event and key and key not in seen:
            seen.add(key)
            cleaned.append(event)
    return cleaned[:6]


def event_factor(events):
    if len(events) >= 3:
        return 1.04
    if events:
        return 1.02
    return 1.0


@st.cache_data(ttl=300, show_spinner=False)
def route_estimate(origin_lat, origin_lon, dest_lat, dest_lon):
    url = URLS["osrm"].format(olon=origin_lon, olat=origin_lat, dlon=dest_lon, dlat=dest_lat)
    r = safe_get(url, params={"overview": "false", "alternatives": "false", "steps": "false"}, timeout=10)
    if not r:
        return None
    try:
        route = r.json().get("routes", [])[0]
        return {"minutes": route["duration"] / 60.0, "miles": route["distance"] / 1609.344}
    except (ValueError, IndexError, KeyError, TypeError):
        return None


def recent_demand_factor(row, med_volume, med_occupancy, med_lwbs):
    factor = 1.0
    if pd.notna(row.get("recent_ed_visits")) and med_volume:
        factor *= max(0.96, min(1.06, 1 + 0.04 * (float(row["recent_ed_visits"]) / med_volume - 1)))
    if pd.notna(row.get("recent_occupancy_pct")) and med_occupancy:
        factor *= max(0.97, min(1.05, 1 + 0.02 * ((float(row["recent_occupancy_pct"]) - med_occupancy) / 10.0)))
    if pd.notna(row.get("left_before_seen_pct")) and med_lwbs:
        factor *= max(0.97, min(1.05, 1 + 0.025 * (float(row["left_before_seen_pct"]) / med_lwbs - 1)))
    return max(0.92, min(1.12, factor))


def fmt_minutes(v):
    if pd.isna(v):
        return "—"
    m = max(0, int(round(v)))
    return f"{m} min" if m < 60 else f"{m // 60}h {m % 60}m"


def fmt_range(lo, hi):
    """'17–40 min' when both ends are under an hour, otherwise '3h 17m–3h 55m'."""
    if pd.isna(lo) or pd.isna(hi):
        return "—"
    if round(hi) < 60:
        return f"{int(round(lo))}–{int(round(hi))} min"
    return f"{fmt_minutes(lo)}–{fmt_minutes(hi)}"


def current_condition_label(dynamic_factor):
    if dynamic_factor >= 1.08:
        return "Elevated"
    if dynamic_factor <= 0.96:
        return "Lower than typical"
    return "Typical"


def build_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, major_events, historical_layer=None):
    wf = current_weather_factor(weather_obs, alerts)
    inf, illness_label = illness_factor(ari)
    dynamic_factor = max(0.86, min(1.24, wf * inf * temporal_factor(now_dt) * event_factor(major_events)))
    med_ed = df["typical_ed_minutes"].median()
    med_volume = df["recent_ed_visits"].median()
    med_occupancy = df["recent_occupancy_pct"].median()
    med_lwbs = df["left_before_seen_pct"].median() if "left_before_seen_pct" in df and df["left_before_seen_pct"].notna().any() else None

    national, forecast = load_national()
    selected_predictor = (national or {}).get("selected_model")
    learned_promoted = bool((national or {}).get("learned_model_promoted", False))
    fc_by_id = {} if forecast is None else forecast.set_index("cms_provider_id").to_dict("index")
    fc_med = float(forecast["forecast_op18b"].median()) if forecast is not None and len(forecast) else None

    rows = []
    for _, row in df.iterrows():
        route = route_estimate(origin_lat, origin_lon, row["latitude"], row["longitude"])
        drive_min, route_miles = (float("nan"), float("nan")) if route is None else (route["minutes"], route["miles"])

        historical_wait = float(row["legacy_wait_to_provider_min"])
        current_relative = float(row["typical_ed_minutes"]) / med_ed if med_ed else 1.0

        fc = fc_by_id.get(str(row["cms_provider_id"]).zfill(6), {})
        predicted_relative = float(fc["forecast_op18b"]) / fc_med if fc and fc_med else 1.0

        # Only blend in the historical prediction when a learned model was promoted. With the
        # Persistence baseline, the "prediction" is the latest archived value, which is nearly the
        # same number as the current CMS value, so blending would count one signal twice.
        hist_weight = 0.40 if learned_promoted else 0.0
        blended_throughput_relative = (1 - hist_weight) * current_relative + hist_weight * predicted_relative
        throughput_factor = max(0.90, min(1.12, blended_throughput_relative ** 0.30))

        hospital_demand = recent_demand_factor(row, med_volume, med_occupancy, med_lwbs)
        wait_mid = historical_wait * throughput_factor * hospital_demand * dynamic_factor
        wait_low = max(5, wait_mid * 0.65)

        rows.append({
            **row.to_dict(),
            "route_time_min": drive_min,
            "route_distance_miles": route_miles,
            "modeled_wait_mid": wait_mid,
            "modeled_wait_low": wait_low,
            "modeled_wait_high": max(wait_low + 10, wait_mid * 1.55),
            "visit_mid": fc.get("forecast_op18b", float("nan")),
            "visit_lo": fc.get("lo80", float("nan")),
            "visit_hi": fc.get("hi80", float("nan")),
            "vs_peers_min": fc.get("vs_peers_min", float("nan")),
            "change_flag": bool(fc.get("change_flag", False)),
            "route_ok": bool(pd.notna(drive_min)),
            # Rank by the tested quantity when available: drive + forecast ED visit.
            "access_mid": (drive_min if pd.notna(drive_min) else 0)
                          + (fc["forecast_op18b"] if fc else wait_mid),
            "dynamic_factor": dynamic_factor,
            "hospital_demand_factor": hospital_demand,
            "predicted_throughput_pressure": predicted_relative,
        })

    out = pd.DataFrame(rows)
    out["chance_fastest"] = chance_fastest(out["route_time_min"].where(out["route_ok"]), out["visit_mid"],
                                           out["visit_lo"], out["visit_hi"])
    # Hospitals without a route are ranked after routed ones, by ED time only.
    out = out.sort_values(["route_ok", "access_mid", "modeled_wait_mid"],
                          ascending=[False, True, True]).reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    return out, {
        "dynamic_factor": dynamic_factor,
        "illness_label": illness_label,
        "historical_predictor": selected_predictor,
        "learned_model_promoted": learned_promoted,
    }


st.markdown("""
<style>
/* Same typography and spacing system across ERNow, Methodology, and Forecast Model. */
html, body, [class*="css"], .stApp,
.stMarkdown, .stMarkdown p, .stMarkdown li,
[data-testid="stCaptionContainer"], .stAlert p,
[data-testid="stButton"] button {
  font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif !important;
}

[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
section.main, .stApp, html, body {
  background:var(--ivory) !important;
}

.ernow-nav-rule {
  border-top:1px solid var(--tea);
  margin:.15rem 0 .55rem 0;
}

[data-testid="stButton"] > button {
  background:var(--shell);
  border:1px solid var(--tea);
  border-radius:10px;
  color:var(--ink);
  min-height:2.2rem;
  font-weight:600;
  white-space:nowrap;
}

[data-testid="stButton"] > button:hover {
  border-color:var(--kakishibu);
  color:var(--ink);
  background:var(--kakishibu-wash);
}

.ds-card {
  background:var(--shell);
  border:1px solid var(--tea);
  border-left:4px solid var(--moss);
  border-radius:14px;
  padding:.92rem 1rem;
  margin:.55rem 0 1.1rem;
}
.ds-title {font-weight:700;margin-bottom:.28rem}
.ds-sub {color:var(--soft-ink);font-size:.90rem;line-height:1.5}
.ds-tags {display:flex;flex-wrap:wrap;gap:.38rem .44rem;margin-top:.5rem}
.ds-tag {
  font-size:.71rem;
  border:1px solid var(--tea);
  background:var(--ivory);
  border-radius:999px;
  padding:.22rem .46rem;
  font-weight:600;
  color:var(--soft-ink);
}

.status-card {
  background:var(--shell);
  border:1px solid var(--tea);
  border-left:4px solid var(--moss);
  border-radius:14px;
  padding:.9rem 1rem;
  margin:.5rem 0 .95rem;
}
.status-title {font-weight:700;font-size:.98rem}
.status-copy {color:var(--soft-ink);font-size:.88rem;margin-top:.25rem;line-height:1.48}
.mini-grid {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:.5rem;
  margin:.45rem 0 1rem;
}
.mini-card {
  background:var(--shell);
  border:1px solid var(--tea);
  border-radius:12px;
  padding:.68rem .75rem;
}
.mini-label {
  font-size:.7rem;
  color:var(--soft-ink);
  text-transform:uppercase;
  letter-spacing:.04em;
  font-weight:600;
}
.mini-value {
  font-size:.95rem;
  font-weight:600;
  margin-top:.18rem;
  color:var(--ink);
  word-break:break-word;
}
.feature-grid {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:.5rem;
  margin:.4rem 0 .8rem;
}
.feature-card {
  background:var(--shell);
  border:1px solid var(--tea);
  border-radius:12px;
  padding:.72rem .78rem;
}
.feature-title {font-weight:600;font-size:.86rem;margin-bottom:.18rem}
.feature-copy {font-size:.78rem;color:var(--soft-ink);line-height:1.42}
.callout {
  background:var(--kakishibu-wash);
  border-left:3px solid var(--kakishibu);
  border-radius:10px;
  padding:.78rem .85rem;
  color:var(--soft-ink);
  font-size:.84rem;
  line-height:1.48;
  margin:.52rem 0 .82rem;
}
.note {
  background:var(--shell);
  border:1px solid var(--tea);
  border-radius:12px;
  padding:.78rem .85rem;
  color:var(--soft-ink);
  font-size:.84rem;
  line-height:1.5;
  margin:.52rem 0 .82rem;
}

h1 {margin-bottom:.3rem !important}
h2 {margin-top:1.55rem !important;margin-bottom:.42rem !important}
h3 {margin-top:1.15rem !important;margin-bottom:.35rem !important}
.stMarkdown p {margin:.15rem 0 .72rem !important}
.stMarkdown ul,.stMarkdown ol {margin-top:.18rem !important;margin-bottom:.85rem !important}
.stMarkdown li {margin-bottom:.22rem !important}
[data-testid="stDataFrame"] {margin:.45rem 0 .85rem !important}

@media(max-width:720px) {
  .mini-grid,.feature-grid {grid-template-columns:1fr}
}

/* ===== V3.1 typography + compact layout ===== */
/* Body stays Instrument Sans; headings and key numbers use Instrument Serif. */
.stApp h1, .stApp h2, .stApp h3,
.stApp [data-testid="stHeading"] h1, .stApp [data-testid="stHeading"] h2, .stApp [data-testid="stHeading"] h3 {
  font-family:'Instrument Serif',Georgia,'Times New Roman',serif !important;
  font-weight:400 !important; letter-spacing:-.01em !important; color:var(--ink) !important;
}
.stApp h1 {font-size:2.55rem !important; line-height:1.05 !important; margin:.2rem 0 .25rem !important; padding:0 !important}
.stApp h2 {font-size:1.75rem !important; margin:1.2rem 0 .3rem !important; padding:0 !important}
.stApp h3 {font-size:1.45rem !important; line-height:1.15 !important; margin:1.05rem 0 .3rem !important; padding:0 !important}
.er-wait, .evidence-value, .mini-value, .model-value {
  font-family:'Instrument Serif',Georgia,serif !important; font-weight:400 !important;
  font-variant-numeric:tabular-nums; letter-spacing:0 !important;
}
.block-container {padding-top:3rem !important; padding-bottom:1.5rem !important; max-width:980px !important}
.safety-banner {font-size:.86rem !important; padding:.62rem .9rem !important; border-radius:12px !important; margin:0 0 .6rem !important; font-weight:600 !important}
.ernow-nav-rule {margin:.05rem 0 .45rem !important}
[data-testid="stButton"] > button {min-height:1.95rem !important; padding:.2rem .7rem !important; font-size:.84rem !important}
.brand-sub {font-size:.9rem !important; line-height:1.45 !important; margin:0 0 .75rem !important; max-width:760px}
.model-bar {padding:.62rem .85rem !important; margin:.2rem 0 .6rem !important; border-radius:12px !important}
.model-line-1 {font-size:.88rem !important}
.model-line-2 {font-size:.79rem !important; margin-top:.18rem !important; font-weight:500 !important}
.model-meta {margin-top:.4rem !important}
.model-chip {font-size:.68rem !important; padding:.16rem .44rem !important}
.location-confirm {padding:.5rem .75rem !important; margin:.2rem 0 .45rem !important; font-size:.88rem !important}
[data-testid="stCaptionContainer"] {font-size:.78rem !important; line-height:1.45 !important}
hr, [data-testid="stDivider"] {margin:.55rem 0 .35rem !important}
.stMarkdown p {margin:.1rem 0 .55rem !important}
/* ER cards: two per row on desktop, one on phones */
.er-list {display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.65rem; margin:.35rem 0 .7rem}
.er-card {margin:0 !important; padding:.8rem .9rem .75rem !important; border-radius:14px !important; display:flex; flex-direction:column}
.er-best {border-width:2px !important}
.er-head {display:flex; align-items:baseline; flex-wrap:wrap; gap:.15rem .45rem}
.er-rank {font-family:'Instrument Serif',Georgia,serif !important; font-size:1.25rem !important; font-weight:400 !important; margin:0 !important; color:var(--moss)}
.er-title {font-size:.98rem !important; font-weight:650 !important; line-height:1.25 !important}
.best-label {font-size:.62rem !important; margin:0 !important; padding:.08rem .42rem; border-radius:999px; background:var(--moss); color:#fff !important; letter-spacing:.05em}
.er-flag {margin-left:0 !important; font-size:.62rem !important}
.er-wait-label {font-size:.72rem !important; margin-top:.45rem !important; letter-spacing:.01em}
.er-wait {font-size:1.7rem !important; line-height:1.1 !important; margin:.05rem 0 .5rem !important}
.er-stats {display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.45rem .8rem; padding-top:.5rem; border-top:1px solid rgba(185,173,145,.45)}
.er-stat-k {font-size:.64rem; text-transform:uppercase; letter-spacing:.05em; font-weight:600; color:var(--soft-ink); opacity:.85}
.er-stat-v {font-size:.88rem; font-weight:600; color:var(--ink); font-variant-numeric:tabular-nums}
.er-stat-v span {font-weight:500; color:var(--soft-ink); font-size:.78rem}
.er-actions {margin-top:.6rem !important}
.er-directions {font-size:.7rem !important; padding:.28rem .55rem !important}
/* Methodology + Forecast Model */
.ds-card {padding:.75rem .9rem !important; margin:.35rem 0 .8rem !important}
.ds-title {font-family:'Instrument Serif',Georgia,serif; font-weight:400 !important; font-size:1.25rem; margin-bottom:.2rem !important}
.ds-sub {font-size:.86rem !important}
.evidence-grid {grid-template-columns:repeat(4,minmax(0,1fr)) !important; gap:.5rem !important; margin:.35rem 0 .7rem !important}
.evidence-card {padding:.65rem .75rem !important}
.evidence-value {font-size:1.55rem !important; line-height:1.1 !important}
.evidence-copy {font-size:.76rem !important; line-height:1.4 !important}
.evidence-source {font-size:.6rem !important}
.model-grid {display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.5rem; margin:.35rem 0 .6rem}
.model-card {background:var(--shell); border:1px solid var(--tea); border-radius:12px; padding:.65rem .75rem}
.model-k {font-size:.64rem; text-transform:uppercase; letter-spacing:.05em; font-weight:600; color:var(--soft-ink)}
.model-value {font-size:1.45rem; line-height:1.15; color:var(--ink); margin:.1rem 0 .15rem}
.model-copy {font-size:.76rem; color:var(--soft-ink); line-height:1.4}
.status-card {padding:.65rem .85rem !important; margin:.3rem 0 .6rem !important}
.mini-grid {grid-template-columns:repeat(6,minmax(0,1fr)) !important; gap:.4rem !important; margin:.3rem 0 .7rem !important}
.mini-card {padding:.5rem .6rem !important}
.mini-label {font-size:.58rem !important}
.mini-value {font-size:1.35rem !important; margin-top:.05rem !important}
.callout, .note {font-size:.8rem !important; padding:.6rem .75rem !important; margin:.35rem 0 .6rem !important}
.stMarkdown table {font-size:.8rem !important; margin:.25rem 0 .6rem !important}
.stMarkdown th, .stMarkdown td {padding:.3rem .5rem !important}
.stMarkdown ul, .stMarkdown ol {margin:.1rem 0 .6rem !important}
.stMarkdown li {margin-bottom:.12rem !important; font-size:.9rem}
[data-testid="stTabs"] button p {font-size:.86rem !important; font-weight:600 !important}
[data-testid="stTabs"] [data-baseweb="tab-list"] {gap:.9rem}
@media(max-width:900px){.evidence-grid{grid-template-columns:repeat(2,minmax(0,1fr)) !important}.mini-grid{grid-template-columns:repeat(3,minmax(0,1fr)) !important}.model-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:650px){
  .block-container{padding-top:3.2rem !important}
  .stApp h1{font-size:2.1rem !important}
  .er-list,.evidence-grid,.model-grid{grid-template-columns:1fr !important}
  .mini-grid{grid-template-columns:repeat(2,minmax(0,1fr)) !important}
}

/* closest vs fastest answer */
.answer-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem;margin:.3rem 0 .35rem}
.answer-card,.answer-one{background:var(--shell);border:1px solid var(--tea);border-radius:14px;padding:.75rem .9rem}
.answer-one{margin:.3rem 0 .35rem;border:2px solid var(--moss)}
.answer-fast{border:2px solid var(--moss)}
.answer-k{font-size:.64rem;text-transform:uppercase;letter-spacing:.05em;font-weight:650;color:var(--soft-ink)}
.answer-v{font-family:'Instrument Serif',Georgia,serif;font-size:1.55rem;line-height:1.15;color:var(--ink);margin:.1rem 0 .15rem}
.answer-sub{font-size:.82rem;color:var(--soft-ink);font-variant-numeric:tabular-nums}
.closest-label{font-size:.62rem;padding:.08rem .42rem;border-radius:999px;border:1px solid var(--moss);color:var(--moss);font-weight:650;letter-spacing:.05em;text-transform:uppercase}
[data-testid="stRadio"] label p{font-size:.84rem !important;font-weight:600 !important}
.choice-callout{background:var(--shell);border:1px solid var(--tea);border-left:4px solid var(--kakishibu);border-radius:12px;padding:.7rem .85rem;margin:.2rem 0 .7rem}
.choice-callout .v{font-family:'Instrument Serif',Georgia,serif;font-size:1.45rem;line-height:1.15;color:var(--ink)}
.choice-callout .c{font-size:.8rem;color:var(--soft-ink);line-height:1.45;margin-top:.2rem}
@media(max-width:650px){.answer-grid{grid-template-columns:1fr}}
</style>
""", unsafe_allow_html=True)


def render_home():
    st.title("ERNow Boston")
    st.markdown('<div class="brand-sub">Compare Boston ERs in seconds, when you don’t have minutes to search. Six public data sources, one screen.</div>', unsafe_allow_html=True)

    national, _fc = load_national()
    if national:
        sp, iv, rk = national["split"], national["intervals"], national["ranking"]["selected"]
        st.markdown(
            f"""
    <div class="model-bar">
      <div class="model-line-1"><span class="model-dot"></span>National model: {html.escape(national['selected_model'])}</div>
      <div class="model-line-2">Trained on {sp['hospitals']:,} U.S. hospitals and tested on {sp['test_rows']:,} it had never seen: it picked the fastest ER in a local area {rk['fastest_pick_accuracy']:.0%} of the time, versus {rk['fastest_pick_random_baseline']:.0%} by chance.</div>
      <div class="model-meta">
        <span class="model-chip">{sp['hospitals']:,} U.S. hospitals</span>
        <span class="model-chip">{sp['total_rows']:,} hospital-periods</span>
        <span class="model-chip">Tested 80% ranges ({iv['test_coverage']:.0%} coverage)</span>
        <span class="model-chip">CMS releases {html.escape(national['releases'][0][:4])}–{html.escape(national['releases'][-1][:4])}</span>
      </div>
    </div>
    """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="model-bar"><div class="model-line-1"><span class="model-dot"></span>National model results not found</div><div class="model-line-2">Run <code>python national_model.py</code> to build them.</div></div>', unsafe_allow_html=True)

    st.subheader("Your location")
    location_slot = st.empty()
    with location_slot.container():
        location = streamlit_geolocation()

    origin_lat = origin_lon = None
    location_label = None
    if isinstance(location, dict) and location.get("latitude") is not None and location.get("longitude") is not None:
        origin_lat, origin_lon = float(location["latitude"]), float(location["longitude"])
        location_slot.empty()
        location_label = fetch_location_name(origin_lat, origin_lon)
        st.markdown(f'<div class="location-confirm">Location detected: {location_label}<span class="sub">Results updated from your current location.</span></div>', unsafe_allow_html=True)
    else:
        with st.expander("Location blocked? Choose a Boston area"):
            fallback = st.selectbox("Boston area", list(FALLBACK_ORIGINS.keys()))
            if st.button("Use this area", use_container_width=True):
                st.session_state["fallback_origin"] = fallback
        if st.session_state.get("fallback_origin"):
            fallback = st.session_state["fallback_origin"]
            origin_lat, origin_lon = FALLBACK_ORIGINS[fallback]
            location_label = fallback

    if origin_lat is None:
        st.info("Use **Get My Location**. That's the only input ERNow needs.")
        st.stop()

    loading_slot = st.empty()
    loading_slot.markdown('<div class="ernow-loading-wrap"><div class="ernow-loading"></div></div>', unsafe_allow_html=True)

    now_dt = datetime.now(EASTERN)
    df = load_fallback_data()
    cms = fetch_cms_metrics(tuple(df["cms_provider_id"].tolist()))
    cms_live = (not cms.empty) and ("cms_current_baseline" in cms) and cms["cms_current_baseline"].notna().any()
    if not cms.empty:
        df = df.merge(cms, on="cms_provider_id", how="left")
        if "cms_current_baseline" in df:
            mask = df["cms_current_baseline"].notna()
            df.loc[mask, "typical_ed_minutes"] = df.loc[mask, "cms_current_baseline"]

    weather_obs = fetch_current_weather(origin_lat, origin_lon)
    alerts = fetch_nws_alerts(origin_lat, origin_lon)
    ari = fetch_cdc_ari()
    major_events = major_event_titles(now_dt)
    ranked, context = build_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, major_events)
    loading_slot.empty()

    weather_status = weather_obs.get("description", "Unavailable") if weather_obs else "Unavailable"
    event_status = "; ".join(major_events[:2]) if major_events else "None detected"
    st.caption(
        f"Updated **{now_dt.strftime('%-I:%M %p')}** · {location_label} · "
        f"CMS data: **{'live' if cms_live else 'saved copy (live request failed)'}** · "
        f"Weather: **{weather_status}** · Respiratory illness: **{context['illness_label']}** · Major events: **{event_status}**"
    )

    st.divider()
    st.subheader("Nearby ERs")

    # Two answers up front: the closest ER (what most people look for) and the one likely
    # to get you seen and home fastest. Same hospital -> one clear answer.
    routed = ranked[ranked["route_ok"]]
    closest = routed.loc[routed["route_time_min"].idxmin()] if len(routed) else None
    fastest = ranked.iloc[0]
    if closest is not None:
        if closest["hospital"] == fastest["hospital"]:
            answer = (f'<div class="answer-one"><div class="answer-k">Closest and likely fastest overall</div>'
                      f'<div class="answer-v">{html.escape(str(fastest["hospital"]))}</div>'
                      f'<div class="answer-sub">~{fmt_minutes(fastest["route_time_min"])} drive · typical visit {fmt_range(fastest["visit_lo"], fastest["visit_hi"])}</div></div>')
        else:
            extra = fastest["route_time_min"] - closest["route_time_min"]
            saved = closest["visit_mid"] - fastest["visit_mid"]
            answer = (f'<div class="answer-k">Closest ER</div><div class="answer-v">{html.escape(str(closest["hospital"]))}</div>'
                      f'<div class="answer-sub">~{fmt_minutes(closest["route_time_min"])} drive · typical visit {fmt_range(closest["visit_lo"], closest["visit_hi"])}</div>')
            answer = (f'<div class="answer-grid"><div class="answer-card">{answer}</div>'
                      f'<div class="answer-card answer-fast"><div class="answer-k">Likely fastest overall</div>'
                      f'<div class="answer-v">{html.escape(str(fastest["hospital"]))}</div>'
                      f'<div class="answer-sub">{"+" if extra >= 0 else "−"}{fmt_minutes(abs(extra))} drive vs closest, '
                      f'typically ~{fmt_minutes(max(saved, 0))} shorter in the ED</div></div></div>')
        st.markdown(answer, unsafe_allow_html=True)
        st.caption("Emergency or getting worse? Go to the closest ER or call 911. "
                   "For urgent, non-life-threatening visits, the fastest overall option can save real time.")

    sort_by = st.radio("Sort ERs by", ["Fastest overall", "Closest"], horizontal=True, label_visibility="collapsed",
                       key="er_sort")
    if sort_by == "Closest":
        ranked = ranked.sort_values(["route_ok", "route_time_min"], ascending=[False, True]).reset_index(drop=True)
        st.caption("Sorted by drive time from your location. Each range is a hospital's typical performance for the next CMS period, not today's live queue.")
    else:
        st.caption("Sorted by drive time plus expected ED visit. Each range is a hospital's typical performance for the next CMS period, not today's live queue.")
    closest_name = None if closest is None else closest["hospital"]

    cards = []
    for pos, (_, row) in enumerate(ranked.iterrows(), start=1):
        row = row.copy()
        row["rank"] = pos
        best = " er-best" if row["hospital"] == fastest["hospital"] else ""
        best_label = '<span class="best-label">Likely fastest overall</span>' if row["hospital"] == fastest["hospital"] else ""
        if row["hospital"] == closest_name:
            best_label += '<span class="closest-label">Closest</span>'
        has_fc = pd.notna(row.get("visit_mid"))
        visit_range = (fmt_range(row["visit_lo"], row["visit_hi"]) if has_fc
                       else fmt_range(row["modeled_wait_low"], row["modeled_wait_high"]))
        headline_label = "Expected ED visit · tested 80% range" if has_fc else "Estimated ER wait"
        wait_range = fmt_minutes(row["legacy_wait_to_provider_min"])
        if pd.notna(row["route_time_min"]):
            drive = f"~{fmt_minutes(row['route_time_min'])}"
            drive_sub = f"{row['route_distance_miles']:.1f} mi" if pd.notna(row["route_distance_miles"]) else ""
        else:
            drive, drive_sub = "Unavailable", "ranked by ED time"
        cf = row.get("chance_fastest")
        chance = "—" if pd.isna(cf) else ("<1%" if cf < 0.005 else f"{cf:.0%}")
        vs = row.get("vs_peers_min")
        vs_txt = "—" if pd.isna(vs) else f"{'+' if vs >= 0 else '−'}{fmt_minutes(abs(vs))}"
        flag = ('<span class="er-flag">Unusual change since last release</span>' if row.get("change_flag") else "")
        directions_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={origin_lat},{origin_lon}"
            f"&destination={row['latitude']},{row['longitude']}"
            "&travelmode=driving"
        )
        cards.append(f"""<div class="er-card{best}">
      <div class="er-head"><span class="er-rank">{int(row['rank'])}</span><span class="er-title">{html.escape(str(row['hospital']))}</span>{best_label}{flag}</div>
      <div class="er-wait-label">{headline_label}</div><div class="er-wait">{visit_range}</div>
      <div class="er-stats">
        <div class="er-stat"><div class="er-stat-k">Drive</div><div class="er-stat-v">{drive} <span>{drive_sub}</span></div></div>
        <div class="er-stat"><div class="er-stat-k">Chance fastest</div><div class="er-stat-v">{chance}</div></div>
        <div class="er-stat"><div class="er-stat-k">Vs similar U.S. hospitals</div><div class="er-stat-v">{vs_txt}</div></div>
        <div class="er-stat"><div class="er-stat-k">Provider wait, 2019 data</div><div class="er-stat-v">{wait_range}</div></div>
      </div>
      <div class="er-actions"><a class="er-directions" href="{directions_url}" target="_blank" rel="noopener noreferrer">Open Directions</a></div>
    </div>""")
    st.markdown('<div class="er-list">' + "".join(cards) + '</div>', unsafe_allow_html=True)

    with st.expander("About today's Boston conditions"):
        st.write("Weather, respiratory illness, and major events are shown for context only. They do not change any number on this page, "
                 "because no public data exists to test such an adjustment. A learned respiratory-surge forecast is next on the roadmap.")
        if major_events:
            st.caption("Major event sources detected: " + "; ".join(major_events[:4]))
        else:
            st.caption("No qualifying major event was detected by the current source checks. This does not guarantee that no event is occurring.")
        st.caption("Every number on the ER cards is either public data or a model output tested on held-out hospitals.")

    st.subheader("Map")
    st.map(ranked[["hospital", "latitude", "longitude"]], latitude="latitude", longitude="longitude", size=95)


def _table(df):
    """Static markdown table: text wraps (never truncated) and there is no index column."""
    def cell(v):
        return str(v).replace("|", "\\|").replace("\n", " ")
    cols = list(df.columns)
    lines = ["| " + " | ".join(cell(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    st.markdown("\n".join(lines))


def _pct(v):
    return "—" if v is None or pd.isna(v) else f"{v:.0%}"


def render_methodology():
    st.title("Methodology")
    st.caption("Why ERNow exists, what it estimates, and exactly where every number comes from.")
    national, forecast = load_national()
    ev = (national or {}).get("evidence", {})

    st.markdown("""
    <div class="ds-card">
      <div class="ds-title">The mission: ER transparency now, not years from now</div>
      <div class="ds-sub">Boston has no single place to compare emergency departments, and hospitals do not publish live wait times. The useful data already exists, scattered across CMS, CHIA, the CDC, the Weather Service, event calendars, and maps. ERNow shows what is possible today with public data alone: one screen, seconds instead of minutes, with every number labeled by source and period.</div>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("Why it matters: the evidence")
    if ev:
        cards = [
            (fmt_minutes(ev["boston_spread_min"]),
             f"Gap in median ED visit time between Boston's fastest ({ev['boston_fastest']}, {fmt_minutes(ev['boston_fastest_min'])}) and slowest ({ev['boston_slowest']}, {fmt_minutes(ev['boston_slowest_min'])}) ED.",
             "CMS OP-18b, latest release"),
            (f"{ev['data_lag_months_min']:.0f}–{ev['data_lag_months_max']:.0f} months",
             "How long after a reporting period ends CMS publishes its ED data.",
             f"Computed across {ev['releases']} CMS releases"),
            ("~33% → ~44%",
             "Share of Massachusetts ED visits lasting over 4 hours, Jul–Sep 2019 vs Jul–Sep 2025.",
             "CHIA, reported by the Boston Globe (May 2026)"),
            (f"{ev['hospitals_latest_release']:,}",
             "U.S. hospitals the same pipeline already covers. Boston is the first city deployed.",
             "CMS Hospital Compare archives"),
        ]
        st.markdown('<div class="evidence-grid">' + "".join(
            f'<div class="evidence-card"><div class="evidence-value">{html.escape(v)}</div>'
            f'<div class="evidence-copy">{html.escape(c)}</div><div class="evidence-source">{html.escape(src)}</div></div>'
            for v, c, src in cards) + '</div>', unsafe_allow_html=True)

    choice_path = Path(__file__).resolve().parent / "data" / "boston_choice.json"
    if choice_path.exists():
        ch = json.loads(choice_path.read_text())
        st.markdown(
            f'<div class="choice-callout"><div class="v">The closest ER is usually not the fastest: {ch["closest_not_fastest_share"]:.0%} of Boston locations</div>'
            f'<div class="c">Across {ch["locations"]:,} points in Boston, for urgent but non-life-threatening visits, a different ER than the closest had the shortest '
            f'drive plus typical ED visit {ch["closest_not_fastest_share"]:.0%} of the time, typically about {fmt_minutes(ch["median_minutes_saved_when_different"])} shorter '
            f'for about {fmt_minutes(ch["median_extra_drive_min_when_different"])} more driving. Drive times in this analysis are estimated from distance; '
            'the app uses real road routing. In an emergency, always go to the closest ER.</div></div>', unsafe_allow_html=True)

    if national:
        sp, iv, rk = national["split"], national["intervals"], national["ranking"]["selected"]
        vals = {m["model"]: m for m in national["models"]}
        sel = vals[national["selected_model"]]
        st.subheader("The models behind it")
        tiles = [
            ("National forecaster", f"{sel['MAE']:.1f} min avg. error",
             f"Four models compared on {sp['hospitals']:,} U.S. hospitals ({sp['total_rows']:,} hospital-periods): Persistence, Ridge, partial pooling, gradient boosting. "
             f"{national['selected_model']} won on chronological validation (R² {sel['R2']:.2f})."),
            ("Tested ranges", f"{iv['backtest_coverage']:.0%} & {iv['test_coverage']:.0%} coverage",
             f"Regime-adaptive conformal prediction builds each 80% range from real errors and recent volatility; tested on two held-out years. "
             f"Median width {fmt_minutes(iv['median_width_min'])}, {iv['old_fixed_band_median_width_min'] / max(iv['median_width_min'], 1):.1f}× narrower than the old fixed band."),
            ("Ranking test", f"{rk['fastest_pick_accuracy']:.0%} vs {rk['fastest_pick_random_baseline']:.0%}",
             f"Picked the actual fastest ER in {rk['local_groups']} local areas {rk['fastest_pick_accuracy']:.0%} of the time, versus {rk['fastest_pick_random_baseline']:.0%} by chance."),
            ("Chance it's the fastest", "4,000 scenarios",
             "Monte Carlo simulation over each hospital's tested range plus your drive time turns uncertainty into one decision-ready probability."),
            ("Peer comparison", "25 nearest peers",
             "Nearest-neighbor matching on ED volume, hospital type, ownership, star rating, and case complexity (heart-attack and stroke volume, cardiac surgery, inpatient volume)."),
            ("Drivers & ablation", "Honest by design",
             "Permutation importance shows what moves ED time; ablation shows extra features did not beat Persistence, so ERNow keeps the simpler model."),
        ]
        st.markdown('<div class="model-grid">' + "".join(
            f'<div class="model-card"><div class="model-k">{html.escape(k)}</div><div class="model-value">{html.escape(v)}</div>'
            f'<div class="model-copy">{html.escape(c)}</div></div>' for k, v, c in tiles) + '</div>', unsafe_allow_html=True)
        st.caption("Full results, tables, and validation details are on the Forecast Model page.")

    st.subheader("Reading an ER card")
    st.markdown("""
    - **Expected ED visit:** typical time from arrival to leaving for patients sent home, with a range checked against real outcomes.
    - **Drive:** road route from where you are, without live traffic.
    - **Chance fastest:** how often this ER comes out quickest across 4,000 what-if scenarios.
    - **Vs similar U.S. hospitals:** faster or slower than comparable hospitals nationwide.
    - **Provider wait, 2019 data:** the last public CMS measure of time to see a provider (retired after 2019), shown as-is for context.
    """)
    st.caption("Cards are sorted by drive time plus expected ED visit. ERs without a route are listed last.")

    st.subheader("What would make this live")
    st.write("ERNow is built so that live hospital data could plug in directly. If Boston hospitals published these fields, ERNow could switch from typical performance to current conditions:")
    st.markdown("""
    - Current median time from arrival to first provider, updated hourly.
    - Number of patients waiting to be seen, by triage level.
    - Number of admitted patients boarding in the ED.
    - Ambulance diversion status.
    """)
    st.caption("Until then, every ERNow number is labeled with its source and period, so nothing is presented as live.")

    st.subheader("Data sources and freshness")
    fresh = pd.DataFrame([
        ["National model + ED visit time", "CMS Hospital Compare (OP-18b, OP-18c, OP-22, ED volume)", f"{len((national or {}).get('releases', []))} releases", "Annual-period medians; published 9–12 months later"],
        ["Case complexity (peers)", "CMS Complications & Deaths (patient volumes)", "Latest release", "Heart-attack/stroke volume, cardiac surgery, inpatient volume"],
        ["Hospital utilization", "CHIA Hospital Profiles", "HFY 2024", "Annual ED visits and inpatient occupancy (context)"],
        ["Provider wait", "CMS Hospital Compare OP-20 (retired)", "2019 or earlier", "Shown as-is for context"],
        ["Weather", "National Weather Service", "Current observation + alerts", "Boston-wide context"],
        ["Respiratory illness", "CDC Massachusetts ARI", "Latest reporting week", "Statewide context"],
        ["Major events", "Boston-area public sources", "Checked today", "Boston-wide context"],
        ["Route", "OpenStreetMap / OSRM (public demo server)", "At search", "No live traffic"],
    ], columns=["Factor", "Source", "Freshness", "Meaning"])
    _table(fresh)

    st.subheader("Limitations")
    st.markdown("""
    - ERNow cannot see live triage, staffing, open rooms, boarding, or how many people are waiting right now.
    - The forecast describes typical ED performance for a CMS period. No public source reports live waits, which is the gap ERNow is built to expose.
    - OP-18b covers discharged patients. Peer matching adjusts for case complexity with public proxies, not for each patient's severity.
    - Travel time excludes live traffic, parking, and ambulance transport.
    """)


def render_forecast_model():
    st.title("Forecast Model")
    st.caption("A national ED performance model, trained and tested on every U.S. hospital in the CMS archives, then applied to Boston.")
    national, forecast = load_national()
    if not national:
        st.info("Run `python national_model.py` to build the national model results.")
        return
    sp, iv = national["split"], national["intervals"]
    rk, rp = national["ranking"]["selected"], national["ranking"]["persistence"]

    st.markdown(
        '<div class="status-card"><div class="status-title">Selected model: ' + html.escape(national["selected_model"]) + '</div>'
        '<div class="status-copy">Every model was trained on earlier CMS releases, selected on the next release, and scored once on the latest release it had never seen.</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""<div class="mini-grid">
        <div class="mini-card"><div class="mini-label">U.S. hospitals</div><div class="mini-value">{sp['hospitals']:,}</div></div>
        <div class="mini-card"><div class="mini-label">Hospital-periods</div><div class="mini-value">{sp['total_rows']:,}</div></div>
        <div class="mini-card"><div class="mini-label">Held-out test rows</div><div class="mini-value">{sp['test_rows']:,}</div></div>
        <div class="mini-card"><div class="mini-label">80% range coverage</div><div class="mini-value">{iv['test_coverage']:.0%}</div></div>
        <div class="mini-card"><div class="mini-label">Fastest-pick accuracy</div><div class="mini-value">{rk['fastest_pick_accuracy']:.0%}</div></div>
        <div class="mini-card"><div class="mini-label">CMS releases</div><div class="mini-value">{len(national['releases'])}</div></div>
        </div>""",
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["Models", "Accuracy", "What drives it", "Boston & insights", "Freshness & details"])
    with tabs[0]:
        st.subheader("What the model predicts")
        st.write("Each hospital's next-period CMS OP-18b: the median time discharged patients spend in the ED from arrival to departure. "
                 "Features come only from releases available before the period being predicted, so there is no look-ahead leakage.")

        st.subheader("Model comparison")
        mt = pd.DataFrame(national["models"]).rename(columns={"model": "Model", "validation_MAE": "Validation MAE (min)",
                                                              "MAE": "Test MAE (min)", "RMSE": "Test RMSE (min)", "R2": "Test R²"})
        for c in ["Validation MAE (min)", "Test MAE (min)", "Test RMSE (min)"]:
            mt[c] = mt[c].map(lambda v: f"{v:.1f}")
        mt["Test R²"] = mt["Test R²"].map(lambda v: f"{v:.3f}")
        _table(mt)
        vals = {m["model"]: m["validation_MAE"] for m in national["models"]}
        base, best = vals["Persistence baseline"], vals[national["best_learned_model"]]
        gain = (base - best) / base
        if national["learned_model_promoted"]:
            summary = f"{national['best_learned_model']} beat Persistence by {gain:.1%} on validation, clearing the {national['promotion_margin']:.0%} promotion bar, so ERNow uses it."
        else:
            summary = (f"Even with {sp['total_rows']:,} rows, Persistence was hard to beat. The best challenger, {national['best_learned_model']}, "
                       f"improved validation error by {gain:.1%}, short of the {national['promotion_margin']:.0%} bar, so ERNow keeps Persistence. "
                       "The finding itself is useful: a hospital's ED performance is highly persistent from one year to the next, which is why last year's public number is already informative.")
        st.markdown(f'<div class="callout">{summary}</div>', unsafe_allow_html=True)
        st.caption(f"Train: {sp['train_rows']:,} rows ({sp['train_transitions']}). Validation: {sp['validation_rows']:,} rows ({sp['validation_transition']}). Test: {sp['test_rows']:,} rows ({sp['test_transition']}).")

    with tabs[1]:
        st.subheader("Tested 80% ranges")
        st.write(f"{iv['method']}. Ranges are calibrated on one release, then scaled by how much hospitals changed in the latest release "
                 "(known at prediction time), because a calm year and a volatile year need different widths.")
        cov = pd.DataFrame([
            ["Old fixed band (0.65×–1.55×)", _pct(iv["old_fixed_band_coverage"]), fmt_minutes(iv["old_fixed_band_median_width_min"])],
            ["Conformal, static", _pct(iv["static_test_coverage"]), fmt_minutes(iv["static_width_min"])],
            ["Conformal, regime-adaptive (current)", _pct(iv["test_coverage"]), fmt_minutes(iv["median_width_min"])],
        ], columns=["Range on the final test year", "Contained the actual value", "Median width"])
        _table(cov)
        st.caption(f"Target {iv['target_coverage']:.0%}. The adaptive method was chosen on an earlier held-out year ({_pct(iv['backtest_coverage'])} coverage) "
                   f"before the final test year ({_pct(iv['test_coverage'])}). It is {iv['old_fixed_band_median_width_min'] / max(iv['median_width_min'], 1):.1f}× narrower than the old band.")
        st.caption("Coverage by ED volume: " + " · ".join(f"{k} {_pct(v)}" for k, v in iv["coverage_by_volume"].items()) + ".")

        st.subheader("Does the ranking hold?")
        rt = pd.DataFrame([
            ["Rank correlation, all U.S. hospitals", f"{rk['national_spearman']:.2f}"],
            [f"Rank correlation within local areas ({rk['local_groups']} counties with 3+ hospitals)", f"{rk['mean_local_spearman']:.2f}"],
            ["Picked the actual fastest ER in the area", _pct(rk["fastest_pick_accuracy"])],
            ["Random pick would be right", _pct(rk["fastest_pick_random_baseline"])],
        ], columns=["Test", "Result"])
        _table(rt)
        bt = national.get("boston_backtest", {})
        if bt.get("hospitals"):
            st.caption(f"Boston backtest on the latest release: average error {bt['MAE_selected']:.1f} min across {bt['hospitals']} hospitals; "
                       f"rank correlation {bt['spearman_selected']:.2f}; fastest hospital predicted correctly: {'yes' if bt['fastest_pick_correct'] else 'no'}.")

    with tabs[2]:
        st.subheader("Which inputs actually help (ablation)")
        ab = pd.DataFrame(national["ablation"]).rename(columns={"features": "Gradient boosting features", "test_MAE": "Test MAE (min)"})
        ab["Test MAE (min)"] = ab["Test MAE (min)"].map(lambda v: f"{v:.2f}")
        _table(ab)
        st.caption("Adding feature groups did not beat Persistence on the test release. ERNow reports this rather than shipping a more complex model that does not help.")

        st.subheader("What drives changes in ED time")
        dr = pd.DataFrame(national["drivers"]).rename(columns={"feature": "Input", "importance_min": "Error increase when shuffled (min)"})
        names = {"state_mean_gap": "Gap to state average", "lag1": "Last reported ED time", "lag2": "ED time two releases ago",
                 "delta": "Most recent change", "op22": "Left without being seen (%)", "op18c": "Psychiatric-patient ED time",
                 "edv": "ED volume category", "rating": "CMS star rating", "hospital_type": "Hospital type",
                 "ownership": "Ownership", "state": "State", "peer_mean_gap": "Gap to peer average"}
        dr["Input"] = dr["Input"].map(names).fillna(dr["Input"])
        dr = dr[dr["Error increase when shuffled (min)"] > 0.005].copy()
        dr["Error increase when shuffled (min)"] = dr["Error increase when shuffled (min)"].map(lambda v: f"{v:.2f}")
        _table(dr)
        st.caption("Permutation importance on the test release for the gradient-boosting challenger: how much worse its predictions get when each input is scrambled.")

    with tabs[3]:
        st.subheader("Boston forecasts and peers")
        if forecast is not None:
            bf = pd.DataFrame({
                "Hospital": forecast["hospital"],
                "Latest ED visit": forecast["latest_op18b"].map(fmt_minutes),
                "Forecast (80% range)": [f"{fmt_minutes(a)} ({fmt_minutes(l)}–{fmt_minutes(h)})" for a, l, h in
                                         zip(forecast["forecast_op18b"], forecast["lo80"], forecast["hi80"])],
                "Similar U.S. hospitals": forecast["peer_median_op18b"].map(fmt_minutes),
                "Difference": [f"{'+' if v >= 0 else '−'}{fmt_minutes(abs(v))}" for v in forecast["vs_peers_min"]],
                "Unusual change": forecast["change_flag"].map({True: "Yes", False: "No"}),
            })
            _table(bf)
            st.caption(f"Latest period ends {forecast['period_end'].iloc[0]}. Peers are the 25 most similar U.S. hospitals by ED volume, type, ownership, star rating, and case complexity.")
            base = pd.read_csv(HOSPITAL_DATA)
            ctx = pd.DataFrame({"Hospital": base["hospital"],
                                "ED visits, HFY 2024": base["recent_ed_visits"].map(lambda v: f"{int(v):,}"),
                                "Inpatient occupancy, HFY 2024": base["recent_occupancy_pct"].map(lambda v: f"{v:.1f}%"),
                                "Provider wait, 2019 data": base["legacy_wait_to_provider_min"].map(fmt_minutes)})
            st.caption("Hospital context (CHIA annual profiles and the retired CMS OP-20 measure)")
            _table(ctx)

        st.subheader("Who waits longest")
        stc = national["structure"]
        if True:
            st.caption("By ED volume (latest release)")
            bv = pd.DataFrame(stc["by_volume"])
            bv = pd.DataFrame({"ED volume": bv["ed_volume"].str.capitalize(), "Hospitals": bv["hospitals"].map("{:,}".format),
                               "Median ED visit": bv["median_op18b"].map(fmt_minutes),
                               "Median left without being seen": bv["median_op22"].map(lambda v: f"{v:.0f}%")})
            _table(bv)
            st.caption("By ownership (six largest groups)")
            bo = pd.DataFrame(stc["by_ownership"]).sort_values("hospitals", ascending=False).head(6).sort_values("median_op18b", ascending=False)
            bo = pd.DataFrame({"Ownership": bo["ownership"], "Hospitals": bo["hospitals"].map("{:,}".format),
                               "Median ED visit": bo["median_op18b"].map(fmt_minutes),
                               "Median left without being seen": bo["median_op22"].map(lambda v: f"{v:.0f}%")})
            _table(bo)
        st.caption(f"Across U.S. hospitals, longer ED visits go with more patients leaving before being seen (rank correlation {stc['spearman_op18b_vs_left_without_being_seen']:.2f}).")

    with tabs[4]:
        st.subheader("Freshness and retraining")
        gen = pd.Timestamp(national["generated_at"]).strftime("%B %-d, %Y")
        st.write(f"Results generated {gen} from CMS releases {pd.Timestamp(national['releases'][0]).strftime('%b %Y')} to {pd.Timestamp(national['releases'][-1]).strftime('%b %Y')}. "
                 "When CMS publishes a new release, add its archive to `data/cms_archives/` and run `python national_model.py`; the app reads the new results automatically.")

        with st.expander("Technical details"):
            st.markdown(f"""
        **Target:** {national['target']}.

        **Models:** Persistence baseline; Ridge regression on the change; robust partial pooling (shrink toward state and peer averages, weights fit by least absolute error); gradient boosting on the change.

        **Validation:** chronological. Train on earlier releases, select on the next, test once on the latest. A learned model must beat Persistence by {national['promotion_margin']:.0%} on validation to be promoted.

        **Ranges:** regime-adaptive conformalized quantile regression: gradient-boosted 10th/90th percentiles, a calibration offset from the prior release, then scaled by the ratio of current to calibration-period national volatility (median absolute change).

        **Ranking:** Spearman rank correlation and fastest-pick accuracy within counties that have 3 or more hospitals.

        **Peers:** nearest neighbors on ED volume, CMS star rating, hospital type, ownership, and case complexity (heart-attack and stroke patient volume, cardiac-surgery capability, inpatient volume from CMS Complications & Deaths).
        """)
    st.divider()
    st.caption("ERNow Forecast Model · National CMS model · Not a live queue model.")


def _set_ernow_view(view_name):
    st.session_state["ernow_view"] = view_name


if "ernow_view" not in st.session_state:
    st.session_state["ernow_view"] = "ERNow"

st.markdown("""
<div class="safety-banner"><strong>Possible emergency?</strong> Call 911 or go to the nearest appropriate emergency department. Do not delay care or drive farther because of an ERNow estimate, and do not use this app while driving.</div>
""", unsafe_allow_html=True)

st.markdown('<div class="ernow-nav-rule"></div>', unsafe_allow_html=True)

current_view = st.session_state["ernow_view"]
nav1, nav2, nav3, _ = st.columns([1.10, 1.45, 1.45, 3.00])

with nav1:
    st.button(
        "ERNow",
        icon=":material/emergency:",
        use_container_width=True,
        key="nav_home",
        type="primary" if current_view == "ERNow" else "secondary",
        on_click=_set_ernow_view,
        args=("ERNow",),
    )

with nav2:
    st.button(
        "Methodology",
        icon=":material/menu_book:",
        use_container_width=True,
        key="nav_methodology",
        type="primary" if current_view == "Methodology" else "secondary",
        on_click=_set_ernow_view,
        args=("Methodology",),
    )

with nav3:
    st.button(
        "Forecast Model",
        icon=":material/monitoring:",
        use_container_width=True,
        key="nav_model",
        type="primary" if current_view == "Forecast Model" else "secondary",
        on_click=_set_ernow_view,
        args=("Forecast Model",),
    )

if current_view == "Methodology":
    render_methodology()
elif current_view == "Forecast Model":
    render_forecast_model()
else:
    render_home()
