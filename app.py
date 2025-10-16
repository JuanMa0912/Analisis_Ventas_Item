import os, sys, io
import streamlit as st
import pandas as pd
import altair as alt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from utils import (
    prepare_dataframe, items_display_list,
    build_daily_table_all_range, build_numeric_pivot_range,
)

# =============================
# Config y utilidades
# =============================
DISPLAY_EMPRESA = {
    "mercamio": "Mercamio",
    "mtodo": "Mercatodo",
    "bogota": "Bogotá",
}

EMPRESA_ORDER = ["mercamio", "mtodo", "bogota"]

def sort_empresas(values):
    # orden preferido si existen en el dataset
    present = [e for e in EMPRESA_ORDER if e in values]
    others = [e for e in values if e not in present]
    return present + sorted(others)

# =============================
# Estado global de UI
# =============================
if "empresas_locked" not in st.session_state:
    st.session_state.empresas_locked = False
if "empresas_label_sel" not in st.session_state:
    st.session_state.empresas_label_sel = []

st.set_page_config(page_title="Ventas x Ítem — Tabla y Gráficas", layout="wide")
st.title("📊 Ventas por Ítem(s) x Sedes — Tabla única + Gráficas")
st.caption(
    "Rango de fechas, selección de empresa (bloqueable), guiones en lugar de 0, totales, domingos en rojo y varias gráficas."
)

with st.expander("Formato esperado del CSV", expanded=False):
    st.markdown(
        "`empresa, fecha_dcto, id_co, id_item, descripcion, linea, und_dia, venta_sin_impuesto_dia, und_acum, venta_sin_impuesto_acum`"
    )

uploaded = st.file_uploader("📥 Cargar CSV", type=["csv"]) 
if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

# ====== Carga y preparación ======
try:
    raw = pd.read_csv(uploaded)
    df = prepare_dataframe(raw)  # añade empresa_norm, sede, fecha, normaliza numéricos
except Exception as e:
    st.error(f"No se pudo procesar el CSV: {e}")
    st.stop()

# ====== Selector de empresas (NUEVO: multi-selección con bloqueo) ======
empresas_disponibles = df["empresa_norm"].dropna().unique().tolist()
if not empresas_disponibles:
    st.error("No se encontraron empresas válidas en el archivo.")
    st.stop()

empresas_disponibles = sort_empresas(empresas_disponibles)
labels = [DISPLAY_EMPRESA.get(e, e.title()) for e in empresas_disponibles]
label_to_value = dict(zip(labels, empresas_disponibles))

empresas_container = st.container()
with empresas_container:
    if not st.session_state.empresas_locked:
        with st.form("form_empresas", clear_on_submit=False):
            empresas_label_sel = st.multiselect(
                "Empresas",
                options=labels,
                default=(st.session_state.empresas_label_sel or labels[:1]),
                help="Elige una o varias (p. ej., Mercamio + Mercatodo). Luego pulsa 'Aplicar' para actualizar solo los datos.",
                max_selections=len(labels) if labels else 1,
            )
            aplicar = st.form_submit_button("✅ Aplicar empresas")
            if aplicar:
                st.session_state.empresas_label_sel = empresas_label_sel
                st.session_state.empresas_locked = True
    else:
        empresas_label_sel = st.session_state.empresas_label_sel
        st.success("Empresas: " + (" + ".join(empresas_label_sel) if empresas_label_sel else "(ninguna)"))
        if st.button("✏️ Cambiar empresas"):
            st.session_state.empresas_locked = False
            st.stop()

# Si sigue sin selección (primer render), usa 1ra por defecto
if not st.session_state.empresas_label_sel and empresas_disponibles:
    st.session_state.empresas_label_sel = [labels[0]]

empresas_label_sel = st.session_state.empresas_label_sel
if not empresas_label_sel:
    st.info("Selecciona al menos una empresa.")
    st.stop()

empresas_sel = [label_to_value[l] for l in empresas_label_sel]
empresas_caption = " + ".join(empresas_label_sel)

# Filtramos TODO por las empresas elegidas
df_emp = df[df["empresa_norm"].isin(empresas_sel)].copy()
if df_emp.empty:
    st.warning("No hay datos para las empresas seleccionadas.")
    st.stop()

# Rango de fechas por defecto según el subset filtrado
if df_emp["fecha"].notna().any():
    min_d = df_emp["fecha"].min().date()
    max_d = df_emp["fecha"].max().date()
else:
    st.error("No hay fechas válidas en el archivo para las empresas seleccionadas.")
    st.stop()

# ====== Filtros: fechas, límite e ítems (sobre las empresas) ======
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    date_range = st.date_input(
        "Rango de fechas (YYYY-MM-DD)", value=(min_d, max_d), format="YYYY-MM-DD"
    )
with c2:
    limit = st.number_input("Límite de ítems", min_value=1, max_value=10, value=10, step=1)

items_all = items_display_list(df_emp)
items_sel = st.multiselect("Ítems (por ID o descripción)", items_all, max_selections=limit, help="Si no eliges ninguno, se tomará el top inicial automáticamente")
# Comportamiento: si no hay selección, NO frenamos la app; usamos todos (o top 'limit')
if not items_sel:
    # Top por frecuencia dentro del rango/empresa (preliminar, antes de filtrar por fecha)
    top_default = items_all[:limit] if len(items_all) > limit else items_all
    items_sel = top_default

start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

# Filtrar por rango + ítems (dentro de la empresa)
mask = (df_emp["fecha"] >= start) & (df_emp["fecha"] <= end)
df_f = df_emp.loc[mask].copy()

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

# ====== Tabla principal ======
tabla = build_daily_table_all_range(df_f, start, end)

st.subheader(
    f"Tabla diaria consolidada (unidades) - {empresas_caption}")
if tabla.empty:
    st.warning("No se encontraron registros para los filtros aplicados.")
else:
    # Estilos en pantalla (Streamlit)
    def style_headers(df_styler):
        return df_styler.set_table_styles(
            [{"selector": "th", "props": [("font-weight", "bold")] }]
        )

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
    sty = style_headers(sty)
    sty = sty.format(precision=2, na_rep="-")

    st.dataframe(sty, use_container_width=True)

# ====== DESCARGAS: Excel y CSV ======
output_excel = io.BytesIO()
output_csv = io.BytesIO()

# CSV
tabla.to_csv(output_csv, index=False, encoding="utf-8-sig")

tag_empresas = "_".join([e for e in empresas_sel]) if len(empresas_sel) > 1 else empresas_sel[0]
excel_name = f"tabla_diaria_items_{tag_empresas}_sedes.xlsx"
csv_name  = f"tabla_diaria_items_{tag_empresas}_sedes.csv"

with pd.ExcelWriter(output_excel, engine="xlsxwriter") as writer:
    tabla.to_excel(writer, index=False, sheet_name="Tabla Consolidada")

    workbook = writer.book
    worksheet = writer.sheets["Tabla Consolidada"]

    # Formatos
    fmt_header = workbook.add_format({"bold": True, "border": 1})
    fmt_sunday = workbook.add_format({"font_color": "red", "bold": True, "border": 1})
    fmt_total = workbook.add_format({"bold": True, "bg_color": "#e6f2ff", "border": 1})
    fmt_num = workbook.add_format({"num_format": "#,##0.##", "border": 1})
    fmt_text = workbook.add_format({"border": 1})
    fmt_bold_num = workbook.add_format({"bold": True, "num_format": "#,##0.##", "border": 1})
    fmt_border_ext = workbook.add_format({"border": 2})

    last_row = len(tabla)
    last_col = len(tabla.columns) - 1

    # Anchos
    for i, col in enumerate(tabla.columns):
        col_width = max(tabla[col].astype(str).map(len).max(), len(col)) + 2
        worksheet.set_column(i, i, col_width)

    # Cabeceras
    for c in range(0, last_col + 1):
        worksheet.write(0, c, tabla.columns[c], fmt_header)

    # Domingos
    worksheet.conditional_format(
        1, 0, last_row - 1, last_col,
        {"type": "formula", "criteria": 'RIGHT($A2,3)="dom"', "format": fmt_sunday},
    )

    # Datos
    for r in range(1, last_row):
        for c in range(0, last_col + 1):
            val = tabla.iloc[r - 1, c]
            if c == 0:
                worksheet.write(r, c, val, fmt_text)
            else:
                if isinstance(val, (int, float)):
                    worksheet.write_number(r, c, val, fmt_num)
                else:
                    worksheet.write(r, c, val, fmt_text)

    # Fila de acumulado
    for c in range(0, last_col + 1):
        val = tabla.iloc[-1, c]
        if c > 0 and isinstance(val, (int, float)):
            worksheet.write_number(last_row, c, val, fmt_total)
        else:
            worksheet.write(last_row, c, val, fmt_total)

    # Columna T. Dia en negrita
    if "T. Dia" in tabla.columns:
        col_tdia = tabla.columns.get_loc("T. Dia")
        for r in range(1, last_row):
            val = tabla.iloc[r - 1, col_tdia]
            if isinstance(val, (int, float)):
                worksheet.write_number(r, col_tdia, val, fmt_bold_num)
            else:
                worksheet.write(r, col_tdia, val, fmt_text)

    # Borde exterior
    worksheet.conditional_format(0, 0, 0, last_col, {"type": "no_errors", "format": fmt_border_ext})
    worksheet.conditional_format(last_row, 0, last_row, last_col, {"type": "no_errors", "format": fmt_border_ext})
    worksheet.conditional_format(0, 0, last_row, 0, {"type": "no_errors", "format": fmt_border_ext})
    worksheet.conditional_format(0, last_col, last_row, last_col, {"type": "no_errors", "format": fmt_border_ext})

# Botones de descarga
b1, b2, _ = st.columns([1, 1, 6])
with b1:
    st.download_button(
        "💾 Descargar Excel",
        data=output_excel.getvalue(),
        file_name=excel_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with b2:
    st.download_button(
        "🧾 Descargar CSV",
        data=output_csv.getvalue(),
        file_name=csv_name,
        mime="text/csv",
        use_container_width=True,
    )

st.markdown("---")

# ====== GRÁFICAS (Altair) ======
st.subheader(
    f"Gráficas — {empresas_caption}"
)

pivot_num = build_numeric_pivot_range(df_f, start, end)

# DataFrames para charts
df_line = pivot_num.rename_axis("fecha").reset_index()
df_line["fecha_dia"] = pd.to_datetime(df_line["fecha"]).dt.date
df_line = df_line.rename(columns={"T. Dia": "T_Dia"})

# Si la empresa solo tiene una sede, Altair igual dibuja la serie total

df_stack = (
    pivot_num.drop(columns=["T. Dia"]) if "T. Dia" in pivot_num.columns else pivot_num.copy()
)
if not df_stack.empty:
    df_stack = (
        df_stack.rename_axis("fecha").reset_index().melt(id_vars="fecha", var_name="sede", value_name="unidades")
    )
    df_stack["fecha_dia"] = pd.to_datetime(df_stack["fecha"]).dt.date

acum_por_sede = (
    (pivot_num.drop(columns=["T. Dia"]) if "T. Dia" in pivot_num.columns else pivot_num.copy())
    .sum(axis=0)
    .sort_values(ascending=False)
    .rename_axis("sede")
    .reset_index(name="unidades")
)

layout = st.radio("Distribución de gráficas", ["Una columna", "Dos columnas"], index=0, horizontal=True)

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

if not df_stack.empty:
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
else:
    stack_chart = None
    heatmap = None

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
    if stack_chart is not None:
        st.altair_chart(stack_chart, use_container_width=True)
        st.altair_chart(heatmap, use_container_width=True)
    st.altair_chart(acum_chart, use_container_width=True)
else:
    colA, colB = st.columns(2)
    with colA:
        st.altair_chart(line_chart, use_container_width=True)
        if heatmap is not None:
            st.altair_chart(heatmap, use_container_width=True)
    with colB:
        if stack_chart is not None:
            st.altair_chart(stack_chart, use_container_width=True)
        st.altair_chart(acum_chart, use_container_width=True)
