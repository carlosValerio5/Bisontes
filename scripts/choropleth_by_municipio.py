# ...existing code...
import pathlib
import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import unicodedata

BASE = pathlib.Path(__file__).resolve().parents[1]
# prefer the _by_municipio outputs (these should already include municipio assignments)
POINTS_BY_MUN_GPKG = BASE / "nuevo_leon_points_by_municipio.gpkg"
POINTS_BY_MUN_CSV = BASE / "nuevo_leon_points_by_municipio.csv"
POINTS_GPKG = BASE / "nuevo_leon_points.gpkg"
POINTS_CSV = BASE / "nuevo_leon_points.csv"
MUNICIPIOS_SHP = BASE / "municipios.shp"

OUT_PNG = BASE / "nuevo_leon_municipio_choropleth.png"
OUT_SUMMARY = BASE / "nuevo_leon_points_by_municipio_summary.csv"


def load_points():
    """Load already-classified points (prefer by-municipio outputs).

    Returns a GeoDataFrame which ideally contains either a 'municipio' column
    or an 'index_right' column referencing the municipios index.
    """
    # prefer the by-municipio GeoPackage/CSV if present
    if POINTS_BY_MUN_GPKG.exists():
        try:
            gdf = gpd.read_file(POINTS_BY_MUN_GPKG, layer="nuevo_leon_points_by_municipio")
        except Exception:
            # fallback to reading any layer
            gdf = gpd.read_file(POINTS_BY_MUN_GPKG)
        return gdf

    if POINTS_BY_MUN_CSV.exists():
        df = pd.read_csv(POINTS_BY_MUN_CSV)
        # This CSV is expected to be per-municipio summary: name_2 + density
        return df

    # fallback to original raw points (not recommended)
    if POINTS_GPKG.exists():
        pts = gpd.read_file(POINTS_GPKG, layer="nuevo_leon_points")
        return pts
    if POINTS_CSV.exists():
        df = pd.read_csv(POINTS_CSV)
        if not {"longitude", "latitude"}.issubset(df.columns):
            raise RuntimeError("CSV must contain 'longitude' and 'latitude' columns")
        pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs="EPSG:4326")
        return pts

    raise FileNotFoundError("No input points found: expected nuevo_leon_points_by_municipio.* or raw points files")


def detect_name_col(gdf):
    candidates = ["NAME_2", "NAME_1", "NAME", "NOM_MUN", "MUNICIPIO", "NOMBRE", "NOM_ENT", "MUN_NAME"]
    cols = list(gdf.columns)
    for cand in candidates:
        for c in cols:
            if c.upper() == cand:
                return c
    # fallback: first string-like non-geometry column
    for c in cols:
        if c.lower() in ("geometry", "geom"):
            continue
        if gdf[c].dtype == object:
            return c
    return None


def normalize_name(s: str) -> str:
    if pd.isna(s):
        return ""
    s = str(s)
    s = s.strip().lower()
    # remove accents
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = " ".join(s.split())
    return s


def main():
    print("Loading municipios polygon...")
    if not MUNICIPIOS_SHP.exists():
        raise FileNotFoundError(f"Municipios shapefile not found at {MUNICIPIOS_SHP}")
    mun = gpd.read_file(MUNICIPIOS_SHP)
    if mun.crs and mun.crs.to_string() != "EPSG:4326":
        mun = mun.to_crs(epsg=4326)

    name_col = detect_name_col(mun)
    print("Municipality name column detected:", name_col)

    print("Loading points...")
    pts = load_points()
    # If points is a GeoDataFrame with geometry, it's unexpected here; prefer the by-municipio CSV.
    # If we received a DataFrame (from the by-municipio CSV), use it directly as values.
    if isinstance(pts, gpd.GeoDataFrame):
        # if GeoDataFrame was returned, try to extract municipio and density columns
        pts_df = pts.copy()
    else:
        pts_df = pts.copy()

    print("Using by-municipio data from CSV/GPKG and merging into municipio polygons")

    # detect municipio name column in pts_df (case-insensitive)
    mun_name_col = "NAME_2"

    # detect density column in pts_df
    density_col = "mean_population_density"

    print(f"Detected municipio column in CSV: {mun_name_col}; density column: {density_col}")

    # build agg DataFrame: municipio -> density value (use CSV values directly)
    agg = pts_df[[mun_name_col, density_col]].copy()
    agg = agg.rename(columns={mun_name_col: "municipio", density_col: "density"})

    # normalize municipio names on both sides for safe merge
    mun2 = mun.copy()
    mun2["_mun_norm"] = mun2[name_col].astype(str).apply(normalize_name)
    agg["_mun_norm"] = agg["municipio"].astype(str).apply(normalize_name)

    merged = mun2.merge(agg, left_on="_mun_norm", right_on="_mun_norm", how="left")

    # compute area in km2 after projecting to a metric CRS
    merged_metric = merged.to_crs(epsg=3857)
    merged["area_km2"] = merged_metric.geometry.area / 1e6

    # compute density per km2 if sum_population_density present
    # If the by-municipio CSV provided a 'density' column, treat it as pop_per_km2 directly.
    if "density" in merged.columns:
        merged["pop_per_km2"] = pd.to_numeric(merged["density"], errors="coerce")
    elif "sum_population_density" in merged.columns:
        merged["pop_per_km2"] = merged["sum_population_density"] / merged["area_km2"].replace({0: np.nan})

    # choose column to plot
    plot_col = None
    if "pop_per_km2" in merged.columns:
        plot_col = "pop_per_km2"
        legend_label = "Population density (sum per km²)"
    elif "mean_population_density" in merged.columns:
        plot_col = "mean_population_density"
        legend_label = "Mean population density (per point)"
    elif "point_count" in merged.columns:
        plot_col = "point_count"
        legend_label = "Point count"
    else:
        raise RuntimeError("No suitable column to plot after aggregation")

    # plot choropleth
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    merged.plot(column=plot_col, ax=ax, cmap="viridis", legend=True, missing_kwds={"color": "lightgrey"})
    mun_bound = merged.boundary
    mun_bound.plot(ax=ax, color="black", linewidth=0.5)
    ax.set_title("Nuevo León - " + legend_label)
    ax.set_axis_off()
    plt.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    print(f"Saved choropleth to {OUT_PNG}")


if __name__ == "__main__":
    main()
# ...existing code...