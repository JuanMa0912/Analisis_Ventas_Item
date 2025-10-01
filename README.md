
# App: Ventas por Ítem(s) x Sedes — Diario

Pequeña app en Streamlit para cargar un CSV y generar una tabla diaria por **sede** (mapeo por `empresa` + `id_co`), sumando `und_dia` para los ítems seleccionados. Agrega columna **T. Dia** y fila final **Acum. Mes**.

## Ejecutar localmente

```bash
# 1) Crear/activar un virtualenv (opcional)
pip install -r requirements.txt

# 2) Iniciar la app
streamlit run app.py
```

## CSV esperado
Columnas: `empresa,fecha_dcto,id_co,id_item,descripcion,linea,und_dia,venta_sin_impuesto_dia,und_acum,venta_sin_impuesto_acum`

## Notas
- El `id_co` se normaliza a 3 dígitos (e.g., `5` -> `005`).
- `fecha_dcto` se parsea como `YYYYMMDD`.
- Mapeos de sedes:
  - **mercamio**: 001=La 5, 002=La 39, 003=Plaza, 004=Jardin, 005=C.sur, 006=Palmira
  - **mercatodo**: 001=FTA, 002=FLA, 003=MN
  - **bogota**: 001=La 80, 002=Chia
- Orden preferido de columnas por empresa.
