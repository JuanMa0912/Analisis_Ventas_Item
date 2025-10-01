
import os, sys
import streamlit as st
import pandas as pd

# Asegura import relativo utils.py (misma carpeta)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from utils import (
    prepare_dataframe, items_display_list, build_daily_table_all_range
)

st.set_page_config(page_title="Ventas x Ítem — Tabla única (todas las empresas)", layout="wide")
st.title("📊 Ventas por Ítem(s) x Sedes — **Tabla única** (todas las empresas)")
st.caption("Rango de fechas, todas las sedes, **T. Dia** y **Acum. Rango**. Encabezados en negrilla, totales resaltados y domingos en rojo.")

with st.expander("Formato esperado del CSV", expanded=False):
    st.markdown("`empresa, fecha_dcto, id_co, id_item, descripcion, linea, und_dia, venta_sin_impuesto_dia, und_acum, venta_sin_impuesto_acum`")

uploaded = st.file_uploader("📥 Cargar CSV", type=["csv"])
if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

# Cargar y preparar
try:
    raw = pd.read_csv(uploaded)
    df = prepare_dataframe(raw)
except Exception as e:
    st.error(f"No se pudo procesar el CSV: {e}")
    st.stop()

# Rango por defecto (min..max) según datos válidos
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
    limit = st.number_input("Límite de ítems", min_value=1, max_value=10, value=10, step=1)
with c3:
    footer_label = st.text_input("Etiqueta de total", value="Acum. Rango:")

# Items
items_all = items_display_list(df)
items_sel = st.multiselect("Ítems (por ID o descripción)", items_all, max_selections=limit)
if not items_sel:
    st.info("Selecciona al menos un ítem.")
    st.stop()

start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

# Filtrado por rango
mask = (df["fecha"] >= start) & (df["fecha"] <= end)
df_f = df.loc[mask].copy()

# Filtrado por ítems (acepta id o texto de descripción)
ids = set()
descr_needles = []
for it in items_sel:
    s = str(it)
    if " - " in s:
        ids.add(s.split(" - ", 1)[0].strip())
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

tabla = build_daily_table_all_range(df_f, start, end, footer_label=footer_label)

st.subheader("Tabla diaria consolidada (unidades)")
if tabla.empty:
    st.warning("No se encontraron registros para los filtros aplicados.")
else:
    # Estilos: encabezados en negrilla, T. Dia en negrilla, totales con fondo, domingos en rojo
    def style_headers(df_styler):
        return df_styler.set_table_styles([{'selector': 'th', 'props': [('font-weight', 'bold')]}])

    def style_totals(row):
        is_total = row.name == len(tabla) - 1
        return ['font-weight: bold; background-color: #e6f2ff' if is_total else '' for _ in row]

    def style_sundays(row):
        # Se identifica domingo por '/dom' en la Fecha (ej. 7/dom)
        is_sunday = isinstance(row['Fecha'], str) and ('/dom' in row['Fecha'])
        if row.name == len(tabla) - 1:
            return ['' for _ in row]
        return ['color: red; font-weight: bold' if is_sunday else '' for _ in row]

    sty = tabla.style.apply(style_totals, axis=1).apply(style_sundays, axis=1)
    if "T. Dia" in tabla.columns:
        sty = sty.set_properties(subset=['T. Dia'], **{'font-weight': 'bold'})
    sty = style_headers(sty)

    st.dataframe(sty, use_container_width=True)
    st.download_button(
        "⬇️ Descargar CSV",
        data=tabla.to_csv(index=False).encode("utf-8"),
        file_name="tabla_diaria_items_sedes_TODAS.csv",
        mime="text/csv"
    )
