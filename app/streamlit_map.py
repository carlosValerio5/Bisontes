import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import unicodedata
from folium.plugins import HeatMap

# Helper to normalize names
def normalize(s):
    if pd.isna(s):
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode('ascii')
    return ' '.join(s.split())

# Load data
@st.cache_data
def load_data():
    mun_gdf = gpd.read_file("municipios.shp")
    csv = pd.read_csv("nuevo_leon_points_by_municipio.csv")
    med = pd.read_csv("unidades_medicas_totales.csv")
    temp = pd.read_csv("temperature_data_by_municipio.csv")
    temp["_mun_norm"] = temp["NAME_2"].astype(str).apply(normalize)
    mun_gdf["_mun_norm"] = mun_gdf["NAME_2"].astype(str).apply(normalize)
    csv["_mun_norm"] = csv["NAME_2"].astype(str).apply(normalize)
    med["_mun_norm"] = med["Municipio"].astype(str).apply(normalize)
    mun_gdf = mun_gdf.merge(temp[["_mun_norm", "Tmax"]], on="_mun_norm", how="left")
    csv = csv.merge(med[["_mun_norm", "Total"]], on="_mun_norm", how="left")
    merged = mun_gdf.merge(csv, left_on="_mun_norm", right_on="_mun_norm", how="left")
    return merged

st.set_page_config(page_title="Nuevo León Interactive Map", layout="wide")
st.title("Nuevo León Municipality Explorer")

merged = load_data()

# Sidebar filters
st.sidebar.header("Map Layers & Filters")
municipalities = merged["NAME_2_x"].sort_values().unique().tolist()
municipalities.insert(0, "All")
selected_mun = st.sidebar.selectbox("Select Municipality", municipalities)

# Layer toggles
show_med = st.sidebar.checkbox("Show Medical Units", value=True)
show_pop = st.sidebar.checkbox("Show Population Density Heatmap", value=True)
show_temp = st.sidebar.checkbox("Show Temperature Heatmap", value=False)

# Create base map centered on state or selected municipality
if selected_mun != "All":
    mun_row = merged[merged["NAME_2_x"] == selected_mun].iloc[0]
    center = [mun_row.geometry.centroid.y, mun_row.geometry.centroid.x]
    zoom = 10
else:
    center = [merged.geometry.centroid.y.mean(), merged.geometry.centroid.x.mean()]
    zoom = 7

m = folium.Map(location=center, zoom_start=zoom, tiles="CartoDB positron")

# Base GeoJson layer (municipal boundaries)
folium.GeoJson(merged.geometry, name="Municipalities", style_function=lambda x: {"color": "blue", "weight": 1, "fillOpacity": 0.05}).add_to(m)

# Medical units: show circle markers sized by 'Total' if available
if show_med:
    med_fg = folium.FeatureGroup(name="Medical Units")
    for idx, row in merged.iterrows():
        try:
            y = row.geometry.centroid.y
            x = row.geometry.centroid.x
        except Exception:
            continue
        total = row.get("Total", None)
        popup = f"{row.get('NAME_2_x', '')}: {int(total) if pd.notna(total) else 'N/A'}"
        radius = 4
        if pd.notna(total):
            try:
                radius = max(3, min(20, int(total) // 2))
            except Exception:
                radius = 4
        folium.CircleMarker(location=[y, x], radius=radius, color="red", fill=True, fill_opacity=0.7, popup=popup).add_to(med_fg)
    med_fg.add_to(m)

# Population density heatmap
if show_pop:
    pop_fg = folium.FeatureGroup(name="Population Density Heatmap")
    pop_points = []
    for idx, row in merged.iterrows():
        if row.geometry is None:
            continue
        y = row.geometry.centroid.y
        x = row.geometry.centroid.x
        w = row.get("mean_population_density", None)
        if pd.notna(w):
            pop_points.append([y, x, float(w)])
    # population gradient: cool -> warm
    pop_gradient = {
        0.2: "#440154",
        0.4: "#3b528b",
        0.6: "#21918c",
        0.8: "#5ec962",
        1.0: "#fde725",
    }
    if pop_points:
        HeatMap(pop_points, radius=20, blur=15, min_opacity=0.4, gradient=pop_gradient).add_to(pop_fg)
    pop_fg.add_to(m)

# Temperature heatmap
if show_temp:
    temp_fg = folium.FeatureGroup(name="Temperature Heatmap")
    temp_points = []
    for idx, row in merged.iterrows():
        if row.geometry is None:
            continue
        y = row.geometry.centroid.y
        x = row.geometry.centroid.x
        t = row.get("Tmax", None)
        if pd.notna(t):
            try:
                temp_points.append([y, x, float(t)])
            except Exception:
                continue
    # temperature gradient: light yellow -> red
    temp_gradient = {
        0.2: "#ffffb2",
        0.4: "#fecc5c",
        0.6: "#fd8d3c",
        0.8: "#f03b20",
        1.0: "#bd0026",
    }
    if temp_points:
        HeatMap(temp_points, radius=20, blur=15, min_opacity=0.4, gradient=temp_gradient).add_to(temp_fg)
    temp_fg.add_to(m)

# If a municipality is selected, highlight it and show metrics
if selected_mun != "All":
    try:
        folium.GeoJson(mun_row.geometry, name="Selected Municipality", style_function=lambda x: {"color": "blue", "weight": 2, "fillOpacity": 0.15}).add_to(m)
        folium.Marker([mun_row.geometry.centroid.y, mun_row.geometry.centroid.x], popup=selected_mun).add_to(m)
    except Exception:
        pass

# Create legends for layers (left side with dark translucent background)
# compute ranges
pop_vals = merged["mean_population_density"].dropna() if "mean_population_density" in merged.columns else pd.Series([])
temp_vals = merged["Tmax"].dropna() if "Tmax" in merged.columns else pd.Series([])
med_vals = merged["Total"].dropna() if "Total" in merged.columns else pd.Series([])

pop_vmin, pop_vmax = (float(pop_vals.min()), float(pop_vals.max())) if len(pop_vals) > 0 else (None, None)
temp_vmin, temp_vmax = (float(temp_vals.min()), float(temp_vals.max())) if len(temp_vals) > 0 else (None, None)
med_vmin, med_vmax = (float(med_vals.min()), float(med_vals.max())) if len(med_vals) > 0 else (None, None)

# Gradient CSS builders (match the gradients used earlier)
pop_gradient = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"]
temp_gradient = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]

def gradient_css(colors):
    # create a linear-gradient CSS from list of colors
    stops = []
    n = len(colors)
    for i, c in enumerate(colors):
        pct = int((i / (n - 1)) * 100) if n > 1 else 0
        stops.append(f"{c} {pct}%")
    return "linear-gradient(to right, " + ", ".join(stops) + ")"

legend_html = ""
pos_bottom = 10
left_offset = 10
box_style = "background: rgba(20,20,20,0.85); color: white; padding:8px; border-radius:6px; font-size:12px;"

if pop_vmin is not None:
    pop_bar = gradient_css(pop_gradient)
    legend_html += f"<div style='position: absolute; bottom: {pos_bottom}px; left: {left_offset}px; z-index:1000; {box_style}'>"
    legend_html += f"<b>Population density</b><div style='width:160px; height:12px; margin-top:6px; background: {pop_bar}; border-radius:4px;'></div>"
    legend_html += f"<div style='display:flex; justify-content:space-between; color: #eee;'><span>{pop_vmin:.1f}</span><span>{pop_vmax:.1f}</span></div></div>"
    pos_bottom += 66

if temp_vmin is not None:
    temp_bar = gradient_css(temp_gradient)
    legend_html += f"<div style='position: absolute; bottom: {pos_bottom}px; left: {left_offset}px; z-index:1000; {box_style}'>"
    legend_html += f"<b>Temperature (Tmax)</b><div style='width:160px; height:12px; margin-top:6px; background: {temp_bar}; border-radius:4px;'></div>"
    legend_html += f"<div style='display:flex; justify-content:space-between; color: #eee;'><span>{temp_vmin:.1f}</span><span>{temp_vmax:.1f}</span></div></div>"
    pos_bottom += 66

if med_vmin is not None:
    # simple legend for medical units (marker sizes)
    small = max(3, int(med_vmin) // 2) if med_vmin >= 1 else 3
    large = max(6, int(med_vmax) // 2) if med_vmax >= 1 else 6
    # SVG with white labels
    legend_html += f"<div style='position: absolute; bottom: {pos_bottom}px; left: {left_offset}px; z-index:1000; {box_style}'>"
    legend_html += f"<b>Medical units (Total)</b><div style='margin-top:6px;'>"
    legend_html += f"<svg width='160' height='36'><circle cx='30' cy='18' r='{small}' fill='red' opacity='0.8' /><text x='55' y='22' font-size='12' fill='#fff'>{int(med_vmin)}</text>"
    legend_html += f"<circle cx='110' cy='18' r='{large}' fill='red' opacity='0.8' /><text x='125' y='22' font-size='12' fill='#fff'>{int(med_vmax)}</text></svg></div></div>"

if legend_html:
    m.get_root().html.add_child(folium.Element(legend_html))

# Layer control and display
folium.LayerControl().add_to(m)
st_folium(m, width=1000, height=700)

st.markdown("---")
st.markdown("Select a municipality from the sidebar to view its data and location. More filters and data can be added easily.")
