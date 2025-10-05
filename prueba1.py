from pathlib import Path
import pandas as pd
import streamlit as st
import altair as alt

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
# Helpers
# -----------------------------
def clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns=lambda c: str(c).replace("\ufeff", "").replace("\xa0", " ").strip())

def ensure_municipio_col(df: pd.DataFrame) -> pd.DataFrame:
    """Asegura una columna 'Municipio' a partir de posibles variantes."""
    df = clean_headers(df)
    if "Municipio" in df.columns:
        return df
    for cand in ["NOM_MUN", "MUNICIPIO", "municipio", "nom_mun"]:
        if cand in df.columns:
            return df.rename(columns={cand: "Municipio"})
    return df  # si no se encuentra, lo dejamos y fallará más adelante con un mensaje claro

def lollipop(df, cat_col, val_col, title="", fmt=None):
    d = df.copy().sort_values(val_col)
    d["cero"] = 0
    base = alt.Chart(d).properties(height=max(240, 28*len(d)), title=title)
    rule = base.mark_rule(strokeWidth=3, opacity=.45).encode(
        y=alt.Y(f"{cat_col}:N", sort=d[cat_col].tolist(), title=""),
        x="cero:Q", x2=alt.X2(f"{val_col}:Q")
    )
    pts = base.mark_circle(size=120).encode(
        y=f"{cat_col}:N",
        x=alt.X(f"{val_col}:Q", title=val_col),
        tooltip=[cat_col, alt.Tooltip(val_col, format=fmt) if fmt else val_col]
    )
    labels = base.mark_text(align="left", dx=6, fontSize=12).encode(
        y=f"{cat_col}:N",
        x=alt.X(f"{val_col}:Q"),
        text=alt.Text(f"{val_col}:Q", format=fmt) if fmt else f"{val_col}:Q"
    )
    return (rule + pts + labels).configure_axis(grid=False)

def read_csv_safe(path: Path):
    return pd.read_csv(path) if path.exists() else None

# -----------------------------
# Load data
# -----------------------------
elec        = read_csv_safe(ELEC)
men         = read_csv_safe(SALUD_MIN)
mas         = read_csv_safe(SALUD_MAX)
elec_muni   = read_csv_safe(ELEC_MUNI)
min_viv_df  = read_csv_safe(VIV_MIN)

# -----------------------------
# Tabs
# -----------------------------
t1, t2, t3 = st.tabs(["⚡ Electricidad", "🏥 Salud", "🏡 Viviendas"])

# ---------------------------------
# Tab 1: Electricidad (Top 10 % sin)
# ---------------------------------
with t1:
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
            st.subheader("Top 10: % de viviendas sin electricidad")
            st.dataframe(elec[["Municipio", "pct_sin_electricidad"]])
            ch = lollipop(
                elec,
                "Municipio",
                "pct_sin_electricidad",
                title="Top 10: % sin electricidad",
                fmt=".2f"
            )
            st.altair_chart(ch, use_container_width=True)

# --------------------
# Tab 2: Salud (Top 5)
# --------------------
with t2:
    if men is None or mas is None:
        st.error(f"Faltan `{SALUD_MIN.as_posix()}` y/o `{SALUD_MAX.as_posix()}`.")
    else:
        men = ensure_municipio_col(men)
        mas = ensure_municipio_col(mas)

        if not {"Municipio", "Total"}.issubset(men.columns) or not {"Municipio", "Total"}.issubset(mas.columns):
            st.error("Las tablas de salud deben tener columnas 'Municipio' y 'Total'.")
        else:
            st.subheader("Top 5: centros de salud (menos y más)")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Menores 5**")
                st.dataframe(men[["Municipio", "Total"]])
                st.altair_chart(
                    lollipop(men, "Municipio", "Total", "Menores 5", fmt="d"),
                    use_container_width=True
                )
            with c2:
                st.markdown("**Mayores 5**")
                st.dataframe(mas[["Municipio", "Total"]])
                st.altair_chart(
                    lollipop(mas, "Municipio", "Total", "Mayores 5", fmt="d"),
                    use_container_width=True
                )


# ---------------------------------
# Tab 3: Viviendas (Top 5 con menos)
# ---------------------------------
with t3:
    if min_viv_df is None:
        st.error(f"Falta `{VIV_MIN.as_posix()}`.")
    else:
        d = ensure_municipio_col(min_viv_df)
        # En el pipeline nuevo: columnas esperadas -> Municipio, TVIVHAB
        if "TVIVHAB" not in d.columns:
            st.error(f"`{VIV_MIN.name}` debe tener 'TVIVHAB'. Columnas: {list(d.columns)}")
        else:
            d = d.rename(columns={"TVIVHAB": "Viviendas_habitadas"})
            st.subheader("Top 5: Municipios con menos viviendas")
            st.dataframe(d[["Municipio", "Viviendas_habitadas"]])
            ch = lollipop(
                d,
                "Municipio",
                "Viviendas_habitadas",
                title="Top 5: Municipios con menos viviendas",
                fmt="d",
            )
            st.altair_chart(ch, use_container_width=True)

