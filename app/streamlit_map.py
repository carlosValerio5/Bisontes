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
    mun_gdf["_mun_norm"] = mun_gdf["NAME_2"].astype(str).apply(normalize)
    csv["_mun_norm"] = csv["NAME_2"].astype(str).apply(normalize)
    med["_mun_norm"] = med["Municipio"].astype(str).apply(normalize)
    csv = csv.merge(med[["_mun_norm", "Total"]], on="_mun_norm", how="left")
    merged = mun_gdf.merge(csv, left_on="_mun_norm", right_on="_mun_norm", how="left")
    return merged

st.set_page_config(page_title="Nuevo León Interactive Map", layout="wide")
st.title("Nuevo León Municipality Explorer")

merged = load_data()

# Sidebar filters
st.sidebar.header("Filters")
municipalities = merged["NAME_2_x"].sort_values().unique().tolist()
municipalities.append("All")
selected_mun = st.sidebar.selectbox("Select Municipality", municipalities)
tab1, tab2 = st.tabs(["Medical Units", "Population Density Heatmap"])

with tab1:
    # Filtered data

    if selected_mun != "All":
        mun_row = merged[merged["NAME_2_x"] == selected_mun].iloc[0]

        # Map
        m = folium.Map(location=[mun_row.geometry.centroid.y, mun_row.geometry.centroid.x], zoom_start=8, tiles="CartoDB positron")
        folium.GeoJson(mun_row.geometry, name=selected_mun, style_function=lambda x: {"color": "blue", "weight": 2, "fillOpacity": 0.2}).add_to(m)
        folium.Marker([mun_row.geometry.centroid.y, mun_row.geometry.centroid.x], popup=selected_mun).add_to(m)

        st.subheader(f"Municipality: {selected_mun}")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Mean Population Density", f"{mun_row.get('mean_population_density', 'N/A'):.2f}")
            st.metric("Sum Population Density", f"{mun_row.get('sum_population_density', 'N/A'):.2f}")
            st.metric("Point Count", f"{mun_row.get('point_count', 'N/A')}")
        with col2:
            st.metric("Medical Units (Total)", int(mun_row.get('Total', 0)) if 'Total' in mun_row else 'N/A')
    else:
        # Map for all municipalities
        m = folium.Map(location=[merged.geometry.centroid.y.mean(), merged.geometry.centroid.x.mean()], zoom_start=7, tiles="CartoDB positron")
        folium.GeoJson(merged.geometry, name="All Municipalities", style_function=lambda x: {"color": "blue", "weight": 1, "fillOpacity": 0.1}).add_to(m)

        st.subheader("All Municipalities Summary")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Mean Population Density", f"{merged['mean_population_density'].mean():.2f}")
            st.metric("Sum Population Density", f"{merged['sum_population_density'].sum():.2f}")
            st.metric("Total Point Count", f"{merged['point_count'].sum():.0f}")
        with col2:
            st.metric("Medical Units (Total)", int(merged['Total'].sum()) if 'Total' in merged else 'N/A')
    st_folium(m, width=900, height=600)

with tab2:
    # After creating your map object (m = folium.Map(...))
    st.subheader("Population Density Heatmap")
    m2 = folium.Map(location=[merged.geometry.centroid.y.mean(), merged.geometry.centroid.x.mean()], zoom_start=7, tiles="CartoDB positron")

    folium.GeoJson(merged, name="All Municipalities", style_function=lambda x: {"color": "blue", "weight": 1, "fillOpacity": 0.1}).add_to(m2)

    # Prepare heatmap data: [lat, lon, weight]
    heat_data = [
        [row.geometry.centroid.y, row.geometry.centroid.x, row.get("mean_population_density", 1)]
        for idx, row in merged.iterrows()
        if row.geometry is not None and not pd.isna(row.geometry.centroid.x) and not pd.isna(row.geometry.centroid.y)
    ]

    if heat_data:
        HeatMap(heat_data, radius=20, blur=15, min_opacity=0.5, max_zoom=13).add_to(m2)

    st_folium(m2, width=900, height=600)

# Structure for future filters
st.sidebar.markdown("---")
st.sidebar.subheader("Future Filters")
st.sidebar.text("Add more filters here (e.g., year, type, etc.)")

st.markdown("---")
st.markdown("Select a municipality from the sidebar to view its data and location. More filters and data can be added easily.")
