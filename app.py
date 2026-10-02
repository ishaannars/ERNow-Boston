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
from concurrent.futures import ThreadPoolExecutor
from threading import current_thread
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

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


def decision_summary():
    """Measured decision times (record_decision_time.py); {} until the test has been run."""
    try:
        import record_decision_time
        return record_decision_time.summary()
    except Exception:
        return {}


def fmt_seconds(sec):
    sec = int(round(sec))
    return f"{sec // 60}m {sec % 60:02d}s" if sec >= 60 else f"{sec}s"


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
    "<style>" + (Path(__file__).parent / "styles.css").read_text() + "</style>",
    unsafe_allow_html=True,
)


def secret_or_env(name):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name)


def parallel_calls(calls, max_workers=8):
    """Run independent I/O together, retaining Streamlit's per-session cache context."""
    if not calls:
        return []
    ctx = get_script_run_ctx()
    def initialize_worker():
        if ctx is not None:
            add_script_run_ctx(current_thread(), ctx)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(calls)), initializer=initialize_worker) as pool:
        futures = [pool.submit(fn, *args) for fn, args in calls]
        return [future.result() for future in futures]


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


@st.cache_data(ttl=3600, show_spinner=False)
def load_fallback_data():
    df = pd.read_csv(DATA_PATH, dtype={"cms_provider_id": str})
    for col in ["typical_ed_minutes", "legacy_wait_to_provider_min", "recent_ed_visits", "recent_occupancy_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_cms_metrics(provider_ids):
    rows = []
    def fetch_provider(provider_id):
        return safe_get(URLS["cms"], params={"size": 100, "offset": 0, "filter[Facility ID]": provider_id}, timeout=5)
    responses = parallel_calls([(fetch_provider, (pid,)) for pid in provider_ids])
    for provider_id, r in zip(provider_ids, responses):
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
    # Reuse cached news and Ticketmaster results within the same quarter-hour.
    now_dt = now_dt.replace(minute=(now_dt.minute // 15) * 15, second=0, microsecond=0)
    day = now_dt.date().isoformat()
    events = []
    sources = parallel_calls([
        (fetch_city_events, (day,)),
        (fetch_tdgarden_events, (day,)),
        (fetch_red_sox_home_games, (day,)),
        (fetch_boston_news_event_layer, (now_dt.isoformat(),)),
    ], max_workers=4)
    for source in sources:
        events.extend(source)
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


def build_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, major_events, historical_layer=None, routes=None):
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
        route = (routes.get((row["latitude"], row["longitude"])) if routes is not None
                 else route_estimate(origin_lat, origin_lon, row["latitude"], row["longitude"]))
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
            "lwbs_pct": fc.get("left_without_seen_pct", float("nan")),
            "lwbs_us_median": fc.get("national_median_left_without_seen_pct", float("nan")),
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



def render_home():
    st.title("ERNow Boston")
    _nat, _ = load_national()
    _ds = decision_summary()
    # Tagline uses the measured median ERNow decision time, rounded to the nearest 5 seconds.
    tagline_secs = max(5, int(5 * round(_ds["ernow"]["median_seconds"] / 5))) if "ernow" in _ds else 15
    n_hosp = f"{_nat['split']['hospitals']:,}" if _nat else "4,000+"
    st.markdown('<div class="brand-sub">For urgent, non-life-threatening visits: find the ER that gets you seen and home fastest, '
                f'not just the closest, in about {tagline_secs} seconds.</div>'
                '<div class="brand-pitch">Live ER wait times could be years away. ERNow brings ER transparency to Boston now: '
                f'models built on {n_hosp} U.S. hospitals predict which ER will usually get you in and out fastest, drive included.</div>', unsafe_allow_html=True)

    national, _fc = load_national()
    if national:
        sp, iv, rk = national["split"], national["intervals"], national["ranking"]["selected"]
        vals_lm = {m["model"]: m["validation_MAE"] for m in national["models"]}
        best_gain = (vals_lm["Persistence baseline"] - vals_lm[national["best_learned_model"]]) / vals_lm["Persistence baseline"]
        live = [
            ("Expected ED visit", "Last year's figure", "ED times persist; in the latest test no learned model beat it by 2%."),
            ("The range on each card", f"{iv['test_coverage']:.0%} held true", "In a year the model never saw (target 80%)."),
            ("Vs similar hospitals", "25 look-alikes", "Matched on ED size, type, ownership, rating, and case mix."),
            ("Chance fastest", "4,000 trips", "Your drive, replayed over each ER's range."),
        ]
        techniques = ["Method: persistence", "Method: conformal ranges", "Method: nearest neighbors", "Method: trip simulation"]
        ds = decision_summary()
        measured = ""
        if "ernow" in ds and "quick" in ds:
            secs = lambda v: f"{int(round(v))} seconds" if v < 60 else fmt_seconds(v)
            measured = (f'<div class="live-proof" title="Median times, measured with timing_test.py">'
                        f'<b>Timed test: ERNow picked an ER in {secs(ds["ernow"]["median_seconds"])}.</b> '
                        f'A Google “ER near me” search took {secs(ds["quick"]["median_seconds"])} and only found the closest one.</div>')
        tiles = "".join(f'<div class="live-tile"><div class="live-k">{html.escape(k)}</div><div class="live-v">{html.escape(v)}</div>'
                        f'<div class="live-c">{html.escape(c)}</div><div class="live-t">{html.escape(t)}</div></div>'
                        for (k, v, c), t in zip(live, techniques))
        st.markdown(
            f"""<div class="model-bar">
      <div class="live-head"><span class="model-dot"></span><span class="live-title">4 models running live</span></div>
      {measured}
      <div class="live-meta">{sp['hospitals']:,} U.S. hospitals · {sp['total_rows']:,} hospital-periods · CMS {html.escape(national['releases'][0][:4])}–{html.escape(national['releases'][-1][:4])} ·
      in a held-out year, picked the local ER with the shortest visit {rk['fastest_pick_accuracy']:.0%} of the time vs {rk['fastest_pick_random_baseline']:.0%} by chance</div>
      <div class="live-grid">{tiles}</div>
    </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="model-bar"><div class="model-line-1"><span class="model-dot"></span>National model results not found</div><div class="model-line-2">Run <code>python national_model.py</code> to build them.</div></div>', unsafe_allow_html=True)

    saved = st.session_state.get("origin")
    origin_lat = origin_lon = None
    location_label = None
    if saved:
        origin_lat, origin_lon, location_label = saved
        st.subheader("Your visit")
        with st.container(border=True):
            loc_l, loc_r = st.columns([3, 1.4], vertical_alignment="center")
            with loc_l:
                st.markdown(f'<div class="location-confirm">Location: {html.escape(str(location_label))}'
                            f'<span class="sub">Results are for this spot.</span></div>', unsafe_allow_html=True)
            with loc_r:
                if st.button("Change location", key="change_location", use_container_width=True):
                    st.session_state.pop("origin", None)
                    st.session_state.pop("fallback_origin", None)
                    st.rerun()
            st.caption("Change location to use your device location again or choose a different Boston area. Saved for this visit only.")
    else:
        st.subheader("Get your location")
        location = streamlit_geolocation()
        if isinstance(location, dict) and location.get("latitude") is not None and location.get("longitude") is not None:
            origin_lat, origin_lon = float(location["latitude"]), float(location["longitude"])
            location_label = fetch_location_name(origin_lat, origin_lon)
        else:
            with st.expander("Location blocked? Choose a Boston area"):
                fallback = st.selectbox("Boston area", list(FALLBACK_ORIGINS.keys()))
                if st.button("Use this area", use_container_width=True):
                    st.session_state["fallback_origin"] = fallback
            if st.session_state.get("fallback_origin"):
                fallback = st.session_state["fallback_origin"]
                origin_lat, origin_lon = FALLBACK_ORIGINS[fallback]
                location_label = fallback
        if origin_lat is not None:
            # Remember it for this visit, so Methodology / Forecast Model and back don't ask again.
            st.session_state["origin"] = (origin_lat, origin_lon, location_label)
            st.rerun()

    if origin_lat is None:
        st.stop()


    now_dt = datetime.now(EASTERN)
    df_all = load_fallback_data()
    if "ed_type" not in df_all:
        df_all["ed_type"] = "general"
    df_all["ed_type"] = df_all["ed_type"].fillna("general")
    # General EDs are compared and ranked; specialty, pediatric, and VA EDs serve specific patients
    # and are shown separately so no one is sent to an ED that can't treat them.
    SYSTEMS = ["Any", "Mass General Brigham", "Beth Israel Lahey Health", "Boston Medical Center Health System", "Tufts Medicine"]
    with st.container(border=True):
        sel_l, sel_r = st.columns([1, 1.35])
        with sel_l:
            em_type = st.radio("Type of emergency", ["General", "Eye, ear, nose, or throat"], index=0, horizontal=True,
                               key="emergency_type", help="Eye, ear, nose, or throat brings in Mass Eye and Ear, the specialist ED.")
            st.caption("Choose General unless this is an eye, ear, nose, or throat problem.")
        with sel_r:
            my_system = st.selectbox("Your doctors' hospital system (optional)", SYSTEMS, index=0, key="my_system",
                                     help="Your records follow you within a system. ERNow still ranks by time, and shows the quickest ER in your system.")
            st.caption("Choose your doctors’ system to highlight its ERs and see its quickest option. Any compares all systems; ranking stays time-based.")
    status_slot = st.empty()
    focus = "specialty" if em_type != "General" else None
    sys_map = dict(zip(df_all["hospital"], df_all.get("health_system", pd.Series([""] * len(df_all)))))
    general = df_all[df_all["ed_type"] == "general"]
    # Eye/ENT: Mass Eye and Ear has public ED-time data, so it joins the full comparison.
    df = (pd.concat([general, df_all[df_all["ed_type"] == "specialty"]]) if focus == "specialty" else general).reset_index(drop=True)
    others = df_all[(df_all["ed_type"] != "general") & (df_all["ed_type"] != focus)].reset_index(drop=True)
    destinations = list(dict.fromkeys(zip(df_all["latitude"], df_all["longitude"])))
    def fetch_routes():
        values = parallel_calls([(route_estimate, (origin_lat, origin_lon, lat, lon)) for lat, lon in destinations])
        return dict(zip(destinations, values))
    cms, weather_obs, alerts, ari, major_events, routes = parallel_calls([
        (fetch_cms_metrics, (tuple(df["cms_provider_id"].dropna().tolist()),)),
        (fetch_current_weather, (origin_lat, origin_lon)),
        (fetch_nws_alerts, (origin_lat, origin_lon)),
        (fetch_cdc_ari, ()),
        (major_event_titles, (now_dt,)),
        (fetch_routes, ()),
    ], max_workers=6)
    cms_live = (not cms.empty) and ("cms_current_baseline" in cms) and cms["cms_current_baseline"].notna().any()
    if not cms.empty:
        df = df.merge(cms, on="cms_provider_id", how="left")
        if "cms_current_baseline" in df:
            mask = df["cms_current_baseline"].notna()
            df.loc[mask, "typical_ed_minutes"] = df.loc[mask, "cms_current_baseline"]

    ranked, context = build_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, major_events, routes=routes)

    weather_status = weather_obs.get("description", "Unavailable") if weather_obs else "Unavailable"
    event_status = "; ".join(major_events[:2]) if major_events else "None detected"
    status_slot.caption(
        f"Updated **{now_dt.strftime('%-I:%M %p')}** · {location_label} · "
        f"CMS data: **{'live' if cms_live else 'latest saved copy'}** · "
        f"Weather: **{weather_status}** · Respiratory illness: **{context['illness_label']}** · Major events: **{event_status}**"
    )

    st.divider()
    routed = ranked[ranked["route_ok"]]
    closest = routed.loc[routed["route_time_min"].idxmin()] if len(routed) else None
    fastest = ranked.iloc[0]          # ranked = drive + typical ED visit

    def opt_rows(r):
        tot = (r["route_time_min"] + r["visit_mid"]) if pd.notna(r["route_time_min"]) and pd.notna(r["visit_mid"]) else None
        return (f'<div class="opt-rows">'
                f'<div><span>Drive</span><b>~{fmt_minutes(r["route_time_min"])}</b></div>'
                f'<div><span>Typical ED visit</span><b>{fmt_range(r["visit_lo"], r["visit_hi"])}</b></div>'
                f'<div><span>Drive + typical visit</span><b>{"~" + fmt_minutes(tot) if tot else "—"}</b></div></div>')

    if focus == "specialty":
        st.caption("Mass Eye and Ear is included because this is an eye, ear, nose, or throat emergency. "
                   "For any other emergency, choose General.")

    specialist = None
    if focus == "specialty":
        sp_rows = ranked[ranked["hospital"].isin(df_all.loc[df_all["ed_type"] == "specialty", "hospital"])]
        specialist = sp_rows.iloc[0] if len(sp_rows) else None
    best = specialist if specialist is not None else fastest
    st.subheader("Your best option")
    if closest is not None:
        same = closest["hospital"] == best["hospital"]
        if specialist is not None:
            label = "Eye & ENT specialist" + (" · closest" if same else "")
            note = "Built for eye, ear, nose, and throat emergencies."
            if fastest["hospital"] != best["hospital"]:
                note += (f" {html.escape(str(fastest['hospital']))} is usually quicker overall "
                         f"(~{fmt_minutes(fastest['route_time_min'] + fastest['visit_mid'])}), but it's a general ED.")
        elif same:
            label, note = "Closest and usually quickest", "The closest ER is also the one that usually gets you seen and home fastest."
        else:
            extra = best["route_time_min"] - closest["route_time_min"]
            net = (closest["route_time_min"] + closest["visit_mid"]) - (best["route_time_min"] + best["visit_mid"])
            label = "Usually quickest overall"
            note = (f"Usually done about <b>{fmt_minutes(net)} sooner</b> than at the closest ER, "
                    f"{html.escape(str(closest['hospital']))} (~{fmt_minutes(closest['route_time_min'])} away), "
                    f"even after {fmt_minutes(max(extra, 0))} more driving." if net > 0 else
                    f"About the same total time as the closest ER, {html.escape(str(closest['hospital']))}.")
        if my_system != "Any":
            in_sys = ranked[ranked["hospital"].map(sys_map) == my_system]
            in_sys = in_sys[in_sys["route_ok"]].sort_values("access_mid")
            if sys_map.get(best["hospital"]) == my_system:
                note += f" It's in your system ({html.escape(my_system)})."
            elif len(in_sys):
                q = in_sys.iloc[0]
                diff = (q["route_time_min"] + q["visit_mid"]) - (best["route_time_min"] + best["visit_mid"])
                note += (f" Quickest in your system ({html.escape(my_system)}): <b>{html.escape(str(q['hospital']))}</b>, "
                         f"usually about {fmt_minutes(max(diff, 0))} longer overall.")
        st.markdown(f'<div class="answer-one"><div class="answer-k">{label}</div>'
                    f'<div class="answer-v">{html.escape(str(best["hospital"]))}</div>{opt_rows(best)}'
                    f'<div class="answer-note">{note}</div></div>', unsafe_allow_html=True)
        st.caption("“Usually” means typical public CMS times, not tonight's queue. Emergency or getting worse? "
                   "Go to the closest ER or call 911.")
        st.markdown('<div class="note"><strong>Insurance:</strong> every ER must examine and stabilize you regardless of insurance (EMTALA), '
                    'and emergency care at an out-of-network ER is billed at your in-network cost-sharing (No Surprises Act). '
                    'Follow-up care after you are stable can depend on your plan.</div>', unsafe_allow_html=True)

    st.subheader(f"All {len(ranked)} Boston ERs" + (" for this problem" if focus == "specialty" else ""))
    sort_opts = ["Closest", "Fastest overall"] + ([f"{my_system} first"] if my_system != "Any" else [])
    sort_by = st.radio("Sort by", sort_opts, index=0, horizontal=True, key="er_sort")
    if sort_by == "Closest":
        ranked = ranked.sort_values(["route_ok", "route_time_min"], ascending=[False, True]).reset_index(drop=True)
    elif sort_by.endswith(" first"):
        # Your system's ERs first, each group ordered by usual total time (drive + typical visit)
        ranked = ranked.assign(_in=ranked["hospital"].map(sys_map) == my_system)
        ranked = ranked.sort_values(["_in", "route_ok", "access_mid"], ascending=[False, False, True]).drop(columns="_in").reset_index(drop=True)
    if specialist is not None:   # the eye/ENT specialist leads when that's the emergency
        ranked = pd.concat([ranked[ranked["hospital"] == specialist["hospital"]],
                            ranked[ranked["hospital"] != specialist["hospital"]]]).reset_index(drop=True)
    st.caption("Times are each ER's typical performance from public CMS data, not tonight's live wait. Drive times use real roads without live traffic.")
    closest_name = None if closest is None else closest["hospital"]

    cards = []
    for pos, (_, row) in enumerate(ranked.iterrows(), start=1):
        top = " er-best" if row["hospital"] == best["hospital"] else ""
        tags = ""
        if row["hospital"] == closest_name:
            tags += '<span class="closest-label">Closest</span>'
        if specialist is not None and row["hospital"] == specialist["hospital"]:
            tags += '<span class="best-label">Eye &amp; ENT specialist</span>'
        if row["hospital"] == fastest["hospital"]:
            tags += '<span class="best-label">Usually quickest</span>'
        if my_system != "Any" and sys_map.get(row["hospital"]) == my_system:
            tags += '<span class="closest-label">Your system</span>'
        has_fc = pd.notna(row.get("visit_mid"))
        visit_range = (fmt_range(row["visit_lo"], row["visit_hi"]) if has_fc
                       else fmt_range(row["modeled_wait_low"], row["modeled_wait_high"]))
        vs = row.get("vs_peers_min")
        is_specialist = specialist is not None and row["hospital"] == specialist["hospital"]
        # A specialty eye/ENT hospital has no true national peers in CMS data, so no peer comparison for it.
        peer = ("" if pd.isna(vs) or is_specialist else
                f'<div class="er-peer">{fmt_minutes(abs(vs))} {"longer" if vs >= 0 else "shorter"} than similar U.S. hospitals</div>')
        if pd.notna(row["route_time_min"]):
            drive = f"~{fmt_minutes(row['route_time_min'])}"
            drive_sub = f"{row['route_distance_miles']:.1f} mi" if pd.notna(row["route_distance_miles"]) else ""
            total = f"~{fmt_minutes(row['route_time_min'] + row['visit_mid'])}" if has_fc else "—"
        else:
            drive, drive_sub, total = "Unavailable", "", "—"
        cf = row.get("chance_fastest")
        chance = "—" if pd.isna(cf) else ("&lt;1%" if cf < 0.005 else (">99%" if cf > 0.995 else f"{cf:.0%}"))
        lw, lw_us = row.get("lwbs_pct"), row.get("lwbs_us_median")
        lwbs = "—" if pd.isna(lw) else f"{lw:.0f}%"
        lwbs_sub = "2024" if pd.isna(lw_us) else f"U.S. {lw_us:.0f}% · 2024"
        flag = ('<span class="er-flag">Unusual change since last year</span>' if row.get("change_flag") else "")
        directions_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={origin_lat},{origin_lon}"
            f"&destination={row['latitude']},{row['longitude']}"
            "&travelmode=driving"
        )
        cards.append(f"""<div class="er-card{top}">
      <div class="er-tags"><span class="rank-chip">#{pos}</span>{tags}{flag}</div>
      <div class="er-head"><span class="er-title">{html.escape(str(row['hospital']))}</span></div>
      <div class="er-system">{html.escape(str(sys_map.get(row['hospital'], '')))}</div>
      <div class="er-wait-label">Typical ED visit · tested range</div><div class="er-wait">{visit_range}</div>{peer}
      <div class="er-stats">
        <div class="er-stat"><div class="er-stat-k">Drive</div><div class="er-stat-v">{drive} <span>{drive_sub}</span></div></div>
        <div class="er-stat"><div class="er-stat-k">Drive + typical visit</div><div class="er-stat-v">{total}</div></div>
        <div class="er-stat"><div class="er-stat-k">Chance fastest</div><div class="er-stat-v">{chance}</div></div>
        <div class="er-stat"><div class="er-stat-k">Left before seen</div><div class="er-stat-v">{lwbs} <span>{lwbs_sub}</span></div></div>
      </div>
      <div class="er-actions"><a class="er-directions" href="{directions_url}" target="_blank" rel="noopener noreferrer">Open Directions</a></div>
    </div>""")
    st.markdown('<div class="er-list">' + "".join(cards) + '</div>', unsafe_allow_html=True)
    st.caption("These are Boston's general emergency departments, compared side by side. Carney Hospital's ED closed in 2024. "
               "EDs outside Boston, such as Cambridge's, aren't included yet.")

    if len(others):
        _, fc_other = load_national()
        fc_map = {} if fc_other is None else fc_other.set_index("cms_provider_id").to_dict("index")
        tag_names = {"specialty": "Eye & ENT only", "pediatric": "Children only", "veterans": "Veterans only"}
        st.subheader("Other Boston emergency departments")
        st.caption("Open to specific patients only, so they aren't ranked against the EDs above. If one fits you, "
                   "it may be the right place to go." + ("" if focus else " For an eye, ear, nose, or throat emergency, change the type of emergency at the top."))
        ocards = []
        for _, o in others.iterrows():
            route = routes.get((o["latitude"], o["longitude"]))
            drive = f"~{fmt_minutes(route['minutes'])}" if route else "Unavailable"
            dist = f"{route['miles']:.1f} mi" if route else ""
            fc = fc_map.get(str(o.get("cms_provider_id") or "").split(".")[0].zfill(6), {})
            if fc:
                visit_k, visit_v = "Typical ED visit · tested range", fmt_range(fc["lo80"], fc["hi80"])
                visit_class = "er-wait er-wait-sm"
            else:
                visit_k, visit_v = "Typical ED visit", "No public ED-time data"
                visit_class = "er-no-data"
            url = ("https://www.google.com/maps/dir/?api=1"
                   f"&origin={origin_lat},{origin_lon}&destination={o['latitude']},{o['longitude']}&travelmode=driving")
            ocards.append(f"""<div class="er-card er-other">
      <div class="er-tags"><span class="closest-label">{html.escape(tag_names.get(o['ed_type'], 'Restricted'))}</span></div>
      <div class="er-head"><span class="er-title">{html.escape(str(o['hospital']))}</span></div>
      <div class="er-system">{html.escape(str(o.get('health_system') or ''))}</div>
      <div class="er-peer er-audience">{html.escape(str(o.get('who_for') or ''))}</div>
      <div class="er-wait-label">{visit_k}</div><div class="{visit_class}">{visit_v}</div>
      <div class="er-stats">
        <div class="er-stat"><div class="er-stat-k">Drive</div><div class="er-stat-v">{drive} <span>{dist}</span></div></div>
        <div class="er-stat"><div class="er-stat-k">Address</div><div class="er-stat-v er-address">{html.escape(str(o['address']))}</div></div>
      </div>
      <div class="er-actions"><a class="er-directions" href="{url}" target="_blank" rel="noopener noreferrer">Open Directions</a></div>
    </div>""")
        st.markdown('<div class="er-list er-list-3">' + "".join(ocards) + '</div>', unsafe_allow_html=True)

    with st.expander("About today's Boston conditions"):
        st.write("Weather, respiratory illness, and major events are shown for context only. They do not change any number on this page, "
                 "because no public data exists to test such an adjustment. A learned respiratory-surge forecast is next on the roadmap.")
        if major_events:
            st.caption("Major event sources detected: " + "; ".join(major_events[:4]))
        else:
            st.caption("No qualifying major event was detected by the current source checks. This does not guarantee that no event is occurring.")
        st.caption("Every number on the ER cards is either public data or a model output tested on held-out hospitals.")

    st.subheader("Map")
    map_df = pd.concat([ranked[["hospital", "latitude", "longitude"]], others[["hospital", "latitude", "longitude"]]], ignore_index=True)
    try:
        st.map(map_df, latitude="latitude", longitude="longitude", size=95, height=320)
    except TypeError:
        st.map(map_df, latitude="latitude", longitude="longitude", size=95)


def _table(df):
    """Readable, escaped tables with keyboard-accessible horizontal scrolling."""
    headers = "".join(f'<th scope="col">{html.escape(str(c))}</th>' for c in df.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>"
        for row in df.itertuples(index=False)
    )
    st.markdown(
        '<div class="table-scroll" role="region" aria-label="Results table" tabindex="0">'
        f"<table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _pct(v):
    return "—" if v is None or pd.isna(v) else f"{v:.0%}"


def render_methodology():
    st.title("Methodology")
    st.caption("Why ERNow exists, how it decides, and where every number comes from, in plain terms.")
    national, forecast = load_national()
    ev = (national or {}).get("evidence", {})

    st.markdown("""
    <div class="ds-card">
      <div class="ds-title">The mission: the ER that usually gets you in and out fastest, not just the closest</div>
      <div class="ds-sub"><strong>Live ER wait times could be years away. ERNow brings ER transparency to Boston now: models built on 4,400+ U.S. hospitals predict which ER will usually get you in and out fastest, drive included.</strong> Today people search "ER near me" and go to the closest one, with no information about the ED itself. Hospitals don't publish live waits, and ERNow doesn't need them: the differences come from staffing, size, boarding, and case mix, which change slowly. ERNow assembles the data from CMS, CHIA, the CDC, the Weather Service, and road routing into one screen, labels every number by source and period, and is built so live hospital data can plug in the day it exists.</div>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("Why this matters")
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
            (f"{ev['hospitals_with_op18b_latest']:,}",
             "U.S. hospitals with public ED-time data the same pipeline already covers. Boston is the first city deployed.",
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
            f'for about {fmt_minutes(ch["median_extra_drive_min_when_different"])} more driving. Drive times in this analysis are estimated from distance '
            + (f'(the finding holds at {ch["sensitivity"]["share_min"]:.0%}–{ch["sensitivity"]["share_max"]:.0%} from gridlock to free-flowing traffic); ' if ch.get("sensitivity") else '; ')
            + 'the app uses real road routing. In an emergency, always go to the closest ER.</div></div>', unsafe_allow_html=True)

    if national and ev:
        sel_m = {m["model"]: m for m in national["models"]}[national["selected_model"]]
        rk_m = national["ranking"]["selected"]
        st.subheader("Why it works without live data")
        why = [
            ("Differences persist", f"R² {sel_m['R2']:.2f}",
             f"A hospital's ED time predicts its next year's across {national['split']['hospitals']:,} U.S. hospitals. "
             "Size, staffing, boarding, and case mix change slowly."),
            ("Boston's order holds", f"Rank correlation {national['boston_backtest']['spearman_selected']:.2f}",
             f"Last year's public data put Boston's {national['boston_backtest']['hospitals']} EDs in the same order as the following year"
             + (", including the fastest one." if national["boston_backtest"].get("fastest_pick_correct") else ".")),
            ("The gaps are big", fmt_minutes(ev["boston_spread_min"]),
             "Between Boston's fastest and slowest EDs. Gaps this large are built into how EDs run, not tonight's luck."),
        ]
        st.markdown('<div class="model-grid">' + "".join(
            f'<div class="model-card"><div class="model-k">{html.escape(k)}</div><div class="model-value">{html.escape(v)}</div>'
            f'<div class="model-copy">{html.escape(c)}</div></div>' for k, v, c in why) + '</div>', unsafe_allow_html=True)
        st.markdown('<div class="note"><strong>Like restaurants:</strong> you don\'t need a live feed to know which place on your block is usually packed. '
                    '<strong>What ERNow can\'t see:</strong> a usually fast ED having a bad night. No public data shows how often that happens, '
                    'which is why ERNow shows tested ranges, labels everything "typical, not live," and is built to plug in live hospital data the day it exists.</div>',
                    unsafe_allow_html=True)

    ds = decision_summary()
    if "ernow" in ds and ({"full", "quick"} & set(ds)):
        e = fmt_seconds(ds["ernow"]["median_seconds"])
        cards = []
        if "quick" in ds:
            share = (f" From {ch['closest_not_fastest_share']:.0%} of Boston locations, the closest isn't the fastest overall." if choice_path.exists() else "")
            cards.append(("ERNow vs the usual search", f'{e} vs {fmt_seconds(ds["quick"]["median_seconds"])}',
                          f'"ER near me" finds only the closest ER. ERNow is faster and also shows the usually quickest one.{share}'))
        if "full" in ds:
            cards.append(("Information ERNow assembles", f'{fmt_seconds(ds["full"]["median_seconds"])} by hand',
                          "Gathering each ER's ED time and drive time by hand takes minutes; ERNow shows them on one screen."))
        st.markdown('<div class="answer-grid">' + "".join(
            f'<div class="answer-card"><div class="answer-k">{html.escape(k)}</div><div class="answer-v">{html.escape(v)}</div>'
            f'<div class="answer-sub">{html.escape(c)}</div></div>' for k, v, c in cards) + '</div>', unsafe_allow_html=True)
        st.caption("Timed with the protocol in TIMING_TEST.md.")

    if national:
        sp, iv, rk = national["split"], national["intervals"], national["ranking"]["selected"]
        vals = {m["model"]: m for m in national["models"]}
        sel = vals[national["selected_model"]]
        st.subheader("The models behind it, in plain terms")
        tiles = [
            ("National forecaster", f"{sel['MAE']:.1f} min avg. error",
             f"Four models compared on {sp['hospitals']:,} U.S. hospitals ({sp['total_rows']:,} hospital-periods): Persistence, Ridge, partial pooling, gradient boosting. "
             f"The best challenger was only {(vals[national['selected_model']]['validation_MAE'] - vals[national['best_learned_model']]['validation_MAE']) / vals[national['selected_model']]['validation_MAE']:.1%} better on validation, under the 2% bar, so ERNow keeps {national['selected_model']} (R² {sel['R2']:.2f})."),
            ("Tested ranges", f"{iv['test_coverage']:.0%} coverage, latest year",
             f"Conformal prediction builds each 80% range from real errors and recent volatility. Median width {fmt_minutes(iv['median_width_min'])}, "
             f"{iv['old_fixed_band_median_width_min'] / max(iv['median_width_min'], 1):.1f}× narrower than ERNow's early fixed range."
             + (f" Across {len(national.get('rolling') or [])} held-out years coverage ran "
                f"{min(r['coverage'] for r in national['rolling'] if r.get('coverage') is not None):.0%}–"
                f"{max(r['coverage'] for r in national['rolling'] if r.get('coverage') is not None):.0%}, missing most in volatile years."
                if any(r.get('coverage') is not None for r in (national.get('rolling') or [])) else "")),
            ("Ranking test", f"{rk['fastest_pick_accuracy']:.0%} vs {rk['fastest_pick_random_baseline']:.0%}",
             f"Picked the actual fastest ER in {rk['local_groups']} local areas {rk['fastest_pick_accuracy']:.0%} of the time, versus {rk['fastest_pick_random_baseline']:.0%} by chance."),
            ("Chance it's the fastest", "4,000 scenarios",
             "A trip simulation (Monte Carlo) replays your drive with each hospital's tested range 4,000 times, turning uncertainty into one decision-ready probability."),
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
    - **Typical ED visit:** how long patients who are sent home usually spend in that ED, from arrival to leaving (CMS OP-18b median, Persistence forecast). The range is an 80% conformal prediction interval, checked against real outcomes.
    - **Similar U.S. hospitals:** that time vs 25 look-alike hospitals nationwide (k-nearest neighbors on ED volume, type, ownership, star rating, and case-complexity proxies).
    - **Drive:** real road route from where you are (OpenStreetMap/OSRM), without live traffic.
    - **Drive + typical visit:** the two added together, which is how ERNow ranks "usually quickest" (the expected total, not a guarantee).
    - **Chance fastest:** how often this ER came out quickest across 4,000 simulated trips (a trip simulation, known in statistics as Monte Carlo, using each ER's range plus your drive).
    - **Left before seen (2024):** the share of patients who left before being seen (CMS OP-22). A high number signals long waits.
    - **Hospital system:** the network each ER belongs to. If you pick your doctors' system, ERNow tags its ERs and names the quickest one in it, because records follow you within a system. Ranking stays time-based.
    - **Insurance:** not a ranking factor. Every ER must treat you (EMTALA), and emergency care is billed at in-network cost-sharing even out of network (No Surprises Act).
    """)
    st.caption("Sort by Closest (the default) or by Fastest overall (drive + typical visit). ERs without a route are listed last. "
               "For an eye, ear, nose, or throat emergency, choosing that type of emergency adds Mass Eye and Ear to the comparison.")

    st.subheader("What would make it live")
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
        ["Left before being seen", "CMS Hospital Compare OP-22", "2024", "Shown on each ER card"],
        ["Hospital system", "Each health system's public hospital list", "Current", "Shown on each card; optional hospital-system preference"],
        ["Provider wait", "CMS Hospital Compare OP-20 (no longer published)", "2019 or earlier", "Context table on the Forecast Model page only"],
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
    st.markdown('<div class="note"><strong>Left out on purpose:</strong> hour-by-hour or day-of-week patterns (no public hospital-level data), '
                'traffic-aware drive times (paid APIs only), live waits (not published), Cambridge and other cities (next on the roadmap), '
                'and a respiratory-surge forecast (planned). Each was skipped because it would need data ERNow can\'t get or test today.</div>',
                unsafe_allow_html=True)


def render_forecast_model():
    st.title("Forecast Model")
    st.caption("The evidence behind ERNow, for anyone who wants to check it: tested on every U.S. hospital in the CMS archives, then applied to Boston.")
    national, forecast = load_national()
    if not national:
        st.info("Run `python national_model.py` to build the national model results.")
        return
    sp, iv = national["split"], national["intervals"]
    rk, rp = national["ranking"]["selected"], national["ranking"]["persistence"]

    sel_fm = {m["model"]: m for m in national["models"]}[national["selected_model"]]
    summary_cards = [
        ("Forecast accuracy", f"{sel_fm['MAE']:.1f} min avg. error",
         f"On {sp['test_rows']:,} U.S. hospitals in a year the model never saw (mean absolute error, R² {sel_fm['R2']:.2f})."),
        ("Honest ranges", f"{iv['test_coverage']:.0%} held the true value",
         f"Each 80% range contained the actual ED time {iv['test_coverage']:.0%} of the time in that held-out year (conformal prediction)."),
        ("Right ER", f"{rk['fastest_pick_accuracy']:.0%} vs {rk['fastest_pick_random_baseline']:.0%} by chance",
         f"How often it picked the actual fastest ER across {rk['local_groups']} local areas (ranking test)."),
    ]
    st.markdown('<div class="model-grid">' + "".join(
        f'<div class="model-card"><div class="model-k">{html.escape(k)}</div><div class="model-value">{html.escape(v)}</div>'
        f'<div class="model-copy">{html.escape(c)}</div></div>' for k, v, c in summary_cards) + '</div>', unsafe_allow_html=True)
    st.caption(f"Built on {sp['hospitals']:,} U.S. hospitals and {sp['total_rows']:,} hospital-periods from {len(national['releases'])} CMS releases. "
               "Every model learned from earlier releases, was chosen on the next one, and was scored once on the newest release it had never seen.")

    PLAIN_MODEL = {"Persistence baseline": "Persistence (last year's value)",
                   "Ridge regression": "Ridge regression (linear model)",
                   "Partial pooling (shrink toward state & peer means)": "Partial pooling (nudged toward similar hospitals)",
                   "Gradient boosting": "Gradient boosting (decision trees)"}
    best_plain = PLAIN_MODEL.get(national["best_learned_model"], national["best_learned_model"])
    tabs = st.tabs(["The forecast", "Is it accurate?", "What drives ED times", "Boston up close", "Data & updates"])
    with tabs[0]:
        st.caption("In plain terms: ERNow forecasts each hospital's typical ED visit for the next period, and checks that against what actually happened.")
        st.subheader("What it predicts")
        st.write("Each hospital's typical ED visit next period: the median time patients who are sent home spend in the ED, from arrival "
                 "to leaving (CMS measure OP-18b). It only uses data published before that period, so it never peeks at the answer "
                 "(no look-ahead leakage).")

        st.subheader("Which forecast is most accurate?")
        plain = {"Persistence baseline": "Persistence (last year's value)",
                 "Ridge regression": "Ridge regression (linear model)",
                 "Partial pooling (shrink toward state & peer means)": "Partial pooling (nudged toward similar hospitals)",
                 "Gradient boosting": "Gradient boosting (decision trees)"}
        mt = pd.DataFrame(national["models"])
        mt = pd.DataFrame({"Model": mt["model"].map(lambda m: plain.get(m, m)),
                           "Avg. error, selection year (MAE)": mt["validation_MAE"].map(lambda v: f"{v:.1f} min"),
                           "Avg. error, test year (MAE)": mt["MAE"].map(lambda v: f"{v:.1f} min"),
                           "Variance explained (R²)": mt["R2"].map(lambda v: f"{v:.3f}")})
        _table(mt)
        vals = {m["model"]: m["validation_MAE"] for m in national["models"]}
        base, best = vals["Persistence baseline"], vals[national["best_learned_model"]]
        gain = (base - best) / base
        if national["learned_model_promoted"]:
            summary = f"{national['best_learned_model']} beat Persistence by {gain:.1%} on validation, clearing the {national['promotion_margin']:.0%} promotion bar, so ERNow uses it."
        else:
            summary = (f"Even with {sp['total_rows']:,} hospital-periods, Persistence was hard to beat. The best challenger, {best_plain}, "
                       f"was {gain:.1%} more accurate in the selection year, short of the {national['promotion_margin']:.0%} bar, so ERNow keeps Persistence. "
                       "In stable years, this is the reason ERNow works: a hospital's ED performance is highly persistent from one year to the next, so last year's public number already points to the likely fastest ER, before any live data exists.")
        st.markdown(f'<div class="callout">{summary}</div>', unsafe_allow_html=True)
        st.caption(f"Learned from {sp['train_rows']:,} hospital-periods, chose a model on the next release ({sp['validation_rows']:,}), "
                   f"and scored it once on the newest release ({sp['test_rows']:,} hospitals).")

    with tabs[1]:
        st.caption("In plain terms: we hid the most recent year from the models, then checked how often they got it right.")
        roll = national.get("rolling") or []
        if roll:
            st.subheader("Year by year (rolling backtest)")
            yr = pd.DataFrame([{
                "Held-out CMS release": pd.Timestamp(r["target_release"]).strftime("%b %Y"),
                "Hospitals": f"{r['hospitals']:,}",
                "Persistence avg. error (MAE)": f"{r['persistence_MAE']:.1f} min",
                "Best challenger avg. error": f"{r['best_challenger_MAE']:.1f} min",
                "ERNow's rule used": {"Persistence baseline": "Persistence"}.get(r.get("rule_model"), "Learned model" if r.get("rule_model") else "—"),
                "80% range held the true value": _pct(r.get("coverage")),
                "Picked the fastest local ER": _pct(r.get("fastest_pick_accuracy")),
            } for r in roll])
            _table(yr)
            wins = sum(1 for r in roll if r["best_challenger_MAE"] <= r["persistence_MAE"] * (1 - national["promotion_margin"]))
            covs = [r["coverage"] for r in roll if r.get("coverage") is not None]
            cov_txt = f" Range coverage ran {min(covs):.0%}–{max(covs):.0%} against the 80% target." if covs else ""
            wf = national.get("walk_forward") or {}
            wf_txt = (f" Run year by year (choosing with last year's results), ERNow's rule averaged {wf['rule_MAE']:.1f} min of error vs "
                      f"{wf['always_persistence_MAE']:.1f} min for always using Persistence, switching to a learned model in "
                      f"{wf['years_rule_switched']} of {wf['years']} years." if wf.get("years") else "")
            st.caption(f"Each row trains only on releases before that year, then scores it once. In {wins} of {len(roll)} held-out years, "
                       f"a learned model beat Persistence by the {national['promotion_margin']:.0%} bar.{cov_txt}{wf_txt} "
                       "Ranges miss most in the most volatile years, when last year's pattern breaks.")

        st.subheader("Are the ranges honest?")
        st.write("Each range is built from the model's real past errors (conformal prediction), then widened or narrowed by how much "
                 "hospitals changed in the latest release, because a calm year and a volatile year need different widths "
                 "(regime-adaptive). That change is known before the forecast, so nothing is borrowed from the future.")
        cov = pd.DataFrame([
            ["Early version: fixed ±band", _pct(iv["old_fixed_band_coverage"]), fmt_minutes(iv["old_fixed_band_median_width_min"])],
            ["Conformal, fixed width", _pct(iv["static_test_coverage"]), fmt_minutes(iv["static_width_min"])],
            ["Conformal, adapts to volatility (live)", _pct(iv["test_coverage"]), fmt_minutes(iv["median_width_min"])],
        ], columns=["Method, on the held-out year", "Held the actual ED time", "Typical range width"])
        _table(cov)
        st.caption(f"Target {iv['target_coverage']:.0%}. The live method was chosen on an earlier held-out year ({_pct(iv['backtest_coverage'])}) before "
                   f"checking the final one ({_pct(iv['test_coverage'])}), and is {iv['old_fixed_band_median_width_min'] / max(iv['median_width_min'], 1):.1f}× "
                   "narrower than the early fixed band, which was wide enough to be nearly useless.")
        st.caption("Coverage by ED volume: " + " · ".join(f"{k} {_pct(v)}" for k, v in iv["coverage_by_volume"].items()) + ".")

        st.subheader("Does it pick the right ER?")
        rt = pd.DataFrame([
            ["Order of all U.S. hospitals matched reality (rank correlation, 1 = perfect)", f"{rk['national_spearman']:.2f}"],
            [f"Order within local areas matched reality ({rk['local_groups']} counties with 3+ hospitals)", f"{rk['mean_local_spearman']:.2f}"],
            ["Picked the actual fastest ER in the area", _pct(rk["fastest_pick_accuracy"])],
            ["A random pick would be right", _pct(rk["fastest_pick_random_baseline"])],
        ], columns=["Test, on the held-out year", "Result"])
        _table(rt)
        cf = national.get("confidence")
        if cf:
            st.subheader("How sure are these numbers?")
            lo_p, hi_p = cf["fastest_pick_ci95"]
            lo_c, hi_c = iv.get("test_coverage_ci95", [None, None])
            lo_g, hi_g = cf["mae_gain_ci95"]
            ct = pd.DataFrame([
                ["Picked the fastest local ER", _pct(rk["fastest_pick_accuracy"]), f"{lo_p:.0%}–{hi_p:.0%}"],
                ["80% range coverage", _pct(iv["test_coverage"]), f"{lo_c:.0%}–{hi_c:.0%}" if lo_c is not None else "—"],
                [f"{best_plain} vs Persistence (error saved per hospital)",
                 f"{cf['mae_gain_vs_best_challenger_min'] * 60:.0f} seconds", f"{lo_g * 60:.0f}–{hi_g * 60:.0f} seconds"],
            ], columns=["Result on the final test year", "Estimate", "95% confidence interval"])
            _table(ct)
            st.caption(f"Bootstrap with {cf['resamples']:,} resamples (hospitals for errors and coverage, counties for fastest-pick). "
                       + ("The best challenger's edge is real but tiny, seconds on a 3–5 hour visit," if lo_g > 0 else
                          "The best challenger's edge is not distinguishable from zero (its interval includes 0),")
                       + " and it missed the 2% bar on validation, so Persistence stays.")

        bt = national.get("boston_backtest", {})
        if bt.get("hospitals"):
            st.caption(f"Boston backtest on the latest release: average error {bt['MAE_selected']:.1f} min across {bt['hospitals']} hospitals; "
                       f"rank correlation {bt['spearman_selected']:.2f}; fastest hospital predicted correctly: {'yes' if bt['fastest_pick_correct'] else 'no'}.")

    with tabs[2]:
        st.caption("In plain terms: which information actually improves the forecast, and which doesn't.")
        st.subheader("Did extra data help? (ablation)")
        ab_names = {"Persistence (no features)": "Nothing extra: last year's value (Persistence)",
                    "History only": "Past ED times only",
                    "+ other ED measures": "+ other ED measures (left before seen, psychiatric ED time)",
                    "+ hospital characteristics": "+ hospital traits (volume, type, ownership, rating)",
                    "+ geography & peers (full)": "+ state and peer averages (everything)"}
        ab = pd.DataFrame(national["ablation"])
        ab = pd.DataFrame({"Information given to the model": ab["features"].map(lambda f: ab_names.get(f, f)),
                           "Avg. error, test year (MAE)": ab["test_MAE"].map(lambda v: f"{v:.2f} min")})
        _table(ab)
        st.caption("Adding feature groups did not beat Persistence on the test release. ERNow reports this rather than shipping a more complex model that does not help.")

        st.subheader("What moves ED times (permutation importance)")
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
        st.subheader("Who waits longest nationally")
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

    with tabs[3]:
        st.caption("In plain terms: the numbers behind each Boston card, and how Boston compares nationally.")
        st.subheader("Boston's ERs at a glance")
        if forecast is not None:
            forecast = forecast.sort_values("forecast_op18b").reset_index(drop=True)
            bf = pd.DataFrame({
                "Hospital": forecast["hospital"].replace({"Mass Eye and Ear": "Mass Eye and Ear (eye & ENT only)"}),
                "Latest ED visit": forecast["latest_op18b"].map(fmt_minutes),
                "Forecast (80% range)": [f"{fmt_minutes(a)} ({fmt_minutes(l)}–{fmt_minutes(h)})" for a, l, h in
                                         zip(forecast["forecast_op18b"], forecast["lo80"], forecast["hi80"])],
                "Similar U.S. hospitals": forecast["peer_median_op18b"].map(fmt_minutes),
                "Difference": [f"{'+' if v >= 0 else '−'}{fmt_minutes(abs(v))}" for v in forecast["vs_peers_min"]],
                "Left before being seen (2024)": forecast["left_without_seen_pct"].map(lambda v: "—" if pd.isna(v) else f"{v:.0f}%") if "left_without_seen_pct" in forecast else "—",
            "Unusual change": forecast["change_flag"].map({True: "Yes", False: "No"}),
            })
            _table(bf)
            st.caption(f"Latest period ends {forecast['period_end'].iloc[0]}. Peers are the 25 most similar U.S. hospitals by ED volume, type, ownership, star rating, and case complexity.")
            base = pd.read_csv(HOSPITAL_DATA)
            base = base[base["recent_ed_visits"].notna() | base["legacy_wait_to_provider_min"].notna()]
            ctx = pd.DataFrame({"Hospital": base["hospital"],
                                "ED visits, HFY 2024": base["recent_ed_visits"].map(lambda v: "—" if pd.isna(v) else f"{int(v):,}"),
                                "Inpatient occupancy, HFY 2024": base["recent_occupancy_pct"].map(lambda v: "—" if pd.isna(v) else f"{v:.1f}%"),
                                "Provider wait (pre-2020 data)": base["legacy_wait_to_provider_min"].map(fmt_minutes)})
            st.caption("Hospital context (CHIA annual profiles and the discontinued CMS OP-20 measure)")
            _table(ctx)


    with tabs[4]:
        st.subheader("How fresh is the data?")
        gen = pd.Timestamp(national["generated_at"]).strftime("%B %-d, %Y")
        st.write(f"Results generated {gen} from CMS releases {pd.Timestamp(national['releases'][0]).strftime('%b %Y')} to {pd.Timestamp(national['releases'][-1]).strftime('%b %Y')}. "
                 "ERNow is retrained each time CMS publishes a new release, so every number on these pages moves forward with the public data.")

        st.markdown('<div class="note"><strong>Tried or considered, and not shipped:</strong> a hierarchical mixed-effects model (partial pooling covers the same idea more simply), '
                    'SHAP values (permutation importance answers the same question without extra dependencies), deep learning (10 yearly releases per hospital is too little history '
                    'to train it reliably), and the 2016 CMS archive (its download link is offline).</div>', unsafe_allow_html=True)
        with st.expander("Technical details"):
            st.markdown(f"""
        **Target:** {national['target']}.

        **Models:** Persistence baseline; Ridge regression on the change; robust partial pooling (shrink toward state and peer averages, weights fit by least absolute error); gradient boosting on the change.

        **Validation:** chronological. Train on earlier releases, select on the next, test once on the latest. A learned model must beat Persistence by {national['promotion_margin']:.0%} on validation to be promoted.

        **Ranges:** regime-adaptive conformalized quantile regression: gradient-boosted 10th/90th percentiles, a calibration offset from the prior release, then scaled by the ratio of current to calibration-period national volatility (median absolute change).

        **Ranking:** Spearman rank correlation and fastest-pick accuracy within counties that have 3 or more hospitals.

        **Chance fastest:** 4,000 Monte Carlo draws per hospital from a lognormal matched to its 80% range, plus drive time; hospitals are treated as independent, which is an assumption.

        **What the 83% measures:** ranking hospitals by ED time within a county. The app's "usually quickest" also adds your drive time, which public data can't backtest.

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

loading_slot = st.empty()
loading_slot.markdown('<div class="ernow-loading-wrap"><div class="ernow-loading"></div></div>', unsafe_allow_html=True)
try:
    if current_view == "Methodology":
        render_methodology()
    elif current_view == "Forecast Model":
        render_forecast_model()
    else:
        render_home()
finally:
    # Clear the one loader after all cards, specialist routes, and the map render.
    loading_slot.empty()
