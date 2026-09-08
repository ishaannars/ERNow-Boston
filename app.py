from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import os
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st
from streamlit_geolocation import streamlit_geolocation

st.set_page_config(page_title="ERNow Boston", page_icon="✚", layout="wide")
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
    "osrm": "https://router.project-osrm.org/route/v1/driving/{olon},{olat};{dlon},{dlat}",
}

HEADERS = {
    "User-Agent": "ERNow-Boston/1.0 portfolio-project contact=ernow-boston",
    "Accept": "application/geo+json, application/json",
}

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');

:root {
  --ivory:#F8F4E6;
  --shell:#FFFDF5;
  --ink:#1C1B19;
  --soft-ink:#403A32;
  --tea:#B9AD91;
  --moss:#48513C;
  --beni:#8C2F2F;
  --kakishibu:#A85B45;
  --kakishibu-wash:rgba(168,91,69,.10);
}
html, body, [class*="css"], .stApp {font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif;}
.stApp {background:var(--ivory); color:var(--ink);}
.block-container {padding-top:5.4rem !important; padding-bottom:2rem; max-width:960px;}
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display:none !important;}

.safety-banner {
  display:block; width:100%; box-sizing:border-box; overflow:visible;
  background:var(--beni); color:#FFFFFF !important; border-radius:16px; padding:16px 19px;
  font-size:1rem; line-height:1.5; font-weight:650; margin:0 0 .9rem 0;
}
.safety-banner, .safety-banner * {color:#FFFFFF !important; opacity:1 !important;}
.nav-wrap {border-bottom:1px solid var(--tea); padding-bottom:.55rem; margin-bottom:1.15rem;}
[data-testid="stPageLink-NavLink"] {background:var(--shell)!important;border:1px solid var(--tea)!important;border-radius:10px!important;color:var(--ink)!important;font-weight:650!important;}
[data-testid="stPageLink-NavLink"]:hover {border-color:var(--kakishibu)!important;background:var(--kakishibu-wash)!important;}
.material-symbols-rounded {color:var(--beni)!important;}
.location-confirm {background:var(--kakishibu-wash);border-bottom:2px solid var(--kakishibu);border-radius:10px 10px 4px 4px;padding:.72rem .9rem;margin:.35rem 0 .75rem 0;color:var(--ink);font-weight:600;}
.location-confirm .sub {color:var(--soft-ink);font-size:.84rem;font-weight:500;margin-left:.35rem;}
.brand-sub {color:var(--soft-ink); margin-top:-.35rem; margin-bottom:1.1rem; font-size:.98rem;}
.er-card {
  background:var(--shell); border:1px solid var(--tea); border-radius:16px;
  padding:1.05rem 1.1rem; margin-bottom:.8rem;
}
.er-best {border:2px solid var(--moss);}
.best-label {color:var(--moss); font-size:.76rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; margin-bottom:.25rem;}
.er-title {font-size:1.15rem; font-weight:650; color:var(--ink);}
.er-rank {font-size:1.12rem; font-weight:700; margin-right:.4rem; color:var(--moss);}
.er-wait-label {font-size:.82rem; color:var(--soft-ink); margin-top:.6rem;}
.er-wait {font-size:1.65rem; font-weight:700; letter-spacing:-.02em; margin:.08rem 0 .45rem 0; color:var(--ink);}
.er-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.38rem 1.1rem;margin-top:.15rem;}
.er-metric {font-size:.93rem; color:var(--soft-ink);}
.er-metric b {color:var(--ink); font-weight:600;}
.er-context {font-size:.82rem; color:var(--soft-ink); margin-top:.65rem; padding-top:.55rem; border-top:1px solid #DDD4BE;}
.er-reason {font-size:.82rem; color:var(--moss); font-weight:600; margin-top:.5rem;}
@media (max-width:650px){.block-container{padding-top:4.8rem!important}.er-grid{grid-template-columns:1fr}.er-wait{font-size:1.5rem}}
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
    numeric = ["typical_ed_minutes", "legacy_wait_to_provider_min", "recent_ed_visits", "recent_occupancy_pct"]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_cms_metrics(provider_ids):
    rows = []
    for provider_id in provider_ids:
        params = {"size": 100, "offset": 0, "filter[Facility ID]": provider_id}
        r = safe_get(URLS["cms"], params=params, timeout=10)
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
            mid = item.get("Measure ID")
            try:
                score = float(item.get("Score"))
            except (TypeError, ValueError):
                continue
            if mid == "OP_18b":
                record["cms_current_baseline"] = score
                record["cms_start_date"] = item.get("Start Date", "")
                record["cms_end_date"] = item.get("End Date", "")
            elif mid == "OP_22":
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
            }
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_location_name(lat, lon):
    r = safe_get(URLS["nws_points"].format(lat=f"{lat:.4f}", lon=f"{lon:.4f}"), timeout=8)
    if not r:
        return "Current location"
    try:
        props = r.json().get("properties", {})
        rel = (props.get("relativeLocation") or {}).get("properties", {})
        city = rel.get("city")
        state = rel.get("state")
        if city and state:
            return f"{city}, {state}"
        if city:
            return city
    except (ValueError, AttributeError):
        pass
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
        temp_c = obs.get("temperature_c")
        wind = obs.get("wind_kmh")
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
    mapping = {"minimal": 0.99, "very low": 0.99, "low": 1.00, "moderate": 1.02, "high": 1.04, "very high": 1.06}
    return mapping.get(label, 1.0), (label.title() if label else "Unavailable")


def nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    delta = (weekday - d.weekday()) % 7
    return d + timedelta(days=delta + 7 * (n - 1))


def last_weekday(year, month, weekday):
    d = (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1))
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
        factor *= 1.04 if "Marathon" not in hname else 1.07
    return factor


@st.cache_data(ttl=900, show_spinner=False)
def fetch_boston_events(today_iso):
    r = safe_get(URLS["boston_events"], headers={"User-Agent": HEADERS["User-Agent"]}, timeout=8)
    if not r:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    target = datetime.fromisoformat(today_iso)
    tokens = {target.strftime("%B %d, %Y").replace(" 0", " "), target.strftime("%Y-%m-%d")}
    titles = []
    for item in root.findall(".//item"):
        text = " ".join((c.text or "") for c in list(item))
        if any(tok.lower() in text.lower() for tok in tokens):
            titles.append((item.findtext("title") or "Boston event").strip())
    return titles


@st.cache_data(ttl=900, show_spinner=False)
def fetch_ticketmaster_events(now_iso, end_iso, api_key):
    if not api_key:
        return []
    params = {
        "apikey": api_key, "city": "Boston", "stateCode": "MA", "countryCode": "US",
        "startDateTime": now_iso, "endDateTime": end_iso, "size": 50, "sort": "date,asc",
    }
    r = safe_get(URLS["ticketmaster"], params=params, timeout=10)
    if not r:
        return []
    try:
        return r.json().get("_embedded", {}).get("events", [])
    except ValueError:
        return []


def event_factor(city_titles, ticketmaster_events):
    keywords = ["marathon", "parade", "festival", "fireworks", "road closure", "race", "concert", "game", "championship"]
    titles = list(city_titles) + [e.get("name", "") for e in ticketmaster_events]
    high = [t for t in titles if any(k in t.lower() for k in keywords)]
    if len(high) >= 3:
        return 1.04
    if high:
        return 1.02
    return 1.0


@st.cache_data(ttl=300, show_spinner=False)
def route_estimate(origin_lat, origin_lon, dest_lat, dest_lon):
    url = URLS["osrm"].format(olon=origin_lon, olat=origin_lat, dlon=dest_lon, dlat=dest_lat)
    r = safe_get(url, params={"overview": "false", "alternatives": "false", "steps": "false"}, timeout=10)
    if not r:
        return None
    try:
        payload = r.json()
        route = payload.get("routes", [])[0]
        return {"minutes": route["duration"] / 60.0, "miles": route["distance"] / 1609.344}
    except (ValueError, IndexError, KeyError, TypeError):
        return None


def recent_demand_factor(row, med_volume, med_occupancy, med_lwbs):
    # Relative hospital-demand adjustment using recent reported utilization only.
    # Bounded intentionally because these are historical operational signals, not a live census.
    factor = 1.0
    if pd.notna(row.get("recent_ed_visits")) and med_volume:
        volume_ratio = float(row["recent_ed_visits"]) / med_volume
        factor *= max(0.96, min(1.06, 1 + 0.04 * (volume_ratio - 1)))
    if pd.notna(row.get("recent_occupancy_pct")) and med_occupancy:
        occ_diff = (float(row["recent_occupancy_pct"]) - med_occupancy) / 10.0
        factor *= max(0.97, min(1.05, 1 + 0.02 * occ_diff))
    if pd.notna(row.get("left_before_seen_pct")) and med_lwbs:
        lwbs_ratio = float(row["left_before_seen_pct"]) / med_lwbs
        factor *= max(0.97, min(1.05, 1 + 0.025 * (lwbs_ratio - 1)))
    return max(0.92, min(1.12, factor))


def fmt_minutes(v):
    if pd.isna(v):
        return "—"
    m = max(0, int(round(v)))
    return f"{m} min" if m < 60 else f"{m // 60}h {m % 60}m"


def current_condition_label(dynamic_factor):
    if dynamic_factor >= 1.08:
        return "Elevated"
    if dynamic_factor <= 0.96:
        return "Lower than typical"
    return "Typical"


def build_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, city_events, tm_events):
    wf = current_weather_factor(weather_obs, alerts)
    inf, illness_label = illness_factor(ari)
    tf = temporal_factor(now_dt)
    ef = event_factor(city_events, tm_events)
    dynamic_factor = max(0.86, min(1.24, wf * inf * tf * ef))

    med_ed = df["typical_ed_minutes"].median()
    med_volume = df["recent_ed_visits"].median()
    med_occupancy = df["recent_occupancy_pct"].median()
    med_lwbs = df["left_before_seen_pct"].median() if "left_before_seen_pct" in df and df["left_before_seen_pct"].notna().any() else None

    rows = []
    for _, row in df.iterrows():
        route = route_estimate(origin_lat, origin_lon, row["latitude"], row["longitude"])
        if route is None:
            # If road routing fails, keep the hospital visible but do not fake a route time.
            drive_min, route_miles = float("nan"), float("nan")
        else:
            drive_min, route_miles = route["minutes"], route["miles"]

        historical_wait = float(row["legacy_wait_to_provider_min"])
        recent_ed = float(row["typical_ed_minutes"])
        throughput_relative = recent_ed / med_ed if med_ed else 1.0
        throughput_factor = max(0.90, min(1.12, throughput_relative ** 0.30))
        hospital_demand = recent_demand_factor(row, med_volume, med_occupancy, med_lwbs)

        wait_mid = historical_wait * throughput_factor * hospital_demand * dynamic_factor
        wait_low = max(5, wait_mid * 0.65)
        wait_high = max(wait_low + 10, wait_mid * 1.55)
        access_mid = (drive_min if pd.notna(drive_min) else 999) + wait_mid

        rows.append({
            **row.to_dict(),
            "route_time_min": drive_min,
            "route_distance_miles": route_miles,
            "modeled_wait_mid": wait_mid,
            "modeled_wait_low": wait_low,
            "modeled_wait_high": wait_high,
            "access_mid": access_mid,
            "dynamic_factor": dynamic_factor,
            "hospital_demand_factor": hospital_demand,
        })

    out = pd.DataFrame(rows).sort_values(["access_mid", "modeled_wait_mid"]).reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    return out, {"dynamic_factor": dynamic_factor, "illness_label": illness_label}


st.markdown(
    """
<div class="safety-banner">
🚨 <strong>Possible emergency?</strong> Call 911 or go to the nearest appropriate emergency department.
Do not delay care or drive farther because of an ERNow estimate, and do not use this app while driving.
</div>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
nav1, nav2, _ = st.columns([1, 1, 4])
with nav1:
    st.page_link("app.py", label="ERNow", icon=":material/emergency:", use_container_width=True)
with nav2:
    st.page_link("pages/1_Methodology.py", label="Methodology", icon=":material/menu_book:", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.title("ERNow Boston")
st.markdown('<div class="brand-sub">Nearby Boston emergency departments, ranked using estimated ER wait and road-route access.</div>', unsafe_allow_html=True)

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
    st.markdown(
        f'<div class="location-confirm">Location detected: {location_label}<span class="sub">Results updated from your current location.</span></div>',
        unsafe_allow_html=True,
    )
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

now_dt = datetime.now(EASTERN)
df = load_fallback_data()
cms = fetch_cms_metrics(tuple(df["cms_provider_id"].tolist()))
if not cms.empty:
    df = df.merge(cms, on="cms_provider_id", how="left")
    m = df["cms_current_baseline"].notna() if "cms_current_baseline" in df else pd.Series(False, index=df.index)
    df.loc[m, "typical_ed_minutes"] = df.loc[m, "cms_current_baseline"]

weather_obs = fetch_current_weather(origin_lat, origin_lon)
alerts = fetch_nws_alerts(origin_lat, origin_lon)
ari = fetch_cdc_ari()
city_events = fetch_boston_events(now_dt.date().isoformat())
tm_key = secret_or_env("TICKETMASTER_API_KEY")
tm_events = fetch_ticketmaster_events(
    now_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
    (now_dt + timedelta(hours=6)).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
    tm_key,
) if tm_key else []

ranked, context = build_model(df, origin_lat, origin_lon, now_dt, weather_obs, alerts, ari, city_events, tm_events)

weather_status = weather_obs.get("description", "Unavailable") if weather_obs else "Unavailable"
event_status = "Major event signal" if event_factor(city_events, tm_events) > 1 else "No major event signal"
st.caption(
    f"Updated **{now_dt.strftime('%-I:%M %p')}** · {location_label} · "
    f"Weather: **{weather_status}** · Respiratory activity: **{context['illness_label']}** · Events: **{event_status}**"
)

st.divider()
st.subheader("Nearby ERs")
st.caption("Ranked by estimated ER wait plus estimated road-route time. Route estimates do not include live traffic.")

for _, row in ranked.iterrows():
    best = " er-best" if int(row["rank"]) == 1 else ""
    best_label = '<div class="best-label">Best overall estimate</div>' if int(row["rank"]) == 1 else ""
    wait_range = f"{fmt_minutes(row['modeled_wait_low'])}–{fmt_minutes(row['modeled_wait_high'])}"
    route_time = f"~{fmt_minutes(row['route_time_min'])}" if pd.notna(row["route_time_min"]) else "Unavailable"
    route_dist = f"{row['route_distance_miles']:.1f} mi" if pd.notna(row["route_distance_miles"]) else "—"
    current_demand = current_condition_label(row["dynamic_factor"])
    reason = "Ranking combines estimated ER wait, recent hospital demand, current local conditions, route access, and other relevant factors. Estimates are not live hospital queue times."

    card = f"""
<div class="er-card{best}">
  {best_label}
  <div><span class="er-rank">#{int(row['rank'])}</span><span class="er-title">{row['hospital']}</span></div>
  <div class="er-wait-label">Estimated ER wait</div>
  <div class="er-wait">{wait_range}</div>
  <div class="er-grid">
    <div class="er-metric"><b>Estimated route:</b> {route_time} · {route_dist}</div>
    <div class="er-metric"><b>Current demand conditions:</b> {current_demand}</div>
    <div class="er-metric"><b>Historical wait:</b> {fmt_minutes(row['legacy_wait_to_provider_min'])}</div>
    <div class="er-metric"><b>Typical visit duration:</b> {fmt_minutes(row['typical_ed_minutes'])}</div>
  </div>
  <div class="er-reason">{reason}</div>
</div>
"""
    st.markdown(card, unsafe_allow_html=True)

with st.expander("What changes the estimate right now?"):
    st.write("ERNow automatically uses the current Boston time/day, holiday status, National Weather Service conditions and alerts, current Boston event signals, and the latest Massachusetts respiratory-illness activity available from CDC.")
    st.caption("Recent hospital demand and capacity data are used in the model but are not shown as if they were live conditions.")

st.subheader("Map")
st.map(ranked[["hospital", "latitude", "longitude"]], latitude="latitude", longitude="longitude", size=95)

st.caption("ERNow Boston · Forecasting prototype · Not a clinical decision tool or confirmed live hospital wait-time service.")
