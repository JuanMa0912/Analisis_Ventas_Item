
import pandas as pd
import numpy as np

# ====== Sede mappings by empresa (normalize id_co to 3 digits) ======
SEDE_MAP = {
    "mercamio": {
        "001": "La 5",
        "002": "La 39",
        "003": "Plaza",
        "004": "Jardin",
        "005": "C.sur",
        "006": "Palmira",
    },
    "mercatodo": {
        "001": "FTA",
        "002": "FLA",
        "003": "MN",
    },
    "bogota": {
        "001": "La 80",
        "002": "Chia",
    }
}

# Preferred column order for each empresa (others appended at end)
PREFERRED_ORDER = {
    "mercamio": ["La 5", "La 39", "Plaza", "Jardin", "C.sur", "Palmira"],
    "mercatodo": ["FTA", "FLA", "MN"],
    "bogota": ["La 80", "Chia"],
}

DOW_ABBR_ES = {0: "lun", 1: "mar", 2: "mié", 3: "jue", 4: "vie", 5: "sáb", 6: "dom"}

def normalize_empresa(x: str) -> str:
    return (x or "").strip().lower()

def normalize_id_co(x) -> str:
    # handle numbers/strings like 5 or '005' or '5 '
    try:
        # If it's numeric, cast to int first then zfill
        xi = int(str(x).strip())
        return f"{xi:03d}"
    except Exception:
        s = str(x).strip()
        # if already 3+ chars, keep last 3
        if len(s) >= 3 and s[:3].isdigit():
            return s[:3]
        if s.isdigit():
            return s.zfill(3)
        return s  # fallback

def map_sede(empresa: str, id_co: str) -> str:
    emp = normalize_empresa(empresa)
    idn = normalize_id_co(id_co)
    mapping = SEDE_MAP.get(emp, {})
    return mapping.get(idn, idn)

def parse_fecha(fecha_series: pd.Series) -> pd.Series:
    # soporta 20250901, '2025-09-01', '20250901.0'
    s = fecha_series.astype(str).str.replace(r"\.0$", "", regex=True).str.replace("-", "", regex=False)
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")

def prepare_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    required_cols = ["empresa","fecha_dcto","id_co","id_item","descripcion","linea","und_dia",
                     "venta_sin_impuesto_dia","und_acum","venta_sin_impuesto_acum"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en el CSV: {missing}")
    df["empresa_norm"] = df["empresa"].apply(normalize_empresa)
    df["id_co_norm"] = df["id_co"].apply(normalize_id_co)
    df["sede"] = [map_sede(e, i) for e, i in zip(df["empresa"], df["id_co"])]
    df["fecha"] = parse_fecha(df["fecha_dcto"])
    # coerce numeric
    for c in ["und_dia", "und_acum", "venta_sin_impuesto_dia", "venta_sin_impuesto_acum"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    # trim descripcion
    df["descripcion"] = df["descripcion"].astype(str).str.strip()
    return df

def month_floor(d: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(year=d.year, month=d.month, day=1)

def filter_by_empresa_items_month(df: pd.DataFrame, empresa: str, items: list, month: pd.Timestamp) -> pd.DataFrame:
    emp_norm = normalize_empresa(empresa)
    df1 = df[df["empresa_norm"] == emp_norm].copy()
    # month range
    m0 = month_floor(month)
    m1 = (m0 + pd.offsets.MonthEnd(0)).normalize()
    mask = (df1["fecha"] >= m0) & (df1["fecha"] <= m1)
    df1 = df1.loc[mask]
    # items filter by id OR descripcion (case-insensitive contains if given as text)
    if items:
        # items could be id_item codes OR "id - descripcion" strings; normalize by splitting at ' - '
        ids = set()
        descr_needles = []
        for it in items:
            s = str(it)
            if " - " in s:
                ids.add(s.split(" - ", 1)[0])
            elif s.isdigit() or s.strip().isdigit():
                ids.add(s.strip())
            else:
                descr_needles.append(s.lower().strip())
        ok = pd.Series(False, index=df1.index)
        if ids:
            ok = ok | df1["id_item"].astype(str).isin(ids)
        if descr_needles:
            pat = "|".join([pd.re.escape(t) for t in descr_needles])
            ok = ok | df1["descripcion"].str.lower().str.contains(pat, na=False)
        df1 = df1[ok]
    return df1

def build_daily_table(df: pd.DataFrame, empresa: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    # pivot
    pt = pd.pivot_table(
        df,
        index="fecha",
        columns="sede",
        values="und_dia",
        aggfunc="sum",
        fill_value=0.0
    ).sort_index()

    # order columns
    pref = PREFERRED_ORDER.get(normalize_empresa(empresa), [])
    ordered_cols = [c for c in pref if c in pt.columns] + [c for c in pt.columns if c not in pref]
    pt = pt.reindex(columns=ordered_cols)

    # T. Dia (row sum)
    pt["T. Dia"] = pt.sum(axis=1)

    # index formatting "d/abr"
    dow = pt.index.dayofweek
    fechas_fmt = [f"{i.day}/{DOW_ABBR_ES.get(dw, '')}" for i, dw in zip(pt.index, dow)]
    pt.insert(0, "Fecha", fechas_fmt)

    # Add accumulated row
    acum = pt.drop(columns=["Fecha"]).sum(axis=0)
    acum_row = pd.DataFrame([["Acum. Mes:"] + list(acum.values)], columns=["Fecha"] + list(acum.index))
    final = pd.concat([pt.reset_index(drop=True), acum_row], ignore_index=True)

    # Cast to int when values are "whole" (so it looks like your sample). Otherwise keep one decimal.
    def _fmt_number(x):
        if pd.isna(x):
            return 0
        if abs(x - int(x)) < 1e-9:
            return int(x)
        return round(x, 1)

    num_cols = [c for c in final.columns if c != "Fecha"]
    for c in num_cols:
        final[c] = final[c].astype(float).map(_fmt_number)

    return final

def items_display_list(df: pd.DataFrame):
    # Unique items as "id - descripcion"
    ix = (df["id_item"].astype(str) + " - " + df["descripcion"].astype(str)).dropna().unique().tolist()
    ix.sort()
    return ix


def build_daily_table_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construye una única tabla diaria sumando `und_dia` por sede para TODAS las empresas presentes.
    - La primera columna es la Fecha formateada "d/abbr"
    - Luego columnas de sedes en orden preferido por empresa (Mercamio, Mercatodo, Bogotá)
    - Última columna "T. Dia"
    - Fila final "Acum. Mes:" con los acumulados por sede y total
    """
    if df.empty:
        return pd.DataFrame()

    # Pivot diario por sede
    pt = pd.pivot_table(
        df,
        index="fecha",
        columns="sede",
        values="und_dia",
        aggfunc="sum",
        fill_value=0.0
    ).sort_index()

    # Armar orden deseado concatenando los preferidos de cada empresa y luego los restantes
    preferred_all = []
    for emp in ["mercamio", "mercatodo", "bogota"]:
        preferred_all += [c for c in PREFERRED_ORDER.get(emp, []) if c in pt.columns]
    # Agregar cualquier sede restante que no esté en las listas anteriores
    preferred_all += [c for c in pt.columns if c not in preferred_all]

    pt = pt.reindex(columns=preferred_all)

    # Total por día
    pt["T. Dia"] = pt.sum(axis=1)

    # Formato de la columna fecha "d/xxx"
    dow = pt.index.dayofweek
    fechas_fmt = [f"{i.day}/{DOW_ABBR_ES.get(dw, '')}" for i, dw in zip(pt.index, dow)]
    pt.insert(0, "Fecha", fechas_fmt)

    # Fila de acumulado del mes
    acum = pt.drop(columns=["Fecha"]).sum(axis=0)
    acum_row = pd.DataFrame([["Acum. Mes:"] + list(acum.values)], columns=["Fecha"] + list(acum.index))
    final = pd.concat([pt.reset_index(drop=True), acum_row], ignore_index=True)

    # Formato numérico bonito
    def _fmt_number(x):
        if pd.isna(x):
            return 0
        if abs(x - int(x)) < 1e-9:
            return int(x)
        return round(x, 1)

    num_cols = [c for c in final.columns if c != "Fecha"]
    for c in num_cols:
        final[c] = final[c].astype(float).map(_fmt_number)

    return final
