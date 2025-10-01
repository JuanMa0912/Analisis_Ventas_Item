
import streamlit as st
import pandas as pd
from utils import prepare_dataframe, items_display_list, filter_by_empresa_items_month, build_daily_table, month_floor

st.set_page_config(page_title="Ventas por Ítem x Sedes (Diario)", layout="wide")

st.title("📊 Ventas por Ítem(s) x Sedes — Diario")
st.caption("Carga tu CSV, elige la **empresa**, selecciona hasta N ítems y obtén la tabla diaria con totales y fila de **Acum. Mes**.")

with st.expander("Formato esperado del CSV (separado por comas)", expanded=False):
    st.markdown("""
    Debe contener al menos estas columnas (exactamente con estos nombres):
    - `empresa`
    - `fecha_dcto` (ej. 20250901)
    - `id_co`
    - `id_item`
    - `descripcion`
    - `linea`
    - `und_dia`
    - `venta_sin_impuesto_dia`
    - `und_acum`
    - `venta_sin_impuesto_acum`
    """)

uploaded = st.file_uploader("📥 Cargar CSV", type=["csv"])

if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

# Read CSV
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

empresas = sorted(df["empresa"].dropna().unique().tolist())
emp_sel = st.selectbox("Empresa", empresas, index=0)

# Mes selector basado en datos
min_date = df.loc[df["empresa"].str.lower() == emp_sel.lower(), "fecha"].min()
max_date = df.loc[df["empresa"].str.lower() == emp_sel.lower(), "fecha"].max()
if pd.isna(min_date):
    st.warning("No hay fechas válidas para esta empresa en el archivo.")
    st.stop()

default_month = month_floor(max_date)
month_sel = st.date_input("Mes", value=default_month, format="YYYY-MM-DD")

# Items multiselect (up to limit)
all_items = items_display_list(df[df["empresa"].str.lower() == emp_sel.lower()])
limit = st.number_input("Límite de ítems a seleccionar", min_value=1, max_value=50, value=10, step=1)
items_sel = st.multiselect("Ítems (por ID o descripción)", all_items, max_selections=limit)

if not items_sel:
    st.info("Selecciona al menos un ítem para continuar.")
    st.stop()

# Filter and build table
df_f = filter_by_empresa_items_month(df, emp_sel, items_sel, pd.to_datetime(month_sel))
tabla = build_daily_table(df_f, emp_sel)

if tabla.empty:
    st.warning("No se encontraron registros para los filtros aplicados.")
    st.stop()

st.subheader("Tabla diaria (unidades)")
st.dataframe(tabla, use_container_width=True)

# Download
csv_bytes = tabla.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Descargar CSV de la tabla", data=csv_bytes, file_name="tabla_diaria_items_sedes.csv", mime="text/csv")
