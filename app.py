import os, sys, io
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
st.caption("Rango de fechas, todas las sedes (Mercamio → Mercatodo → Bogotá), guiones en lugar de 0, totales resaltados, domingos en rojo y varias gráficas.")

with st.expander("Formato esperado del CSV", expanded=False):
    st.markdown("`empresa, fecha_dcto, id_co, id_item, descripcion, linea, und_dia, venta_sin_impuesto_dia, und_acum, venta_sin_impuesto_acum`")

uploaded = st.file_uploader("📥 Cargar CSV", type=["csv"])
if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

# ====== Carga y preparación ======
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
    limit = st.number_input("Límite de ítems", min_value=1, max_value=10, value=10, step=1)

items_all = items_display_list(df)
items_sel = st.multiselect("Ítems (por ID o descripción)", items_all, max_selections=limit)
if not items_sel:
    st.info("Selecciona al menos un ítem.")
    st.stop()

start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

# Filtrar por rango + ítems
mask = (df["fecha"] >= start) & (df["fecha"] <= end)
df_f = df.loc[mask].copy()

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

st.subheader("Tabla diaria consolidada (unidades)")
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
    sty = sty.format(precision=2, na_rep="-")  # enteros como enteros / decimales hasta 2

    st.dataframe(sty, use_container_width=True)

        # ====== DESCARGAS: Excel y CSV (XLSXWRITER corregido) ======
output_excel = io.BytesIO()
output_csv = io.BytesIO()

# CSV
tabla.to_csv(output_csv, index=False, encoding="utf-8-sig")

with pd.ExcelWriter(output_excel, engine="xlsxwriter") as writer:
    tabla.to_excel(writer, index=False, sheet_name="Tabla Consolidada")

    workbook  = writer.book
    worksheet = writer.sheets["Tabla Consolidada"]

    # Formatos
    fmt_header = workbook.add_format({"bold": True, "border": 1})
    fmt_sunday = workbook.add_format({"font_color": "red", "bold": True, "border": 1})
    fmt_total  = workbook.add_format({"bold": True, "bg_color": "#e6f2ff", "border": 1})
    fmt_num    = workbook.add_format({"num_format": "#,##0.##", "border": 1})
    fmt_text   = workbook.add_format({"border": 1})
    fmt_bold_num = workbook.add_format({"bold": True, "num_format": "#,##0.##", "border": 1})
    fmt_border_ext = workbook.add_format({"border": 2})

    last_row = len(tabla)                 # índice de fila en Excel para "Acum. Rango"
    last_col = len(tabla.columns) - 1

    # Ancho de columnas (SIN formato de columna)
    for i, col in enumerate(tabla.columns):
        col_width = max(tabla[col].astype(str).map(len).max(), len(col)) + 2
        worksheet.set_column(i, i, col_width)  # <— solo ancho

    # Re-escribir cabecera celda por celda (evita que se derrame a la derecha)
    for c in range(0, last_col + 1):
        worksheet.write(0, c, tabla.columns[c], fmt_header)

    # Domingos en rojo (solo dentro del rango)
    worksheet.conditional_format(
        1, 0, last_row - 1, last_col,
        {"type": "formula", "criteria": 'RIGHT($A2,3)="dom"', "format": fmt_sunday}
    )

    # Contenido normal con formato numérico/texto (bordes finos internos)
    # Recorremos las filas de datos (2..last_row) y columnas (0..last_col)
    for r in range(1, last_row):  # filas de datos (sin incluir fila de acumulado)
        for c in range(0, last_col + 1):
            val = tabla.iloc[r - 1, c]
            if c == 0:
                # Columna Fecha (texto)
                worksheet.write(r, c, val, fmt_text)
            else:
                # Numérico o texto "-"
                if isinstance(val, (int, float)):
                    worksheet.write_number(r, c, val, fmt_num)
                else:
                    worksheet.write(r, c, val, fmt_text)

    # Fila "Acum. Rango:" SOLO hasta last_col (sin derramar)
    for c in range(0, last_col + 1):
        val = tabla.iloc[-1, c]
        # Si es numérico, respeta num_format, si es texto, aplícalo como texto
        if c > 0 and isinstance(val, (int, float)):
            worksheet.write_number(last_row, c, val, fmt_total)
        else:
            worksheet.write(last_row, c, val, fmt_total)

    # Columna "T. Dia" en negrita — SOLO dentro del rango usado
    if "T. Dia" in tabla.columns:
        col_tdia = tabla.columns.get_loc("T. Dia")
        # Cabecera ya quedó en negrita; formateamos datos + acumulado
        for r in range(1, last_row + 1):
            val = tabla.iloc[r - 1, col_tdia] if r <= last_row else None
            if r == last_row:
                # ya la escribimos con fmt_total, no tocar
                continue
            if isinstance(val, (int, float)):
                worksheet.write_number(r, col_tdia, val, fmt_bold_num)
            else:
                worksheet.write(r, col_tdia, val, fmt_text)

    # Borde exterior grueso solo contorno
    # Superior
    worksheet.conditional_format(0, 0, 0, last_col, {"type": "no_errors", "format": fmt_border_ext})
    # Inferior
    worksheet.conditional_format(last_row, 0, last_row, last_col, {"type": "no_errors", "format": fmt_border_ext})
    # Izquierda
    worksheet.conditional_format(0, 0, last_row, 0, {"type": "no_errors", "format": fmt_border_ext})
    # Derecha
    worksheet.conditional_format(0, last_col, last_row, last_col, {"type": "no_errors", "format": fmt_border_ext})

# Botones lado a lado
with b1:
    st.download_button(
        "💾 Descargar Excel",
        data=output_excel.getvalue(),
        file_name="tabla_diaria_items_sedes_TODAS.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
with b2:
    st.download_button(
        "⬇️ Descargar CSV",
        data=output_csv.getvalue(),
        file_name="tabla_diaria_items_sedes_TODAS.csv",
        mime="text/csv"
    )
b1, b2 = set.columns(2)

    # ====== GRÁFICAS (Altair) ======
    st.subheader("Gráficas")

    # Pivot numérico (todas las fechas del rango, sedes en columnas)
    pivot_num = build_numeric_pivot_range(df_f, start, end)  # incluye 'T. Dia' :contentReference[oaicite:2]{index=2}

    # --- DataFrames para charts ---
    # 1) Línea total por día (renombrar "T. Dia" y fecha solo día)
    df_line = pivot_num.rename_axis('fecha').reset_index()
    df_line['fecha_dia'] = pd.to_datetime(df_line['fecha']).dt.date
    df_line = df_line.rename(columns={'T. Dia': 'T_Dia'})

    # 2) Apilado por sede por día (melt + fecha solo día)
    df_stack = (
        pivot_num.drop(columns=["T. Dia"])
        .rename_axis("fecha").reset_index()
        .melt(id_vars="fecha", var_name="sede", value_name="unidades")
    )
    df_stack["fecha_dia"] = pd.to_datetime(df_stack["fecha"]).dt.date

    # 3) Acumulado por sede
    acum_por_sede = (
        pivot_num.drop(columns=["T. Dia"])
        .sum(axis=0)
        .sort_values(ascending=False)
        .rename_axis("sede")
        .reset_index(name="unidades")
    )

    # === Diseño en dos columnas ===
    gcol1, gcol2 = st.columns(2)

    # --- Columna izquierda: Línea + Heatmap ---
    with gcol1:
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
        st.altair_chart(line_chart, use_container_width=True)

        # Heatmap: Fecha × Sede (intensidad = unidades)
        heatmap = (
            alt.Chart(df_stack, title="Mapa de calor: unidades por sede y día")
            .mark_rect()
            .encode(
                x=alt.X("fecha_dia:T",
                        axis=alt.Axis(title="Fecha", format="%d-%b", labelAngle=-45)),
                y=alt.Y("sede:N", sort='-x', axis=alt.Axis(title="Sede")),
                color=alt.Color("unidades:Q",
                                scale=alt.Scale(scheme="inferno"),  # puedes probar "greens", "inferno", etc.
                                legend=alt.Legend(title="Unidades")),
                tooltip=[
                    alt.Tooltip("fecha_dia:T", title="Fecha", format="%Y-%m-%d"),
                    alt.Tooltip("sede:N", title="Sede"),
                    alt.Tooltip("unidades:Q", title="Unidades", format=",.2f"),
                ],
            )
            .properties(height=320)
            .interactive()
        )
        st.altair_chart(heatmap, use_container_width=True)

    # --- Columna derecha: Apilado + Acumulado ---
    with gcol2:
        stack_chart = (
            alt.Chart(df_stack, title="Unidades por sede por día (apilado)")
            .mark_bar()
            .encode(
                x=alt.X("fecha_dia:T",
                        axis=alt.Axis(title="Fecha", format="%d-%b", labelAngle=-45)),
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
        st.altair_chart(stack_chart, use_container_width=True)

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
        st.altair_chart(acum_chart, use_container_width=True)
