# app.py — versión con multiselector de empresas + título dinámico según ítems (1ra palabra, orden de selección)

import os, sys, io, re
import streamlit as st
import pandas as pd
import altair as alt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from utils import (
    prepare_dataframe, items_display_list,
    build_daily_table_all_range, build_numeric_pivot_range
)

st.set_page_config(page_title="Ventas x Ítem — Tabla y Gráficas", layout="wide")
st.title("📊 Ventas por Ítem(s) x Sedes — Tabla única + Gráficas")
st.caption("Rango de fechas, filtro por empresas, todas las sedes por empresa, guiones en lugar de 0, totales resaltados, domingos en rojo y varias gráficas.")

with st.expander("Formato esperado del CSV", expanded=False):
    st.markdown("`empresa, fecha_dcto, id_co, id_item, descripcion, linea, und_dia, venta_sin_impuesto_dia, und_acum, venta_sin_impuesto_acum`")

uploaded = st.file_uploader("📥 Cargar CSV", type=["csv"])
if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

# ====== Carga y preparación (cacheada) ======
@st.cache_data(show_spinner=False)
def _load_df(file_bytes: bytes) -> pd.DataFrame:
    raw = pd.read_csv(io.BytesIO(file_bytes))
    return prepare_dataframe(raw)

try:
    df = _load_df(uploaded.getvalue())
except Exception as e:
    st.error(f"No se pudo procesar el CSV: {e}")
    st.stop()

# ====== Filtro de empresas ======
EMPRESA_LABELS = {
    "mercamio": "MERCAMIO",
    "mtodo": "MERCATODO",
    "bogota": "BOGOTÁ",
}
empresas_disponibles = sorted(df["empresa_norm"].dropna().unique().tolist())
labels = [EMPRESA_LABELS.get(x, x.upper()) for x in empresas_disponibles]

st.subheader("Filtros")
empresas_sel_labels = st.multiselect(
    "Empresas",
    options=labels,
    default=labels,  # por defecto todas
    help="Selecciona una o varias empresas."
)
# Mapa inverso label->clave normalizada
label_to_key = {EMPRESA_LABELS.get(k, k.upper()): k for k in empresas_disponibles}
empresas_sel = [label_to_key[l] for l in empresas_sel_labels] if empresas_sel_labels else []

if not empresas_sel:
    st.warning("Selecciona al menos una empresa para continuar.")
    st.stop()

# Filtramos por empresa antes de todo lo demás
df = df[df["empresa_norm"].isin(empresas_sel)].copy()
if df.empty:
    st.warning("No hay datos para las empresas seleccionadas.")
    st.stop()

# ====== Rango de fechas basado en las empresas filtradas ======
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

# ====== Ítems disponibles (ya restringidos por empresa y fechas para ayudar al usuario) ======
start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
mask_emp_fec = (df["fecha"] >= start) & (df["fecha"] <= end)
df_emp_fec = df.loc[mask_emp_fec].copy()

items_all = items_display_list(df_emp_fec if not df_emp_fec.empty else df)
items_sel = st.multiselect("Ítems (por ID o descripción)", items_all, max_selections=limit)
if not items_sel:
    # Título por defecto si no hay ítems aún
    st.subheader("Tabla diaria consolidada (unidades)")
    st.info("Selecciona al menos un ítem.")
    st.stop()

# ====== TÍTULO DINÁMICO de la tabla según ítems (1ra palabra, en orden real de selección) =====
if "items_order" not in st.session_state:
    st.session_state["items_order"] = []

current = items_sel[:]  # selección actual del multiselect

# agrega nuevos ítems en el orden en que fueron clicados
for it in current:
    if it not in st.session_state["items_order"]:
        st.session_state["items_order"].append(it)

# elimina los que ya no están seleccionados
st.session_state["items_order"] = [it for it in st.session_state["items_order"] if it in current]

def _first_word_from_option(opt: str) -> str:
    # Si viene "123 - Descripción del producto", tomar solo la descripción
    desc = opt.split(" - ", 1)[1] if " - " in opt else opt
    desc = desc.strip()

    # Limpieza básica: quita caracteres especiales al final (.,;:! etc)
    desc = re.sub(r"[^\wÁÉÍÓÚáéíóúÑñ/ ]+", "", desc)

    if not desc:
        return ""

    # Divide en palabras separadas por espacio, conservando expresiones como "C/RES"
    palabras = desc.split()

    # Toma hasta 2 palabras
    primeras = palabras[:2]
    return " ".join(primeras)

if st.session_state["items_order"]:
    first_words = [_first_word_from_option(s) for s in st.session_state["items_order"]]
    titulo_tabla = "Tabla diaria consolidada — " + " · ".join(first_words) + " (unidades)"
else:
    titulo_tabla = "Tabla diaria consolidada (unidades)"

# ====== Filtrado final por ítems ======
df_f = df_emp_fec.copy()
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
    pat = "|".join([re.escape(t) for t in descr_needles])  # usar re.escape
    ok = ok | df_f["descripcion"].str.lower().str.contains(pat, na=False)
df_f = df_f[ok]

# ====== Tabla principal ======
tabla = build_daily_table_all_range(df_f, start, end)

st.subheader(titulo_tabla)

if tabla.empty:
    st.warning("No se encontraron registros para los filtros aplicados.")
else:
    # Estilos en pantalla (Streamlit)
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
    sty = sty.format(precision=2, na_rep="-")

    st.dataframe(sty, use_container_width=True)

# ====== DESCARGAS: Excel y CSV ======
output_excel = io.BytesIO()
output_csv = io.BytesIO()

# CSV
tabla.to_csv(output_csv, index=False, encoding="utf-8-sig")

with pd.ExcelWriter(output_excel, engine="xlsxwriter") as writer:
    tabla.to_excel(writer, index=False, sheet_name="Tabla Consolidada", startrow=7)

    workbook  = writer.book
    worksheet = writer.sheets["Tabla Consolidada"]

    # === Formatos ===
    fmt_titulo = workbook.add_format({
        "bold": True, "font_color": "red",
        "font_size": 14, "align": "center"
    })
    fmt_header = workbook.add_format({"bold": True, "border": 1, "align": "center"})
    fmt_sunday = workbook.add_format({"font_color": "red", "bold": True, "border": 1, "align": "center"})
    fmt_total  = workbook.add_format({"bold": True, "bg_color": "#e6f2ff", "border": 1, "align": "center"})
    fmt_num    = workbook.add_format({"num_format": "#,##0.##", "border": 1, "align": "center"})
    fmt_text   = workbook.add_format({"border": 1, "align": "center"})
    fmt_bold_num = workbook.add_format({"bold": True, "num_format": "#,##0.##", "border": 1, "align": "center"})
    fmt_border_ext = workbook.add_format({"border": 2})

    # === Título dinámico centrado ===
    last_col = len(tabla.columns) - 1
    titulo_excel = titulo_tabla.replace("Tabla diaria consolidada — ", "").replace("(unidades)", "").strip()
    worksheet.merge_range(1, 0, 1, last_col, f"TÍTULO DE LA TABLA — {titulo_excel.upper()}", fmt_titulo)

    # === Ajustes de ancho de columnas ===
    for i, col in enumerate(tabla.columns):
        col_width = max(tabla[col].astype(str).map(len).max(), len(col)) + 2
        worksheet.set_column(i, i, col_width)

    # === Reescribir cabecera con formato ===
    for c in range(0, last_col + 1):
        worksheet.write(7, c, tabla.columns[c], fmt_header)

    last_row = len(tabla) + 7  # porque empezamos en la fila 8 (índice 7)

    # === Domingos en rojo ===
    worksheet.conditional_format(
        8, 0, last_row - 1, last_col,
        {"type": "formula", "criteria": 'RIGHT($A9,3)="dom"', "format": fmt_sunday}
    )

    # === Cuerpo de la tabla ===
    for r in range(8, last_row):
        for c in range(0, last_col + 1):
            val = tabla.iloc[r - 8, c]
            if c == 0:
                worksheet.write(r, c, val, fmt_text)
            else:
                if isinstance(val, (int, float)):
                    worksheet.write_number(r, c, val, fmt_num)
                else:
                    worksheet.write(r, c, val, fmt_text)

    # === Fila total final (última fila + 1) ===
    total_row = last_row
    for c in range(0, last_col + 1):
        val = tabla.iloc[-1, c]
        if c > 0 and isinstance(val, (int, float)):
            worksheet.write_number(total_row, c, val, fmt_total)
        else:
            worksheet.write(total_row, c, val, fmt_total)

    # === Columna "T. Dia" en negrita ===
    if "T. Dia" in tabla.columns:
        col_tdia = tabla.columns.get_loc("T. Dia")
        for r in range(8, total_row):
            val = tabla.iloc[r - 8, col_tdia]
            if isinstance(val, (int, float)):
                worksheet.write_number(r, col_tdia, val, fmt_bold_num)
            else:
                worksheet.write(r, col_tdia, val, fmt_text)

    # === Borde grueso alrededor de toda la tabla ===
    worksheet.conditional_format(7, 0, total_row, last_col, {"type": "no_errors", "format": fmt_border_ext})


# === BOTONES (lado a lado, alineados a la izquierda) ===
b1, b2, _ = st.columns([1, 1, 6])
with b1:
    st.download_button(
        "💾 Descargar Excel",
        data=output_excel.getvalue(),
        file_name="tabla_diaria_items_sedes_TODAS.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
with b2:
    st.download_button(
        "🧾 Descargar CSV",
        data=output_csv.getvalue(),
        file_name="tabla_diaria_items_sedes_TODAS.csv",
        mime="text/csv",
        use_container_width=True
    )

st.markdown("---")

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

