
import pandas as pd
import numpy as np

# ======= Mapeos de sedes =======
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
    },
}

# Orden preferido por empresa
PREFERRED_ORDER = {
    "mercamio": ["La 5", "La 39", "Plaza", "Jardin", "C.sur", "Palmira"],
    "mercatodo": ["FTA", "FLA", "MN"],
    "bogota": ["La 80", "Chia"],
}

DOW_ABBR_ES = {0: "lun", 1: "mar", 2: "mié", 3: "jue", 4: "vie", 5: "sáb", 6: "dom"}

def normalize_empresa(x: str) -> str:
    return (x or "").strip().lower()

def normalize_id_co(x) -> str:
    # Soporta 5 -> 005, "005" -> "005"
    try:
        xi = int(str(x).strip())
        return f"{xi:03d}"
    except Exception:
        s = str(x).strip()
        if len(s) >= 3 and s[:3].isdigit():
            return s[:3]
        if s.isdigit():
            return s.zfill(3)
        return s

def map_sede(empresa: str, id_co: str) -> str:
    emp = normalize_empresa(empresa)
    idn = normalize_id_co(id_co)
    mapping = SEDE_MAP.get(emp, {})
    return mapping.get(idn, idn)

def parse_fecha(fecha_series: pd.Series) -> pd.Series:
    # Acepta 20250901, '2025-09-01', '20250901.0'
    s = fecha_series.astype(str).str.replace(r"\.0$", "", regex=True).str.replace("-", "", regex=False)
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")

def prepare_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    required = ["empresa","fecha_dcto","id_co","id_item","descripcion","linea",
                "und_dia","venta_sin_impuesto_dia","und_acum","venta_sin_impuesto_acum"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en el CSV: {missing}")
    df["empresa_norm"] = df["empresa"].apply(normalize_empresa)
    df["id_co_norm"] = df["id_co"].apply(normalize_id_co)
    df["sede"] = [map_sede(e, i) for e, i in zip(df["empresa"], df["id_co"])]
    df["fecha"] = parse_fecha(df["fecha_dcto"])
    for c in ["und_dia","und_acum","venta_sin_impuesto_dia","venta_sin_impuesto_acum"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["descripcion"] = df["descripcion"].astype(str).str.strip()
    return df

def items_display_list(df: pd.DataFrame):
    # Mostrar como "id - descripcion"
    ix = (df["id_item"].astype(str) + " - " + df["descripcion"].astype(str)).dropna().unique().tolist()
    ix.sort()
    return ix

def build_daily_table_all_range(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, footer_label="Acum. Rango:") -> pd.DataFrame:
    """
    Construye una única tabla diaria sumando `und_dia` por sede para TODAS las empresas, entre start y end (inclusive).
    - Index: fecha (se completa con todos los días del rango).
    - Columnas: sedes en orden preferido por empresa + "T. Dia".
    - Primera columna visible: "Fecha" (formato d/abbr, ej. 7/dom).
    - Última fila: totales del rango con etiqueta `footer_label`.
    """
    all_days = pd.date_range(start=start, end=end, freq="D")

    if df.empty:
        base = pd.DataFrame(index=all_days)
        base["T. Dia"] = 0.0
        fechas_fmt = [f"{i.day}/{DOW_ABBR_ES.get(i.dayofweek, '')}" for i in base.index]
        base.insert(0, "Fecha", fechas_fmt)
        final = pd.concat([base.reset_index(drop=True),
                           pd.DataFrame([[footer_label, 0.0]], columns=["Fecha","T. Dia"])],
                          ignore_index=True)
        final["T. Dia"] = final["T. Dia"].astype(float).map(_fmt_number)
        return final

    pt = pd.pivot_table(
        df, index="fecha", columns="sede", values="und_dia",
        aggfunc="sum", fill_value=0.0
    )
    pt = pt.reindex(all_days, fill_value=0.0).sort_index()

    # Orden preferido concatenado por empresa, luego las sedes restantes
    preferred_all = []
    for emp in ["mercamio","mercatodo","bogota"]:
        preferred_all += [c for c in PREFERRED_ORDER.get(emp, []) if c in pt.columns]
    preferred_all += [c for c in pt.columns if c not in preferred_all]
    pt = pt.reindex(columns=preferred_all)

    pt["T. Dia"] = pt.sum(axis=1)

    fechas_fmt = [f"{i.day}/{DOW_ABBR_ES.get(i.dayofweek, '')}" for i in pt.index]
    pt.insert(0, "Fecha", fechas_fmt)

    acum = pt.drop(columns=["Fecha"]).sum(axis=0)
    final = pd.concat([pt.reset_index(drop=True),
                       pd.DataFrame([[footer_label] + list(acum.values)],
                                    columns=["Fecha"] + list(acum.index))],
                      ignore_index=True)

    # Formateo de números
    for c in [c for c in final.columns if c != "Fecha"]:
        final[c] = final[c].astype(float).map(_fmt_number)
    return final

def _fmt_number(x):
    if pd.isna(x):
        return 0
    if abs(x - int(x)) < 1e-9:
        return int(x)
    return round(x, 1)
