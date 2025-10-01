
import os, sys
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

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

tabla = build_daily_table_all_range(df_f, start, end, footer_label=footer_label)

st.subheader("Tabla diaria consolidada (unidades)")
if tabla.empty:
    st.warning("No se encontraron registros para los filtros aplicados.")
else:
    # Estilos con Styler
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

    # ======== GRÁFICAS ========
    st.subheader("Gráficas")

    # Pivot numérico para gráficas
    pivot_num = build_numeric_pivot_range(df_f, start, end)
    fechas_idx = pivot_num.index
    sedes_cols = [c for c in pivot_num.columns if c != "T. Dia"]

    # 1) Línea: Total por día
    st.markdown("**Total por día (T. Dia)**")
    fig1 = plt.figure()
    plt.plot(fechas_idx, pivot_num["T. Dia"])
    plt.xlabel("Fecha")
    plt.ylabel("Unidades")
    plt.title("Total por día (T. Dia)")
    st.pyplot(fig1)

    # 2) Barras apiladas: Unidades por sede por día
    st.markdown("**Unidades por sede por día (barras apiladas)**")
    fig2 = plt.figure()
    bottom = None
    for col in sedes_cols:
        if bottom is None:
            plt.bar(fechas_idx, pivot_num[col])
            bottom = pivot_num[col].values
        else:
            plt.bar(fechas_idx, pivot_num[col], bottom=bottom)
            bottom = bottom + pivot_num[col].values
    plt.xlabel("Fecha")
    plt.ylabel("Unidades")
    plt.title("Unidades por sede por día (apilado)")
    st.pyplot(fig2)

    # 3) Barras: Acumulado del rango por sede (desc)
    st.markdown("**Acumulado del rango por sede**")
    acum_por_sede = pivot_num.drop(columns=["T. Dia"]).sum(axis=0).sort_values(ascending=False)
    fig3 = plt.figure()
    plt.bar(acum_por_sede.index, acum_por_sede.values)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Unidades")
    plt.title("Acumulado del rango por sede")
    st.pyplot(fig3)

    # 4) Multilínea por sede (todas)
    st.markdown("**Serie diaria por sede (multilínea)**")
    fig4 = plt.figure()
    for col in sedes_cols:
        plt.plot(fechas_idx, pivot_num[col], label=col)
    plt.xlabel("Fecha")
    plt.ylabel("Unidades")
    plt.title("Serie diaria por sede")
    plt.legend(loc="upper right", fontsize="small")
    st.pyplot(fig4)
