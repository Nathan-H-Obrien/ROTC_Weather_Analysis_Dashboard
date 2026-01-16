#!/usr/bin/env python3
"""
training_dashboard.py - Streamlit Version

Military training weather dashboard with:
 - Current conditions + 14-day forecast
 - Training Date Planner - select specific dates for analysis
 - WBGT estimate, wind chill, heat category (TRADOC-like)
 - Army uniform recommendations
 - Precipitation handling
 - OpenWeatherMap API
"""
from newsapi import NewsApiClient
import streamlit as st
import requests
import math
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# -----------------------
# CONFIG
# -----------------------
WEATHER_API_KEY = st.secrets.get("OPENWEATHER_API_KEY", "")
NEWS_API_KEY = st.secrets.get("NEWSAPI", "")
WBGT_CUTOFF_F = 50
FORECAST_DAYS = 16  # Developer plan provides 16-day forecast

# Location presets
LOCATIONS = {
    "Brookings, SD": {"lat": 44.3114, "lon": -96.7984, "tz": "America/Chicago"},
    "Enter City/State": {"lat": 0, "lon": 0, "tz": "America/Chicago"}
}

# US State to Timezone mapping (most common timezone for each state)
STATE_TIMEZONES = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
    "GA": "America/New_York", "HI": "Pacific/Honolulu", "ID": "America/Denver",
    "IL": "America/Chicago", "IN": "America/New_York", "IA": "America/Chicago",
    "KS": "America/Chicago", "KY": "America/New_York", "LA": "America/Chicago",
    "ME": "America/New_York", "MD": "America/New_York", "MA": "America/New_York",
    "MI": "America/New_York", "MN": "America/Chicago", "MS": "America/Chicago",
    "MO": "America/Chicago", "MT": "America/Denver", "NE": "America/Chicago",
    "NV": "America/Los_Angeles", "NH": "America/New_York", "NJ": "America/New_York",
    "NM": "America/Denver", "NY": "America/New_York", "NC": "America/New_York",
    "ND": "America/Chicago", "OH": "America/New_York", "OK": "America/Chicago",
    "OR": "America/Los_Angeles", "PA": "America/New_York", "RI": "America/New_York",
    "SC": "America/New_York", "SD": "America/Chicago", "TN": "America/Chicago",
    "TX": "America/Chicago", "UT": "America/Denver", "VT": "America/New_York",
    "VA": "America/New_York", "WA": "America/Los_Angeles", "WV": "America/New_York",
    "WI": "America/Chicago", "WY": "America/Denver"
}

# -----------------------
# Page Config
# -----------------------
st.set_page_config(
    page_title="Training Dashboard",
    page_icon="🌡️",
    layout="wide"
)

# -----------------------
# Helpers
# -----------------------
def f_to_c(Tf):
    return (Tf - 32.0) * 5.0 / 9.0

def c_to_f(Tc):
    return Tc * 9.0 / 5.0 + 32.0

def wind_chill_f(Tf, wind_mph):
    if Tf > 50 or wind_mph <= 3:
        return None
    return 35.74 + 0.6215 * Tf - 35.75 * (wind_mph ** 0.16) + 0.4275 * Tf * (wind_mph ** 0.16)

def approx_natural_wet_bulb(Tc, rh):
    rh = max(0.0, min(100.0, rh))
    return (Tc * math.atan(0.151977 * math.sqrt(rh + 8.313659)) +
            math.atan(Tc + rh) - math.atan(rh - 1.676331) +
            0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh) -
            4.686035)

def approx_wbgt(Tc, rh, sunny=False, globe_offset_c=3.0):
    Tw = approx_natural_wet_bulb(Tc, rh)
    Tg = Tc + globe_offset_c if sunny else Tc
    wbgt_c = 0.7 * Tw + 0.3 * Tg
    return wbgt_c, Tw, Tg

def heat_category_from_wbgt_f(wbgt_f):
    if wbgt_f < 78:
        return "Below White", 1
    if 78 <= wbgt_f <= 81.9:
        return "White (Cat 1)", 1
    if 82 <= wbgt_f <= 84.9:
        return "Green (Cat 2)", 2
    if 85 <= wbgt_f <= 87.9:
        return "Yellow (Cat 3)", 3
    if 88 <= wbgt_f <= 89.9:
        return "Red (Cat 4)", 4
    return "Black (Cat 5)", 5

def interpret_condition(cond_text):
    c = (cond_text or "").lower()
    if "thunder" in c or "storm" in c:
        return "extreme", "Thunderstorm / lightning risk", "NO OUTDOOR TRAINING"
    if "freezing rain" in c or ("freezing" in c and "rain" in c):
        return "extreme", "Freezing rain / ice risk", "NO OUTDOOR TRAINING"
    if "sleet" in c or "ice" in c or "icy" in c:
        return "extreme", "Icy conditions", "NO OUTDOOR TRAINING"
    if "blizzard" in c:
        return "extreme", "Blizzard / near-zero visibility", "NO OUTDOOR_TRAINING"
    if "heavy snow" in c:
        return "high", "Heavy snow — visibility & slip risk", None
    if "snow" in c or "flurr" in c:
        return "moderate", "Snow present — traction/visibility caution", None
    if "heavy rain" in c or "torrential" in c:
        return "high", "Heavy rain — hypothermia & slip risk", None
    if "rain" in c or "shower" in c:
        return "moderate", "Rain — wet/hypothermia risk", None
    if "drizzle" in c or "light rain" in c:
        return "low", "Light rain / drizzle", None
    if "fog" in c or "mist" in c:
        return "moderate", "Fog / reduced visibility", None
    return "low", "No precipitation hazards", None

def recommend_uniform_option_a(temp_f, wind_chill_f, heat_cat_num, wbgt_applicable, precip_level="low"):
    if wbgt_applicable and heat_cat_num is not None:
        if heat_cat_num >= 5:
            return ("Light clothing only; no armor; full hydration and move indoors", 3)
        if heat_cat_num == 4:
            return ("Light OCP/PT, reduce load, hydrate frequently", 2)
        if heat_cat_num == 3:
            return ("OCP, consider modified load and frequent water breaks", 1)
        return ("Standard OCP/PT uniform", 0)
    if wind_chill_f is not None:
        if wind_chill_f <= -20:
            return ("Arctic clothing / extreme cold gear. No exposed skin. No outdoor training.", 3)
        if wind_chill_f <= 0:
            return ("Parka + layered clothing + gloves + balaclava. Move indoors for prolonged training.", 2)
        if wind_chill_f <= 20:
            return ("OCP + parka + gloves + warm layers. Limit prolonged exposed activities.", 2)
        if wind_chill_f <= 32:
            return ("OCP + fleece + gloves recommended.", 1)
    if temp_f <= 50 and temp_f > 33:
        return ("OCP + fleece optional; monitor wind and wetness.", 1)
    return ("Standard OCP/PT uniform", 0)

def recommend_pt_uniform(temp_f):
    try:
        t = float(temp_f)
    except Exception:
        return "Standard PT uniform"
    if t > 80:
        return "APFU Short-sleeve + shorts"
    if 60 <= t <= 80:
        return "APFU Short-sleeve shirt + APFU shorts"
    if 40 <= t <= 59:
        return "APFU Short-sleeve + APFU Long-sleeve + APFU shorts"
    if 20 <= t <= 39:
        return "APFU Short-sleeve + APFU Long-sleeve + APFU Pants + APFU Jacket + Fleece Cap"
    return "APFU Short-sleeve + APFU Long-sleeve + APFU Pants + APFU Jacket + Fleece Cap + Gloves"

def final_training_decision(temp_f, wind_chill_f, heat_cat_num, wbgt_applicable, precip_override=None, precip_level="low"):
    if precip_override:
        return precip_override
    if wind_chill_f is not None and wind_chill_f <= -20:
        return "NO OUTDOOR TRAINING — EXTREME COLD"
    if wind_chill_f is not None and wind_chill_f <= 0:
        return "MOVE TRAINING INDOORS / HIGH COLD RISK"
    if wind_chill_f is not None and wind_chill_f <= 20:
        return "LIMIT OUTDOOR TRAINING / USE INDOORS WHEN POSSIBLE (COLD CAUTION)"
    if precip_level == "high":
        return "LIMIT OUTDOOR TRAINING / USE INDOORS WHEN POSSIBLE (PRECIPITATION)"
    if wbgt_applicable and heat_cat_num is not None:
        if heat_cat_num >= 5:
            return "NO OUTDOOR TRAINING — EXTREME HEAT (BLACK FLAG)"
        if heat_cat_num == 4:
            return "LIMIT OUTDOOR TRAINING / USE INDOORS WHEN POSSIBLE (HEAT)"
        if heat_cat_num == 3:
            return "TRAIN OUTDOORS WITH CAUTION (HEAT)"
        return "TRAIN OUTDOORS (NO RESTRICTIONS)"
    return "TRAIN OUTDOORS (NO RESTRICTIONS)"

# -----------------------
# API Functions
# -----------------------
def geocode_location(city, state, country="US"):
    """Convert city/state to coordinates using OpenWeatherMap Geocoding API"""
    url = "http://api.openweathermap.org/geo/1.0/direct"
    params = {
        "q": f"{city},{state},{country}",
        "limit": 1,
        "appid": WEATHER_API_KEY
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    if not data:
        return None
    
    return {
        "lat": data[0]["lat"],
        "lon": data[0]["lon"],
        "name": data[0].get("name", city),
        "state": data[0].get("state", state)
    }

@st.cache_data(ttl=600)
def fetch_current_weather(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": WEATHER_API_KEY,
        "units": "imperial"
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    return {
        "location": {
            "name": data.get("name", "Brookings"),
            "region": "SD",
            "country": "US",
            "tz_id": "America/Chicago"
        },
        "current": {
            "temp_f": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "wind_mph": data["wind"]["speed"],
            "cloud": data["clouds"]["all"],
            "condition": {
                "text": data["weather"][0]["description"].title()
            }
        }
    }

@st.cache_data(ttl=3600)
def fetch_forecast(lat, lon, days=14):
    """Fetch forecast - tries daily first, falls back to hourly aggregation"""
    url_daily = "https://api.openweathermap.org/data/2.5/forecast/daily"
    params_daily = {
        "lat": lat,
        "lon": lon,
        "cnt": days,
        "appid": WEATHER_API_KEY,
        "units": "imperial"
    }
    
    try:
        resp = requests.get(url_daily, params=params_daily, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        forecast_days = []
        for item in data.get("list", []):
            dt = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
            rain_mm = item.get("rain", 0)
            snow_mm = item.get("snow", 0)
            
            forecast_days.append({
                "date": dt.strftime("%Y-%m-%d"),
                "day": {
                    "avgtemp_f": item["temp"]["day"],
                    "avgtemp_c": f_to_c(item["temp"]["day"]),
                    "avghumidity": item["humidity"],
                    "maxwind_mph": item["speed"],
                    "daily_chance_of_rain": 100 if rain_mm > 0 else 0,
                    "daily_chance_of_snow": 100 if snow_mm > 0 else 0,
                    "condition": {
                        "text": item["weather"][0]["description"].title()
                    }
                }
            })
        
        return {
            "location": {
                "name": data["city"]["name"],
                "region": "SD",
                "country": data["city"]["country"]
            },
            "forecast": {
                "forecastday": forecast_days
            }
        }
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return fetch_forecast_hourly_fallback(lat, lon, days)
        raise
    
@st.cache_data(ttl=3600)
def fetch_forecast_hourly_fallback(lat, lon, days):
    """Fallback to 5-day/3-hour forecast and aggregate to daily"""
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": WEATHER_API_KEY,
        "units": "imperial"
    }
    
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    daily_data = {}
    for item in data["list"]:
        dt = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
        date_key = dt.strftime("%Y-%m-%d")
        
        if date_key not in daily_data:
            daily_data[date_key] = {
                "temps": [],
                "humidity": [],
                "wind": [],
                "rain": 0,
                "snow": 0,
                "conditions": []
            }
        
        daily_data[date_key]["temps"].append(item["main"]["temp"])
        daily_data[date_key]["humidity"].append(item["main"]["humidity"])
        daily_data[date_key]["wind"].append(item["wind"]["speed"])
        daily_data[date_key]["rain"] += item.get("rain", {}).get("3h", 0)
        daily_data[date_key]["snow"] += item.get("snow", {}).get("3h", 0)
        daily_data[date_key]["conditions"].append(item["weather"][0]["description"])
    
    forecast_days = []
    for date_key in sorted(daily_data.keys())[:days]:
        day_data = daily_data[date_key]
        avg_temp = sum(day_data["temps"]) / len(day_data["temps"])
        
        forecast_days.append({
            "date": date_key,
            "day": {
                "avgtemp_f": avg_temp,
                "avgtemp_c": f_to_c(avg_temp),
                "avghumidity": sum(day_data["humidity"]) / len(day_data["humidity"]),
                "maxwind_mph": max(day_data["wind"]),
                "daily_chance_of_rain": 100 if day_data["rain"] > 0 else 0,
                "daily_chance_of_snow": 100 if day_data["snow"] > 0 else 0,
                "condition": {
                    "text": max(set(day_data["conditions"]), key=day_data["conditions"].count).title()
                }
            }
        })
    
    return {
        "location": {
            "name": data["city"]["name"],
            "region": "SD",
            "country": data["city"]["country"]
        },
        "forecast": {
            "forecastday": forecast_days
        }
    }
    

def get_status_color(decision_text):
    """Return color based on decision severity"""
    if "NO OUTDOOR" in decision_text or "MOVE" in decision_text:
        return "🔴"
    elif "LIMIT" in decision_text:
        return "🟡"
    else:
        return "🟢"

# -----------------------
# Main App
# -----------------------
def main():
    st.title("S2 Dashboard")
    
    # API Key Check
    if not WEATHER_API_KEY:
        st.error("OpenWeather API key not configured. Please add OPENWEATHER_API_KEY to your Streamlit secrets.")
        st.info("For local development, create `.streamlit/secrets.toml` with:\n```\nOPENWEATHER_API_KEY = \"your_key_here\"\n```")
        st.stop()
    
    # Location selector in sidebar
    st.sidebar.header("Location Settings")
    location_choice = st.sidebar.selectbox(
        "Select Location",
        options=list(LOCATIONS.keys()),
        index=0
    )
    
    if location_choice == "Enter City/State":
        st.sidebar.subheader("Custom Location")
        custom_city = st.sidebar.text_input("City", value="Sioux Falls", help="Enter city name")
        custom_state = st.sidebar.text_input("State (2-letter code)", value="SD", max_chars=2, help="e.g., SD, TX, CA").upper()
        
        if st.sidebar.button("Find Location", type="primary"):
            with st.spinner("Looking up coordinates..."):
                try:
                    geo_data = geocode_location(custom_city, custom_state)
                    if geo_data:
                        # Store in session state
                        st.session_state.custom_lat = geo_data["lat"]
                        st.session_state.custom_lon = geo_data["lon"]
                        st.session_state.custom_name = f"{geo_data['name']}, {geo_data['state']}"
                        st.session_state.custom_tz = STATE_TIMEZONES.get(custom_state, "America/Chicago")
                        st.sidebar.success(f"Found: {st.session_state.custom_name}")
                    else:
                        st.sidebar.error(f"Could not find '{custom_city}, {custom_state}'. Please check spelling.")
                except Exception as e:
                    st.sidebar.error(f"Geocoding error: {e}")
        
        # Use stored values or defaults
        if hasattr(st.session_state, 'custom_lat'):
            lat = st.session_state.custom_lat
            lon = st.session_state.custom_lon
            location_name = st.session_state.custom_name
            tz_name = st.session_state.custom_tz
            st.sidebar.info(f"📍 Using: {location_name}")
        else:
            st.sidebar.warning("Click 'Find Location' to search")
            # Use default values
            lat, lon = 44.3114, -96.7984
            location_name = "Brookings, SD (default)"
            tz_name = "America/Chicago"
    else:
        loc_data = LOCATIONS[location_choice]
        lat = loc_data["lat"]
        lon = loc_data["lon"]
        tz_name = loc_data["tz"]
        location_name = location_choice
    
    # Fetch data
    try:
        current_data = fetch_current_weather(lat, lon)
        
        if tz_name and ZoneInfo:
            local_time = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S %Z")
        else:
            local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        st.caption(f"{location_name} • {local_time}")
    except Exception as e:
        st.error(f"Weather fetch failed: {e}")
        return
    footer_html = """
    <style>

    /* CSS styles for the main footer container */
    .footer {
        position: static; /* Fixes the footer to the viewport */
        left: 0;
        bottom: 105px;
        width: 100%;
        background-color: none; /* Background color of the footer */
        color: white; /* Text color */
        text-align: center; /* Centers the content */
        padding: 10px 0; /* Some padding for better appearance */
    }
    </style>
    <div class="footer">
        <p>Built in reference to TRADOC 350-29 and AR 670-1</p>
    </div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Current Conditions", "16-Day Forecast", "Training Planner", "Weekly Report", "Current News"])
    
    # TAB 1: Current Conditions
    with tab1:
        weather = current_data["current"]
        temp_f = weather["temp_f"]
        rh = weather.get("humidity", 50)
        wind_mph = weather.get("wind_mph", 0.0)
        clouds = weather.get("cloud", 0)
        weather_text = weather.get("condition", {}).get("text", "")
        
        sunny = clouds < 30
        temp_c = f_to_c(temp_f)
        wbgt_c, twb_c, tg_c = approx_wbgt(temp_c, rh, sunny)
        wbgt_f = c_to_f(wbgt_c)
        
        wc = wind_chill_f(temp_f, wind_mph)
        wc_text = f"{wc:.1f} °F" if wc is not None else "N/A"
        
        wbgt_applicable = temp_f > WBGT_CUTOFF_F
        heat_label, heat_num = heat_category_from_wbgt_f(wbgt_f) if wbgt_applicable else ("N/A (cold)", None)
        
        precip_level, cond_note, precip_override = interpret_condition(weather_text)
        
        uniform, uniform_level = recommend_uniform_option_a(temp_f, wc, heat_num, wbgt_applicable, precip_level)
        final_dec = final_training_decision(temp_f, wc, heat_num, wbgt_applicable, precip_override, precip_level)
        pt_uniform = recommend_pt_uniform(temp_f)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Temperature", f"{temp_f:.1f}°F", f"{temp_c:.1f}°C")
        with col2:
            st.metric("Humidity", f"{int(rh)}%")
        with col3:
            st.metric("Wind", f"{wind_mph:.1f} mph")
        with col4:
            st.metric("Clouds", f"{clouds}%")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Heat Analysis")
            st.write(f"**WBGT (est.):** {wbgt_f:.1f}°F ({wbgt_c:.1f}°C)")
            st.write(f"**Heat Category:** {heat_label}")
            st.write(f"**Condition:** {weather_text}")
            st.caption(f"_{cond_note}_")
        
        with col2:
            st.subheader("Cold Analysis")
            st.write(f"**Wind Chill:** {wc_text}")
            
        st.divider()
        
        st.subheader("Uniform Recommendations")
        st.info(f"**Duty Uniform:** {uniform}")
        st.success(f"**PT Uniform:** {pt_uniform}")
        
        st.divider()
        
        status_icon = get_status_color(final_dec)
        st.subheader(f"{status_icon} Training Decision")
        
        if "NO OUTDOOR" in final_dec or "MOVE" in final_dec:
            st.error(final_dec)
        elif "LIMIT" in final_dec:
            st.warning(final_dec)
        else:
            st.success(final_dec)
    
    # TAB 2: 16-Day Forecast
    with tab2:
        try:
            fdata = fetch_forecast(lat, lon, days=FORECAST_DAYS)
            forecast_days = fdata.get("forecast", {}).get("forecastday", [])
            
            for day in forecast_days:
                with st.expander(f"{day['date']}", expanded=False):
                    dday = day["day"]
                    cond = dday["condition"]["text"]
                    
                    avg_f = dday["avgtemp_f"]
                    avg_c = dday["avgtemp_c"]
                    rh_d = dday.get("avghumidity", 50)
                    wind_max = dday.get("maxwind_mph", 0)
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Temp", f"{avg_f:.1f}°F")
                    with col2:
                        st.metric("Humidity", f"{int(rh_d)}%")
                    with col3:
                        st.metric("Wind", f"{wind_max:.1f} mph")
                    with col4:
                        st.write(f"**Condition:** {cond}")
                    
                    clouds_pct = max(dday.get("daily_chance_of_rain", 0), dday.get("daily_chance_of_snow", 0))
                    sunny_d = clouds_pct < 30
                    wbgt_c_d, _, _ = approx_wbgt(avg_c, rh_d, sunny_d)
                    wbgt_f_d = c_to_f(wbgt_c_d)
                    wc_d = wind_chill_f(avg_f, wind_max)
                    wc_text_d = f"{wc_d:.1f} °F" if wc_d is not None else "N/A"
                    
                    wbgt_app_d = avg_f > WBGT_CUTOFF_F
                    heat_label_d, heat_num_d = heat_category_from_wbgt_f(wbgt_f_d) if wbgt_app_d else ("Cold", None)
                    
                    precip_level_d, _, precip_override_d = interpret_condition(cond)
                    uniform_d, _ = recommend_uniform_option_a(avg_f, wc_d, heat_num_d, wbgt_app_d, precip_level_d)
                    final_d = final_training_decision(avg_f, wc_d, heat_num_d, wbgt_app_d, precip_override_d, precip_level_d)
                    pt_uniform_d = recommend_pt_uniform(avg_f)
                    
                    st.write(f"**WBGT:** {wbgt_f_d:.1f}°F • **Heat Cat:** {heat_label_d} • **Wind Chill:** {wc_text_d}")
                    st.info(f"**Uniform:** {uniform_d}")
                    st.success(f"**PT Uniform:** {pt_uniform_d}")
                    
                    status_icon = get_status_color(final_d)
                    st.write(f"{status_icon} **Decision:** {final_d}")
        
        except Exception as e:
            st.error(f"Forecast fetch failed: {e}")
    
    # TAB 3: Training Planner
    with tab3:
        st.subheader("Training Date Planner")
        st.write("Select specific dates to analyze training conditions. Dates within the next 16 days will use forecast data.")
        
        col1, col2, col3 = st.columns(3)
        dates = []
        with col1:
            d1 = st.date_input("Training Date 1", value=None, key="d1")
            if d1: dates.append(d1)
            d2 = st.date_input("Training Date 2", value=None, key="d2")
            if d2: dates.append(d2)
        with col2:
            d3 = st.date_input("Training Date 3", value=None, key="d3")
            if d3: dates.append(d3)
            d4 = st.date_input("Training Date 4", value=None, key="d4")
            if d4: dates.append(d4)
        with col3:
            d5 = st.date_input("Training Date 5", value=None, key="d5")
            if d5: dates.append(d5)
        
        if st.button("🔍 Analyze Dates", type="primary"):
            if not dates:
                st.warning("Please select at least one date.")
            else:
                analyze_training_dates(dates, location_name, lat, lon, tz_name)
    
    # TAB 4: Weekly Report
    with tab4:
        st.subheader("Weekly Training Analysis")
        
        try:
            fdata = fetch_forecast(lat, lon, days=FORECAST_DAYS)
            forecast_days = fdata.get("forecast", {}).get("forecastday", [])
            
            data = []
            for day in forecast_days:
                dday = day["day"]
                avg_f = dday["avgtemp_f"]
                avg_c = dday["avgtemp_c"]
                rh_d = dday.get("avghumidity", 50)
                wind_max = dday.get("maxwind_mph", 0)
                cond = dday["condition"]["text"]
                
                clouds_pct = max(dday.get("daily_chance_of_rain", 0), dday.get("daily_chance_of_snow", 0))
                sunny_d = clouds_pct < 30
                wbgt_c_d, _, _ = approx_wbgt(avg_c, rh_d, sunny_d)
                wbgt_f_d = c_to_f(wbgt_c_d)
                wc_d = wind_chill_f(avg_f, wind_max)
                
                wbgt_app_d = avg_f > WBGT_CUTOFF_F
                heat_label_d, heat_num_d = heat_category_from_wbgt_f(wbgt_f_d) if wbgt_app_d else ("Cold", None)
                
                precip_level_d, _, precip_override_d = interpret_condition(cond)
                uniform_d, _ = recommend_uniform_option_a(avg_f, wc_d, heat_num_d, wbgt_app_d, precip_level_d)
                final_d = final_training_decision(avg_f, wc_d, heat_num_d, wbgt_app_d, precip_override_d, precip_level_d)
                pt_uniform_d = recommend_pt_uniform(avg_f)
                
                data.append({
                    "Date": day["date"],
                    "Temp (°F)": f"{avg_f:.1f}",
                    "RH%": f"{int(rh_d)}",
                    "Wind (mph)": f"{wind_max:.1f}",
                    "WBGT (°F)": f"{wbgt_f_d:.1f}",
                    "Heat Cat": heat_label_d,
                    "Wind Chill": "N/A" if wc_d is None else f"{wc_d:.1f}",
                    "Decision": final_d,
                    "Uniform": uniform_d,
                    "PT Uniform": pt_uniform_d
                })
            
            st.dataframe(data, use_container_width=True, hide_index=True)
            
        except Exception as e:
            st.error(f"Forecast fetch failed: {e}")

    with tab5:
        newsapi = NewsApiClient(api_key=NEWS_API_KEY)

        top_headlines = newsapi.get_top_headlines(sources='politico', language='en')

        # fetch the top news under that category
        Headlines = top_headlines['articles']
        newsArticles = []
        for headline in Headlines:
            if headline['title'] and headline['urlToImage'] and headline['description'] and headline['url']:
                newsArticles.append(headline)

        st.subheader('Latest News')

        cols = []
        cols2 = []
        match(len(newsArticles)):
            case 0:
                st.subheader('No news today! Check back tomorrow.')
            case 1:
                cols = st.columns(1, border=True)
            case 2:
                cols = st.columns(2, border=True)
            case 3:
                cols = st.columns((2, 1, 1), border=True)
            case 4:
                cols = st.columns((2, 1, 1), border=True)
                cols2 = st.columns(1, border=True)
            case 5:
                cols = st.columns((2, 1, 1), border=True)
                cols2 = st.columns(2, border=True)
            case _:
                cols = st.columns((2, 1, 1), border=True)
                cols2 = st.columns((2, 1, 1), border=True)

        for i in range(len(newsArticles)):
            if i == 6:
                break
            if i < 3:
                with cols[i]:
                    if i == 0:
                        st.header(newsArticles[i]['title'])
                    else:
                        st.subheader(newsArticles[i]['title'])
                    st.image(newsArticles[i]['urlToImage'])
                    st.write(newsArticles[i]['description'])
                    st.write(newsArticles[i]['url'])
            if i >= 3:
                with cols2[i-3]:
                    if i == 3:
                        st.header(newsArticles[i]['title'])
                    else:
                        st.subheader(newsArticles[i]['title'])
                    st.image(newsArticles[i]['urlToImage'])
                    st.write(newsArticles[i]['description'])
                    st.write(newsArticles[i]['url'])

def analyze_training_dates(dates, location_name, lat, lon, tz_name):
    """Analyze specific training dates"""
    try:
        fdata = fetch_forecast(lat, lon, days=14)
        forecast_days = fdata.get("forecast", {}).get("forecastday", [])
    except:
        forecast_days = []
    
    today = datetime.now(ZoneInfo(tz_name)).date()
    
    for target_date in dates:
        days_from_now = (target_date - today).days
        
        st.divider()
        st.subheader(f"{target_date.strftime('%Y-%m-%d')}")
        
        if 0 <= days_from_now <= 16:
            # Find matching forecast
            found = False
            data = []
            for day in forecast_days:
                if day["date"] == target_date.strftime("%Y-%m-%d"):
                    found = True
                    dday = day["day"]
                    avg_f = dday["avgtemp_f"]
                    avg_c = dday["avgtemp_c"]
                    rh_d = dday.get("avghumidity", 50)
                    wind_max = dday.get("maxwind_mph", 0)
                    cond = dday["condition"]["text"]
                    
                    clouds_pct = max(dday.get("daily_chance_of_rain", 0), dday.get("daily_chance_of_snow", 0))
                    sunny_d = clouds_pct < 30
                    wbgt_c_d, _, _ = approx_wbgt(avg_c, rh_d, sunny_d)
                    wbgt_f_d = c_to_f(wbgt_c_d)
                    wc_d = wind_chill_f(avg_f, wind_max)
                    
                    wbgt_app_d = avg_f > WBGT_CUTOFF_F
                    heat_label_d, heat_num_d = heat_category_from_wbgt_f(wbgt_f_d) if wbgt_app_d else ("Cold", None)
                    
                    precip_level_d, _, precip_override_d = interpret_condition(cond)
                    uniform_d, _ = recommend_uniform_option_a(avg_f, wc_d, heat_num_d, wbgt_app_d, precip_level_d)
                    final_d = final_training_decision(avg_f, wc_d, heat_num_d, wbgt_app_d, precip_override_d, precip_level_d)
                    pt_uniform_d = recommend_pt_uniform(avg_f)
                    
                    data.append({
                        "Date": day["date"],
                        "Temp (°F)": f"{avg_f:.1f}",
                        "RH%": f"{int(rh_d)}",
                        "Wind (mph)": f"{wind_max:.1f}",
                        "WBGT (°F)": f"{wbgt_f_d:.1f}",
                        "Heat Cat": heat_label_d,
                        "Wind Chill": "N/A" if wc_d is None else f"{wc_d:.1f}",
                        "Decision": final_d,
                        "Uniform": uniform_d,
                        "PT Uniform": pt_uniform_d
                    })
            
            st.dataframe(data, use_container_width=True, hide_index=True)
            
            
            if not found:
                st.warning("Forecast data not available for this date. Try a date within the next 16 days.")
        else:
            st.warning("This date is outside the 16-day forecast window.")

if __name__ == "__main__":
    main()