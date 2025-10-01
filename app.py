
import streamlit as st
import pandas as pd
import numpy as np

# ===================== UTILIDADES (embebidas) =====================
SEDE_MAP = {
    "mercamio": {"001": "La 5", "002": "La 39", "003": "Plaza", "004": "Jardin", "005": "C.sur", "006": "Palmira"},
    "mercatodo": {"001": "FTA", "002": "FLA", "003": "MN"},
    "bogota": {"001": "La 80", "002": "Chia"},
}
PREFERRED_ORDER = {
    "mercamio": ["La 5", "La 39", "Plaza", "Jardin", "C.sur", "Palmira"],
    "mercatodo": ["FTA", "FLA", "MN"],
    "bogota": ["La 80", "Chia"],
}
DOW_ABBR_ES = {0: "lun", 1: "mar", 2: "mié", 3: "jue", 4: "vie", 5: "sáb", 6: "dom"}

def normalize_empresa(x: str) -> str:
    return (x or "").strip().lower()

def normalize_id_co(x) -> str:
    try:
        xi = int(str(x).strip())
        return f"{xi:03d}"
    except Exception:
        s = str(x).strip()
        if len(s) >= 3 and s[:3].isdigit():
            return s[:3]
        if s.isdigit():
            return s.zfill(3)
        return s

def map_sede(empresa: str, id_co: str) -> str:
    emp = normalize_empresa(empresa)
    idn = normalize_id_co(id_co)
    mapping = SEDE_MAP.get(emp, {})
    return mapping.get(idn, idn)

def parse_fecha(fecha_series: pd.Series) -> pd.Series:
    s = fecha_series.astype(str).str.replace(r"\.0$", "", regex=True).str.replace("-", "", regex=False)
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")

def prepare_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    required_cols = ["empresa","fecha_dcto","id_co","id_item","descripcion","linea","und_dia",
                     "venta_sin_impuesto_dia","und_acum","venta_sin_impuesto_acum"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en el CSV: {missing}")
    df["empresa_norm"] = df["empresa"].apply(normalize_empresa)
    df["id_co_norm"] = df["id_co"].apply(normalize_id_co)
    df["sede"] = [map_sede(e, i) for e, i in zip(df["empresa"], df["id_co"])]
    df["fecha"] = parse_fecha(df["fecha_dcto"])
    for c in ["und_dia", "und_acum", "venta_sin_impuesto_dia", "venta_sin_impuesto_acum"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["descripcion"] = df["descripcion"].astype(str).str.strip()
    return df

def items_display_list(df: pd.DataFrame):
    ix = (df["id_item"].astype(str) + " - " + df["descripcion"].astype(str)).dropna().unique().tolist()
    ix.sort()
    return ix

def build_daily_table_all(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, footer_label="Acum. Rango:") -> pd.DataFrame:
    if df.empty:
        days = pd.date_range(start=start, end=end, freq="D")
        base = pd.DataFrame({"Fecha": [f\"{d.day}/{DOW_ABBR_ES.get(d.dayofweek,'')}\" for d in days]})
        base["T. Dia"] = 0
        base = pd.concat([base, pd.DataFrame([{"Fecha": footer_label, "T. Dia": 0}])], ignore_index=True)
        return base

    all_days = pd.date_range(start=start, end=end, freq="D")
    pt = pd.pivot_table(df, index="fecha", columns="sede", values="und_dia", aggfunc="sum", fill_value=0.0)
    pt = pt.reindex(all_days, fill_value=0.0).sort_index()

    preferred_all = []
    for emp in ["mercamio", "mercatodo", "bogota"]:
        preferred_all += [c for c in PREFERRED_ORDER.get(emp, []) if c in pt.columns]
    preferred_all += [c for c in pt.columns if c not in preferred_all]
    pt = pt.reindex(columns=preferred_all)

    pt["T. Dia"] = pt.sum(axis=1)
    fechas_fmt = [f\"{i.day}/{DOW_ABBR_ES.get(i.dayofweek, '')}\" for i in pt.index]
    pt.insert(0, "Fecha", fechas_fmt)

    acum = pt.drop(columns=["Fecha"]).sum(axis=0)
    final = pd.concat([pt.reset_index(drop=True),
                       pd.DataFrame([[footer_label] + list(acum.values)], columns=["Fecha"] + list(acum.index))],
                      ignore_index=True)

    def _fmt_number(x):
        if pd.isna(x): return 0
        if abs(x - int(x)) < 1e-9: return int(x)
        return round(x, 1)
    for c in [c for c in final.columns if c != "Fecha"]:
        final[c] = final[c].astype(float).map(_fmt_number)
    return final

# ===================== APP =====================
st.set_page_config(page_title="Ventas x Ítem — Tabla única (todas las empresas)", layout="wide")
st.title("📊 Ventas por Ítem(s) x Sedes — **Tabla única** (todas las empresas)")
st.caption("Rango de fechas, todas las sedes, T. Dia y Acum. Rango. Encabezados en negrilla, totales resaltados y domingos en rojo.")

with st.expander("Formato esperado del CSV", expanded=False):
    st.markdown("`empresa, fecha_dcto, id_co, id_item, descripcion, linea, und_dia, venta_sin_impuesto_dia, und_acum, venta_sin_impuesto_acum`")

uploaded = st.file_uploader("📥 Cargar CSV", type=["csv"])
if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

try:
    raw = pd.read_csv(uploaded)
    df = prepare_dataframe(raw)
except Exception as e:
    st.error(f"No se pudo procesar el CSV: {e}")
    st.stop()

if df["fecha"].notna().any():
    min_d = df["fecha"].min().date()
    max_d = df["fecha"].max().date()
else:
    st.error("No hay fechas válidas en el archivo.")
    st.stop()

c1, c2, c3 = st.columns([2,1,1])
with c1:
    date_range = st.date_input("Rango de fechas (YYYY-MM-DD)", value=(min_d, max_d), format="YYYY-MM-DD")
with c2:
    limit = st.number_input("Límite de ítems", min_value=1, max_value=50, value=10, step=1)
with c3:
    footer_label = st.text_input("Etiqueta de total", value="Acum. Rango:")

items_all = items_display_list(df)
items_sel = st.multiselect("Ítems (por ID o descripción)", items_all, max_selections=limit)
if not items_sel:
    st.info("Selecciona al menos un ítem.")
    st.stop()

start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

# Filtrado por rango e ítems para todas las empresas (en un solo DataFrame)
mask = (df["fecha"] >= start) & (df["fecha"] <= end)
df_f = df.loc[mask].copy()

ids = set()
descr_needles = []
for it in items_sel:
    s = str(it)
    if " - " in s:
        ids.add(s.split(" - ", 1)[0])
    elif s.isdigit() or s.strip().isdigit():
        ids.add(s.strip())
    else:
        descr_needles.append(s.lower().strip())

ok = pd.Series(False, index=df_f.index)
if ids:
    ok = ok | df_f["id_item"].astype(str).isin(ids)
if descr_needles:
    pat = "|".join([pd.re.escape(t) for t in descr_needles])
    ok = ok | df_f["descripcion"].str.lower().str.contains(pat, na=False)
df_f = df_f[ok]

tabla = build_daily_table_all(df_f, start, end, footer_label=footer_label)

st.subheader("Tabla diaria consolidada (unidades)")
if tabla.empty:
    st.warning("No se encontraron registros para los filtros aplicados.")
else:
    def style_headers(df_styler):
        return df_styler.set_table_styles([{'selector': 'th', 'props': [('font-weight', 'bold')]}])
    def style_totals(row):
        is_total = row.name == len(tabla) - 1
        return ['font-weight: bold; background-color: #e6f2ff' if is_total else '' for _ in row]
    def style_sundays(row):
        is_sunday = isinstance(row['Fecha'], str) and ('/dom' in row['Fecha'])
        if row.name == len(tabla) - 1:
            return ['' for _ in row]
        return ['color: red; font-weight: bold' if is_sunday else '' for _ in row]

    sty = tabla.style.apply(style_totals, axis=1).apply(style_sundays, axis=1)
    if "T. Dia" in tabla.columns:
        sty = sty.set_properties(subset=['T. Dia'], **{'font-weight': 'bold'})
    sty = style_headers(sty)

    st.dataframe(sty, use_container_width=True)
    st.download_button("⬇️ Descargar CSV", data=tabla.to_csv(index=False).encode("utf-8"),
                       file_name="tabla_diaria_items_sedes_TODAS.csv", mime="text/csv")
