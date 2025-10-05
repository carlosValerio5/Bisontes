import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import unicodedata
from folium.plugins import HeatMap
from pathlib import Path
from prueba1 import clean_headers, ensure_municipio_col, lollipop, read_csv_safe

sources = {
    "Fuentes fijas": "fixed_sources",
    "Fuentes móviles": "mobile_sources",
    "Fuentes naturales": "natural_sources",
    "Fuentes de área": "area_sources",
    "Fuentes moviles que no circulan por carretera": "non_road_mobile_sources",
}

# -----------------------------
# Paths
# -----------------------------
DATA = Path("data")
ELEC       = DATA / "top10_electricidad.csv"   # esperado: Municipio, pct_sin_electricidad
SALUD_MIN  = DATA / "salud_menores.csv"        # esperado: Municipio, Total, TVIVHAB (opcional)
SALUD_MAX  = DATA / "salud_mayores.csv"        # esperado: Municipio, Total, TVIVHAB (opcional)
ELEC_MUNI  = DATA / "elec_muni.csv"            # esperado: NOM_MUN/Municipio, TVIVHAB, VPH_S_ELEC
VIV_MIN    = DATA / "menos_viv.csv"            # esperado: Municipio, TVIVHAB

# -----------------------------
# Load data
# -----------------------------
elec        = read_csv_safe(ELEC)
men         = read_csv_safe(SALUD_MIN)
mas         = read_csv_safe(SALUD_MAX)
elec_muni   = read_csv_safe(ELEC_MUNI)
min_viv_df  = read_csv_safe(VIV_MIN)

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
    # load files
    mun_gdf = gpd.read_file("municipios.shp")
    csv = pd.read_csv("nuevo_leon_points_by_municipio.csv")
    med = pd.read_csv("unidades_medicas_totales.csv")
    temp = pd.read_csv("temperature_data_by_municipio.csv")
    green = pd.read_csv("espacios_verdes.csv")

    # normalize name columns
    temp["_mun_norm"] = temp["NAME_2"].astype(str).apply(normalize)
    mun_gdf["_mun_norm"] = mun_gdf["NAME_2"].astype(str).apply(normalize)
    csv["_mun_norm"] = csv["NAME_2"].astype(str).apply(normalize)
    med["_mun_norm"] = med["Municipio"].astype(str).apply(normalize)
    green["_mun_norm"] = green["Municipio"].astype(str).apply(normalize)

    # merge data
    mun_gdf = mun_gdf.merge(green[["_mun_norm", "m^2 por habitante"]], on="_mun_norm", how="left")
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
show_pop = st.sidebar.checkbox("Show Population Density Heatmap", value=True)
show_med = st.sidebar.checkbox("Show Medical Units", value=False)
show_temp = st.sidebar.checkbox("Show Temperature Heatmap", value=False)
show_green = st.sidebar.checkbox("Show Green Areas", value=False)

# Create two tabs: main map and pollution heatmap
# compute a safe default center (useful if selected_mun is not set yet)
default_center = [merged.geometry.centroid.y.mean(), merged.geometry.centroid.x.mean()]
default_zoom = 7

tab_map, tab_pollution, tab_electricity, tab_health, tab_housing = st.tabs(["Map", "Pollution", "Electricity", "Health", "Housing"])

with tab_map:
    # Create base map centered on state or selected municipality; use default_center to avoid empty maps
    try:
        if selected_mun != "All":
            mun_row = merged[merged["NAME_2_x"] == selected_mun].iloc[0]
            center = [mun_row.geometry.centroid.y, mun_row.geometry.centroid.x]
            zoom = 10
        else:
            center = default_center
            zoom = default_zoom

        m = folium.Map(location=center, zoom_start=zoom, tiles="CartoDB positron")
    except Exception as e:
        st.error(f"Failed to create base map: {e}")
        st.write("Showing default center instead")
        m = folium.Map(location=default_center, zoom_start=default_zoom, tiles="CartoDB positron")

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

    if show_green:
        green_fg = folium.FeatureGroup(name="Green Areas (m² per inhabitant)")

        for idx, row in merged.iterrows():
            try:
                y = row.geometry.centroid.y
                x = row.geometry.centroid.x
            except Exception:
                continue
            green_area = row.get("m^2 por habitante", None)
            popup = f"{row.get('NAME_2_x', '')}: {green_area:.1f} m²/habitante" if pd.notna(green_area) else f"{row.get('NAME_2_x', '')}: N/A"
            color = "green" if pd.notna(green_area) and green_area >= 10 else "orange" if pd.notna(green_area) and green_area >= 5 else "red"
            folium.CircleMarker(location=[y, x], radius=10, color=color, fill=True, fill_opacity=0.7, popup=popup).add_to(green_fg)
        green_fg.add_to(m)

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
    green_vals = merged["m^2 por habitante"].dropna() if "m^2 por habitante" in merged.columns else pd.Series([])

    pop_vmin, pop_vmax = (float(pop_vals.min()), float(pop_vals.max())) if len(pop_vals) > 0 else (None, None)
    temp_vmin, temp_vmax = (float(temp_vals.min()), float(temp_vals.max())) if len(temp_vals) > 0 else (None, None)
    med_vmin, med_vmax = (float(med_vals.min()), float(med_vals.max())) if len(med_vals) > 0 else (None, None)
    green_vmin, green_vmax = (float(green_vals.min()), float(green_vals.max())) if len(green_vals) > 0 else (None, None)

    # Gradient CSS builders (match the gradients used earlier)
    pop_gradient = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"]
    temp_gradient = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
    green_gradient = ["#ca2020", "#f48405", "#31a354", "#006837"]

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

    if pop_vmin is not None and show_pop:
        pop_bar = gradient_css(pop_gradient)
        legend_html += f"<div style='position: absolute; bottom: {pos_bottom}px; left: {left_offset}px; z-index:1000; {box_style}'>"
        legend_html += f"<b>Population density</b><div style='width:160px; height:12px; margin-top:6px; background: {pop_bar}; border-radius:4px;'></div>"
        legend_html += f"<div style='display:flex; justify-content:space-between; color: #eee;'><span>{pop_vmin:.1f}</span><span>{pop_vmax:.1f}</span></div></div>"
        pos_bottom += 66

    if temp_vmin is not None and show_temp:
        temp_bar = gradient_css(temp_gradient)
        legend_html += f"<div style='position: absolute; bottom: {pos_bottom}px; left: {left_offset}px; z-index:1000; {box_style}'>"
        legend_html += f"<b>Temperature (Tmax)</b><div style='width:160px; height:12px; margin-top:6px; background: {temp_bar}; border-radius:4px;'></div>"
        legend_html += f"<div style='display:flex; justify-content:space-between; color: #eee;'><span>{temp_vmin:.1f}</span><span>{temp_vmax:.1f}</span></div></div>"
        pos_bottom += 66

    if med_vmin is not None and show_med:
        # simple legend for medical units (marker sizes)
        small = max(3, int(med_vmin) // 2) if med_vmin >= 1 else 3
        large = max(6, int(med_vmax) // 2) if med_vmax >= 1 else 6
        # SVG with white labels
        legend_html += f"<div style='position: absolute; bottom: {pos_bottom}px; left: {left_offset}px; z-index:1000; {box_style}'>"
        legend_html += f"<b>Medical units (Total)</b><div style='margin-top:6px;'>"
        legend_html += f"<svg width='160' height='54'><circle cx='30' cy='18' r='{small}' fill='red' opacity='0.8' /><text x='55' y='22' font-size='12' fill='#fff'>{int(med_vmin)}</text>"
        legend_html += f"<circle cx='110' cy='18' r='{large}' fill='red' opacity='0.8' /><text x='125' y='22' font-size='12' fill='#fff'>{int(med_vmax)}</text></svg></div></div>"
        pos_bottom += 66

    if green_vmin is not None and show_green:
        green_bar = gradient_css(green_gradient)
        legend_html += f"<div style='position: absolute; bottom: {pos_bottom}px; left: {left_offset}px; z-index:1000; {box_style}'>"
        legend_html += f"<b>Green areas (m² per inhabitant)</b><div style='width:160px; height:12px; margin-top:6px; background: {green_bar}; border-radius:4px;'></div>"
        legend_html += f"<div style='display:flex; justify-content:space-between; color: #eee;'><span>{green_vmin:.1f}</span><span>{green_vmax:.1f}</span></div></div>"
        pos_bottom += 66

    if legend_html:
        m.get_root().html.add_child(folium.Element(legend_html))

    # Layer control and display
    folium.LayerControl().add_to(m)
    st_folium(m, width=1000, height=700)

    st.markdown("---")
    st.markdown("Select a municipality from the sidebar to view its data and location. More filters and data can be added easily.")

with tab_pollution:
    st.header("Pollution heatmap by emission type")
    # load pollution data
    aire = pd.read_csv("aire.csv")
    aire["_mun_norm"] = aire["Municipio"].astype(str).apply(normalize)

    # pollutant selector
    pollutants = ["SO_2", "CO", "NOx", "COV", "PM_010", "PM_2_5", "NH_3"]
    pollutant = st.selectbox("Select pollutant", pollutants, index=0)

    # source type filter (Tipo_de_Fuente)
    types = sources
    # default to no selection so user must choose which source types to display
    types_selected = st.multiselect("(source types)", options=types.values(), default=[])

    # If the user deselects all types, show a message and a base map instead of failing silently
    if not types_selected:
        st.warning("No source types selected. Please pick at least one source type to see pollution layers.")
        p_map = folium.Map(location=default_center, zoom_start=default_zoom, tiles="CartoDB positron")
        folium.LayerControl().add_to(p_map)
        st_folium(p_map, width=1000, height=700)
        # skip further processing
    else:
        try:
            # aggregate by municipality and source type
            aire_filtered = aire[aire["Tipo_de_Fuente"].isin(types.keys())].copy()
            aire_filtered[pollutant] = pd.to_numeric(aire_filtered[pollutant], errors="coerce")
            agg = aire_filtered.groupby(["_mun_norm", "Tipo_de_Fuente"])[pollutant].sum().reset_index()

            # join with merged to get geometries
            agg = agg.merge(merged[["_mun_norm", "geometry", "NAME_2_x"]], on="_mun_norm", how="left")

            st.write(f"Aggregated rows: {len(agg)}")

            # create map for pollution
            p_center = default_center
            p_map = folium.Map(location=p_center, zoom_start=default_zoom, tiles="CartoDB positron")

            # for each source type create a heat layer
            any_points = False
            for t in agg["Tipo_de_Fuente"].unique():
                sub = agg[agg["Tipo_de_Fuente"] == t]
                points = []
                for idx, row in sub.iterrows():
                    if pd.isna(row[pollutant]) or row["geometry"] is None:
                        continue
                    try:
                        y = row["geometry"].centroid.y
                        x = row["geometry"].centroid.x
                    except Exception:
                        continue
                    points.append([y, x, float(row[pollutant])])
                st.write(f"Source type '{t}': {len(points)} points")
                if not points:
                    continue
                any_points = True
                fg = folium.FeatureGroup(name=f"{t} ({pollutant})")
                # use a red-oriented gradient for pollution
                pol_grad = {0.2: "#ffffb2", 0.4: "#fecc5c", 0.6: "#fd8d3c", 0.8: "#f03b20", 1.0: "#bd0026"}
                HeatMap(points, radius=18, blur=15, min_opacity=0.4, gradient=pol_grad).add_to(fg)
                fg.add_to(p_map)

            if not any_points:
                st.info("No pollution points available for the selected pollutant/source types.")

            # Add a legend for the pollutant (gradient + min/max + source types)
            poll_vals = agg[pollutant].dropna() if pollutant in agg.columns else pd.Series([])
            if len(poll_vals) > 0:
                pvmin = float(poll_vals.min())
                pvmax = float(poll_vals.max())

                # create gradient CSS (match pol_grad used above)
                def gradient_css_local(colors):
                    stops = []
                    n = len(colors)
                    for i, c in enumerate(colors):
                        pct = int((i / (n - 1)) * 100) if n > 1 else 0
                        stops.append(f"{c} {pct}%")
                    return "linear-gradient(to right, " + ", ".join(stops) + ")"

                pol_colors = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]
                bar_css = gradient_css_local(pol_colors)

                types_html = "".join([f"<li style='color:#ddd;margin:0;padding:0'>{t}</li>" for t in types_selected])
                legend_html = f"""
                <div style='position: absolute; top: 10px; right: 10px; z-index:1000; background: rgba(20,20,20,0.9); color: white; padding:10px; border-radius:6px; font-size:12px; max-width:220px;'>
                  <b>{pollutant}</b>
                  <div style='width:180px; height:12px; margin-top:6px; background: {bar_css}; border-radius:4px;'></div>
                  <div style='display:flex; justify-content:space-between; color:#eee; margin-top:6px;'><span>{pvmin:.1f}</span><span>{pvmax:.1f}</span></div>
                  <div style='margin-top:8px; color:#ddd;'><small>Source types:</small><ul style='margin:4px 0 0 14px;padding:0;'>{types_html}</ul></div>
                </div>
                """
                p_map.get_root().html.add_child(folium.Element(legend_html))

            folium.LayerControl().add_to(p_map)
            st.subheader(f"Pollutant: {pollutant} — source types: {', '.join(types_selected)}")
            st_folium(p_map, width=1000, height=700)
        except Exception as e:
            st.error(f"Failed to build pollution map: {e}")
            # show empty base map so user still sees something
            p_map = folium.Map(location=default_center, zoom_start=default_zoom, tiles="CartoDB positron")
            folium.LayerControl().add_to(p_map)
            st_folium(p_map, width=1000, height=700)

    
with tab_electricity:
    if elec is None:
        st.error(f"Falta `{ELEC.as_posix()}`.")
    else:
        elec = clean_headers(elec)
        # Estándar esperado: Municipio + pct_sin_electricidad
        elec = ensure_municipio_col(elec)
        if "pct_sin_electricidad" not in elec.columns:
            st.error("`pct_sin_electricidad` no está en top10_electricidad.csv")
        elif "Municipio" not in elec.columns:
            st.error("No se encontró columna de municipio (Municipio/NOM_MUN).")
        else:
            st.subheader("Top 10: % Housing without electricity")
            st.dataframe(elec[["Municipio", "pct_sin_electricidad"]])
            ch = lollipop(
                elec,
                "Municipio",
                "pct_sin_electricidad",
                title="Top 10: % without electricity",
                fmt=".2f"
            )
            st.altair_chart(ch, use_container_width=True)

with tab_health:
    if men is None or mas is None:
        st.error(f"Faltan `{SALUD_MIN.as_posix()}` y/o `{SALUD_MAX.as_posix()}`.")
    else:
        men = ensure_municipio_col(men)
        mas = ensure_municipio_col(mas)

        if not {"Municipio", "Total"}.issubset(men.columns) or not {"Municipio", "Total"}.issubset(mas.columns):
            st.error("Las tablas de salud deben tener columnas 'Municipio' y 'Total'.")
        else:
            st.subheader("Top 5: Health Centers")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Bottom 5**")
                st.dataframe(men[["Municipio", "Total"]])
                st.altair_chart(
                    lollipop(men, "Municipio", "Total", "Bottom 5", fmt="d"),
                    use_container_width=True
                )
            with c2:
                st.markdown("**Top 5**")
                st.dataframe(mas[["Municipio", "Total"]])
                st.altair_chart(
                    lollipop(mas, "Municipio", "Total", "Top 5", fmt="d"),
                    use_container_width=True
                )

with tab_housing:
    if min_viv_df is None:
        st.error(f"Falta `{VIV_MIN.as_posix()}`.")
    else:
        d = ensure_municipio_col(min_viv_df)
        if "TVIVHAB" not in d.columns:
            st.error(f"`{VIV_MIN.name}` debe tener 'TVIVHAB'. Columnas: {list(d.columns)}")
        else:
            d = d.rename(columns={"TVIVHAB": "Ocupied_Housing"})
            st.subheader("Top 5: Municipality with less housing")
            st.dataframe(d[["Municipio", "Ocupied_Housing"]])
            ch = lollipop(
                d,
                "Municipio",
                "Ocupied_Housing",
                title="Top 5: Municipalities with less housing",
                fmt="d",
            )
            st.altair_chart(ch, use_container_width=True)

