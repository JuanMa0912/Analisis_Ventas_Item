import os, sys, io
import streamlit as st
import pandas as pd

# =============================
# Bootstrap imports
# =============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from utils import (
    prepare_dataframe,
    items_display_list,
    build_daily_table_all_range,
    build_numeric_pivot_range,
)

# =============================
# Page config
# =============================
st.set_page_config(page_title="Ventas por Item x Sedes", layout="wide")
st.title("Ventas por Item x Sedes - Tabla")

with st.expander("Formato esperado del CSV", expanded=False):
    st.write(
        "empresa, fecha_dcto, id_co, id_item, descripcion, linea, und_dia, venta_sin_impuesto_dia, und_acum, venta_sin_impuesto_acum"
    )

# =============================
# Uploader
# =============================
uploaded = st.file_uploader("Cargar CSV", type=["csv"]) 
if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

# =============================
# Load and prepare
# =============================
try:
    raw = pd.read_csv(uploaded)
    df = prepare_dataframe(raw)  # agrega empresa_norm, fecha y normaliza numericos
except Exception as e:
    st.error(f"No se pudo procesar el CSV: {e}")
    st.stop()

# =============================
# Company multiselect (filtra antes de todo)
# =============================
emp_col = "empresa_norm" if "empresa_norm" in df.columns else ("empresa" if "empresa" in df.columns else None)
if emp_col is None:
    st.error("El archivo no contiene columna de empresa ni empresa_norm.")
    st.stop()

emp_options = sorted(df[emp_col].dropna().astype(str).unique().tolist())
if not emp_options:
    st.error("No se encontraron empresas en el archivo.")
    st.stop()

emp_sel = st.multiselect(
    "Empresas",
    options=emp_options,
    default=emp_options[:1],
    help="Puedes elegir una o varias empresas. La tabla se actualizará con la selección."
)

if not emp_sel:
    st.info("Selecciona al menos una empresa para continuar.")
    st.stop()

# filtrar por empresas seleccionadas
df = df[df[emp_col].isin(emp_sel)].copy()
if df.empty:
    st.warning("No hay datos para las empresas seleccionadas.")
    st.stop()

# =============================
# Fecha default por subset filtrado
# =============================
if df["fecha"].notna().any():
    min_d = pd.to_datetime(df["fecha"]).min().date()
    max_d = pd.to_datetime(df["fecha"]).max().date()
else:
    st.error("No hay fechas válidas en el archivo para las empresas seleccionadas.")
    st.stop()

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    date_range = st.date_input(
        "Rango de fechas (YYYY-MM-DD)", value=(min_d, max_d), format="YYYY-MM-DD"
    )
with c2:
    limit = st.number_input("Limite de items", min_value=1, max_value=50, value=10, step=1)

# =============================
# Items selector (opcional). Si está vacío, usamos todos o top N
# =============================
items_all = items_display_list(df)
items_sel = st.multiselect(
    "Items (por ID o descripcion)", items_all, max_selections=limit,
    help="Opcional. Si no eliges ninguno, se usan todos (o el top mostrado)."
)

start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
mask_date = (df["fecha"] >= start) & (df["fecha"] <= end)
df_f = df.loc[mask_date].copy()

# filtrar por items si hay seleccion (acepta ID o descripcion parcial del helper)
if items_sel:
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

if df_f.empty:
    st.warning("No hay registros para los filtros aplicados.")
    st.stop()

# =============================
# Tabla principal
# =============================
emp_tag = "_".join(emp_sel) if len(emp_sel) > 1 else emp_sel[0]
st.subheader(f"Tabla diaria consolidada (unidades) - {emp_tag}")

tabla = build_daily_table_all_range(df_f, start, end)
if tabla.empty:
    st.warning("No se encontraron registros para el rango.")
else:
    # estilos basicos en pantalla
    def style_totals(row):
        is_total = row.name == len(tabla) - 1
        return ["font-weight: bold; background-color: #e6f2ff" if is_total else "" for _ in row]

    def style_sundays(row):
        is_sunday = isinstance(row["Fecha"], str) and ("/dom" in row["Fecha"])
        if row.name == len(tabla) - 1:
            return ["" for _ in row]
        return ["color: red; font-weight: bold" if is_sunday else "" for _ in row]

    sty = tabla.style.apply(style_totals, axis=1).apply(style_sundays, axis=1)
    if "T. Dia" in tabla.columns:
        sty = sty.set_properties(subset=["T. Dia"], **{"font-weight": "bold"})
    sty = sty.format(precision=2, na_rep="-")

    st.dataframe(sty, use_container_width=True)

# =============================
# Descargas
# =============================
excel_name = f"tabla_diaria_items_{emp_tag}_sedes.xlsx"
csv_name = f"tabla_diaria_items_{emp_tag}_sedes.csv"

buffer_xlsx = io.BytesIO()
with pd.ExcelWriter(buffer_xlsx, engine="xlsxwriter") as writer:
    tabla.to_excel(writer, index=False, sheet_name="Tabla")

buffer_csv = io.BytesIO()
tabla.to_csv(buffer_csv, index=False, encoding="utf-8-sig")

col_d1, col_d2, _ = st.columns([1, 1, 6])
with col_d1:
    st.download_button(
        "Descargar Excel",
        data=buffer_xlsx.getvalue(),
        file_name=excel_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with col_d2:
    st.download_button(
        "Descargar CSV",
        data=buffer_csv.getvalue(),
        file_name=csv_name,
        mime="text/csv",
        use_container_width=True,
    )

# ====== GRÁFICAS (Altair) ======
st.subheader("Gráficas")

# Pivot numérico
pivot_num = build_numeric_pivot_range(df_f, start, end)

# DataFrames para charts
df_line = pivot_num.rename_axis('fecha').reset_index()
df_line['fecha_dia'] = pd.to_datetime(df_line['fecha']).dt.date
df_line = df_line.rename(columns={'T. Dia': 'T_Dia'})

df_stack = (
    pivot_num.drop(columns=["T. Dia"])
    .rename_axis("fecha").reset_index()
    .melt(id_vars="fecha", var_name="sede", value_name="unidades")
)
df_stack["fecha_dia"] = pd.to_datetime(df_stack["fecha"]).dt.date

acum_por_sede = (
    pivot_num.drop(columns=["T. Dia"])
    .sum(axis=0)
    .sort_values(ascending=False)
    .rename_axis("sede")
    .reset_index(name="unidades")
)

# selector de layout
layout = st.radio("Distribución de gráficas", ["Una columna", "Dos columnas"], index=0, horizontal=True)

# charts
line_chart = (
    alt.Chart(df_line, title="Total por día (T. Dia)")
    .mark_line(point=True)
    .encode(
        x=alt.X("fecha_dia:T", axis=alt.Axis(title="Fecha", format="%d-%b")),
        y=alt.Y("T_Dia:Q", axis=alt.Axis(title="Unidades")),
        tooltip=[
            alt.Tooltip("fecha_dia:T", title="Fecha", format="%Y-%m-%d"),
            alt.Tooltip("T_Dia:Q", title="T. Dia", format=",.2f"),
        ],
    )
    .properties(height=260)
    .interactive()
)

stack_chart = (
    alt.Chart(df_stack, title="Unidades por sede por día (apilado)")
    .mark_bar()
    .encode(
        x=alt.X("fecha_dia:T", axis=alt.Axis(title="Fecha", format="%d-%b", labelAngle=-45)),
        y=alt.Y("unidades:Q", stack="zero", axis=alt.Axis(title="Unidades")),
        color=alt.Color("sede:N", legend=alt.Legend(title="Sede")),
        tooltip=[
            alt.Tooltip("fecha_dia:T", title="Fecha", format="%Y-%m-%d"),
            alt.Tooltip("sede:N", title="Sede"),
            alt.Tooltip("unidades:Q", title="Unidades", format=",.2f"),
        ],
    )
    .properties(height=320)
    .interactive()
)

heatmap = (
    alt.Chart(df_stack, title="Mapa de calor: unidades por sede y día")
    .mark_rect()
    .encode(
        x=alt.X("fecha_dia:T", axis=alt.Axis(title="Fecha", format="%d-%b", labelAngle=-45)),
        y=alt.Y("sede:N", sort='-x', axis=alt.Axis(title="Sede")),
        color=alt.Color("unidades:Q", scale=alt.Scale(scheme="inferno"), legend=alt.Legend(title="Unidades")),
        tooltip=[
            alt.Tooltip("fecha_dia:T", title="Fecha", format="%Y-%m-%d"),
            alt.Tooltip("sede:N", title="Sede"),
            alt.Tooltip("unidades:Q", title="Unidades", format=",.2f"),
        ],
    )
    .properties(height=320)
    .interactive()
)

acum_chart = (
    alt.Chart(acum_por_sede, title="Acumulado del rango por sede")
    .mark_bar()
    .encode(
        x=alt.X("sede:N", sort="-y", axis=alt.Axis(title="Sede")),
        y=alt.Y("unidades:Q", axis=alt.Axis(title="Unidades")),
        tooltip=[
            alt.Tooltip("sede:N", title="Sede"),
            alt.Tooltip("unidades:Q", title="Unidades", format=",.2f"),
        ],
    )
    .properties(height=260)
    .interactive()
)

if layout == "Una columna":
    st.altair_chart(line_chart, use_container_width=True)
    st.altair_chart(stack_chart, use_container_width=True)
    st.altair_chart(heatmap, use_container_width=True)
    st.altair_chart(acum_chart, use_container_width=True)
else:
    colA, colB = st.columns(2)
    with colA:
        st.altair_chart(line_chart, use_container_width=True)
        st.altair_chart(heatmap, use_container_width=True)
    with colB:
        st.altair_chart(stack_chart, use_container_width=True)
        st.altair_chart(acum_chart, use_container_width=True)

