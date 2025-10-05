import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Air Quality Monitor",
    page_icon="🌬️",
    layout="wide"
)

# --- API CONFIGURATION ---
try:
    OPENWEATHER_API_KEY = st.secrets["OPENWEATHER_API_KEY"]
except FileNotFoundError:
    OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

if not OPENWEATHER_API_KEY:
    st.error("OpenWeatherMap API key not found! Please configure it in .streamlit/secrets.toml")
    st.stop()

# --- AIRNOW AQI GUIDE ---
AIRNOW_AQI_GUIDE = [
    {"range": (0, 50), "level": "Good", "color": "#00e400", "description": "Air quality is satisfactory, and air pollution poses little or no risk."},
    {"range": (51, 100), "level": "Moderate", "color": "#ffff00", "description": "Air quality is acceptable. However, there may be a risk for some people, particularly those who are unusually sensitive to air pollution."},
    {"range": (101, 150), "level": "Unhealthy for Sensitive Groups", "color": "#ff7e00", "description": "Members of sensitive groups may experience health effects. The general public is less likely to be affected."},
    {"range": (151, 200), "level": "Unhealthy", "color": "#ff0000", "description": "Some members of the general public may experience health effects; members of sensitive groups may experience more serious health effects."},
    {"range": (201, 300), "level": "Very Unhealthy", "color": "#8f3f97", "description": "Health alert: The risk of health effects is increased for everyone."},
    {"range": (301, 10000), "level": "Hazardous", "color": "#7e0023", "description": "Health warning of emergency conditions: everyone is more likely to be affected."}
]

def get_airnow_aqi_info(aqi_value):
    """Finds the corresponding AQI level, color, and description from the AirNow guide."""
    for category in AIRNOW_AQI_GUIDE:
        low, high = category["range"]
        if low <= aqi_value <= high:
            return category
    return AIRNOW_AQI_GUIDE[-1]

BREAKPOINTS = {
    'o3_ppm': [(0.000,0.054,0,50),(0.055,0.070,51,100),(0.071,0.085,101,150),(0.086,0.105,151,200),(0.106,0.200,201,300),(0.201,0.404,301,400)],
    'pm2_5': [(0.0,9.0,0,50),(9.1,35.4,51,100),(35.5,55.4,101,150),(55.5,125.4,151,200),(125.5,225.4,201,300),(225.5,325.4,301,400)],
    'pm10': [(0,54,0,50),(55,154,51,100),(155,254,101,150),(255,354,151,200),(355,424,201,300),(425,504,301,400)],
    'co_ppm': [(0.0,4.4,0,50),(4.5,9.4,51,100),(9.5,12.4,101,150),(12.5,15.4,151,200),(15.5,30.4,201,300),(30.5,40.4,301,400)],
    'so2_ppb': [(0,35,0,50),(36,75,51,100),(76,185,101,150),(186,304,151,200),(305,604,201,300),(605,804,301,400)],
    'no2_ppb': [(0,53,0,50),(54,100,51,100),(101,360,101,150),(361,649,151,200),(650,1249,201,300),(1250,1649,301,400)]
}
POLLUTANT_NAMES = {'o3_ppm':'Ozone (O₃)','pm2_5':'PM₂.₅','pm10':'PM₁₀','co_ppm':'CO','so2_ppb':'SO₂','no2_ppb':'NO₂'}

def calculate_pollutant_aqi(pollutant_key, concentration):
    if concentration < 0: return 0
    breakpoints = BREAKPOINTS.get(pollutant_key)
    if not breakpoints: return 0
    for bp_low,bp_hi,i_low,i_hi in breakpoints:
        if bp_low <= concentration <= bp_hi:
            if(bp_hi - bp_low) == 0: return i_low
            aqi = ((i_hi - i_low) / (bp_hi - bp_low)) * (concentration - bp_low) + i_low
            return round(aqi)
    bp_low,bp_hi,i_low,i_hi = breakpoints[-1]
    if concentration > bp_hi:
        if(bp_hi - bp_low) == 0: return i_hi
        aqi = ((i_hi - i_low) / (bp_hi - bp_low)) * (concentration - bp_low) + i_low
        return round(aqi)
    return 0

MW_O3, MW_CO, MW_SO2, MW_NO2 = 48.0, 28.01, 64.07, 46.01
MOLAR_VOLUME = 24.45
@st.cache_data(ttl=600)
def fetch_air_quality_data(lat, lon, api_key):
    air_quality_url = f"https://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    geocode_url = f"https://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={lon}&limit=1&appid={api_key}"
    try:
        air_res, geo_res = requests.get(air_quality_url), requests.get(geocode_url)
        air_res.raise_for_status(); geo_res.raise_for_status()
        return air_res.json(), geo_res.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data: {e}"); return None, None
def geocode_city(city_name, api_key):
    geocode_url = f"https://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={api_key}"
    try:
        response = requests.get(geocode_url); response.raise_for_status()
        data = response.json()
        if data: return data[0]['lat'], data[0]['lon']
    except requests.exceptions.RequestException: return None, None

if 'center' not in st.session_state: st.session_state['center'] = [-10.9472, -37.0731]
if 'zoom' not in st.session_state: st.session_state['zoom'] = 13

st.title("Air Quality Monitor")
top_cols = st.columns([2, 3])
with top_cols[0]:
    search_query = st.text_input("Search by city", placeholder="Enter a city name...")
    if st.button("Search"):
        if search_query:
            lat, lon = geocode_city(search_query, OPENWEATHER_API_KEY)
            if lat and lon: st.session_state['center'] = [lat, lon]; st.session_state['zoom'] = 13
            else: st.error(f"City '{search_query}' not found.")

current_lat, current_lon = st.session_state['center']
air_data, geo_data = fetch_air_quality_data(current_lat, current_lon, OPENWEATHER_API_KEY)

m = folium.Map(location=st.session_state['center'], zoom_start=st.session_state['zoom'])
if air_data and geo_data:
    components = air_data['list'][0]['components']
    o3_v, pm25_v, pm10_v = components.get('o3',0), components.get('pm2_5',0), components.get('pm10',0)
    co_v, so2_v, no2_v = components.get('co',0), components.get('so2',0), components.get('no2',0)
    
    o3_raw_ppm = (o3_v * MOLAR_VOLUME) / (MW_O3 * 1000)
    co_raw_ppm = (co_v * MOLAR_VOLUME) / (MW_CO * 1000)
    so2_raw_ppb = (so2_v * MOLAR_VOLUME) / MW_SO2
    no2_raw_ppb = (no2_v * MOLAR_VOLUME) / MW_NO2

    o3_c = int(o3_raw_ppm * 1000) / 1000.0
    pm25_c = int(pm25_v * 10) / 10.0; pm10_c = int(pm10_v)
    co_c = int(co_raw_ppm * 10) / 10.0
    so2_c = int(so2_raw_ppb); no2_c = int(no2_raw_ppb)

    aqi_v = {'o3_ppm':calculate_pollutant_aqi('o3_ppm',o3_c),'pm2_5':calculate_pollutant_aqi('pm2_5',pm25_c),
             'pm10':calculate_pollutant_aqi('pm10',pm10_c),'co_ppm':calculate_pollutant_aqi('co_ppm',co_c),
             'so2_ppb':calculate_pollutant_aqi('so2_ppb',so2_c),'no2_ppb':calculate_pollutant_aqi('no2_ppb',no2_c)}
    overall_aqi = max(aqi_v.values()) if aqi_v else 0

    location_name = geo_data[0].get('name', 'Unknown Location')
    airnow_info = get_airnow_aqi_info(overall_aqi)
    popup_text = f"<b>{location_name}</b><br>AQI: {overall_aqi} ({airnow_info['level']})"
    
    with top_cols[1]:
        text_color = "#000000" if airnow_info['color'] == "#ffff00" else "#000000"
        st.markdown(f"""
        <div style="background-color: {airnow_info['color']}; color: {text_color}; padding: 10px; border-radius: 8px; text-align: center; height: 100%;">
            <div style="font-size: 1.1em; font-weight: bold;">{airnow_info['level']} (AQI: {overall_aqi})</div>
            <p style="font-size: 0.9em; margin-top: 5px;">{airnow_info['description']}</p>
            <p style="font-size: 0.8em; margin-top: 8px; opacity: 0.8;"><em>From AirNow</em></p>
        </div>
        """, unsafe_allow_html=True)

    folium.Marker(location=[current_lat, current_lon], popup=popup_text, tooltip="Current Location").add_to(m)

map_data = st_folium(m, center=st.session_state['center'], zoom=st.session_state['zoom'], width='100%', height=400)
if map_data and map_data['last_clicked']:
    new_lat, new_lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
    if (new_lat, new_lon) != (current_lat, current_lon):
        st.session_state['center'] = [new_lat, new_lon]; st.rerun()

if air_data and geo_data:
    dominant_pollutant_key = max(aqi_v, key=aqi_v.get)
    
    st.markdown("---")
    st.subheader(f"AQI Analysis for {location_name}")
    aqi_cols = st.columns(2)
    with aqi_cols[0]:
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="width: 25px; height: 25px; background-color: {airnow_info['color']}; border: 1px solid #888; border-radius: 50%;"></div>
            <div><span style='font-size: 1.2em; font-weight: bold;'>{overall_aqi}</span><span style='font-size: 1.1em;'> - {airnow_info['level']}</span></div>
        </div>""", unsafe_allow_html=True)
    aqi_cols[1].metric("Dominant Pollutant", POLLUTANT_NAMES.get(dominant_pollutant_key, "N/A"))

    with st.expander("See Concentrations"):
        st.write("This table shows the original concentrations from the API (in μg/m³) and the resulting individual AQI calculated for each pollutant.")
        calc_details_cols = st.columns(6)
        calc_details_cols[0].metric(label="O₃ (μg/m³)", value=f"{o3_v:.2f}", delta=f"AQI: {aqi_v['o3_ppm']}")
        calc_details_cols[1].metric(label="PM₂.₅ (μg/m³)", value=f"{pm25_v:.2f}", delta=f"AQI: {aqi_v['pm2_5']}")
        calc_details_cols[2].metric(label="PM₁₀ (μg/m³)", value=f"{pm10_v:.2f}", delta=f"AQI: {aqi_v['pm10']}")
        calc_details_cols[3].metric(label="CO (μg/m³)", value=f"{co_v:.2f}", delta=f"AQI: {aqi_v['co_ppm']}")
        calc_details_cols[4].metric(label="SO₂ (μg/m³)", value=f"{so2_v:.2f}", delta=f"AQI: {aqi_v['so2_ppb']}")
        calc_details_cols[5].metric(label="NO₂ (μg/m³)", value=f"{no2_v:.2f}", delta=f"AQI: {aqi_v['no2_ppb']}")
else:
    st.warning("Waiting for a location to be selected on the map or searched to display data.")