import pandas as pd
import unidecode
import altair as alt  # (not used here, but you had it)
import re
from pathlib import Path
import unicodedata

# -----------------------------
# Paths
# -----------------------------
ITER_PATH = "ITER2020 - 19 Nuevo León.csv"          
UNITS_PATH = "unidades_medicas_totales.csv"          
SUMM_PATH  = "resumen_municipios_inegi_nl.csv"      
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------
# Helpers
# -----------------------------
def clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Strip BOM/NBSP and spaces from headers."""
    df = df.rename(columns=lambda c: str(c).replace("\ufeff", "").replace("\xa0", " ").strip())
    return df

def fix_mojibake(s: str) -> str:
    """Fix common UTF-8 read as latin-1 mojibake."""
    if pd.isna(s):
        return ""
    s = str(s)
    try:
        return s.encode("latin-1").decode("utf-8")
    except Exception:
        return s

def normalize_basic(s: str) -> str:
    """Light text cleanup preserving accents (for display)."""
    s = fix_mojibake(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip(" .,_-")
    s = re.sub(r"\(.*?\)", "", s).strip()
    return s

def muni_key(s: str) -> str:
    """Canonical merge key for municipios (remove accents/case/spacing)."""
    s = normalize_basic(s)
    s = unidecode.unidecode(s)          
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper()

def to_int_safe(series: pd.Series) -> pd.Series:
    """Keep only digits, parse to Int64 (nullable)."""
    cleaned = (
        series.astype(str)
              .str.replace(r"[^0-9]", "", regex=True)
              .replace("", pd.NA)
    )
    return pd.to_numeric(cleaned, errors="coerce").astype("Int64")

# -----------------------------
# 1) Build municipality summary from ITER (TVIVHAB, VPH_S_ELEC, etc.)
# -----------------------------
cols_interes = [
    "TVIVHAB", "TVIVPAR", "VIVPAR_DES",
    "VPH_C_ELEC", "VPH_S_ELEC",
    "VPH_AGUADV", "VPH_AEASP", "VPH_AGUAFV",
    "VPH_DRENAJ", "VPH_NODREN", "VPH_C_SERV"
]

iter_df = pd.read_csv(ITER_PATH, encoding="utf-8")
iter_df = clean_headers(iter_df)

# Ensure municipality name exists
if "NOM_MUN" not in iter_df.columns:
    raise KeyError(f"'NOM_MUN' not found in {ITER_PATH}. Got: {list(iter_df.columns)}")

# Clean names for display and a key for joins
iter_df["NOM_MUN"] = iter_df["NOM_MUN"].apply(normalize_basic)
iter_df["MUNI_KEY"] = iter_df["NOM_MUN"].apply(muni_key)

# Coerce numeric indicator columns
for col in cols_interes:
    if col in iter_df.columns:
        iter_df[col] = to_int_safe(iter_df[col])
    else:
        # If some column is missing, create it as 0 to avoid KeyError in sum
        iter_df[col] = pd.Series([0] * len(iter_df), dtype="Int64")

# Group to municipality level
mun_summary = (
    iter_df.groupby("MUNI_KEY", as_index=False)[cols_interes].sum(min_count=1)
)

# Keep a representative display name (first occurrence)
name_map = (
    iter_df.groupby("MUNI_KEY", as_index=False)
           .agg(NOM_MUN=("NOM_MUN", "first"))
)

mun_summary = name_map.merge(mun_summary, on="MUNI_KEY", how="left")

# Compute % without electricity
mun_summary["pct_sin_electricidad"] = (
    (mun_summary["VPH_S_ELEC"].astype("float") / mun_summary["TVIVHAB"].astype("float")) * 100
).round(2)

# Exports based on municipality-only stats (optional)
top5_menos_viv = (
    mun_summary.dropna(subset=["TVIVHAB"])
               .sort_values("TVIVHAB", ascending=True)
               .head(5)
               .reset_index(drop=True)
               .rename(columns={"NOM_MUN": "Municipio"})
)
top10_pct = (
    mun_summary.sort_values("pct_sin_electricidad", ascending=False)
               .head(10)
               .reset_index(drop=True)
               .rename(columns={"NOM_MUN": "Municipio"})
)

# Save CSVs used elsewhere in our app
top5_menos_viv[["Municipio", "TVIVHAB"]].to_csv(DATA_DIR / "menos_viv.csv", index=False)
top10_pct[["Municipio", "pct_sin_electricidad"]].to_csv(DATA_DIR / "top10_electricidad.csv", index=False)

# -----------------------------
# 2) Read medical-units file and merge TVIVHAB into it
# -----------------------------
df = pd.read_csv(UNITS_PATH, encoding="utf-8")
df = clean_headers(df)

# Normalize expected columns
# Try to find Municipio/Total columns even if they came with slightly different headers
col_ren = {}
for c in df.columns:
    cu = c.upper()
    if cu in {"MUNICIPIO", "NOM_MUN"}:   col_ren[c] = "Municipio"
    if cu in {"TOTAL", "TOTAL_UNIDADES", "CENTROS", "UNIDADES"}: col_ren[c] = "Total"
df = df.rename(columns=col_ren)

missing = {"Municipio", "Total"} - set(df.columns)
if missing:
    raise KeyError(f"{UNITS_PATH} is missing columns: {missing}. Got: {list(df.columns)}")

# Clean text & numbers
df["Municipio"] = (df["Municipio"]
                   .apply(fix_mojibake)
                   .apply(normalize_basic))
df["MUNI_KEY"] = df["Municipio"].apply(muni_key)
df["Total"] = to_int_safe(df["Total"])

# Aggregate by municipality (sum total units) and keep a display name
df_units = (
    df.groupby("MUNI_KEY", as_index=False)
      .agg(Municipio=("Municipio", "first"), Total=("Total", "sum"))
)

# Bring TVIVHAB from municipality summary (already computed from ITER)
df_units = df_units.merge(
    mun_summary[["MUNI_KEY", "TVIVHAB"]],
    on="MUNI_KEY",
    how="left"
)

# -----------------------------
# 3) Build top-5 CSVs for medical units
# -----------------------------
top5_menos_units = (
    df_units.sort_values("Total", ascending=True)
            .head(5)
            .reset_index(drop=True)
)
top5_mas_units = (
    df_units.sort_values("Total", ascending=False)
            .head(5)
            .reset_index(drop=True)
)

print("Top 5 municipios con menos centros de salud:")
print(top5_menos_units[["Municipio", "Total", "TVIVHAB"]])

print("Top 5 municipios con más centros de salud:")
print(top5_mas_units[["Municipio", "Total", "TVIVHAB"]])

top5_menos_units[["Municipio", "Total", "TVIVHAB"]].to_csv(DATA_DIR / "salud_menores.csv", index=False)
top5_mas_units[["Municipio", "Total", "TVIVHAB"]].to_csv(DATA_DIR / "salud_mayores.csv", index=False)

# (Optional) also export the merged full table
df_units[["Municipio", "Total", "TVIVHAB"]].to_csv(DATA_DIR / "salud_con_tvivhab.csv", index=False)
