
import streamlit as st
import pandas as pd
from utils import (
    prepare_dataframe, items_display_list, filter_by_empresa_items_month,
    build_daily_table_all, month_floor
)

st.set_page_config(page_title="Ventas x Ítem — Tabla única (todas las empresas)", layout="wide")

st.title("📊 Ventas por Ítem(s) x Sedes — **Tabla única** (todas las empresas)")
st.caption("Una sola tabla con **Fecha** (d/abr) + todas las sedes; **T. Dia** y **Acum. Mes**. Estilos: encabezados en negrilla, fila de totales resaltada y domingos en rojo.")

with st.expander("Formato esperado del CSV", expanded=False):
    st.markdown("`empresa, fecha_dcto, id_co, id_item, descripcion, linea, und_dia, venta_sin_impuesto_dia, und_acum, venta_sin_impuesto_acum`")

uploaded = st.file_uploader("📥 Cargar CSV", type=["csv"])

if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

try:
    raw = pd.read_csv(uploaded)
except Exception as e:
    st.error(f"No se pudo leer el CSV: {e}")
    st.stop()

try:
    df = prepare_dataframe(raw)
except Exception as e:
    st.error(f"Error de formato: {e}")
    st.stop()

# Mes por defecto: mes de la fecha máxima
if df["fecha"].notna().any():
    default_month = month_floor(df["fecha"].max())
else:
    st.error("No hay fechas válidas en el archivo.")
    st.stop()

c1, c2 = st.columns([2, 1])
with c1:
    month_sel = st.date_input("Mes (YYYY-MM-DD)", value=default_month, format="YYYY-MM-DD")
with c2:
    limit = st.number_input("Límite de ítems", min_value=1, max_value=50, value=10, step=1)

items_all = items_display_list(df)
items_sel = st.multiselect("Ítems (por ID o descripción)", items_all, max_selections=limit)
if not items_sel:
    st.info("Selecciona al menos un ítem.")
    st.stop()

# Filtrar por mes + ítems (todas las empresas)
month_ts = pd.to_datetime(month_sel)
dfs = []
for emp in df["empresa_norm"].unique():
    dfe = filter_by_empresa_items_month(df, emp, items_sel, month_ts)
    if not dfe.empty:
        dfs.append(dfe)
df_f = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=df.columns)

tabla = build_daily_table_all(df_f)

st.subheader("Tabla diaria consolidada (unidades)")

if tabla.empty:
    st.warning("No se encontraron registros para los filtros aplicados.")
else:
    # === Estilos ===
    def style_headers(df_styler):
        return df_styler.set_table_styles([
            {'selector': 'th', 'props': [('font-weight', 'bold')]}
        ])

    def style_totals(row):
        is_total = row.name == len(tabla) - 1  # última fila
        return ['font-weight: bold; background-color: #e6f2ff' if is_total else '' for _ in row]

    def style_sundays(row):
        is_sunday = isinstance(row['Fecha'], str) and ('/dom' in row['Fecha'])
        if row.name == len(tabla) - 1:
            return ['' for _ in row]
        return ['color: red; font-weight: bold' if is_sunday else '' for _ in row]

    sty = tabla.style.apply(style_totals, axis=1).apply(style_sundays, axis=1)
    sty = sty.set_properties(subset=['T. Dia'], **{'font-weight': 'bold'})
    sty = style_headers(sty)

    st.dataframe(sty, use_container_width=True)
    st.download_button(
        "⬇️ Descargar CSV de la tabla",
        data=tabla.to_csv(index=False).encode("utf-8"),
        file_name="tabla_diaria_items_sedes_TODAS.csv",
        mime="text/csv"
    )
