import io
import re
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y API KEY
# ==========================================
st.set_page_config(page_title="Agente Analítico AI & Reportes PDF", page_icon="⚡", layout="wide")

API_KEY = "AQ.Ab8RN6JePMHzV5fnnmPDSd-6QmpJ7BnGkYLQgA90Eg-3Tj55Kg"
client = genai.Client(api_key=API_KEY)

# POOL BASADO EXACTAMENTE EN TUS CAPTURAS DE GOOGLE AI STUDIO
MODELOS_POOL = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash"
]

st.markdown("""
    <style>
    .badge-val { background-color: #dbeafe; color: #1e40af; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .badge-key { background-color: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .metric-card {
        background-color: #ffffff; border-left: 5px solid #2563eb;
        border-radius: 8px; padding: 14px; margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. FUNCIONES DE APOYO (GRÁFICOS, PDF Y LLAMADAS RÁPIDAS)
# ==========================================
def crear_grafico_distribucion(df, columna):
    fig, ax = plt.subplots(figsize=(7, 3))
    serie = pd.to_numeric(df[columna], errors='coerce').dropna()
    ax.hist(serie, bins=25, color="#2563eb", edgecolor="#ffffff", alpha=0.85)
    ax.set_title(f"Distribución de {columna}", fontsize=11, fontweight="bold", pad=8)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180)
    buf.seek(0)
    plt.close(fig)
    return buf

def crear_grafico_linea(df, col_y):
    fig, ax = plt.subplots(figsize=(7, 3))
    y_vals = pd.to_numeric(df[col_y], errors='coerce').dropna().reset_index(drop=True)
    ax.plot(y_vals.values, color="#10b981", linewidth=1.6)
    ax.set_title(f"Tendencia de {col_y}", fontsize=11, fontweight="bold", pad=8)
    ax.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180)
    buf.seek(0)
    plt.close(fig)
    return buf

def limpiar_texto_para_pdf(texto):
    if not texto:
        return ""
    texto = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', texto)

def formatear_texto_web(texto):
    if not texto:
        return ""
    texto = re.sub(r'\$(\d)', r'$ \1', texto)
    texto = re.sub(r'(\$\s?[\d,]+(?:\.\d+)?)', r'<span class="badge-val">\1</span>', texto)
    texto = re.sub(r'([\d,]+(?:\.\d+)?%)', r'<span class="badge-val">\1</span>', texto)
    texto = re.sub(r'\*\*(.*?)\*\*', r'<span class="badge-key">\1</span>', texto)
    return texto

def generar_pdf_informe(nombre_archivo, metricas, texto_ia, img_buf1, img_buf2):
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle('TituloDoc', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor("#1E3A8A"), spaceAfter=3)
    estilo_sub = ParagraphStyle('SubDoc', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor("#64748B"), spaceAfter=10)
    estilo_sec = ParagraphStyle('SecDoc', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor("#1D4ED8"), spaceBefore=8, spaceAfter=5)
    estilo_body = ParagraphStyle('BodyDoc', parent=styles['Normal'], fontSize=8.5, leading=12, textColor=colors.HexColor("#1F2937"), spaceAfter=4)

    story = [
        Paragraph("INFORME EJECUTIVO Y ANÁLISIS DE DATOS", estilo_titulo),
        Paragraph(f"Fuente: <b>{nombre_archivo}</b> | Generado con Inteligencia Artificial", estilo_sub),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=10),
        Paragraph("1. Métricas Clave y Resumen Estadístico", estilo_sec)
    ]

    data_kpis = [
        ["Métrica", "Valor", "Métrica", "Valor"],
        ["Total Registros", f"{metricas['total']:,}", "Variable Evaluada", f"{metricas['columna']}"],
        ["Suma Total", f"{metricas.get('suma', 'N/A')}", "Promedio", f"{metricas.get('promedio', 'N/A')}"],
        ["Valor Máximo", f"{metricas.get('max', 'N/A')}", "Valor Mínimo", f"{metricas.get('min', 'N/A')}"]
    ]
    tabla = Table(data_kpis, colWidths=[135, 135, 135, 135])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tabla)
    story.append(Spacer(1, 8))

    story.append(Paragraph("2. Conclusiones y Resumen Estratégico", estilo_sec))
    if texto_ia:
        for p in texto_ia.split("\n"):
            p_limpio = p.strip()
            if p_limpio:
                story.append(Paragraph(limpiar_texto_para_pdf(p_limpio), estilo_body))
    else:
        story.append(Paragraph("No se generó análisis narrativo previo al PDF.", estilo_body))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. Visualizaciones Analíticas", estilo_sec))
    if img_buf1:
        story.append(RLImage(img_buf1, width=490, height=180))
        story.append(Spacer(1, 6))
    if img_buf2:
        story.append(RLImage(img_buf2, width=490, height=180))

    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer

def llamar_ia_pool(prompt_text):
    for m in MODELOS_POOL:
        try:
            res = client.models.generate_content(model=m, contents=prompt_text)
            if res and res.text:
                return res.text, m
        except Exception:
            continue
    return None, None

def llamar_ia_stream(prompt_text):
    """Streaming de alta velocidad: responde palabra por palabra sin congelar la app."""
    for m in MODELOS_POOL:
        try:
            stream = client.models.generate_content_stream(model=m, contents=prompt_text)
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
            return
        except Exception:
            continue
    yield "Error al conectar con la IA. Intenta nuevamente."

# ==========================================
# 3. INTERFAZ STREAMLIT
# ==========================================
st.title("⚡ Agente Analítico Universal (Gemini 3.8 Flash)")
st.markdown("Procesamiento instantáneo, métricas automáticas y asistente conversacional.")

archivo_subido = st.file_uploader("📁 Sube tu archivo CSV o Excel", type=["csv", "xlsx"])

if archivo_subido is not None:
    @st.cache_data
    def cargar_datos(file):
        if file.name.endswith('.csv'):
            return pd.read_csv(file)
        return pd.read_excel(file)

    df_raw = cargar_datos(archivo_subido)
    df_limpio = df_raw.dropna(how='all')
    total_registros = len(df_limpio)

    columnas_numericas = df_limpio.select_dtypes(include=[np.number]).columns.tolist()
    columnas_cat = df_limpio.select_dtypes(include=['object', 'category', 'string']).columns.tolist()

    if not columnas_numericas:
        st.warning("⚠️ El archivo no contiene columnas numéricas.")
        st.stop()

    col_analisis = st.selectbox("📌 Selecciona la columna a analizar:", columnas_numericas)

    # Métricas universales
    serie_analisis = pd.to_numeric(df_limpio[col_analisis], errors='coerce').dropna()
    suma_total = float(serie_analisis.sum())
    promedio = float(serie_analisis.mean())
    valor_max = float(serie_analisis.max())
    valor_min = float(serie_analisis.min())

    metricas_dict = {
        "columna": col_analisis, "total": total_registros,
        "suma": f"${suma_total:,.2f}", "promedio": f"${promedio:,.2f}",
        "max": f"${valor_max:,.2f}", "min": f"${valor_min:,.2f}"
    }

    # ==========================================================
    # RESUMEN PRECALCULADO RÁPIDO (Cero demoras de procesamiento)
    # ==========================================================
    @st.cache_data
    def precalcular_contexto(df_in, col_num, col_cat_list):
        lineas = []
        lineas.append(f"Dimensiones: {df_in.shape[0]} filas, {df_in.shape[1]} columnas.")
        lineas.append(f"Columnas disponibles: {list(df_in.columns)}")

        # Cruzar rápidamente categorías con números para que sepa quién es el más vendido/sucursal top
        for cat in col_cat_list[:3]:
            try:
                top_group = df_in.groupby(cat)[col_num].sum().nlargest(5).to_dict()
                low_group = df_in.groupby(cat)[col_num].sum().nsmallest(3).to_dict()
                lineas.append(f"Ranking por '{cat}' sumando '{col_num}': Top 5={top_group} | Menores={low_group}")
                lineas.append(f"Frecuencia más repetida en '{cat}': {df_in[cat].value_counts().head(5).to_dict()}")
            except Exception:
                pass

        # Muestra muy ligera (solo las primeras 25 filas)
        lineas.append("Muestra de filas reales:")
        lineas.append(df_in.head(25).to_string(index=False))
        return "\n".join(lineas)

    contexto_negocio = precalcular_contexto(df_limpio, col_analisis, columnas_cat)

    tab_dashboard, tab_chat = st.tabs(["📈 Dashboard y Reporte PDF", "💬 Chatear con los Datos"])

    with tab_dashboard:
        # KPIs
        st.subheader("📌 Indicadores Clave")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Registros Válidos", f"{total_registros:,}")
        c2.metric(f"Total ({col_analisis})", f"${suma_total:,.2f}")
        c3.metric("Promedio", f"${promedio:,.2f}")
        c4.metric("Rango (Mín / Máx)", f"${valor_min:,.1f} - ${valor_max:,.1f}")

        # Gráficos
        st.write("---")
        st.subheader("📈 Visualización de Tendencias")
        g1, g2 = st.columns(2)
        with g1:
            st.write(f"**Secuencia de {col_analisis}**")
            fig_l, ax_l = plt.subplots(figsize=(6, 3.2))
            ax_l.plot(serie_analisis.values, color="#10b981", linewidth=1.5)
            ax_l.axhline(promedio, color="#ef4444", linestyle="--", label=f"Media: ${promedio:,.2f}")
            ax_l.grid(True, linestyle="--", alpha=0.4)
            ax_l.legend(loc="upper right")
            st.pyplot(fig_l)
            plt.close(fig_l)

        with g2:
            st.write(f"**Distribución (Histograma)**")
            fig_h, ax_h = plt.subplots(figsize=(6, 3.2))
            ax_h.hist(serie_analisis, bins=25, color="#2563eb", edgecolor="#ffffff")
            ax_h.grid(axis='y', linestyle="--", alpha=0.4)
            st.pyplot(fig_h)
            plt.close(fig_h)

        # Generador de Informe
        st.write("---")
        st.subheader("🧠 Análisis Ejecutivo Inteligente")
        if "informe_ia" not in st.session_state:
            st.session_state.informe_ia = ""

        if st.button("✨ Generar Análisis Integral"):
            with st.spinner("Procesando con Gemini 3.8 Flash..."):
                prompt = f"""
                Eres un Consultor Senior. Analiza estos datos concisamente:
                Archivo: {archivo_subido.name}
                Métrica '{col_analisis}': Suma=${suma_total:,.2f}, Media=${promedio:,.2f}, Min=${valor_min:,.2f}, Max=${valor_max:,.2f}
                Resumen de datos:
                {contexto_negocio}

                Escribe un informe conciso con:
                1. 🎯 DIAGNÓSTICO GENERAL
                2. 🔍 HALLAZGOS Y ANOMALÍAS (Menciona nombres reales de categorías y cifras)
                3. 🚀 RECOMENDACIONES TÁCTICAS:
                   - 💡 Diversificación de Fuentes: Explorar la introducción de productos o servicios complementarios para amortiguar periodos de baja demanda.
                   - 💡 Optimización Operativa basada en el promedio de ${promedio:,.2f}.
                Pon palabras clave en **negrita** y separa el símbolo '$' con un espacio (ej: $ 100).
                """
                texto_ia, mod = llamar_ia_pool(prompt)
                if texto_ia:
                    st.session_state.informe_ia = texto_ia
                    st.success(f"Generado con: **{mod}**")
                else:
                    st.error("Error al conectar con los modelos.")

        if st.session_state.informe_ia:
            st.markdown(f"""
            <div class="metric-card">
                {formatear_texto_web(st.session_state.informe_ia)}
            </div>
            """, unsafe_allow_html=True)

        # Generador de PDF
        st.write("---")
        st.subheader("📄 Descarga de Reporte Master")
        img_dist = crear_grafico_distribucion(df_limpio, col_analisis)
        img_line = crear_grafico_linea(df_limpio, col_analisis)

        pdf = generar_pdf_informe(archivo_subido.name, metricas_dict, st.session_state.informe_ia, img_dist, img_line)
        st.download_button(
            label="📥 Descargar Reporte Completo en PDF",
            data=pdf,
            file_name=f"Reporte_{archivo_subido.name}.pdf",
            mime="application/pdf"
        )

    # ==========================================================
    # TAB 2: CHAT INTELIGENTE ULTRA RÁPIDO CON STREAMING
    # ==========================================================
    with tab_chat:
        st.subheader("💬 Chatea con tus Datos Reales")
        st.caption("Pregunta por productos más vendidos, sucursal top, montos máximos, clientes o totales.")

        if "mensajes" not in st.session_state:
            st.session_state.mensajes = []

        for m in st.session_state.mensajes:
            with st.chat_message(m["rol"]):
                st.write(m["contenido"])

        if pregunta := st.chat_input("Ej: ¿Cuál es el producto más vendido, el menos vendido y la mejor sucursal?"):
            st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})
            with st.chat_message("user"):
                st.write(pregunta)

            with st.chat_message("assistant"):
                prompt_chat = f"""
                Eres un analista de datos respondiendo en tiempo real.
                Usa este contexto real del archivo subido:
                {contexto_negocio}

                Métrica principal '{col_analisis}':
                - Suma total: ${suma_total:,.2f}
                - Promedio: ${promedio:,.2f}
                - Máximo: ${valor_max:,.2f} | Mínimo: ${valor_min:,.2f}

                Pregunta del usuario: "{pregunta}"

                Instrucciones:
                - Responde EXACTO con nombres de productos, sucursales o valores reales.
                - Sé conciso y directo (usa viñetas con emojis).
                - Separa el signo de peso con un espacio (ejemplo: $ 1,500) para no romper fórmulas de texto.
                """
                # Streaming en vivo: empieza a escribir en milisegundos
                respuesta_texto = st.write_stream(llamar_ia_stream(prompt_chat))
                st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_texto})