from pathlib import Path
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import os
import re
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st
from streamlit_geolocation import streamlit_geolocation

st.set_page_config(page_title="ERFlow Boston", page_icon="🏥", layout="wide")
DATA_PATH = Path(__file__).parent / "data" / "boston_er_data.csv"
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
    "ticketmaster": "https://app.ticketmaster.com/discovery/v2/events.json",
}

HEADERS = {
    "User-Agent": "ERFlow-Boston/1.0 portfolio-project contact=erflow-boston",
    "Accept": "application/geo+json, application/json",
}

st.markdown(
    """
<style>
.block-container {padding-top: 1rem; max-width: 1180px;}
.er-card {border:1px solid rgba(128,128,128,.28); border-radius:16px; padding:1rem 1.05rem; margin-bottom:.85rem;}
.er-best {border:2px solid #2e7d32;}
.er-title {font-size:1.24rem; font-weight:700;}
.er-rank {font-size:1.45rem; font-weight:800; margin-right:.4rem;}
.er-pill {display:inline-block; padding:.24rem .55rem; border-radius:999px; background:rgba(128,128,128,.12); margin:.14rem .2rem .14rem 0; font-size:.84rem;}
.er-big {font-size:1.15rem; font-weight:700; margin:.45rem 0;}
.er-subtle {opacity:.75; font-size:.9rem;}
.feed-ok {font-weight:600;}
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


@st.cache_data(ttl=3600)
def load_fallback_data():
    df = pd.read_csv(DATA_PATH, dtype={"cms_provider_id": str})
    for col in ["typical_ed_minutes", "legacy_wait_to_provider_min"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_cms_baselines(provider_ids):
    rows = []
    for provider_id in provider_ids:
        params = {
            "size": 50,
            "offset": 0,
            "filter[Facility ID]": provider_id,
            "filter[Measure ID]": "OP_18b",
        }
        r = safe_get(URLS["cms"], params=params, timeout=10)
        if not r:
            continue
        try:
            payload = r.json()
        except ValueError:
            continue
        if isinstance(payload, dict):
            payload = payload.get("data", payload.get("results", []))
        for item in payload if isinstance(payload, list) else []:
            if str(item.get("Facility ID", "")) == str(provider_id) and item.get("Measure ID") == "OP_18b":
                try:
                    score = float(item.get("Score"))
                except (TypeError, ValueError):
                    continue
                rows.append({
                    "cms_provider_id": str(provider_id),
                    "cms_current_baseline": score,
                    "cms_start_date": item.get("Start Date", ""),
                    "cms_end_date": item.get("End Date", ""),
                })
                break
    return pd.DataFrame(rows)


@st.cache_data(ttl=600, show_spinner=False)
def fetch_current_weather(lat, lon):
    point = safe_get(URLS["nws_points"].format(lat=f"{lat:.4f}", lon=f"{lon:.4f}"), timeout=8)
    if not point:
        return None
    try:
        props = point.json().get("properties", {})
        stations_url = props.get("observationStations")
    except ValueError:
        return None
    if not stations_url:
        return None
    stations = safe_get(stations_url, timeout=8)
    if not stations:
        return None
    try:
        features = stations.json().get("features", [])
    except ValueError:
        return None
    for station in features[:5]:
        station_url = station.get("id") or station.get("properties", {}).get("@id")
        if not station_url:
            continue
        obs = safe_get(f"{station_url}/observations/latest", timeout=8)
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
                "temperature_c": ((p.get("temperature") or {}).get("value")),
                "wind_kmh": ((p.get("windSpeed") or {}).get("value")),
                "station": station.get("properties", {}).get("stationIdentifier", "NWS station"),
            }
    return None


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
    reasons = []
    if obs:
        text = (obs.get("description") or "").lower()
        temp_c = obs.get("temperature_c")
        wind = obs.get("wind_kmh")
        if any(k in text for k in ["snow", "ice", "sleet", "freezing"]):
            factor *= 1.08
            reasons.append("winter weather")
        elif any(k in text for k in ["thunder", "heavy rain", "rain", "showers"]):
            factor *= 1.03
            reasons.append("rain/storm")
        if isinstance(temp_c, (int, float)) and (temp_c >= 35 or temp_c <= -7):
            factor *= 1.04
            reasons.append("temperature extreme")
        if isinstance(wind, (int, float)) and wind >= 50:
            factor *= 1.03
            reasons.append("strong wind")
    if alerts:
        severe = 0
        for alert in alerts:
            sev = str(alert.get("properties", {}).get("severity", "")).lower()
            if sev in {"severe", "extreme"}:
                severe += 1
        if severe:
            factor *= 1.05
            reasons.append("active severe weather alert")
    return min(factor, 1.15), reasons or ["normal current weather"]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cdc_ari():
    params = {
        "$select": "week_end,geography,label",
        "$where": "geography='Massachusetts'",
        "$order": "week_end DESC",
        "$limit": 1,
    }
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
    # Intentionally small: statewide weekly surveillance is useful context but not a live ED census.
    mapping = {"minimal": 0.99, "very low": 0.99, "low": 1.00, "moderate": 1.02, "high": 1.04, "very high": 1.06}
    return mapping.get(label, 1.0), (label.title() if label else "Unavailable")


def nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    delta = (weekday - d.weekday()) % 7
    return d + timedelta(days=delta + 7 * (n - 1))


def last_weekday(year, month, weekday):
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def observed_fixed(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


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
    return holidays.get(d)


def temporal_factor(now_dt):
    factor = 1.0
    reasons = []
    h, wd = now_dt.hour, now_dt.weekday()
    # Conservative bounded effects; these are model coefficients, not source measurements.
    if 16 <= h < 23:
        factor *= 1.08
        reasons.append("evening")
    elif 0 <= h < 6:
        factor *= 0.96
        reasons.append("overnight")
    if wd == 0:
        factor *= 1.04
        reasons.append("Monday")
    elif wd >= 5:
        factor *= 1.02
        reasons.append("weekend")
    hname = holiday_name(now_dt.date())
    if hname:
        factor *= 1.04 if "Marathon" not in hname else 1.07
        reasons.append(hname)
    return factor, reasons or ["typical time/day"]


@st.cache_data(ttl=900, show_spinner=False)
def fetch_boston_events(today_iso):
    r = safe_get(URLS["boston_events"], headers={"User-Agent": HEADERS["User-Agent"]}, timeout=8)
    if not r:
        return {"status": "unavailable", "titles": []}
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return {"status": "unavailable", "titles": []}
    target = datetime.fromisoformat(today_iso)
    tokens = {
        target.strftime("%B %d, %Y").replace(" 0", " "),
        target.strftime("%Y-%m-%d"),
    }
    titles = []
    for item in root.findall(".//item"):
        text = " ".join((c.text or "") for c in list(item))
        if any(tok.lower() in text.lower() for tok in tokens):
            title = item.findtext("title") or "Boston event"
            titles.append(title.strip())
    return {"status": "current", "titles": titles}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_ticketmaster_events(now_iso, end_iso, api_key):
    if not api_key:
        return None
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
        return None
    try:
        payload = r.json()
        return payload.get("_embedded", {}).get("events", [])
    except ValueError:
        return None


def event_factor(city_events, ticketmaster_events):
    # Only high-impact signals affect the model; ordinary meetings/classes are ignored.
    keywords = ["marathon", "parade", "festival", "fireworks", "road closure", "race", "concert", "game", "championship"]
    titles = list((city_events or {}).get("titles", []))
    if ticketmaster_events:
        titles += [e.get("name", "") for e in ticketmaster_events]
    high_impact = [t for t in titles if any(k in t.lower() for k in keywords)]
    if len(high_impact) >= 3:
        return 1.04, high_impact[:3]
    if high_impact:
        return 1.02, high_impact[:3]
    return 1.0, []


def haversine_miles(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


def proxy_drive_minutes(distance_miles, hour, weekday):
    base = 5 + distance_miles * 3.6
    if weekday < 5 and (7 <= hour < 10 or 16 <= hour < 19):
        return base * 1.35
    if 10 <= hour < 16:
        return base * 1.15
    if 19 <= hour < 22:
        return base * 1.10
    if weekday >= 5:
        return base * 1.08
    return base


def fmt_minutes(v):
    if pd.isna(v):
        return "—"
    m = max(0, int(round(v)))
    return f"{m} min" if m < 60 else f"{m // 60}h {m % 60}m"


def build_consumer_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, city_events, tm_events):
    wf, weather_reasons = current_weather_factor(weather_obs, alerts)
    inf, illness_label = illness_factor(ari)
    tf, time_reasons = temporal_factor(now_dt)
    ef, high_events = event_factor(city_events, tm_events)
    dynamic_factor = max(0.85, min(1.25, wf * inf * tf * ef))

    median_ed = df["typical_ed_minutes"].median()
    rows = []
    for idx, row in df.reset_index(drop=True).iterrows():
        straight = haversine_miles(origin_lat, origin_lon, row["latitude"], row["longitude"])
        # Zero-cost travel estimate. This is intentionally NOT labeled live traffic.
        # It uses current Boston hour/day plus straight-line distance as a transparent proxy.
        drive = proxy_drive_minutes(straight, now_dt.hour, now_dt.weekday())
        route_dist = straight
        travel_source = "Estimated travel"
        traffic_delay = None

        legacy_wait = float(row["legacy_wait_to_provider_min"])
        recent_ed = float(row["typical_ed_minutes"])
        # Recalibrate the legacy wait benchmark modestly using the hospital's current relative throughput.
        throughput_relative = recent_ed / median_ed if median_ed else 1.0
        throughput_factor = max(0.90, min(1.12, throughput_relative ** 0.30))
        wait_mid = legacy_wait * throughput_factor * dynamic_factor
        # Wide interval because OP-20 is legacy data and live queue/staffing/triage are unavailable.
        wait_low = max(5, wait_mid * 0.65)
        wait_high = max(wait_low + 10, wait_mid * 1.55)
        access_low = drive + wait_low
        access_high = drive + wait_high
        access_mid = drive + wait_mid

        rows.append({
            **row.to_dict(),
            "distance_miles": straight,
            "route_distance_miles": route_dist,
            "drive_eta_min": drive,
            "travel_source": travel_source,
            "traffic_delay_min": traffic_delay,
            "modeled_wait_mid": wait_mid,
            "modeled_wait_low": wait_low,
            "modeled_wait_high": wait_high,
            "access_mid": access_mid,
            "access_low": access_low,
            "access_high": access_high,
            "dynamic_factor": dynamic_factor,
            "throughput_factor": throughput_factor,
        })

    out = pd.DataFrame(rows).sort_values(["access_mid", "drive_eta_min", "distance_miles"]).reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    context = {
        "weather_reasons": weather_reasons,
        "illness_label": illness_label,
        "time_reasons": time_reasons,
        "high_events": high_events,
        "dynamic_factor": dynamic_factor,
    }
    return out, context


def congestion_label(row, ranked):
    q1 = ranked["modeled_wait_mid"].quantile(0.33)
    q2 = ranked["modeled_wait_mid"].quantile(0.67)
    if row["modeled_wait_mid"] <= q1:
        return "Lower modeled wait"
    if row["modeled_wait_mid"] <= q2:
        return "Moderate modeled wait"
    return "Higher modeled wait"


# Safety must be the first visible element.
st.error(
    "🚨 **If this may be a medical emergency, call 911 or go to the nearest appropriate emergency department. "
    "Do not delay care or drive farther because ERFlow ranks another hospital higher. Do not use this app while driving.**"
)

st.title("ERFlow Boston")
st.caption("One input: your location. ERFlow compares nearby Boston ERs using modeled wait-to-provider, current time-sensitive travel estimates, and the freshest public demand signals available.")

st.subheader("Where are you right now?")
location = streamlit_geolocation()
origin_lat = origin_lon = None
location_label = None
if isinstance(location, dict) and location.get("latitude") is not None and location.get("longitude") is not None:
    origin_lat, origin_lon = float(location["latitude"]), float(location["longitude"])
    location_label = "Your current location"
    st.success("Location received. ERFlow is recalculating now.")
else:
    with st.expander("Location blocked? Use a Boston area instead"):
        fallback = st.selectbox("Boston area", list(FALLBACK_ORIGINS.keys()))
        if st.button("Use this area", use_container_width=True):
            st.session_state["fallback_origin"] = fallback
    if st.session_state.get("fallback_origin"):
        fallback = st.session_state["fallback_origin"]
        origin_lat, origin_lon = FALLBACK_ORIGINS[fallback]
        location_label = fallback

if origin_lat is None:
    st.info("Use **Get My Location** above. No other consumer input is required.")
    st.stop()

now_dt = datetime.now(EASTERN)
df = load_fallback_data()
cms = fetch_cms_baselines(tuple(df["cms_provider_id"].tolist()))
if not cms.empty:
    df = df.merge(cms, on="cms_provider_id", how="left")
    m = df["cms_current_baseline"].notna()
    df.loc[m, "typical_ed_minutes"] = df.loc[m, "cms_current_baseline"]
    df.loc[m, "source_label"] = "Latest available CMS OP-18b public release"

weather_obs = fetch_current_weather(origin_lat, origin_lon)
alerts = fetch_nws_alerts(origin_lat, origin_lon)
ari = fetch_cdc_ari()
city_events = fetch_boston_events(now_dt.date().isoformat())

tm_key = secret_or_env("TICKETMASTER_API_KEY")

tm_events = fetch_ticketmaster_events(
    now_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
    (now_dt + timedelta(hours=6)).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
    tm_key,
) if tm_key else None

ranked, context = build_consumer_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, city_events, tm_events)
closest = ranked.loc[ranked["drive_eta_min"].idxmin()]
lowest_wait = ranked.loc[ranked["modeled_wait_mid"].idxmin()]

st.caption(f"Calculated at **{now_dt.strftime('%-I:%M %p')}** Boston time for **{location_label}**")

# Freshness/status strip: consumer-readable and honest.
status_cols = st.columns(5)
with status_cols[0]:
    st.metric("Travel estimate", "CURRENT", help="Zero-cost travel estimate recalculated from your location and the current Boston hour/day. It does not use live traffic.")
with status_cols[1]:
    weather_label = "CURRENT" if weather_obs else "UNAVAILABLE"
    st.metric("Weather", weather_label)
with status_cols[2]:
    st.metric("Time/day", "CURRENT")
with status_cols[3]:
    st.metric("Illness", "LATEST WEEKLY" if ari else "UNAVAILABLE", help="CDC respiratory surveillance is published weekly, not live minute-by-minute.")
with status_cols[4]:
    event_ok = (city_events or {}).get("status") == "current" or tm_events is not None
    st.metric("Events", "CURRENT" if event_ok else "UNAVAILABLE")


st.divider()
st.subheader("ER comparison — lowest modeled time to initial evaluation first")
st.caption(
    "Ranking = **estimated travel time + modeled wait to first provider evaluation**. The wait model starts from the 2019 CMS OP-20 historical wait benchmark, modestly recalibrates it with the latest CMS ED-throughput baseline, then applies current external demand signals. It is not a confirmed live hospital queue."
)

for _, row in ranked.iterrows():
    best = " er-best" if int(row["rank"]) == 1 else ""
    wait_range = f"{fmt_minutes(row['modeled_wait_low'])}–{fmt_minutes(row['modeled_wait_high'])}"
    access_range = f"{fmt_minutes(row['access_low'])}–{fmt_minutes(row['access_high'])}"
    traffic_note = row["travel_source"]
    cong = congestion_label(row, ranked)
    card = f"""
<div class="er-card{best}">
  <div><span class="er-rank">#{int(row['rank'])}</span><span class="er-title">{row['hospital']}</span></div>
  <div class="er-big">Modeled time until initial evaluation: {access_range}</div>
  <div>
    <span class="er-pill"><b>Modeled wait to provider:</b> {wait_range}</span>
    <span class="er-pill"><b>Travel:</b> {fmt_minutes(row['drive_eta_min'])} · {row['route_distance_miles']:.1f} mi · {traffic_note}</span>
    <span class="er-pill"><b>Current wait pressure:</b> {cong}</span>
    <span class="er-pill"><b>Historical wait benchmark:</b> {fmt_minutes(row['legacy_wait_to_provider_min'])} (2019)</span>
    <span class="er-pill"><b>Recent historical ED duration:</b> {fmt_minutes(row['typical_ed_minutes'])}</span>
  </div>
  <div class="er-subtle">The 2019 wait benchmark is legacy CMS data. Recent ED duration is CMS OP-18b arrival-to-departure, not a live wait. Current factors adjust the model but cannot observe the hospital's live queue, triage mix, staffing, or boarding.</div>
</div>
"""
    st.markdown(card, unsafe_allow_html=True)

st.info(
    f"**Closest by estimated travel time:** {closest['hospital']} — {fmt_minutes(closest['drive_eta_min'])}.  \n"
    f"**Lowest modeled wait to provider:** {lowest_wait['hospital']} — {fmt_minutes(lowest_wait['modeled_wait_low'])}–{fmt_minutes(lowest_wait['modeled_wait_high'])}.  \n"
    "For a potentially serious emergency, do not drive farther based on these modeled comparisons."
)

with st.expander("What is affecting the model right now?"):
    weather_text = weather_obs.get("description") if weather_obs else "Unavailable"
    weather_time = weather_obs.get("timestamp") if weather_obs else ""
    ari_week = (ari or {}).get("week_end", "Unavailable")
    event_names = context["high_events"] or ["No high-impact event adjustment detected"]
    st.write(f"**Weather:** {weather_text}" + (f" · observation {weather_time}" if weather_time else ""))
    st.write(f"**Time/day:** {', '.join(context['time_reasons'])}")
    st.write(f"**Respiratory activity:** {context['illness_label']} · latest CDC week ending {ari_week}")
    st.write(f"**High-impact events:** {', '.join(event_names)}")
    st.write("**Travel:** Zero-cost estimated travel time based on current hour/day and distance. ERFlow does not claim this is live traffic.")

st.subheader("Map")
st.map(ranked[["hospital", "latitude", "longitude"]], latitude="latitude", longitude="longitude", size=95)

st.page_link("pages/1_Methodology_and_Data_Sources.py", label="How ERFlow works · Methodology & data sources", icon="📚")
st.caption("ERFlow Boston • Portfolio forecasting prototype • Not a clinical decision tool or confirmed live hospital wait-time service.")
