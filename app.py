
import streamlit as st
import pandas as pd
from utils import (
    prepare_dataframe, items_display_list, filter_by_empresa_items_month,
    build_daily_table, month_floor
)

st.set_page_config(page_title="Ventas por Ítem x Sedes (Diario)", layout="wide")

st.title("📊 Ventas por Ítem(s) x Sedes — Diario (Multi-empresa)")
st.caption("Carga tu CSV, elige **mes** y **ítems**; se muestran tablas **responsivas** por empresa (Mercamio, Mercatodo, Bogotá) con T. Dia y fila **Acum. Mes**.")

with st.expander("Formato esperado del CSV (separado por comas)", expanded=False):
    st.markdown("""
    Columnas requeridas:
    `empresa, fecha_dcto, id_co, id_item, descripcion, linea, und_dia, venta_sin_impuesto_dia, und_acum, venta_sin_impuesto_acum`
    """)

uploaded = st.file_uploader("📥 Cargar CSV", type=["csv"])

if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

# Lectura CSV
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

# Lista de empresas presentes
empresas_presentes = (
    df["empresa"].dropna().str.lower().map(lambda s: s.strip()).unique().tolist()
)

# Determinar mes por defecto usando max fecha global
if df["fecha"].notna().any():
    default_month = month_floor(df["fecha"].max())
else:
    st.error("No hay fechas válidas en el archivo.")
    st.stop()

c1, c2 = st.columns([2, 1])
with c1:
    month_sel = st.date_input("Mes", value=default_month, format="YYYY-MM-DD")
with c2:
    limit = st.number_input("Límite de ítems", min_value=1, max_value=50, value=10, step=1)

# Items globales (todos los de todas las empresas para facilitar)
all_items = items_display_list(df)
items_sel = st.multiselect("Ítems (por ID o descripción)", all_items, max_selections=limit)

if not items_sel:
    st.info("Selecciona al menos un ítem para continuar.")
    st.stop()

# Tabs por empresa para ver TODAS
tabs = st.tabs([e.capitalize() for e in empresas_presentes])

tables_to_download = {}

for tab, emp in zip(tabs, empresas_presentes):
    with tab:
        df_f = filter_by_empresa_items_month(df, emp, items_sel, pd.to_datetime(month_sel))
        tabla = build_daily_table(df_f, emp)
        st.subheader(emp.capitalize())
        if tabla.empty:
            st.warning("Sin datos para este filtro.")
        else:
            st.dataframe(tabla, use_container_width=True)
            csv_bytes = tabla.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"⬇️ Descargar CSV — {emp.capitalize()}",
                data=csv_bytes,
                file_name=f"tabla_diaria_items_sedes_{emp}.csv",
                mime="text/csv",
                key=f"dl_{emp}"
            )
            tables_to_download[emp] = csv_bytes

# Opción: descargar todas las tablas en un ZIP si hay más de una
if len(tables_to_download) > 1:
    import io, zipfile
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
        for emp, data in tables_to_download.items():
            z.writestr(f"tabla_diaria_items_sedes_{emp}.csv", data)
    st.download_button(
        "⬇️ Descargar TODAS las tablas (ZIP)",
        data=zip_buf.getvalue(),
        file_name="tablas_diarias_por_empresa.zip",
        mime="application/zip"
    )
