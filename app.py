from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from html import unescape
import html
from urllib.parse import quote
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
    """Small outputs of national_model.py: trained on eligible reporting U.S. hospitals in the CMS archives."""
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
    """Uncalibrated share of simulated drive + hospital-median scenarios won.

    Lognormal spread is approximated from interval bounds; patient-level visit
    variability is not measured. Missing routes or valid bounds are excluded.
    """
    drive_a, mid_a = np.asarray(drive, dtype=float), np.asarray(mid, dtype=float)
    lo_a, hi_a = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    ok = (np.isfinite(drive_a) & np.isfinite(mid_a) & np.isfinite(lo_a) & np.isfinite(hi_a)
          & (mid_a > 0) & (lo_a > 0) & (hi_a >= lo_a))
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
    station_urls = [station.get("id") or station.get("properties", {}).get("@id")
                    for station in features[:3]]
    observations = parallel_calls([
        (safe_get, (f"{url}/observations/latest",)) for url in station_urls if url
    ], max_workers=3)
    for obs in observations:
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


def build_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, major_events, routes=None):
    """Compare saved forecasts of hospital medians plus estimated drive time.

    Context does not alter estimates. Missing forecasts or routes stay unavailable.
    """
    national, forecast = load_national()
    fc_by_id = {} if forecast is None else forecast.set_index("cms_provider_id").to_dict("index")
    rows = []
    for _, row in df.iterrows():
        route = (routes.get((row["latitude"], row["longitude"])) if routes is not None
                 else route_estimate(origin_lat, origin_lon, row["latitude"], row["longitude"]))
        drive, miles = (float("nan"), float("nan")) if route is None else (route["minutes"], route["miles"])
        fc = fc_by_id.get(str(row["cms_provider_id"]).zfill(6), {})
        mid = fc.get("forecast_op18b", float("nan"))
        rows.append({
            **row.to_dict(),
            "route_time_min": drive, "route_distance_miles": miles,
            "visit_mid": mid, "visit_lo": fc.get("lo80", float("nan")),
            "visit_hi": fc.get("hi80", float("nan")),
            "visit_period_end": fc.get("period_end", ""),
            "vs_peers_min": fc.get("vs_peers_min", float("nan")),
            "lwbs_pct": fc.get("left_without_seen_pct", float("nan")),
            "lwbs_us_median": fc.get("national_median_left_without_seen_pct", float("nan")),
            "change_flag": bool(fc.get("change_flag", False)),
            "route_ok": bool(pd.notna(drive) and pd.notna(mid)),
            "access_mid": drive + mid if pd.notna(drive) and pd.notna(mid) else float("inf"),
        })
    out = pd.DataFrame(rows)
    out["chance_fastest"] = chance_fastest(out["route_time_min"], out["visit_mid"], out["visit_lo"], out["visit_hi"])
    out = out.sort_values(["route_ok", "access_mid", "visit_mid"], ascending=[False, True, True]).reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    return out, {"illness_label": (ari or {}).get("label", "Unavailable")}


def render_home():
    st.title("ERNow Boston")
    _nat, _ = load_national()
    n_hosp = f"{_nat['split']['hospitals']:,}" if _nat else "4,000+"
    st.markdown('<div class="brand-sub">For urgent, non-life-threatening visits: compare ERs by estimated drive + hospital median visit time, '
                f'in one screen.</div>'
                '<div class="brand-pitch">ERNow compares published performance now: '
                f'models built on {n_hosp} reporting U.S. hospitals compare typical ED visit times, drive included.</div>', unsafe_allow_html=True)

    national, _fc = load_national()
    if national:
        sp, iv, rk = national["split"], national["intervals"], national["ranking"]["selected"]
        vals_lm = {m["model"]: m["validation_MAE"] for m in national["models"]}
        best_gain = (vals_lm["Persistence baseline"] - vals_lm[national["best_learned_model"]]) / vals_lm["Persistence baseline"]
        live = [
            ("Hospital median visit", "Latest reported median" if national["selected_model"] == "Persistence baseline" else "Selected model forecast", f"Selected: {national['selected_model']}. Challenger validation gain {best_gain:.1%}; promotion threshold {national['promotion_margin']:.0%}."),
            ("The range on each card", f"{iv['test_coverage']:.0%} median coverage", "Held-out hospital medians, not individual visits (target 80%)."),
            ("Vs similar hospitals", "25 look-alikes", "Matched on ED size, type, ownership, rating, and case mix."),
            ("Fastest in simulation", "4,000 scenarios", "Drive + uncertain hospital medians; percentages not yet calibrated."),
        ]
        techniques = [f"Method: {national['selected_model']}", "Method: conformal ranges", "Method: nearest neighbors", "Method: trip simulation"]
        ds = decision_summary()
        measured = ""
        if "ernow" in ds and "quick" in ds:
            secs = lambda v: f"{int(round(v))} seconds" if v < 60 else fmt_seconds(v)
            measured = (f'<div class="live-proof" title="Median times, measured with timing_test.py">'
                        f'<b>Recorded decision median: ERNow {secs(ds["ernow"]["median_seconds"])} ({ds["ernow"]["participants"]} participants).</b> '
                        f'Nearest-ER search: {secs(ds["quick"]["median_seconds"])} ({ds["quick"]["participants"]} participants). Small convenience sample, not a controlled trial.</div>')
        tiles = "".join(f'<div class="live-tile"><div class="live-k">{html.escape(k)}</div><div class="live-v">{html.escape(v)}</div>'
                        f'<div class="live-c">{html.escape(c)}</div><div class="live-t">{html.escape(t)}</div></div>'
                        for (k, v, c), t in zip(live, techniques))
        st.markdown(
            f"""<div class="model-bar">
      <div class="live-head"><span class="model-dot"></span><span class="live-title">4 methods behind the comparison</span></div>
      {measured}
      <div class="live-meta">{sp['hospitals']:,} U.S. hospitals · {sp['total_rows']:,} labeled release pairs · CMS {html.escape(national['releases'][0][:4])}–{html.escape(national['releases'][-1][:4])} ·
      hospital-median error {next(m['MAE'] for m in national['models'] if m['model'] == national['selected_model']):.1f} min · on a held-out release, selected the shortest observed median in {rk['local_groups']} counties {rk['fastest_pick_accuracy']:.0%} of the time vs {rk['fastest_pick_random_baseline']:.0%} by chance</div>
      <div class="live-grid">{tiles}</div>
    </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="model-bar"><div class="model-line-1"><span class="model-dot"></span>National model results not found</div><div class="model-line-2">Run <code>python national_model.py</code> to build them.</div></div>', unsafe_allow_html=True)

    if national is None or _fc is None:
        loading_slot.empty()
        st.stop()

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
                    loading_slot.empty()
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
            loading_slot.empty()
            st.rerun()

    if origin_lat is None:
        loading_slot.empty()
        st.stop()


    now_dt = datetime.now(EASTERN)
    df_all = load_fallback_data()
    if "ed_type" not in df_all:
        df_all["ed_type"] = "general"
    df_all["ed_type"] = df_all["ed_type"].fillna("general")
    # General EDs are compared and ranked; specialty, pediatric, and VA EDs serve specific patients
    # and are shown separately so specialist services are distinguished from general EDs.
    SYSTEMS = ["Any", "Mass General Brigham", "Beth Israel Lahey Health", "Boston Medical Center Health System", "Tufts Medicine"]
    with st.container(border=True):
        sel_l, sel_r = st.columns([1, 1.35])
        with sel_l:
            em_type = st.radio("Type of emergency", ["General", "Eye, ear, nose, or throat"], index=0, horizontal=True,
                               key="emergency_type", help="Eye, ear, nose, or throat brings in Mass Eye and Ear, the specialist ED.")
            st.caption("Choose General unless this is an eye, ear, nose, or throat problem.")
        with sel_r:
            my_system = st.selectbox("Your doctors' hospital system (optional)", SYSTEMS, index=0, key="my_system",
                                     help="Your system may help with care continuity; record sharing varies. ERNow still ranks by estimated time and names its lowest-total ER.")
            st.caption("Choose your doctors’ system to highlight its ERs and see its lowest estimated total. Any compares all systems; ranking stays time-based.")
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
    weather_obs, alerts, ari, major_events, routes = parallel_calls([
        (fetch_current_weather, (origin_lat, origin_lon)),
        (fetch_nws_alerts, (origin_lat, origin_lon)),
        (fetch_cdc_ari, ()),
        (major_event_titles, (now_dt,)),
        (fetch_routes, ()),
    ], max_workers=6)
    ranked, context = build_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, major_events, routes=routes)

    weather_status = weather_obs.get("description", "Unavailable") if weather_obs else "Unavailable"
    event_status = "; ".join(major_events[:2]) if major_events else "None detected"
    status_slot.caption(
        f"Updated **{now_dt.strftime('%-I:%M %p')}** · {location_label} · "
        f"CMS release: **{pd.Timestamp(national['releases'][-1]).strftime('%b %Y') if national else 'unavailable'} (saved)** · "
        f"Weather: **{weather_status}** · Respiratory illness: **{context['illness_label']}** · Major events: **{event_status}**"
    )

    st.divider()
    routed = ranked[ranked["route_ok"]]
    closest = routed.loc[routed["route_time_min"].idxmin()] if len(routed) else None
    fastest = routed.iloc[0] if len(routed) else None
    if fastest is None:
        st.info("Drive-inclusive comparison is unavailable. Hospital-median forecasts are shown below; no lowest-total ER is identified.")

    def opt_rows(r):
        tot = (r["route_time_min"] + r["visit_mid"]) if pd.notna(r["route_time_min"]) and pd.notna(r["visit_mid"]) else None
        return (f'<div class="opt-rows">'
                f'<div><span>Drive</span><b>~{fmt_minutes(r["route_time_min"])}</b></div>'
                f'<div><span>Hospital median visit</span><b>{fmt_range(r["visit_lo"], r["visit_hi"])}</b></div>'
                f'<div><span>Drive + typical visit</span><b>{"~" + fmt_minutes(tot) if tot else "—"}</b></div></div>')

    if focus == "specialty":
        st.caption("Mass Eye and Ear is included because this is an eye, ear, nose, or throat emergency. "
                   "For any other emergency, choose General.")

    specialist = None
    if focus == "specialty":
        sp_rows = ranked[ranked["hospital"].isin(df_all.loc[df_all["ed_type"] == "specialty", "hospital"])]
        specialist = sp_rows.iloc[0] if len(sp_rows) else None
    best = specialist if specialist is not None else fastest
    st.subheader("Your comparison at a glance")
    if closest is not None and best is not None:
        same = closest["hospital"] == best["hospital"]
        if specialist is not None:
            label = "Eye & ENT specialist" + (" · closest" if same else "")
            note = "Built for eye, ear, nose, and throat emergencies."
            if fastest is not None and fastest["hospital"] != best["hospital"]:
                note += (f" {html.escape(str(fastest['hospital']))} has a lower estimated total "
                         f"(~{fmt_minutes(fastest['route_time_min'] + fastest['visit_mid'])}), but it's a general ED.")
        elif same:
            label, note = "Closest and lowest estimated total", "The closest ER also has the lowest estimated drive + hospital median visit time."
        else:
            extra = best["route_time_min"] - closest["route_time_min"]
            net = (closest["route_time_min"] + closest["visit_mid"]) - (best["route_time_min"] + best["visit_mid"])
            label = "Lowest estimated total"
            note = (f"Estimated drive + median visit is <b>{fmt_minutes(net)} shorter</b> than at the closest ER, "
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
                note += (f" Lowest estimated total in your system ({html.escape(my_system)}): <b>{html.escape(str(q['hospital']))}</b>, "
                         f"about {fmt_minutes(max(diff, 0))} longer in estimated drive + median visit.")
        st.markdown(f'<div class="answer-one"><div class="answer-k">{label}</div>'
                    f'<div class="answer-v">{html.escape(str(best["hospital"]))}</div>{opt_rows(best)}'
                    f'<div class="answer-note">{note}</div></div>', unsafe_allow_html=True)
        st.caption("Ranges forecast hospital medians, not your personal visit length. OP-18b excludes psychiatric/mental-health and transfer visits. Emergency or getting worse? "
                   "Go to the nearest appropriate ER or call 911.")
        st.markdown('<div class="note"><strong>Emergency care:</strong> Medicare-participating ERs must screen for an emergency condition '
                    'and stabilize it or arrange an appropriate transfer, regardless of ability to pay. '
                    'For most private insurance, covered emergency services generally have in-network cost-sharing protections. '
                    'Plan exceptions, follow-up care, and ground ambulance billing can differ. '
                    '<a href="https://www.cms.gov/medical-bill-rights">CMS patient rights</a>.</div>', unsafe_allow_html=True)

    st.subheader(f"Compare {len(ranked)} Boston ERs" + (" for this problem" if focus == "specialty" else ""))
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
    st.caption("CMS hospital medians, not live waits or personal visit predictions. Drives exclude live traffic. Simulation percentages are uncalibrated and exclude ERs without routes.")
    closest_name = None if closest is None else closest["hospital"]

    cards = []
    for pos, (_, row) in enumerate(ranked.iterrows(), start=1):
        top = " er-best" if best is not None and row["hospital"] == best["hospital"] else ""
        tags = ""
        if row["hospital"] == closest_name:
            tags += '<span class="closest-label">Closest</span>'
        if specialist is not None and row["hospital"] == specialist["hospital"]:
            tags += '<span class="best-label">Eye &amp; ENT specialist</span>'
        if fastest is not None and row["hospital"] == fastest["hospital"]:
            tags += '<span class="best-label">Lowest estimated total</span>'
        if my_system != "Any" and sys_map.get(row["hospital"]) == my_system:
            tags += '<span class="closest-label">Your system</span>'
        has_fc = pd.notna(row.get("visit_mid"))
        visit_range = (fmt_range(row["visit_lo"], row["visit_hi"]) if has_fc
                       else "Forecast unavailable")
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
        flag = ('<span class="er-flag">Unusual change since prior release</span>' if row.get("change_flag") else "")
        directions_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={origin_lat},{origin_lon}"
            f"&destination={quote(str(row['address']))}"
            "&travelmode=driving"
        )
        cards.append(f"""<div class="er-card{top}">
      <div class="er-tags"><span class="rank-chip">#{pos}</span>{tags}{flag}</div>
      <div class="er-head"><span class="er-title">{html.escape(str(row['hospital']))}</span></div>
      <div class="er-system">{html.escape(str(sys_map.get(row['hospital'], '')))}</div>
      <div class="er-wait-label" title="Forecast range for a hospital median, not an individual visit. Latest CMS reporting period ends {row['visit_period_end']}.">Forecast median {fmt_minutes(row["visit_mid"])} · target-80% range</div><div class="er-wait">{visit_range}</div>{peer}
      <div class="er-stats">
        <div class="er-stat"><div class="er-stat-k">Drive</div><div class="er-stat-v">{drive} <span>{drive_sub}</span></div></div>
        <div class="er-stat"><div class="er-stat-k">Drive + typical visit</div><div class="er-stat-v">{total}</div></div>
        <div class="er-stat"><div class="er-stat-k">Fastest in simulation</div><div class="er-stat-v">{chance}</div></div>
        <div class="er-stat"><div class="er-stat-k">Left before seen</div><div class="er-stat-v">{lwbs} <span>{lwbs_sub}</span></div></div>
      </div>
      <div class="er-actions"><a class="er-directions" href="{directions_url}" target="_blank" rel="noopener noreferrer">Open Directions</a></div>
    </div>""")
    st.markdown('<div class="er-list">' + "".join(cards) + '</div>', unsafe_allow_html=True)
    st.caption("Seven general EDs included in this Boston comparison. Carney Hospital's ED closed in 2024. "
               "EDs outside Boston, such as Cambridge's, aren't included yet.")

    if len(others):
        _, fc_other = load_national()
        fc_map = {} if fc_other is None else fc_other.set_index("cms_provider_id").to_dict("index")
        tag_names = {"specialty": "Eye & ENT", "pediatric": "Pediatric ED", "veterans": "Veterans’ ED"}
        st.subheader("Other Boston emergency departments")
        st.caption("Specialist, pediatric, and veterans’ services are listed separately. Eligibility and services vary; this app does not determine clinical suitability." + ("" if focus else " For an eye, ear, nose, or throat emergency, change the type of emergency at the top."))
        ocards = []
        for _, o in others.iterrows():
            route = routes.get((o["latitude"], o["longitude"]))
            drive = f"~{fmt_minutes(route['minutes'])}" if route else "Unavailable"
            dist = f"{route['miles']:.1f} mi" if route else ""
            fc = fc_map.get(str(o.get("cms_provider_id") or "").split(".")[0].zfill(6), {})
            if fc:
                visit_k, visit_v = f"Forecast median {fmt_minutes(fc['forecast_op18b'])} · target-80% range", fmt_range(fc["lo80"], fc["hi80"])
                visit_class = "er-wait er-wait-sm"
            else:
                visit_k, visit_v = "Typical ED visit", "No public ED-time data"
                visit_class = "er-no-data"
            url = ("https://www.google.com/maps/dir/?api=1"
                   f"&origin={origin_lat},{origin_lon}&destination={quote(str(o['address']))}&travelmode=driving")
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
            st.caption("No qualifying major event was detected. Feeds may be unavailable or incomplete; this does not guarantee that no event is occurring.")
        st.caption("ER cards combine public hospital data, held-out-tested median forecasts, road estimates, and uncalibrated simulation shares.")

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
      <div class="ds-title">The mission: compare typical ED visit times alongside the drive</div>
      <div class="ds-sub"><strong>ERNow compares published performance now: models built on 4,400+ reporting U.S. hospitals compare median ED visit times alongside driving estimates.</strong> The nearest-ER search used in the timing protocol compares location. ERNow adds historical hospital medians. Differences may reflect case mix, staffing, and operations; this model does not establish their causes. ERNow assembles the data from CMS, CHIA, the CDC, the Weather Service, and road routing into one screen, labels every number by source and period, and is built so live hospital data can plug in the day it exists.</div>
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
             "Massachusetts treat-and-release ED visits over 4 hours: Oct–Dec 2019 vs Jul–Sep 2025.",
             "CHIA quarterly ED databook, sheet VI-1 (Sept 2026)"),
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
            f'<div class="choice-callout"><div class="v">Lowest estimated total differs from closest at {ch["closest_not_fastest_share"]:.0%} of sampled points</div>'
            f'<div class="c">Across {ch["locations"]:,} sampled points near Boston ERs, for urgent but non-life-threatening visits, a different ER than the closest had the shortest '
            f'drive plus hospital median visit at {ch["closest_not_fastest_share"]:.0%} of grid points, typically about {fmt_minutes(ch["median_minutes_saved_when_different"])} shorter '
            f'for about {fmt_minutes(ch["median_extra_drive_min_when_different"])} more driving. Drive times in this analysis are estimated from distance '
            + (f'(the finding holds at {ch["sensitivity"]["share_min"]:.0%}–{ch["sensitivity"]["share_max"]:.0%} under assumed driving speeds of 5–30 mph); ' if ch.get("sensitivity") else '; ')
            + 'the app uses real road routing. In an emergency, call 911 or go to the nearest appropriate ER.</div></div>', unsafe_allow_html=True)

    if national and ev:
        sel_m = {m["model"]: m for m in national["models"]}[national["selected_model"]]
        rk_m = national["ranking"]["selected"]
        st.subheader("Why it works without live data")
        why = [
            ("Differences persist", f"R² {sel_m['R2']:.2f}",
             f"The latest reported median predicts the next release’s median across {national['split']['hospitals']:,} U.S. hospitals. "
             "This is an association in published medians, not a causal explanation."),
            ("Boston's order holds", f"Rank correlation {national['boston_backtest']['spearman_selected']:.2f}",
             f"Last year's public data put Boston's {national['boston_backtest']['hospitals']} EDs in the same order as the following year"
             + (", including the fastest one." if national["boston_backtest"].get("fastest_pick_correct") else ".")),
            ("The gaps are big", fmt_minutes(ev["boston_spread_min"]),
             "Between Boston's fastest and slowest EDs. Published median differences do not establish their causes or tonight’s waits."),
        ]
        st.markdown('<div class="model-grid">' + "".join(
            f'<div class="model-card"><div class="model-k">{html.escape(k)}</div><div class="model-value">{html.escape(v)}</div>'
            f'<div class="model-copy">{html.escape(c)}</div></div>' for k, v, c in why) + '</div>', unsafe_allow_html=True)
        st.markdown('<div class="note"><strong>Like restaurants:</strong> you don\'t need a live feed to know which place on your block is usually packed. '
                    '<strong>What ERNow can\'t see:</strong> a usually fast ED having a bad night. This model does not measure tonight’s conditions, '
                    'which is why ERNow shows tested ranges, labels everything "typical, not live," and is built to plug in live hospital data the day it exists.</div>',
                    unsafe_allow_html=True)

    ds = decision_summary()
    if "ernow" in ds and ({"full", "quick"} & set(ds)):
        e = fmt_seconds(ds["ernow"]["median_seconds"])
        cards = []
        if "quick" in ds:
            share = (f" At {ch['closest_not_fastest_share']:.0%} of sampled grid points near Boston ERs, the closest isn't the fastest overall." if choice_path.exists() else "")
            cards.append(("ERNow vs the usual search", f'{e} vs {fmt_seconds(ds["quick"]["median_seconds"])}',
                          f'Recorded medians in a convenience sample: {ds["ernow"]["participants"]} ERNow and {ds["quick"]["participants"]} search participants. Search protocol: choose the nearest ER. This does not establish a population-wide speed benefit.{share}'))
        if "full" in ds:
            cards.append(("Information ERNow assembles", f'{fmt_seconds(ds["full"]["median_seconds"])} by hand',
                          f"Recorded full-comparison median from {ds['full']['participants']} participant; ERNow assembles these fields on one screen."))
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
             f"Four models compared on {sp['hospitals']:,} reporting U.S. hospitals ({sp['total_rows']:,} labeled release pairs): Persistence, Ridge, partial pooling, gradient boosting. "
             f"The best challenger was only {(vals[national['selected_model']]['validation_MAE'] - vals[national['best_learned_model']]['validation_MAE']) / vals[national['selected_model']]['validation_MAE']:.1%} better on validation, under the 2% bar, so ERNow keeps {national['selected_model']} (R² {sel['R2']:.2f})."),
            ("Tested ranges", f"{iv['test_coverage']:.0%} coverage, latest year",
             f"Conformal prediction builds each target-80% range from real errors and recent volatility. Median width {fmt_minutes(iv['median_width_min'])}, "
             f"{iv['old_fixed_band_median_width_min'] / max(iv['median_width_min'], 1):.1f}× narrower than ERNow's early fixed range."
             + (f" Across {len(national.get('rolling') or [])} held-out years coverage ran "
                f"{min(r['coverage'] for r in national['rolling'] if r.get('coverage') is not None):.0%}–"
                f"{max(r['coverage'] for r in national['rolling'] if r.get('coverage') is not None):.0%}, missing most in volatile years."
                if any(r.get('coverage') is not None for r in (national.get('rolling') or [])) else "")),
            ("Ranking test", f"{rk['fastest_pick_accuracy']:.0%} vs {rk['fastest_pick_random_baseline']:.0%}",
             f"Picked the shortest observed hospital median in {rk['local_groups']} local areas {rk['fastest_pick_accuracy']:.0%} of the time, versus {rk['fastest_pick_random_baseline']:.0%} by chance."),
            ("Fastest in simulation", "4,000 scenarios",
             "A trip simulation (Monte Carlo) replays your drive with each hospital's tested range 4,000 times, summarizing simulated hospital-median scenarios. These percentages are not calibrated probabilities for your visit."),
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
    - **Typical ED visit:** the hospital median ED visit duration for eligible discharged patients (CMS OP-18b; excludes psychiatric/mental-health and transfer visits). The range targets 80% coverage of hospital medians, not individual visits; observed national coverage varied by release.
    - **Similar U.S. hospitals:** that time vs 25 look-alike hospitals nationwide (k-nearest neighbors on ED volume, type, ownership, star rating, and case-complexity proxies).
    - **Drive:** real road route from where you are (OpenStreetMap/OSRM), without live traffic.
    - **Drive + typical visit:** the two added together, which is how ERNow ranks "usually quickest" (drive plus a predicted median, not a personal expected duration).
    - **Fastest in simulation:** the fraction of 4,000 independent hospital-median scenarios where this ER has the lowest drive + median. It is not calibrated to individual visits; missing routes are excluded.
    - **Left before seen (2024):** the share of patients who left before being seen (CMS OP-22). This is an association with ED conditions, not a direct wait-time measurement.
    - **Hospital system:** the network each ER belongs to. If you pick your doctors' system, ERNow tags its ERs and names the quickest one in it, to support care continuity; record sharing varies. Ranking stays time-based.
    - **Insurance:** not a ranking factor. Medicare-participating ERs must screen and stabilize emergency conditions or appropriately transfer patients (EMTALA). Most private plans have protections for covered out-of-network emergency services; exceptions apply.
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
        ["Hospital utilization", "CHIA Hospital Profiles", "HFY 2024", "Verified HFY 2024 ED visits and inpatient occupancy; not ED crowding"],
        ["Left before being seen", "CMS Hospital Compare OP-22", "2024", "Shown on each ER card"],
        ["Hospital system", "Public hospital lists + CHIA profiles", "Checked Oct 2, 2026", "Shown on each card; optional hospital-system preference"],
        ["Provider wait", "CMS Hospital Compare OP-20 (no longer published)", "2019 or earlier; unverified archive values", "Context table on the Forecast Model page only"],
        ["Weather", "National Weather Service", "Current observation + alerts", "Boston-wide context"],
        ["Respiratory illness", "CDC Massachusetts ARI", "Latest available reporting week", "Statewide context"],
        ["Major events", "Boston-area public sources", "Detection attempted; cached 15 minutes", "Boston-wide context"],
        ["Route", "OpenStreetMap / OSRM (public demo server)", "Cached up to 5 minutes", "Approximate address coordinates; no live traffic"],
    ], columns=["Factor", "Source", "Freshness", "Meaning"])
    _table(fresh)

    st.subheader("Limitations")
    st.markdown("""
    - ERNow cannot see live triage, staffing, open rooms, boarding, or how many people are waiting right now.
    - The forecast describes typical ED performance for a CMS period. The app has no verified live wait feed for these hospitals.
    - OP-18b covers discharged patients. Peer matching adjusts for case complexity with public proxies, not for each patient's severity.
    - Travel time excludes live traffic, parking, and ambulance transport.
    """)
    st.markdown('<div class="note"><strong>Left out on purpose:</strong> hour-by-hour or day-of-week patterns (no public hospital-level data), '
                'traffic-aware drive times (not integrated), live waits (no verified feed integrated), Cambridge and other cities (next on the roadmap), '
                'and a respiratory-surge forecast (planned). Each was skipped because it would need data ERNow can\'t get or test today.</div>',
                unsafe_allow_html=True)


def render_forecast_model():
    st.title("Forecast Model")
    st.caption("The evidence behind ERNow, for anyone who wants to check it: tested on eligible reporting U.S. hospitals in the CMS archives, then applied to Boston.")
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
        ("Hospital-median ranges", f"{iv['test_coverage']:.0%} held the true value",
         f"Target-80% ranges contained the observed hospital median {iv['test_coverage']:.0%} of the time in that held-out year (conformal prediction)."),
        ("County median ranking", f"{rk['fastest_pick_accuracy']:.0%} vs {rk['fastest_pick_random_baseline']:.0%} by chance",
         f"How often it selected the shortest observed hospital median across {rk['local_groups']} local areas (ranking test)."),
    ]
    st.markdown('<div class="model-grid">' + "".join(
        f'<div class="model-card"><div class="model-k">{html.escape(k)}</div><div class="model-value">{html.escape(v)}</div>'
        f'<div class="model-copy">{html.escape(c)}</div></div>' for k, v, c in summary_cards) + '</div>', unsafe_allow_html=True)
    st.caption(f"Built on {sp['hospitals']:,} U.S. hospitals and {sp['total_rows']:,} labeled release pairs from {len(national['releases'])} CMS releases. "
               "Candidates were fitted on earlier releases; the deployment rule was chosen on validation and evaluated on the final saved release. Targets are published medians, not individual waits.")

    PLAIN_MODEL = {"Persistence baseline": "Persistence (latest reported value)",
                   "Ridge regression": "Ridge regression (linear model)",
                   "Partial pooling (shrink toward state & peer means)": "Partial pooling (nudged toward similar hospitals)",
                   "Gradient boosting": "Gradient boosting (decision trees)"}
    best_plain = PLAIN_MODEL.get(national["best_learned_model"], national["best_learned_model"])
    tabs = st.tabs(["The forecast", "Is it accurate?", "Predictive inputs", "Boston up close", "Data & updates"])
    with tabs[0]:
        st.caption("In plain terms: ERNow forecasts each hospital's median ED visit for the next release, and checks that against what actually happened.")
        st.subheader("What it predicts")
        st.write("Next-release CMS OP-18b: the hospital median arrival-to-departure duration for eligible discharged patients. "
                 "Psychiatric/mental-health and transferred visits are excluded. Features come from an earlier release than the target. Because CMS publishes after reporting periods end, this is a retrospective release-based test, not a prospective test of tonight’s patient outcomes.")

        st.subheader("Which forecast is most accurate?")
        plain = {"Persistence baseline": "Persistence (latest reported value)",
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
            summary = (f"Even with {sp['total_rows']:,} labeled release pairs, Persistence was hard to beat. The best challenger, {best_plain}, "
                       f"was {gain:.1%} more accurate in the selection year, short of the {national['promotion_margin']:.0%} bar, so ERNow keeps Persistence. "
                       "In stable years, the observed release-to-release results show that a hospital's ED performance is highly persistent from one year to the next, although this does not validate tonight’s individual patient outcomes.")
        st.markdown(f'<div class="callout">{summary}</div>', unsafe_allow_html=True)
        st.caption(f"Learned from {sp['train_rows']:,} labeled release pairs, chose a model on the next release ({sp['validation_rows']:,}), "
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
                "Target-80% median range coverage": _pct(r.get("coverage")),
                "Persistence: shortest county median": _pct(r.get("fastest_pick_accuracy")),
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
        st.write("Each hospital-median range uses quantile forecasts plus past calibration errors (conformal prediction), then adapts to how much "
                 "hospitals changed in the latest release, because a calm year and a volatile year need different widths "
                 "(regime-adaptive). That change is known before the forecast, the target release is not used as an input feature. Adaptive scaling is tested empirically; it does not guarantee 80% coverage in every year or hospital.")
        cov = pd.DataFrame([
            ["Early version: fixed ±band", _pct(iv["old_fixed_band_coverage"]), fmt_minutes(iv["old_fixed_band_median_width_min"])],
            ["Conformal, fixed width", _pct(iv["static_test_coverage"]), fmt_minutes(iv["static_width_min"])],
            ["Conformal, adapts to volatility (used)", _pct(iv["test_coverage"]), fmt_minutes(iv["median_width_min"])],
        ], columns=["Method, on the held-out year", "Contained the observed hospital median", "Typical range width"])
        _table(cov)
        st.caption(f"Target {iv['target_coverage']:.0%}. The deployed interval method was chosen on an earlier held-out year ({_pct(iv['backtest_coverage'])}) before "
                   f"checking the final one ({_pct(iv['test_coverage'])}), and is {iv['old_fixed_band_median_width_min'] / max(iv['median_width_min'], 1):.1f}× "
                   "narrower than the early fixed band, which was wide enough to be nearly useless.")
        st.caption("Coverage by ED volume: " + " · ".join(f"{k} {_pct(v)}" for k, v in iv["coverage_by_volume"].items()) + ".")

        st.subheader("Does it pick the right ER?")
        rt = pd.DataFrame([
            ["Order of eligible test hospitals matched observed medians (rank correlation, 1 = perfect)", f"{rk['national_spearman']:.2f}"],
            [f"Order within local areas matched reality ({rk['local_groups']} counties with 3+ hospitals)", f"{rk['mean_local_spearman']:.2f}"],
            ["Picked the shortest observed hospital median in the area", _pct(rk["fastest_pick_accuracy"])],
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
                ["Picked the shortest local hospital median", _pct(rk["fastest_pick_accuracy"]), f"{lo_p:.0%}–{hi_p:.0%}"],
                ["Hospital-median range coverage", _pct(iv["test_coverage"]), f"{lo_c:.0%}–{hi_c:.0%}" if lo_c is not None else "—"],
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
        ab_names = {"Persistence (no features)": "Nothing extra: latest reported value (Persistence)",
                    "History only": "Past ED times only",
                    "+ other ED measures": "+ other ED measures (left before seen, psychiatric ED time)",
                    "+ hospital characteristics": "+ hospital traits (volume, type, ownership, rating)",
                    "+ geography & peers (full)": "+ state and peer averages (everything)"}
        ab = pd.DataFrame(national["ablation"])
        ab = pd.DataFrame({"Information given to the model": ab["features"].map(lambda f: ab_names.get(f, f)),
                           "Avg. error, test year (MAE)": ab["test_MAE"].map(lambda v: f"{v:.2f} min")})
        _table(ab)
        st.caption("Adding feature groups did not beat Persistence on the test release. ERNow reports this rather than shipping a more complex model that does not help.")

        st.subheader("Which inputs help the challenger (permutation importance)")
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
        st.subheader("Which hospitals report longer median visits")
        stc = national["structure"]
        st.caption("By ED volume (latest release)")
        bv = pd.DataFrame(stc["by_volume"])
        bv = pd.DataFrame({"ED volume": bv["ed_volume"].str.capitalize(), "Hospitals": bv["hospitals"].map("{:,}".format),
                           "Median of hospital medians": bv["median_op18b"].map(fmt_minutes),
                           "Median left without being seen": bv["median_op22"].map(lambda v: f"{v:.0f}%")})
        _table(bv)
        st.caption("By ownership (six largest groups)")
        bo = pd.DataFrame(stc["by_ownership"]).sort_values("hospitals", ascending=False).head(6).sort_values("median_op18b", ascending=False)
        bo = pd.DataFrame({"Ownership": bo["ownership"], "Hospitals": bo["hospitals"].map("{:,}".format),
                           "Median of hospital medians": bo["median_op18b"].map(fmt_minutes),
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
                "Median forecast (target-80% range)": [f"{fmt_minutes(a)} ({fmt_minutes(l)}–{fmt_minutes(h)})" for a, l, h in
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
            st.caption("Verified CHIA HFY 2024 context; pre-2020 CMS OP-20 benchmarks have not been independently revalidated. Neither changes ranking.")
            _table(ctx)


    with tabs[4]:
        st.subheader("How fresh is the data?")
        gen = pd.Timestamp(national["generated_at"]).strftime("%B %-d, %Y")
        st.write(f"Results generated {gen} from CMS releases {pd.Timestamp(national['releases'][0]).strftime('%b %Y')} to {pd.Timestamp(national['releases'][-1]).strftime('%b %Y')}. "
                 "To update these estimates, add a CMS release and rerun the documented pipeline. Retraining is manual.")

        st.markdown('<div class="note"><strong>Scope:</strong> Four point-model candidates and conformal intervals were evaluated. '
                    'Deep learning and SHAP explanations were not evaluated. Permutation importance describes the gradient-boosting challenger.</div>', unsafe_allow_html=True)
        with st.expander("Technical details"):
            st.markdown(f"""
        **Target:** {national['target']}.

        **Models:** Persistence baseline; Ridge regression on the change; robust partial pooling (shrink toward state and peer averages, weights fit by least absolute error); gradient boosting on the change.

        **Validation:** chronological. Train on earlier releases, select on the next, test once on the latest. A learned model must beat Persistence by {national['promotion_margin']:.0%} on validation to be promoted.

        **Ranges:** regime-adaptive conformalized quantile regression: gradient-boosted 10th/90th percentiles, a calibration offset from the prior release, then scaled by the ratio of current to calibration-period national volatility (median absolute change).

        **Ranking:** Spearman rank correlation and fastest-pick accuracy within counties that have 3 or more hospitals.

        **Fastest in simulation:** 4,000 independent lognormal draws centered on the predicted hospital median, with spread approximated from the log ratio of the forecast bounds, plus drive time. Bounds can be asymmetric, so these are not exact fitted quantiles. This is uncalibrated hospital-median uncertainty, not a personal-visit probability.

        **What the 83% measures:** choosing the shortest observed hospital median in counties with at least three eligible hospitals. It excludes drive time and individual patient outcomes.

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
