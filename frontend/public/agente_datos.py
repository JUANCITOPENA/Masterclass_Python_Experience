import io
import os
import re
import json
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, date
import math

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    Table, TableStyle, HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

try:
    import pdfplumber
    TIENE_PDFPLUMBER = True
except Exception:
    TIENE_PDFPLUMBER = False

# ==========================================
# 1. CONFIGURACIÓN Y POOL DE MODELOS
# ==========================================
st.set_page_config(page_title="Enterprise BI Copilot 360° · IA & ApexCharts", page_icon="⚡", layout="wide")

MODELOS_POOL = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
]

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/8/8a/Google_Gemini_logo.svg", width=130)
    st.header("⚙️ Configuración")
    API_KEY = st.text_input(
        "Gemini API Key:",
        value="AQ.Ab8RN6JePMHzV5fnnmPDSd-6QmpJ7BnGkYLQgA90Eg-3Tj55Kg",
        type="password",
    )
    st.markdown("**Pool en Cascada Activo:**")
    for idx, m in enumerate(MODELOS_POOL):
        st.caption(f"{idx+1}. `{m}`")

client = None
if API_KEY.strip():
    try:
        client = genai.Client(api_key=API_KEY.strip())
    except Exception as e:
        st.sidebar.error(f"Error al inicializar cliente: {e}")

st.markdown("""
    <style>
    .kpi-card { background-color:#ffffff; border-radius:10px; padding:14px 16px; margin-bottom:10px;
                box-shadow:0 1px 4px rgba(0,0,0,0.06); border-left:6px solid #2563eb; }
    .kpi-title { font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase; letter-spacing:.04em;}
    .kpi-value { font-size:1.40rem; font-weight:800; color:#0f172a; margin-top:3px;}
    .kpi-up   { color:#059669; font-weight:700; font-size:0.85rem;}
    .kpi-down { color:#dc2626; font-weight:700; font-size:0.85rem;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. UTILIDADES DE TEXTO, ETL Y FORMATEO
# ==========================================
LEET_DICT = {
    '@': 'a', '4': 'a', '3': 'e', '1': 'i', '!': 'i',
    '0': 'o', '5': 's', '$': 's', '7': 't', '#': ''
}

def desinfectar_leetspeak(texto):
    if not isinstance(texto, str): return texto
    t = texto.strip()
    for k, v in LEET_DICT.items():
        t = t.replace(k, v)
    t = re.sub(r"[#\$]+$", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.title()

def quitar_acentos(txt):
    if not isinstance(txt, str): return str(txt)
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")

def normalizar_col(col):
    col = quitar_acentos(str(col)).strip().lower()
    col = re.sub(r"[^\w]+", "_", col)
    return re.sub(r"_+", "_", col).strip("_")

def a_numero(serie):
    """Convierte con tolerancia extrema cadenas con comas, comillas, símbolos y negativos a float puro."""
    if isinstance(serie, (int, float, np.number)):
        return float(serie)
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce").fillna(0.0)
    
    limpio = (
        serie.astype(str)
        .str.replace(r'["\']', '', regex=True)
        .str.replace(r'[^\d,.\-()]', '', regex=True)
        .str.replace(r'\((\d+(\.\d+)?)\)', r'-\1', regex=True) # Formato contable (12.25) -> -12.25
        .str.replace(r'\.(?=\d{3}(\D|$))', '', regex=True)   # Separador de miles con punto
        .str.replace(',', '.', regex=False)                    # Coma decimal a punto
    )
    return pd.to_numeric(limpio, errors="coerce").fillna(0.0)

def convertir_fecha_excel_o_cadena(serie):
    if pd.api.types.is_numeric_dtype(serie):
        if serie.dropna().between(35000, 60000).mean() > 0.5:
            return pd.to_datetime('1899-12-30') + pd.to_timedelta(serie, 'D')
    return pd.to_datetime(serie, errors="coerce", dayfirst=True)

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    try:
        p1_lat, p1_lon = math.radians(float(lat1)), math.radians(float(lon1))
        p2_lat, p2_lon = math.radians(float(lat2)), math.radians(float(lon2))
        dlat = p2_lat - p1_lat
        dlon = p2_lon - p1_lon
        a = math.sin(dlat / 2)**2 + math.cos(p1_lat) * math.cos(p2_lat) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(R * c, 2)
    except Exception:
        return np.nan

def fmt_money(v):
    try: return f"$ {float(v):,.2f}" if not pd.isna(v) else "$ 0.00"
    except: return "$ 0.00"

def fmt_pct(v):
    try: return f"{float(v):,.1f}%" if not pd.isna(v) else "0.0%"
    except: return "0.0%"

def fmt_num(v):
    try: return f"{float(v):,.0f}" if not pd.isna(v) else "0"
    except: return "0"

def serializar_para_json(obj):
    if isinstance(obj, dict): return {str(k): serializar_para_json(v) for k, v in obj.items()}
    elif isinstance(obj, list): return [serializar_para_json(i) for i in obj]
    elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)): return int(obj)
    elif isinstance(obj, (np.float64, np.float32)): return float(obj) if not np.isnan(obj) else None
    elif isinstance(obj, (pd.Timestamp, datetime, date)): return obj.isoformat()
    return obj

def limpiar_etiquetas_html(texto):
    if not texto: return ""
    return re.sub(r"<[^>]+>", "", str(texto))

def formatear_texto_web(texto):
    if not texto: return ""
    t = limpiar_etiquetas_html(texto)
    return re.sub(r"\$(\d)", r"$ \1", t)

def limpiar_texto_para_pdf(texto):
    if not texto: return ""
    t = limpiar_etiquetas_html(texto)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"[\U00010000-\U0010ffff\u2600-\u27BF]", "", t)

# ==========================================
# 3. CARGA MULTI-FORMATO & PIPELINE ETL
# ==========================================
def cargar_archivo(archivo):
    nombre = archivo.name
    contenido = archivo.read()
    ext = nombre.lower().rsplit(".", 1)[-1]
    dfs = {}
    try:
        if ext in ["csv", "txt"]:
            for sep in [",", ";", "\t", "|"]:
                try:
                    df = pd.read_csv(io.BytesIO(contenido), sep=sep, engine="python")
                    if df.shape[1] > 1:
                        dfs[nombre] = df
                        break
                except Exception:
                    continue
            if not dfs:
                dfs[nombre] = pd.read_csv(io.BytesIO(contenido), engine="python")
        elif ext in ["xlsx", "xls"]:
            hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None)
            for hoja, df in hojas.items():
                dfs[f"{nombre} [{hoja}]"] = df
        elif ext == "json":
            data = json.loads(contenido.decode("utf-8", errors="ignore"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                        dfs[f"{nombre} · {k}"] = pd.json_normalize(v)
                if not dfs:
                    dfs[nombre] = pd.json_normalize(data)
            else:
                dfs[nombre] = pd.json_normalize(data)
        elif ext == "xml":
            root = ET.fromstring(contenido)
            filas = list(root)
            registros = [{h.tag: h.text for h in f} if list(f) else dict(f.attrib) for f in filas]
            dfs[nombre] = pd.DataFrame(registros)
        elif ext == "sql":
            script = contenido.decode("utf-8", errors="ignore")
            conn = sqlite3.connect(":memory:")
            conn.executescript(script)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas = [t[0] for t in cur.fetchall()]
            for t in tablas:
                dfs[f"{nombre} · {t}"] = pd.read_sql_query(f"SELECT * FROM {t}", conn)
            conn.close()
        elif ext == "pdf" and TIENE_PDFPLUMBER:
            with pdfplumber.open(io.BytesIO(contenido)) as pdf:
                for i, pag in enumerate(pdf.pages):
                    for j, tb in enumerate(pag.extract_tables()):
                        if len(tb) >= 2:
                            headers = [normalizar_col(c) if c else f"col_{idx}" for idx, c in enumerate(tb[0])]
                            dfs[f"{nombre} [pág_{i+1}_t{j+1}]"] = pd.DataFrame(tb[1:], columns=headers)
    except Exception as e:
        st.error(f"Error procesando {nombre}: {e}")
    return dfs

def limpiar_dataframe(df):
    audit_log = []
    df = df.copy()
    df.columns = [normalizar_col(c) for c in df.columns]
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.loc[:, ~df.columns.duplicated()]
    duplicados = int(df.duplicated().sum())
    if duplicados > 0:
        audit_log.append(f"Se eliminaron {duplicados} registros duplicados.")
    df = df.drop_duplicates()

    leet_corregidos = 0
    for col in df.columns:
        if df[col].dtype == object:
            muestra = df[col].dropna().astype(str).head(30)
            if len(muestra) == 0: continue
            
            if any(k in col for k in ["cliente", "chofer", "terminal", "ruta", "producto", "vendedor", "nombre", "categoria", "departamento", "responsable", "cuenta"]):
                antes = df[col].astype(str)
                df[col] = df[col].apply(desinfectar_leetspeak)
                leet_corregidos += int((antes != df[col]).sum())

            if any(k in col for k in ["fecha", "date", "vencimiento", "entrega", "periodo", "salida", "llegada", "hora"]):
                df[col] = convertir_fecha_excel_o_cadena(df[col])
                continue

            # Limpieza de montos monetarios o con comas
            if muestra.str.contains(r"[\d]", regex=True).mean() > 0.6:
                c_num = a_numero(df[col])
                if c_num.notna().mean() > 0.5:
                    df[col] = c_num

    if leet_corregidos > 0:
        audit_log.append(f"Se normalizaron {leet_corregidos} celdas con caracteres Leetspeak/espacios extra.")

    return df, duplicados, audit_log

def clasificar_dataset(df):
    cols = " ".join(df.columns)
    scores = {
        "ventas": sum(1 for w in ["venta", "ingreso", "precio", "factura", "meta", "vendedor", "costo", "total_factura"] if w in cols),
        "inventario": sum(1 for w in ["stock", "inventario", "entrada", "salida", "sku", "almacen", "reorden", "perecedero", "caducidad", "lote"] if w in cols),
        "cuentas_por_cobrar": sum(1 for w in ["cobrar", "cliente", "saldo", "deuda", "atraso", "mora", "cxc", "dias_mora"] if w in cols),
        "cuentas_por_pagar": sum(1 for w in ["pagar", "proveedor", "costo", "compra", "cxp"] if w in cols),
        "entregas": sum(1 for w in ["entrega", "envio", "tracking", "transportista"] if w in cols),
        "transporte": sum(1 for w in ["chofer", "terminal", "boleto", "pasaje", "ticket", "retraso", "asiento"] if w in cols),
        "contabilidad": sum(1 for w in ["debito", "credito", "asiento", "cuenta_contable", "moneda"] if w in cols)
    }
    top = max(scores, key=scores.get)
    return top if scores[top] > 0 else "ventas"

MAPEOS_SUGERIDOS = {
    "ventas": {
        "fecha": ["fecha", "date", "periodo"],
        "ingresos": ["total_factura", "venta_real", "ingreso", "venta", "revenue", "monto", "total", "precio"],
        "costos": ["costo", "cost", "gasto"],
        "meta": ["meta", "target", "objetivo", "budget", "meta_ventas"],
        "categoria": ["sucursal", "producto", "categoria", "cliente", "vendedor", "region"],
    },
    "inventario": {
        "fecha": ["fecha_entrada", "fecha", "date"],
        "entradas": ["entradas", "entrada", "ingreso", "recibido", "compra"],
        "salidas": ["salidas", "salida", "consumo", "despacho"],
        "stock_actual": ["stock_actual", "stock", "existencia", "cantidad", "unidades"],
        "costo_unitario": ["costo_unitario", "costo", "precio_unitario"],
        "punto_reorden": ["stock_minimo", "reorden", "minimo", "seguridad"],
        "fecha_vencimiento": ["fecha_vencimiento", "vencimiento", "caducidad", "dias_vencer"],
        "categoria": ["producto", "sku", "descripcion", "almacen", "categoria"],
    },
    "cuentas_por_cobrar": {
        "saldo": ["monto_factura", "saldo", "monto", "deuda", "total"],
        "fecha_vencimiento": ["fecha_vencimiento", "vencimiento", "fecha_limite", "dias_mora"],
        "fecha_pago": ["fecha_pago", "pagado", "cobro"],
        "tipo_pago": ["tipo_pago", "metodo", "forma_pago", "condicion"],
        "categoria": ["cliente", "deudor", "razon_social"],
    },
    "cuentas_por_pagar": {
        "saldo": ["saldo", "monto", "deuda", "total"],
        "fecha_vencimiento": ["vencimiento", "fecha_limite"],
        "fecha_pago": ["fecha_pago", "pagado"],
        "tipo_pago": ["tipo_pago", "metodo", "forma_pago"],
        "categoria": ["proveedor", "acreedor", "beneficiario"],
    },
    "entregas": {
        "fecha": ["fecha", "fecha_entrega"],
        "status": ["status", "estado", "situacion"],
        "categoria": ["transportista", "ruta", "region", "cliente"],
    },
    "transporte": {
        "fecha": ["fecha", "fecha_hora_salida", "date"],
        "ingresos": ["precio_ticket", "total_recaudado", "precio", "monto"],
        "status": ["estatus", "status", "estado"],
        "categoria": ["ruta", "destino", "chofer", "terminal"],
    },
    "contabilidad": {
        "fecha": ["fecha_hora", "fecha"],
        "ingresos": ["credito", "debito"],
        "costos": ["debito", "credito"],
        "categoria": ["cuenta_contable", "departamento", "tipo_cuenta", "responsable"]
    }
}

def buscar_col(df, candidatas):
    for c in candidatas:
        for col in df.columns:
            if c in col: return col
    return None

# ==========================================
# 4. MOTOR DE NEGOCIO Y CÁLCULOS KPI
# ==========================================
def calcular_kpis_completos(df, tipo, m):
    kpis, tablas = {}, {}

    if tipo in ["ventas", "contabilidad"]:
        ing_col = m.get("ingresos")
        if ing_col:
            ing = a_numero(df[ing_col])
            kpis["ingresos_totales"] = float(ing.sum())
            kpis["ticket_promedio"] = float(ing.mean())
            kpis["operaciones"] = int(len(ing))

            if m.get("costos"):
                costo = a_numero(df[m["costos"]])
                kpis["costos_totales"] = float(costo.sum())
                kpis["margen_bruto"] = float(kpis["ingresos_totales"] - kpis["costos_totales"])
                kpis["pct_margen"] = float((kpis["margen_bruto"] / kpis["ingresos_totales"] * 100)) if kpis["ingresos_totales"] > 0 else 0.0

            if m.get("meta"):
                meta_tot = float(a_numero(df[m["meta"]]).sum())
                kpis["meta_total"] = meta_tot
                kpis["pct_cumplimiento_meta"] = float((kpis["ingresos_totales"] / meta_tot * 100)) if meta_tot > 0 else 0.0

        if m.get("categoria") and ing_col:
            cat = m["categoria"]
            df_temp = df[[cat, ing_col]].copy()
            df_temp[ing_col] = a_numero(df_temp[ing_col])
            t_cat = df_temp.groupby(cat)[ing_col].agg(["sum", "count", "mean"]).reset_index()
            t_cat.columns = [cat.title(), "Total ($)", "Operaciones (#)", "Promedio ($)"]
            t_cat = t_cat.sort_values(by="Total ($)", ascending=False)
            t_cat["% Participación"] = (t_cat["Total ($)"] / t_cat["Total ($)"].sum() * 100).round(1)
            tablas["resumen_categoria"] = t_cat

    elif tipo == "inventario":
        ent_col, sal_col = m.get("entradas"), m.get("salidas")
        stk_col = m.get("stock_actual")

        if ent_col: kpis["entradas_totales"] = float(a_numero(df[ent_col]).sum())
        if sal_col: kpis["salidas_totales"] = float(a_numero(df[sal_col]).sum())

        if stk_col: kpis["stock_actual"] = float(a_numero(df[stk_col]).sum())
        elif ent_col and sal_col: kpis["stock_actual"] = float(kpis["entradas_totales"] - kpis["salidas_totales"])

        stock_ref = kpis.get("stock_actual", 0.0)
        if m.get("costo_unitario") and stock_ref > 0:
            kpis["costo_stock_actual"] = float(stock_ref * a_numero(df[m["costo_unitario"]]).mean())

        if kpis.get("salidas_totales", 0) > 0 and stock_ref > 0:
            rot = kpis["salidas_totales"] / stock_ref
            kpis["rotacion_inventario"] = float(rot)
            kpis["dias_disponibles_inventario"] = float(365 / rot) if rot > 0 else 0.0

        if m.get("fecha_vencimiento"):
            hoy = pd.Timestamp(date.today())
            venc_val = df[m["fecha_vencimiento"]]
            if pd.api.types.is_numeric_dtype(venc_val):
                dias = a_numero(venc_val)
            else:
                venc = pd.to_datetime(venc_val, errors="coerce")
                dias = (venc - hoy).dt.days.fillna(999)

            estatus_v = np.select([dias < 0, dias <= 7, dias <= 30], ["Vencido (Destruir)", "Crítico (≤7d)", "Por Vencer (≤30d)"], default="Fresco")
            kpis["resumen_vencimientos"] = pd.Series(estatus_v).value_counts().to_dict()

            riesgo = df[dias <= 30].copy()
            if not riesgo.empty:
                col_ver = [c for c in [m.get("categoria"), m["fecha_vencimiento"], stk_col] if c]
                tablas["alertas_vencimiento"] = riesgo[col_ver].head(25)

        if m.get("punto_reorden") and stk_col:
            reorden = a_numero(df[m["punto_reorden"]])
            stock = a_numero(df[stk_col])
            estatus_s = np.select([stock <= reorden, stock > reorden * 3], ["Quiebre / Bajo", "Sobre-Stock"], default="Óptimo")
            kpis["resumen_salud_stock"] = pd.Series(estatus_s).value_counts().to_dict()

            quiebres = df[stock <= reorden].copy()
            if not quiebres.empty:
                col_s = [c for c in [m.get("categoria"), stk_col, m["punto_reorden"]] if c]
                tablas["alertas_stock_bajo"] = quiebres[col_s].head(25)

    elif tipo in ["cuentas_por_cobrar", "cuentas_por_pagar"]:
        saldo_col = m.get("saldo")
        if saldo_col:
            saldos = a_numero(df[saldo_col])
            kpis["valor_actual_deuda"] = float(saldos.sum())
            kpis["deuda_promedio"] = float(saldos.mean())

        if m.get("fecha_vencimiento"):
            hoy = pd.Timestamp(date.today())
            venc_col = df[m["fecha_vencimiento"]]
            if pd.api.types.is_numeric_dtype(venc_col):
                dias_atraso = a_numero(venc_col)
            else:
                venc = pd.to_datetime(venc_col, errors="coerce")
                dias_atraso = (hoy - venc).dt.days.fillna(0)

            status = np.select([dias_atraso <= 0, dias_atraso > 45], ["Al Día", "Mora Crítica (>45d)"], default="Mora Leve (1-45d)")
            kpis["resumen_status_pago"] = pd.Series(status).value_counts().to_dict()

            buckets = pd.cut(
                dias_atraso,
                bins=[-99999, 0, 15, 30, 45, 999999],
                labels=["Al Día", "1-15 días", "16-30 días", "31-45 días", "46+ días (Crítica)"]
            )
            kpis["aging_buckets"] = buckets.value_counts().to_dict()

            if saldo_col:
                df_aging = pd.DataFrame({"Aging": buckets, "Monto": saldos}).groupby("Aging", observed=False)["Monto"].agg(["sum", "count"]).reset_index()
                prov_map = {"Al Día": 0.0, "1-15 días": 0.01, "16-30 días": 0.05, "31-45 días": 0.20, "46+ días (Crítica)": 0.50}
                df_aging["Tasa_Prov"] = df_aging["Aging"].map(prov_map)
                df_aging["Provision_$"] = df_aging["sum"] * df_aging["Tasa_Prov"]
                df_aging.columns = ["Tramo Mora", "Total ($)", "Cuentas (#)", "Tasa Prov.", "Provisión ($)"]
                tablas["matriz_aging"] = df_aging

        if m.get("tipo_pago"):
            kpis["resumen_tipos_pago"] = df[m["tipo_pago"]].value_counts().head(5).to_dict()

    elif tipo == "entregas":
        if m.get("status"):
            vc = df[m["status"]].value_counts()
            kpis["resumen_entregas"] = vc.to_dict()
            tot = vc.sum()
            a_tiempo = sum(v for k, v in vc.items() if any(ok in str(k).lower() for ok in ["ok", "entregado", "cumplido", "tiempo"]))
            kpis["pct_entregas_efectivas"] = float((a_tiempo / tot * 100)) if tot > 0 else 0.0

    elif tipo == "transporte":
        ing_col = m.get("ingresos")
        stat_col = m.get("status")
        precios = a_numero(df[ing_col]) if ing_col else pd.Series([0])
        c_retraso = next((c for c in df.columns if any(k in c for k in ["retraso", "minutos_retraso"])), None)
        retrasos = a_numero(df[c_retraso]) if c_retraso else pd.Series([0])

        if stat_col:
            vc = df[stat_col].astype(str).str.lower().value_counts()
            total_v = len(df)
            comp = sum(v for k, v in vc.items() if any(w in k for w in ["completa", "ok", "tiempo"]))
            canc = sum(v for k, v in vc.items() if "cancel" in k)
            kpis["ingresos_totales"] = float(precios[df[stat_col].astype(str).str.lower().str.contains("completa|ok")].sum())
            kpis["perdida_cancelacion"] = float(precios[df[stat_col].astype(str).str.lower().str.contains("cancel")].sum())
            kpis["puntualidad_otp"] = float((comp / total_v * 100)) if total_v > 0 else 0.0
            kpis["tasa_cancelacion"] = float((canc / total_v * 100)) if total_v > 0 else 0.0

        kpis["minutos_promedio_retraso"] = float(retrasos.mean())
        c_chof = next((c for c in df.columns if "chofer" in c), None)
        if c_chof and stat_col:
            df_ch = df.groupby(c_chof).agg(
                Viajes=(stat_col, "count"),
                Retraso_Min=(c_retraso, "mean") if c_retraso else (stat_col, "count"),
                Recaudacion=(ing_col, "sum") if ing_col else (stat_col, "count")
            ).reset_index().sort_values(by="Retraso_Min", ascending=True)
            tablas["scoring_choferes"] = df_ch

    return kpis, tablas

def calcular_cruzado_360(datasets, kpis_global):
    cruzado = {}
    v_tot = 0.0
    mora_critica = 0.0
    inv_vencido = 0.0

    for ds_name, kp in kpis_global.items():
        if "ingresos_totales" in kp:
            v_tot += kp["ingresos_totales"]
        if "aging_buckets" in kp and "46+ días (Crítica)" in kp["aging_buckets"]:
            mora_critica += float(kp["aging_buckets"]["46+ días (Crítica)"])
        if "resumen_status_pago" in kp and "Mora Crítica (>45d)" in kp["resumen_status_pago"]:
            mora_critica += float(kp.get("valor_actual_deuda", 0.0)) * 0.4
        if "costo_stock_actual" in kp and "resumen_vencimientos" in kp:
            inv_vencido += float(kp["costo_stock_actual"]) * 0.15

    perdida_total = mora_critica + inv_vencido
    impacto_ventas = (perdida_total / v_tot * 100) if v_tot > 0 else 0.0

    cruzado["perdida_total_expuesta"] = perdida_total
    cruzado["impacto_ventas_pct"] = impacto_ventas
    cruzado["venta_total_pool"] = v_tot
    return cruzado

def comparar_periodos(df, col_fecha, col_valor):
    d = df[[col_fecha, col_valor]].copy()
    d[col_fecha] = pd.to_datetime(d[col_fecha], errors="coerce")
    d[col_valor] = a_numero(d[col_valor])
    d = d.dropna()
    if d.empty or len(d) < 2: return None

    d["anio"] = d[col_fecha].dt.year
    d["mes"] = d[col_fecha].dt.month
    u_fec = d[col_fecha].max()
    cy, cm = u_fec.year, u_fec.month
    py = cy - 1
    pm = 12 if cm == 1 else cm - 1
    py_pm = cy - 1 if cm == 1 else cy

    def calc_s(y, m=None):
        sub = d[d["anio"] == y]
        if m: sub = sub[sub["mes"] == m]
        return float(sub[col_valor].sum())

    v_cy, v_py = calc_s(cy), calc_s(py)
    v_cm, v_pm = calc_s(cy, cm), calc_s(py_pm, pm)
    v_sm_py = calc_s(py, cm)

    def pct_d(act, ant):
        return ((act - ant) / abs(ant) * 100) if ant and ant != 0 else 0.0

    return {
        "cy": cy, "v_cy": v_cy, "py": py, "v_py": v_py, "yoy_pct": pct_d(v_cy, v_py),
        "cm": cm, "v_cm": v_cm, "v_pm": v_pm, "mom_pct": pct_d(v_cm, v_pm),
        "v_sm_py": v_sm_py, "yoy_same_month_pct": pct_d(v_cm, v_sm_py)
    }

# ==========================================
# 5. GENERACIÓN WEB: TOP 5 GRÁFICOS APEXCHARTS
# ==========================================
def render_apex_chart(chart_id, options_dict, height=340):
    opts_json = json.dumps(options_dict)
    html_code = f"""
    <div id="{chart_id}" style="min-height: {height}px;"></div>
    <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
    <script>
        var options_{chart_id} = {opts_json};
        var chart_{chart_id} = new ApexCharts(document.querySelector("#{chart_id}"), options_{chart_id});
        chart_{chart_id}.render();
    </script>
    """
    components.html(html_code, height=height + 25)

def apex_radial_okr(pct_valor, titulo="Cumplimiento de Meta (OKR)"):
    return {
        "chart": {"height": 300, "type": "radialBar"},
        "series": [min(100.0, round(float(pct_valor), 1))],
        "plotOptions": {
            "radialBar": {
                "hollow": {"size": "65%"},
                "dataLabels": {
                    "name": {"show": True, "fontSize": "13px", "color": "#64748b", "offsetY": -10},
                    "value": {"show": True, "fontSize": "22px", "fontWeight": 800, "color": "#1e293b"}
                }
            }
        },
        "fill": {"colors": ["#10b981" if pct_valor >= 100 else ("#f59e0b" if pct_valor >= 75 else "#ef4444")]},
        "labels": [titulo]
    }

def apex_combo_pareto(df, col_cat, col_val, titulo="Ranking & Concentración Pareto"):
    df_calc = df[[col_cat, col_val]].copy().dropna()
    df_calc[col_val] = a_numero(df_calc[col_val])
    res_num = df_calc.groupby(col_cat)[col_val].sum()
    df_top = pd.to_numeric(res_num, errors='coerce').fillna(0).nlargest(8).reset_index()
    
    total_val = df_top[col_val].sum() or 1.0
    df_top["acum_pct"] = (df_top[col_val].cumsum() / total_val * 100).round(1)

    return {
        "chart": {"height": 330, "type": "line", "toolbar": {"show": False}},
        "series": [
            {"name": col_val.title(), "type": "column", "data": [round(float(v), 2) for v in df_top[col_val]]},
            {"name": "% Acumulado", "type": "line", "data": [float(v) for v in df_top["acum_pct"]]}
        ],
        "stroke": {"width": [0, 3], "curve": "smooth"},
        "colors": ["#2563eb", "#ef4444"],
        "xaxis": {"categories": [str(c) for c in df_top[col_cat]]},
        "yaxis": [
            {"title": {"text": col_val.title()}},
            {"opposite": True, "title": {"text": "% Acumulado"}, "max": 100}
        ],
        "title": {"text": titulo, "style": {"fontSize": "13px", "fontWeight": "bold"}}
    }

def apex_spline_time(df, col_fecha, col_val, titulo="Evolución Histórica"):
    sub = df[[col_fecha, col_val]].copy()
    sub[col_fecha] = pd.to_datetime(sub[col_fecha], errors="coerce")
    sub[col_val] = a_numero(sub[col_val])
    sub = sub.dropna().sort_values(by=col_fecha)

    if len(sub) > 30:
        sub['periodo'] = sub[col_fecha].dt.to_period('M').astype(str)
        sub = sub.groupby('periodo')[col_val].sum().reset_index()
        cats, vals = list(sub['periodo']), [round(float(v), 2) for v in sub[col_val]]
    else:
        cats, vals = list(sub[col_fecha].dt.strftime('%d/%m')), [round(float(v), 2) for v in sub[col_val]]

    return {
        "chart": {"height": 320, "type": "area", "toolbar": {"show": True}},
        "dataLabels": {"enabled": False},
        "stroke": {"curve": "smooth", "width": 2.5},
        "colors": ["#059669"],
        "series": [{"name": col_val.title(), "data": vals}],
        "xaxis": {"categories": cats},
        "fill": {"type": "gradient", "gradient": {"shadeIntensity": 1, "opacityFrom": 0.65, "opacityTo": 0.05}},
        "title": {"text": titulo, "style": {"fontSize": "13px", "fontWeight": "bold"}}
    }

def apex_donut_status(dicc_datos, titulo="Distribución Operativa"):
    limpio = {str(k): float(v) for k, v in dicc_datos.items() if pd.notna(v) and float(a_numero(v)) > 0}
    return {
        "chart": {"height": 310, "type": "donut"},
        "series": list(limpio.values()),
        "labels": list(limpio.keys()),
        "colors": ["#1e40af", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"],
        "legend": {"position": "bottom"},
        "title": {"text": titulo, "style": {"fontSize": "13px", "fontWeight": "bold"}}
    }

def apex_aging_bar(dicc_aging, titulo="Envejecimiento de Cartera (Mora)"):
    cats = list(dicc_aging.keys())
    vals = [float(a_numero(v)) for v in dicc_aging.values()]
    return {
        "chart": {"height": 310, "type": "bar", "toolbar": {"show": False}},
        "plotOptions": {"bar": {"borderRadius": 5, "columnWidth": "45%", "distributed": True}},
        "colors": ["#10b981", "#f59e0b", "#f97316", "#dc2626"][:len(cats)],
        "series": [{"name": "Cuentas", "data": vals}],
        "xaxis": {"categories": cats},
        "legend": {"show": False},
        "title": {"text": titulo, "style": {"fontSize": "13px", "fontWeight": "bold"}}
    }

# ==========================================
# 6. GRÁFICOS STATIC MATPLOTLIB + INTERPRETACIÓN PDF
# ==========================================
def fig_to_buffer(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=190, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf

def static_ranking_top(df, col_cat, col_val, titulo):
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    df_calc = df[[col_cat, col_val]].copy().dropna()
    df_calc[col_val] = a_numero(df_calc[col_val])
    res_num = df_calc.groupby(col_cat)[col_val].sum()
    res = pd.to_numeric(res_num, errors='coerce').fillna(0).nlargest(8).reset_index()

    bars = ax.barh(res[col_cat].astype(str), res[col_val], color="#2563eb", height=0.6)
    ax.invert_yaxis()
    ax.set_title(titulo, fontsize=10, fontweight="bold")
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    for b in bars:
        w = b.get_width()
        ax.annotate(f" {w:,.0f}", (w, b.get_y() + b.get_height() / 2), va="center", fontsize=7.5, fontweight="bold")
    plt.tight_layout()
    return fig_to_buffer(fig)

def static_line_time(df, col_fecha, col_val, titulo):
    fig, ax = plt.subplots(figsize=(7, 3.2))
    sub = df[[col_fecha, col_val]].copy()
    sub[col_fecha] = pd.to_datetime(sub[col_fecha], errors="coerce")
    sub[col_val] = a_numero(sub[col_val])
    sub = sub.dropna().sort_values(by=col_fecha)
    if len(sub) > 30:
        sub['periodo'] = sub[col_fecha].dt.to_period('M').astype(str)
        sub = sub.groupby('periodo')[col_val].sum().reset_index()
        x, y = sub['periodo'], sub[col_val]
    else:
        x, y = sub[col_fecha].dt.strftime('%d/%m'), sub[col_val]
    ax.plot(x, y, marker="o", color="#059669", linewidth=2, markersize=3.5)
    ax.axhline(y.mean(), color="#ef4444", linestyle="--", label=f"Media: {y.mean():,.0f}")
    ax.legend(fontsize=7.5)
    ax.set_title(titulo, fontsize=10, fontweight="bold")
    plt.xticks(rotation=30, ha="right", fontsize=7.5)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    plt.tight_layout()
    return fig_to_buffer(fig)

# ==========================================
# 7. GENERACIÓN DEL REPORTE PDF CON INTERPRETACIÓN
# ==========================================
def crear_pdf_reporte(nombre_doc, audiencia, kpis_por_ds, comparativos, narrativa, items_visuales, cruzado_360=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=34, rightMargin=34, topMargin=34, bottomMargin=34)
    styles = getSampleStyleSheet()

    color_corp = colors.HexColor("#1E3A8A") if audiencia == "directiva" else colors.HexColor("#0F172A")
    titulo_est = ParagraphStyle('T1', parent=styles['Heading1'], fontSize=15, textColor=color_corp, spaceAfter=2)
    sub_est = ParagraphStyle('Tsub', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor("#64748B"), spaceAfter=8)
    h2_est = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=10.5, textColor=color_corp, spaceBefore=8, spaceAfter=4)
    b_est = ParagraphStyle('B', parent=styles['Normal'], fontSize=8, leading=11, textColor=colors.HexColor("#1F2937"), spaceAfter=3)
    th_est = ParagraphStyle('TH', parent=styles['Normal'], fontSize=7.5, leading=9, textColor=colors.HexColor("#FFFFFF"), fontName="Helvetica-Bold")
    td_est = ParagraphStyle('TD', parent=styles['Normal'], fontSize=7.5, leading=9, textColor=colors.HexColor("#1F2937"))
    interp_box_est = ParagraphStyle('InterpBox', parent=styles['Normal'], fontSize=7.8, leading=10.5, textColor=colors.HexColor("#334155"))

    story = [
        Paragraph(limpiar_texto_para_pdf(f"INFORME INTEGRAL DE GESTIÓN BI — AUDIENCIA: {audiencia.upper()}"), titulo_est),
        Paragraph(limpiar_texto_para_pdf(f"Generado con IA Multi-Modelo | Fuentes: <b>{nombre_doc}</b>"), sub_est),
        HRFlowable(width="100%", thickness=1.5, color=color_corp, spaceAfter=8),
        Paragraph("1. Cuadro de Mando Integral y KPIs", h2_est)
    ]

    if cruzado_360 and cruzado_360.get("perdida_total_expuesta", 0) > 0:
        filas_360 = [
            [Paragraph("Métrica Cruzada C-Suite", th_est), Paragraph("Valor Consolidado", th_est)],
            [Paragraph("Pérdida Total Expuesta (Mora + Inventario)", td_est), Paragraph(fmt_money(cruzado_360["perdida_total_expuesta"]), td_est)],
            [Paragraph("% Impacto sobre Facturación Total", td_est), Paragraph(fmt_pct(cruzado_360["impacto_ventas_pct"]), td_est)]
        ]
        t_360 = Table(filas_360, colWidths=[270, 270])
        t_360.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#DC2626")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_360)
        story.append(Spacer(1, 6))

    for ds_name, kp in kpis_por_ds.items():
        filas = [[Paragraph("Métrica / Variable", th_est), Paragraph("Valor", th_est)]]
        for k, v in kp.items():
            if isinstance(v, dict): v_str = ", ".join(f"{kk}: {vv}" for kk, vv in v.items())
            elif isinstance(v, float): v_str = f"{v:,.2f}"
            else: v_str = str(v)
            filas.append([Paragraph(k.replace('_', ' ').title(), td_est), Paragraph(v_str, td_est)])

        story.append(Paragraph(limpiar_texto_para_pdf(f"<b>Dataset: {ds_name}</b>"), b_est))
        t_kpi = Table(filas, colWidths=[270, 270])
        t_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), color_corp),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_kpi)
        story.append(Spacer(1, 6))

    if comparativos:
        story.append(Paragraph("2. Comparativa Temporal (Time-Intelligence)", h2_est))
        for ds_name, comp in comparativos.items():
            if not comp: continue
            filas_c = [
                [Paragraph("Periodo", th_est), Paragraph("Valor", th_est), Paragraph("Variación", th_est)],
                [Paragraph(f"Año {comp['cy']} (Actual)", td_est), Paragraph(fmt_money(comp['v_cy']), td_est), Paragraph("-", td_est)],
                [Paragraph(f"Año {comp['py']} (Previo)", td_est), Paragraph(fmt_money(comp['v_py']), td_est), Paragraph(fmt_pct(comp['yoy_pct']), td_est)],
                [Paragraph("Mes Actual", td_est), Paragraph(fmt_money(comp['v_cm']), td_est), Paragraph("-", td_est)],
                [Paragraph("Mes Anterior", td_est), Paragraph(fmt_money(comp['v_pm']), td_est), Paragraph(fmt_pct(comp['mom_pct']), td_est)],
                [Paragraph("Mismo Mes Año Anterior", td_est), Paragraph(fmt_money(comp['v_sm_py']), td_est), Paragraph(fmt_pct(comp['yoy_same_month_pct']), td_est)],
            ]
            t_c = Table(filas_c, colWidths=[180, 180, 180])
            t_c.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#334155")),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ('PADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(t_c)
            story.append(Spacer(1, 6))

    story.append(Paragraph("3. Dictamen y Conclusiones del Agente IA", h2_est))
    if narrativa:
        for par in narrativa.split("\n"):
            if par.strip():
                story.append(Paragraph(limpiar_texto_para_pdf(par.strip()), b_est))

    if items_visuales:
        story.append(Spacer(1, 6))
        story.append(Paragraph("4. Curvas de Comportamiento e Interpretación Detallada", h2_est))
        for item in items_visuales:
            story.append(RLImage(item["buffer"], width=500, height=185))
            interp_texto = f"""
            <b>📌 Lectura del Gráfico:</b> {item['lectura']}<br/>
            <b>🔍 Diagnóstico Clave:</b> {item['diagnostico']}<br/>
            <b>🚀 Acción Recomendada:</b> {item['accion']}
            """
            t_interp = Table([[Paragraph(limpiar_texto_para_pdf(interp_texto), interp_box_est)]], colWidths=[500])
            t_interp.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor("#94A3B8")),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(t_interp)
            story.append(Spacer(1, 8))

    doc.build(story)
    buf.seek(0)
    return buf

# ==========================================
# 8. POOL CON FALLBACK & STREAMING
# ==========================================
def llamar_ia_pool(prompt_text):
    if not client: return None, None
    for m in MODELOS_POOL:
        try:
            res = client.models.generate_content(model=m, contents=prompt_text)
            if res and res.text: return res.text, m
        except Exception:
            continue
    return None, None

def llamar_ia_stream(prompt_text):
    if not client:
        yield "⚠️ Configura una API Key válida de Gemini en la barra lateral."
        return
    for m in MODELOS_POOL:
        try:
            stream = client.models.generate_content_stream(model=m, contents=prompt_text)
            ok = False
            for chunk in stream:
                if chunk.text:
                    ok = True
                    yield chunk.text
            if ok: return
        except Exception:
            continue
    yield "❌ Error al conectar con el pool de modelos."

# ==========================================
# 9. RENDERIZADOR VISUAL EN CHAT
# ==========================================
def renderizar_tablero_completo_en_chat(ds_clave=None):
    if not st.session_state.datasets:
        st.warning("No hay datasets cargados.")
        return

    ds_target = ds_clave if ds_clave in st.session_state.datasets else list(st.session_state.datasets.keys())[0]
    df = st.session_state.datasets[ds_target]
    kps = st.session_state.kpis_global.get(ds_target, {})
    m_pdf = MAPEOS_SUGERIDOS.get(st.session_state.clasificacion.get(ds_target, "ventas"), {})
    c_cat = buscar_col(df, m_pdf.get("categoria", []))
    c_val = buscar_col(df, m_pdf.get("ingresos", []) + m_pdf.get("stock_actual", []) + m_pdf.get("saldo", []))
    c_fec = buscar_col(df, m_pdf.get("fecha", []))

    st.markdown(f"### 📊 Visualización Ejecutiva en Tiempo Real (`{ds_target}`)")

    if kps:
        c1, c2, c3, c4 = st.columns(4)
        simples = [k for k, v in kps.items() if not isinstance(v, dict)]
        for i, k in enumerate(simples[:4]):
            val = kps[k]
            val_str = fmt_pct(val) if "pct" in k else (fmt_money(val) if any(m in k for m in ["ingreso", "costo", "margen", "saldo", "deuda", "ticket"]) else fmt_num(val))
            with [c1, c2, c3, c4][i]:
                st.metric(k.replace('_', ' ').title(), val_str)

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        if c_cat and c_val:
            st.caption(f"Curva de Concentración: {c_cat.title()} vs {c_val.title()}")
            render_apex_chart(f"chat_pareto_{np.random.randint(1000,9999)}", apex_combo_pareto(df, c_cat, c_val))
        elif kps.get("aging_buckets"):
            st.caption("Matriz de Envejecimiento (Aging Mora)")
            render_apex_chart(f"chat_aging_{np.random.randint(1000,9999)}", apex_aging_bar(kps["aging_buckets"]))

    with col_g2:
        if c_fec and c_val:
            st.caption(f"Evolución Temporal: {c_val.title()}")
            render_apex_chart(f"chat_spline_{np.random.randint(1000,9999)}", apex_spline_time(df, c_fec, c_val))
        elif kps.get("resumen_vencimientos"):
            st.caption("Estatus de Vencimientos de Inventario")
            render_apex_chart(f"chat_donut_{np.random.randint(1000,9999)}", apex_donut_status(kps["resumen_vencimientos"]))

    if ds_target in st.session_state.tablas_global and st.session_state.tablas_global[ds_target]:
        for nom, t_df in st.session_state.tablas_global[ds_target].items():
            st.write(f"**📋 {nom.replace('_', ' ').title()}**")
            st.dataframe(t_df.head(10), width='stretch')

# ==========================================
# 10. INTERFAZ PRINCIPAL STREAMLIT
# ==========================================
for key in ["datasets", "clasificacion", "kpis_global", "tablas_global", "comparativos_global", "narrativas", "chat_history", "audit_logs"]:
    if key not in st.session_state:
        st.session_state[key] = {} if key != "chat_history" else []

st.title("⚡ Enterprise BI Copilot 360° (Full Suite)")
st.markdown("Consolidación multi-archivo, ETL avanzado, Tríada Comercial, Transporte y Chat analítico interactivo.")

tab_c, tab_k, tab_detalles, tab_eda, tab_ia, tab_pdf, tab_ch = st.tabs([
    "📂 Carga & ETL Audit",
    "📊 Top 5 Gráficos & KPIs",
    "📋 Tablas Condicionales",
    "🔍 Profiling EDA",
    "🧠 Informe Estratégico IA",
    "📄 Reporte PDF Explicado",
    "💬 Chat Copilot en Vivo"
])

# ---------- TAB 1: CARGA & ETL ----------
with tab_c:
    archivos = st.file_uploader(
        "Subir archivos (CSV, XLSX, JSON, XML, SQL, TXT, PDF con tablas):",
        type=["csv", "xlsx", "xls", "json", "xml", "sql", "txt", "pdf"],
        accept_multiple_files=True
    )
    if archivos and st.button("🚀 Ingestar y Ejecutar Pipeline ETL"):
        for a in archivos:
            sub_dfs = cargar_archivo(a)
            for nom, raw_df in sub_dfs.items():
                clean_df, dup, logs = limpiar_dataframe(raw_df)
                tipo = clasificar_dataset(clean_df)
                st.session_state.datasets[nom] = clean_df
                st.session_state.clasificacion[nom] = tipo
                st.session_state.audit_logs[nom] = logs
                st.success(f"✅ Ingestado: **{nom}** ({len(clean_df):,} filas) · Categoría: **{tipo.upper()}** (Duplicados removidos: {dup})")

    if st.session_state.datasets:
        st.write("---")
        lista_ds = list(st.session_state.datasets.keys())
        ds_ver = st.selectbox("Inspeccionar tabla en memoria:", lista_ds)
        st.dataframe(st.session_state.datasets[ds_ver].head(25), width='stretch')

        if ds_ver in st.session_state.audit_logs and st.session_state.audit_logs[ds_ver]:
            with st.expander("🛠️ Bitácora de Transformación ETL Aplicada"):
                for l in st.session_state.audit_logs[ds_ver]:
                    st.write(f"- {l}")

        if len(lista_ds) > 1:
            st.write("---")
            st.subheader("🧩 Fusión Relacional (Join)")
            c1, c2, c3, c4 = st.columns(4)
            with c1: d_izq = st.selectbox("Tabla Principal:", lista_ds, key="j_izq")
            with c2: d_der = st.selectbox("Tabla Secundaria:", [d for d in lista_ds if d != d_izq], key="j_der")
            comunes = list(set(st.session_state.datasets[d_izq].columns) & set(st.session_state.datasets[d_der].columns))
            with c3: c_key = st.selectbox("Columna Relacional:", comunes if comunes else ["(Sin llaves)"])
            with c4: j_tipo = st.selectbox("Tipo de Unión:", ["left", "inner", "right", "outer"])

            if comunes and st.button("🔗 Fusionar Tablas"):
                merged = pd.merge(st.session_state.datasets[d_izq], st.session_state.datasets[d_der], on=c_key, how=j_tipo, suffixes=("_izq", "_der"))
                n_fusion = f"Merge_{d_izq[:5]}_{d_der[:5]}"
                st.session_state.datasets[n_fusion] = merged
                st.session_state.clasificacion[n_fusion] = clasificar_dataset(merged)
                st.success(f"Creado: {n_fusion} con {len(merged):,} filas.")
                st.rerun()

# ---------- TAB 2: TOP 5 GRÁFICOS & TABLERO ----------
with tab_k:
    if not st.session_state.datasets:
        st.info("Carga archivos en la primera pestaña.")
    else:
        ds_activo = st.selectbox("Dataset a Analizar:", list(st.session_state.datasets.keys()), key="sb_kpi_ds")
        df_target = st.session_state.datasets[ds_activo]
        tipo_def = st.session_state.clasificacion.get(ds_activo, "ventas")

        tipo_analisis = st.selectbox(
            "Tipo de Análisis:",
            ["ventas", "inventario", "cuentas_por_cobrar", "cuentas_por_pagar", "entregas", "transporte", "contabilidad"],
            index=["ventas", "inventario", "cuentas_por_cobrar", "cuentas_por_pagar", "entregas", "transporte", "contabilidad"].index(tipo_def)
        )

        campos_req = MAPEOS_SUGERIDOS.get(tipo_analisis, {})
        cols_opc = ["(ninguna)"] + list(df_target.columns)
        cols_ui = st.columns(max(1, len(campos_req)))

        mapeo_actual = {}
        for idx, (campo, candidatas) in enumerate(campos_req.items()):
            det = buscar_col(df_target, candidatas)
            pos = cols_opc.index(det) if det in cols_opc else 0
            with cols_ui[idx]:
                sel = st.selectbox(campo.capitalize(), cols_opc, index=pos, key=f"m_{ds_activo}_{campo}")
                if sel != "(ninguna)": mapeo_actual[campo] = sel

        if st.button("⚡ Computar KPIs y Generar Visualizaciones"):
            k_res, t_res = calcular_kpis_completos(df_target, tipo_analisis, mapeo_actual)
            st.session_state.kpis_global[ds_activo] = k_res
            st.session_state.tablas_global[ds_activo] = t_res

            if mapeo_actual.get("fecha"):
                val_c = mapeo_actual.get("ingresos") or mapeo_actual.get("stock_actual") or mapeo_actual.get("saldo")
                if val_c:
                    st.session_state.comparativos_global[ds_activo] = comparar_periodos(df_target, mapeo_actual["fecha"], val_c)

        if ds_activo in st.session_state.kpis_global:
            kps = st.session_state.kpis_global[ds_activo]
            st.write("---")
            st.subheader("🎯 KPIs Principales")
            c_k1, c_k2, c_k3, c_k4 = st.columns(4)
            simples = [k for k, v in kps.items() if not isinstance(v, dict)]

            for i, k in enumerate(simples):
                val = kps[k]
                val_str = fmt_pct(val) if "pct" in k else (fmt_money(val) if any(m in k for m in ["ingreso", "costo", "margen", "saldo", "deuda", "ticket"]) else fmt_num(val))
                with [c_k1, c_k2, c_k3, c_k4][i % 4]:
                    st.markdown(f"""<div class="kpi-card"><div class="kpi-title">{k.replace('_', ' ')}</div><div class="kpi-value">{val_str}</div></div>""", unsafe_allow_html=True)

            if len(st.session_state.datasets) > 1:
                cruz_data = calcular_cruzado_360(st.session_state.datasets, st.session_state.kpis_global)
                if cruz_data.get("perdida_total_expuesta", 0) > 0:
                    st.write("---")
                    st.subheader("⭐ Análisis Cruzado 360° (Pérdida Total Expuesta)")
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">Pérdida Total Expuesta (Mora + Inventario)</div><div class="kpi-value">{fmt_money(cruz_data['perdida_total_expuesta'])}</div></div>""", unsafe_allow_html=True)
                    with cc2:
                        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">% Impacto sobre Facturación</div><div class="kpi-value">{fmt_pct(cruz_data['impacto_ventas_pct'])}</div></div>""", unsafe_allow_html=True)

            if ds_activo in st.session_state.comparativos_global and st.session_state.comparativos_global[ds_activo]:
                cmp = st.session_state.comparativos_global[ds_activo]
                st.write("---")
                st.subheader("📅 Time-Intelligence (Diferenciales)")
                tc1, tc2, tc3 = st.columns(3)
                with tc1:
                    d_y = f"<span class='kpi-up'>▲ {cmp['yoy_pct']:.1f}%</span>" if cmp['yoy_pct'] >= 0 else f"<span class='kpi-down'>▼ {abs(cmp['yoy_pct']):.1f}%</span>"
                    st.markdown(f"""<div class="kpi-card"><div class="kpi-title">YoY Anual ({cmp['py']} vs {cmp['cy']})</div><div class="kpi-value">{fmt_money(cmp['v_cy'])}</div>{d_y}</div>""", unsafe_allow_html=True)
                with tc2:
                    d_m = f"<span class='kpi-up'>▲ {cmp['mom_pct']:.1f}%</span>" if cmp['mom_pct'] >= 0 else f"<span class='kpi-down'>▼ {abs(cmp['mom_pct']):.1f}%</span>"
                    st.markdown(f"""<div class="kpi-card"><div class="kpi-title">MoM (Mes vs Anterior)</div><div class="kpi-value">{fmt_money(cmp['v_cm'])}</div>{d_m}</div>""", unsafe_allow_html=True)
                with tc3:
                    d_sm = f"<span class='kpi-up'>▲ {cmp['yoy_same_month_pct']:.1f}%</span>" if cmp['yoy_same_month_pct'] >= 0 else f"<span class='kpi-down'>▼ {abs(cmp['yoy_same_month_pct']):.1f}%</span>"
                    st.markdown(f"""<div class="kpi-card"><div class="kpi-title">Mismo Mes Año Anterior</div><div class="kpi-value">{fmt_money(cmp['v_cm'])}</div>{d_sm}</div>""", unsafe_allow_html=True)

            st.write("---")
            st.subheader("📊 Top Gráficos Interactivos de Negocio")
            g1, g2 = st.columns(2)

            with g1:
                if mapeo_actual.get("categoria") and mapeo_actual.get("ingresos"):
                    st.caption(f"1. Curva Pareto & Concentración por {mapeo_actual['categoria'].title()}")
                    render_apex_chart("chart_pareto", apex_combo_pareto(df_target, mapeo_actual["categoria"], mapeo_actual["ingresos"]))
                elif kps.get("aging_buckets"):
                    st.caption("1. Matriz de Envejecimiento (Aging de Deuda)")
                    render_apex_chart("chart_aging", apex_aging_bar(kps["aging_buckets"]))

                if kps.get("pct_cumplimiento_meta") is not None:
                    st.caption("3. Indicador Radial de Meta (OKR)")
                    render_apex_chart("chart_okr", apex_radial_okr(kps["pct_cumplimiento_meta"]))

            with g2:
                if mapeo_actual.get("fecha") and (mapeo_actual.get("ingresos") or mapeo_actual.get("saldo")):
                    v_col = mapeo_actual.get("ingresos") or mapeo_actual.get("saldo")
                    st.caption(f"2. Tendencia Temporal Suavizada ({v_col.title()})")
                    render_apex_chart("chart_spline", apex_spline_time(df_target, mapeo_actual["fecha"], v_col))

                for key_st, title_st in [("resumen_status_pago", "Estatus de Cartera"), ("resumen_vencimientos", "Vencimientos"), ("resumen_salud_stock", "Salud del Inventario")]:
                    if kps.get(key_st):
                        st.caption(f"4. {title_st}")
                        render_apex_chart(f"chart_donut_{key_st}", apex_donut_status(kps[key_st], title_st))
                        break

# ---------- TAB 3: TABLAS CONDICIONALES ----------
with tab_detalles:
    if not st.session_state.tablas_global:
        st.info("Computa los KPIs en la pestaña anterior para desbloquear las tablas avanzadas.")
    else:
        ds_t = st.selectbox("Seleccionar Tabla:", list(st.session_state.tablas_global.keys()), key="sb_tablas_ds")
        dict_t = st.session_state.tablas_global[ds_t]

        for nom, df_sub in dict_t.items():
            st.subheader(f"📋 {nom.replace('_', ' ').title()}")
            if "% Participación" in df_sub.columns:
                st.dataframe(
                    df_sub.style.format({"Total ($)": "${:,.2f}", "Promedio ($)": "${:,.2f}", "% Participación": "{:.1f}%"})
                    .background_gradient(subset=["Total ($)"], cmap="Blues"),
                    width='stretch'
                )
            elif "Total ($)" in df_sub.columns and "Provisión ($)" in df_sub.columns:
                st.dataframe(
                    df_sub.style.format({"Total ($)": "${:,.2f}", "Tasa Prov.": "{:.0%}", "Provisión ($)": "${:,.2f}"})
                    .background_gradient(subset=["Provisión ($)"], cmap="Reds"),
                    width='stretch'
                )
            elif "Recaudacion" in df_sub.columns:
                st.dataframe(
                    df_sub.style.format({"Recaudacion": "${:,.2f}", "Retraso_Min": "{:.1f} min"})
                    .background_gradient(subset=["Retraso_Min"], cmap="Greens_r"),
                    width='stretch'
                )
            else:
                st.dataframe(df_sub, width='stretch')

# ---------- TAB 4: EDA PROFILING ----------
with tab_eda:
    if not st.session_state.datasets:
        st.info("Carga archivos primero.")
    else:
        ds_eda = st.selectbox("Dataset para Análisis Exploratorio (EDA):", list(st.session_state.datasets.keys()), key="sb_eda_ds")
        df_eda = st.session_state.datasets[ds_eda]

        c1, c2, c3 = st.columns(3)
        c1.metric("Filas Totales", f"{len(df_eda):,}")
        c2.metric("Columnas", len(df_eda.columns))
        c3.metric("Nulos Totales", int(df_eda.isna().sum().sum()))

        st.write("**Resumen Estadístico Numérico:**")
        num_cols = df_eda.select_dtypes(include=[np.number])
        if not num_cols.empty:
            st.dataframe(num_cols.describe().T.style.background_gradient(cmap="Blues"), width='stretch')
            if num_cols.shape[1] > 1:
                st.write("**Matriz de Correlación:**")
                st.dataframe(num_cols.corr().style.background_gradient(cmap="coolwarm", vmin=-1, vmax=1), width='stretch')
        else:
            st.info("No hay columnas numéricas nativas en este dataset.")

# ---------- TAB 5: INFORME IA ----------
with tab_ia:
    st.subheader("🧠 Informe Ejecutivo con Pool de Modelos")
    aud_ia = st.radio("Audiencia del Informe:", ["directiva", "gerencial", "tecnico"], horizontal=True,
                      format_func=lambda x: {"directiva": "🏛️ Junta Directiva / C-Suite", "gerencial": "🧑‍💼 Gerencial & Operativo", "tecnico": "🧪 Analítico & Técnico"}[x])

    if st.button("✨ Generar Síntesis Inteligente"):
        if not st.session_state.kpis_global:
            st.warning("Computa los KPIs antes de redactar el informe.")
        else:
            with st.spinner("Procesando a través del pool de modelos..."):
                cruz_res = calcular_cruzado_360(st.session_state.datasets, st.session_state.kpis_global)
                prompt_ia = f"""
                Eres un Consultor Senior de BI y Científico de Datos. Redacta un informe para: {aud_ia.upper()}.
                
                KPIS COMPUTADOS POR DATASET:
                {json.dumps(serializar_para_json(st.session_state.kpis_global), ensure_ascii=False, indent=2)}

                ANÁLISIS CRUZADO 360° (PÉRDIDA TOTAL EXPUESTA):
                {json.dumps(serializar_para_json(cruz_res), ensure_ascii=False, indent=2)}

                Estructura tu respuesta:
                1. 🎯 DIAGNÓSTICO EJECUTIVO Y PÉRDIDA TOTAL EXPUESTA
                2. 🔍 ANÁLISIS CRÍTICO, DESVIACIONES Y OPORTUNIDADES
                3. 🚀 RECOMENDACIONES TÁCTICAS Y PLAN DE ACCIÓN A 30, 60 Y 90 DÍAS
                
                Reglas ESTRICTAS:
                - NO uses etiquetas HTML como <span> o <div>.
                - Usa únicamente Markdown limpio: negritas con **texto**.
                - Separa siempre el signo '$' con un espacio (ejemplo: $ 5,000).
                """
                narrativa, mod = llamar_ia_pool(prompt_ia)
                if narrativa:
                    st.session_state.narrativas[aud_ia] = narrativa
                    st.success(f"Generado exitosamente con: **{mod}**")
                else:
                    st.error("No se pudo conectar con el pool de modelos.")

    if aud_ia in st.session_state.narrativas:
        with st.container(border=True):
            st.markdown(formatear_texto_web(st.session_state.narrativas[aud_ia]))

# ---------- TAB 6: PDF EXPLICADO ----------
with tab_pdf:
    st.subheader("📄 Generación de Reporte PDF Oficial con Explicaciones")
    st.caption("Cada gráfico en el PDF incluye su lectura analítica, diagnóstico y acción recomendada sin etiquetas extrañas.")
    aud_pdf = st.selectbox("Enfoque del Reporte PDF:", ["directiva", "gerencial", "tecnico"])

    if st.button("📥 Compilar y Descargar PDF con Explicaciones"):
        if not st.session_state.kpis_global:
            st.error("Calcula los KPIs primero en la pestaña 📊.")
        else:
            items_visuales = []
            for d_name, df_pdf in st.session_state.datasets.items():
                m_pdf = MAPEOS_SUGERIDOS.get(st.session_state.clasificacion.get(d_name, "ventas"), {})
                c_cat = buscar_col(df_pdf, m_pdf.get("categoria", []))
                c_val = buscar_col(df_pdf, m_pdf.get("ingresos", []) + m_pdf.get("stock_actual", []) + m_pdf.get("saldo", []))
                c_fec = buscar_col(df_pdf, m_pdf.get("fecha", []))

                if c_cat and c_val:
                    # Coerción segura a numérico antes de graficar
                    df_pdf[c_val] = a_numero(df_pdf[c_val])
                    if df_pdf[c_val].sum() > 0 and c_cat != c_val:
                        b_ranking = static_ranking_top(df_pdf, c_cat, c_val, f"Top {c_cat.title()} por {c_val.title()} ({d_name})")
                        items_visuales.append({
                            "buffer": b_ranking,
                            "lectura": f"Muestra el volumen acumulado de {c_val.replace('_',' ')} clasificado por {c_cat.replace('_',' ')} ordenado de mayor a menor.",
                            "diagnostico": f"Existe una concentración relevante en los primeros puestos, indicando alta dependencia comercial en las categorías principales.",
                            "accion": f"Diversificar la cartera y blindar los rubros con mayor participación para proteger la liquidez."
                        })

                if c_fec and c_val:
                    df_pdf[c_val] = a_numero(df_pdf[c_val])
                    if df_pdf[c_val].sum() > 0:
                        b_linea = static_line_time(df_pdf, c_fec, c_val, f"Tendencia Temporal de {c_val.title()} ({d_name})")
                        items_visuales.append({
                            "buffer": b_linea,
                            "lectura": f"Monitorea el comportamiento secuencial en el tiempo comparado contra la línea roja de media global.",
                            "diagnostico": "Se aprecian fluctuaciones pronunciadas en ciertos periodos por debajo del promedio histórico.",
                            "accion": "Alinear incentivos comerciales y planificar reposición en periodos tradicionalmente de menor actividad."
                        })

            cruz_pdf = calcular_cruzado_360(st.session_state.datasets, st.session_state.kpis_global)
            pdf_out = crear_pdf_reporte(
                "Consolidado_MultiFuentes", aud_pdf,
                st.session_state.kpis_global, st.session_state.comparativos_global,
                limpiar_etiquetas_html(st.session_state.narrativas.get(aud_pdf, "")), items_visuales,
                cruzado_360=cruz_pdf
            )
            st.download_button(
                label="💾 Descargar Archivo PDF Explicado",
                data=pdf_out,
                file_name=f"Informe_BI_Explicado_{aud_pdf}.pdf",
                mime="application/pdf"
            )

# ---------- TAB 7: CHAT COPILOT EN VIVO ----------
with tab_ch:
    st.subheader("💬 Asistente Analítico Cruzado (Streaming & Gráficos en Vivo)")
    st.caption(f"Consultas en tiempo real procesadas por: {', '.join(MODELOS_POOL)}")

    if st.button("📊 Forzar Despliegue de Tablero Visual Completo (Gráficos + Tablas)"):
        renderizar_tablero_completo_en_chat()

    for m in st.session_state.chat_history:
        with st.chat_message(m["role"]):
            st.markdown(limpiar_etiquetas_html(m["content"]))

    if query_u := st.chat_input("Pregunta sobre mora, productos por vencer, débitos, créditos o cruces de datos:"):
        st.session_state.chat_history.append({"role": "user", "content": query_u})
        with st.chat_message("user"):
            st.markdown(query_u)

        ctx = "REPOSITORIO DE DATOS:\n"
        for n_ds, df_ds in st.session_state.datasets.items():
            ctx += f"\n--- TABLA: {n_ds} ---\nColumnas: {list(df_ds.columns)}\n"
            ctx += f"Muestra:\n{df_ds.head(5).to_string(index=False)}\n"

        cruz_ctx = calcular_cruzado_360(st.session_state.datasets, st.session_state.kpis_global)
        prompt_c = f"""
        Eres un Ingeniero y Analista Cuantitativo Senior. Responde basándote en:
        {ctx}
        KPIs ya calculados:
        {json.dumps(serializar_para_json(st.session_state.kpis_global), ensure_ascii=False)}

        Análisis Cruzado 360°:
        {json.dumps(serializar_para_json(cruz_ctx), ensure_ascii=False)}

        Consulta: "{query_u}"

        Instrucciones:
        - Si el usuario pide gráficos o tablas, explica los hallazgos numéricos directamente con cifras reales.
        - Muestra cifras exactas con formato ($ 1,500 o porcentajes).
        - NO uses etiquetas HTML como <span> o <div>.
        - Sé conciso y estructurado con viñetas y emojis.
        """
        with st.chat_message("assistant"):
            ans = st.write_stream(llamar_ia_stream(prompt_c))
            ans_limpio = limpiar_etiquetas_html(ans)
            st.session_state.chat_history.append({"role": "assistant", "content": ans_limpio})

            if any(w in query_u.lower() for w in ["grafico", "graficos", "tabla", "tablas", "kpi", "okr", "dashboard", "360"]):
                st.write("---")
                renderizar_tablero_completo_en_chat()