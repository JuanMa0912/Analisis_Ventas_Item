
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

tabla = build_daily_table_all_range(df_f, start, end)

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
    # ======== GRÁFICAS ========
    st.subheader("Gráficas")
    
    # Pivot numérico para gráficas
    pivot_num = build_numeric_pivot_range(df_f, start, end)
    fechas_idx = pivot_num.index
    sedes_cols = [c for c in pivot_num.columns if c != "T. Dia"]
    
    # Helper para ejes de fechas compactos
    import matplotlib.dates as mdates
    def format_date_axis(ax):
        locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
        formatter = mdates.ConciseDateFormatter(locator)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
    
    # === Fila 1: dos columnas
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Total por día (T. Dia)**")
        fig1, ax1 = plt.subplots(figsize=(6, 2.6))
        ax1.plot(fechas_idx, pivot_num["T. Dia"])
        ax1.set_xlabel("Fecha")
        ax1.set_ylabel("Unidades")
        ax1.set_title("Total por día (T. Dia)")
        ax1.grid(True, alpha=0.2, linewidth=0.5)
        format_date_axis(ax1)
        fig1.tight_layout()
        st.pyplot(fig1, use_container_width=False)
    
    with col2:
        # 2) Barras apiladas: Unidades por sede por día
        st.markdown("**Unidades por sede por día (barras apiladas)**")
        fig2, ax2 = plt.subplots(figsize=(7,3))   # tamaño compacto
        bottom = None
        for col in sedes_cols:
            vals = pivot_num[col].values
            if bottom is None:
                ax2.bar(fechas_idx, vals, label=col)   # 👈 etiqueta de sede
                bottom = vals
            else:
                ax2.bar(fechas_idx, vals, bottom=bottom, label=col)  # 👈 etiqueta de sede
                bottom = bottom + vals
        ax2.set_xlabel("Fecha")
        ax2.set_ylabel("Unidades")
        ax2.set_title("Unidades por sede por día (apilado)")
        ax2.grid(True, alpha=0.2, linewidth=0.5)
        
        # leyenda automática con nombres de sedes
        ax2.legend(title="Sede", bbox_to_anchor=(1.05, 1), loc="upper left", fontsize="x-small")
        fig2.tight_layout()
        
        st.pyplot(fig2, use_container_width=False)

    # === Fila 2: una columna (ancho completo)
    st.markdown("**Acumulado del rango por sede**")
    acum_por_sede = pivot_num.drop(columns=["T. Dia"]).sum(axis=0).sort_values(ascending=False)
    fig3, ax3 = plt.subplots(figsize=(7, 2.6))
    ax3.bar(acum_por_sede.index, acum_por_sede.values)
    ax3.set_ylabel("Unidades")
    ax3.set_title("Acumulado del rango por sede")
    ax3.grid(True, axis="y", alpha=0.2, linewidth=0.5)
    ax3.tick_params(axis='x', labelrotation=45)
    fig3.tight_layout()
    st.pyplot(fig3, use_container_width=False)
