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
st.set_page_config(
    page_title="Agente Analista Universal IA",
    page_icon="🤖",
    layout="wide"
)

API_KEY = "AQ.Ab8RN6JePMHzV5fnnmPDSd-6QmpJ7BnGkYLQgA90Eg-3Tj55Kg"
client = genai.Client(api_key=API_KEY)

MODELOS_POOL = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

# Estilos CSS para resaltar datos visualmente
st.markdown("""
    <style>
    .badge-val { background-color: #dbeafe; color: #1e40af; padding: 2px 7px; border-radius: 5px; font-weight: 700; }
    .badge-key { background-color: #fef3c7; color: #92400e; padding: 2px 7px; border-radius: 5px; font-weight: 700; }
    .metric-card {
        background-color: #ffffff;
        border-left: 5px solid #2563eb;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. FUNCIONES DE APOYO (PERFILADO, GRÁFICOS Y PDF)
# ==========================================
def obtener_resumen_estructural_universal(df):
    """
    Construye un perfil exhaustivo de cualquier base de datos (ventas, RRHH, logística, salud, etc.)
    para que la IA conozca todos los nombres reales, categorías dominantes y valores extremos.
    """
    contexto = []
    total_filas, total_columnas = df.shape
    contexto.append(f"Dimensiones del dataset: {total_filas:,} filas y {total_columnas} columnas.")
    contexto.append(f"Listado de columnas: {list(df.columns)}")

    # 1. Columnas de texto / categorías
    cols_cat = df.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
    if cols_cat:
        contexto.append("\n--- RESUMEN DE VARIABLES CATEGÓRICAS / TEXTO ---")
        for col in cols_cat[:6]:  # Analiza hasta 6 columnas categóricas
            top_valores = df[col].value_counts().head(5).to_dict()
            unicos = df[col].nunique()
            contexto.append(f"Columna '{col}' ({unicos} valores distintos). Valores más repetidos: {top_valores}")

    # 2. Columnas numéricas
    cols_num = df.select_dtypes(include=[np.number]).columns.tolist()
    if cols_num:
        contexto.append("\n--- ESTADÍSTICAS DE VARIABLES NUMÉRICAS ---")
        for col in cols_num[:6]:  # Analiza hasta 6 columnas numéricas
            s = df[col].dropna()
            if not s.empty:
                idx_max = s.idxmax()
                idx_min = s.idxmin()
                
                # Intentamos identificar qué etiqueta acompaña al máximo y mínimo
                etiqueta_ref = cols_cat[0] if cols_cat else None
                ref_max = f" (Asociado a: {df.loc[idx_max, etiqueta_ref]})" if etiqueta_ref else ""
                ref_min = f" (Asociado a: {df.loc[idx_min, etiqueta_ref]})" if etiqueta_ref else ""

                contexto.append(
                    f"Columna '{col}': Suma={s.sum():,.2f} | Promedio={s.mean():,.2f} | "
                    f"Máx={s.max():,.2f}{ref_max} | Mín={s.min():,.2f}{ref_min}"
                )

    # 3. Cruces inteligentes (Top agrupaciones de negocio si hay categorías + números)
    if cols_cat and cols_num:
        contexto.append("\n--- CRUCES Y RANKINGS PRINCIPALES ---")
        cat_principal = cols_cat[0]
        num_principal = cols_num[0]
        try:
            ranking = df.groupby(cat_principal)[num_principal].sum().nlargest(5).to_dict()
            contexto.append(f"Top 5 en '{cat_principal}' con mayor volumen de '{num_principal}': {ranking}")
            
            # El más bajo / menos vendido / menos frecuente
            ranking_bajo = df.groupby(cat_principal)[num_principal].sum().nsmallest(3).to_dict()
            contexto.append(f"Menores 3 en '{cat_principal}' según '{num_principal}': {ranking_bajo}")
        except Exception:
            pass

    # 4. Muestra representativa de filas
    contexto.append("\n--- MUESTRA REAL DE DATOS (PRIMERAS FILAS) ---")
    contexto.append(df.head(20).to_string(index=False))

    return "\n".join(contexto)

def crear_grafico_distribucion(df, columna):
    fig, ax = plt.subplots(figsize=(7, 3.2))
    serie = pd.to_numeric(df[columna], errors='coerce').dropna()
    ax.hist(serie, bins=25, color="#2563eb", edgecolor="#ffffff", alpha=0.85)
    media = serie.mean()
    ax.axvline(media, color="#ef4444", linestyle="--", linewidth=1.5, label=f"Media: {media:,.2f}")
    ax.set_title(f"Distribución de {columna}", fontsize=11, fontweight="bold", pad=8)
    ax.legend(loc="upper right")
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    buf.seek(0)
    plt.close(fig)
    return buf

def crear_grafico_linea(df, columna):
    fig, ax = plt.subplots(figsize=(7, 3.2))
    serie = pd.to_numeric(df[columna], errors='coerce').dropna().reset_index(drop=True)
    ax.plot(serie.values, color="#10b981", linewidth=1.5, alpha=0.6, label="Valor")
    if len(serie) > 5:
        suavizado = serie.rolling(window=max(3, len(serie)//20), min_periods=1).mean()
        ax.plot(suavizado, color="#047857", linewidth=2.2, label="Tendencia")
    ax.set_title(f"Comportamiento Secuencial de {columna}", fontsize=11, fontweight="bold", pad=8)
    ax.legend(loc="upper right")
    ax.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    buf.seek(0)
    plt.close(fig)
    return buf

def formatear_texto_web(texto):
    if not texto:
        return ""
    # Reemplazar valores monetarios con espacio para evitar conflictos de LaTeX
    texto = re.sub(r'\$(\d)', r'$ \1', texto)
    texto = re.sub(r'(\$\s?[\d,]+(?:\.\d+)?)', r'<span class="badge-val">\1</span>', texto)
    texto = re.sub(r'([\d,]+(?:\.\d+)?%)', r'<span class="badge-val">\1</span>', texto)
    texto = re.sub(r'\*\*(.*?)\*\*', r'<span class="badge-key">\1</span>', texto)
    return texto

def limpiar_texto_para_pdf(texto):
    if not texto:
        return ""
    texto = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Convertir **negrita** a <b>negrita</b>
    texto = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', texto)
    return texto

def generar_pdf_informe(nombre_archivo, metricas, texto_ia, img_buf1, img_buf2):
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle('TituloDoc', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor("#1E3A8A"), spaceAfter=3)
    estilo_sub = ParagraphStyle('SubDoc', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor("#64748B"), spaceAfter=10)
    estilo_sec = ParagraphStyle('SecDoc', parent=styles['Heading2'], fontSize=11, leading=14, textColor=colors.HexColor("#1D4ED8"), spaceBefore=8, spaceAfter=5)
    estilo_body = ParagraphStyle('BodyDoc', parent=styles['Normal'], fontSize=8.5, leading=12, textColor=colors.HexColor("#1F2937"), spaceAfter=4)

    story = [
        Paragraph("INFORME EJECUTIVO Y AUDITORÍA DE DATOS", estilo_titulo),
        Paragraph(f"Dataset: <b>{nombre_archivo}</b> | Generado por Agente Analista Inteligente", estilo_sub),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=10),
        Paragraph("1. Resumen Estadístico Principal", estilo_sec)
    ]

    data_kpis = [
        ["Métrica", "Valor", "Métrica", "Valor"],
        ["Total Registros", f"{metricas['total']:,}", "Variable Evaluada", f"{metricas['columna']}"],
        ["Suma Consolidada", f"{metricas.get('suma', 'N/A')}", "Promedio", f"{metricas.get('promedio', 'N/A')}"],
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

    story.append(Paragraph("2. Diagnóstico Estratégico y Hallazgos de IA", estilo_sec))
    if texto_ia:
        for p in texto_ia.split("\n"):
            p_limpio = p.strip()
            if p_limpio:
                story.append(Paragraph(limpiar_texto_para_pdf(p_limpio), estilo_body))
    else:
        story.append(Paragraph("No se ejecutó análisis antes de exportar.", estilo_body))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. Visualizaciones Analíticas", estilo_sec))
    if img_buf1:
        story.append(RLImage(img_buf1, width=500, height=180))
        story.append(Spacer(1, 6))
    if img_buf2:
        story.append(RLImage(img_buf2, width=500, height=180))

    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer

def consultar_gemini(prompt_text):
    for modelo in MODELOS_POOL:
        try:
            respuesta = client.models.generate_content(
                model=modelo,
                contents=prompt_text
            )
            if respuesta and respuesta.text:
                return respuesta.text, modelo
        except Exception:
            continue
    return None, None

# ==========================================
# 3. INTERFAZ STREAMLIT
# ==========================================
st.title("🤖 Agente Analítico Universal de Datos")
st.markdown("Carga archivos de **ventas, finanzas, recursos humanos, inventarios, operaciones o salud**. La IA comprenderá el contexto, identificará patrones y te responderá cualquier duda.")

archivo_subido = st.file_uploader("📁 Sube tu archivo CSV o Excel aquí", type=["csv", "xlsx"])

if archivo_subido is not None:
    try:
        df = pd.read_csv(archivo_subido) if archivo_subido.name.endswith('.csv') else pd.read_excel(archivo_subido)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        st.stop()

    df_limpio = df.dropna(how='all')
    total_registros = len(df_limpio)

    with st.expander("🔍 Explorar Datos Limpios", expanded=False):
        st.dataframe(df_limpio.head(10), use_container_width=True)

    columnas_numericas = df_limpio.select_dtypes(include=[np.number]).columns.tolist()

    if not columnas_numericas:
        st.warning("⚠️ El archivo subido no contiene columnas numéricas para realizar cálculos y gráficos.")
        st.stop()

    # Selector de columna métrica principal
    col_analisis = st.selectbox("📌 Selecciona la columna numérica que deseas auditar:", columnas_numericas)

    serie_analisis = pd.to_numeric(df_limpio[col_analisis], errors='coerce').dropna()
    suma_total = float(serie_analisis.sum())
    promedio = float(serie_analisis.mean())
    valor_max = float(serie_analisis.max())
    valor_min = float(serie_analisis.min())

    metricas_dict = {
        "columna": col_analisis,
        "total": total_registros,
        "suma": f"${suma_total:,.2f}",
        "promedio": f"${promedio:,.2f}",
        "max": f"${valor_max:,.2f}",
        "min": f"${valor_min:,.2f}"
    }

    # Perfil global para alimentar a la IA
    resumen_datos_global = obtener_resumen_estructural_universal(df_limpio)

    tab_dashboard, tab_chat = st.tabs(["📈 Dashboard y Reporte PDF", "💬 Chatear con los Datos Reales"])

    # ----------------------------------------------------
    # TAB 1: DASHBOARD Y REPORTE PDF
    # ----------------------------------------------------
    with tab_dashboard:
        st.subheader("📌 Indicadores Clave")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Registros Válidos", f"{total_registros:,}")
        c2.metric(f"Total ({col_analisis})", f"${suma_total:,.2f}")
        c3.metric("Promedio", f"${promedio:,.2f}")
        c4.metric("Rango (Mín / Máx)", f"${valor_min:,.1f} - ${valor_max:,.1f}")

        st.write("---")
        st.subheader("📈 Visualización Gráfica")
        g1, g2 = st.columns(2)

        with g1:
            st.write(f"**Tendencia / Secuencia de {col_analisis}**")
            fig_l, ax_l = plt.subplots(figsize=(6, 3.4))
            ax_l.plot(serie_analisis.values, color="#10b981", linewidth=1.4, alpha=0.7, label="Valores")
            if len(serie_analisis) > 5:
                suav = serie_analisis.rolling(window=max(3, len(serie_analisis)//20), min_periods=1).mean()
                ax_l.plot(suav, color="#047857", linewidth=2.0, label="Tendencia")
            ax_l.axhline(promedio, color="#ef4444", linestyle="--", label=f"Media: ${promedio:,.2f}")
            ax_l.set_xlabel("Índice de Fila")
            ax_l.set_ylabel(col_analisis)
            ax_l.legend(loc="upper right", fontsize=8)
            ax_l.grid(True, linestyle="--", alpha=0.3)
            st.pyplot(fig_l)
            plt.close(fig_l)

        with g2:
            st.write(f"**Histograma de Concentración**")
            fig_h, ax_h = plt.subplots(figsize=(6, 3.4))
            ax_h.hist(serie_analisis, bins=25, color="#2563eb", edgecolor="#ffffff", alpha=0.85)
            ax_h.axvline(promedio, color="#ef4444", linestyle="--", label=f"Media: ${promedio:,.2f}")
            ax_h.legend(loc="upper right", fontsize=8)
            ax_h.grid(axis='y', linestyle="--", alpha=0.3)
            st.pyplot(fig_h)
            plt.close(fig_h)

        st.write("---")
        st.subheader("🧠 Diagnóstico Ejecutivo de IA")

        if "informe_ia" not in st.session_state:
            st.session_state.informe_ia = ""

        if st.button("✨ Generar Informe Ejecutivo con IA"):
            with st.spinner("Analizando la temática del archivo y sus correlaciones..."):
                prompt_informe = f"""
                Actúa como un Consultor Estratégico y Chief Data Officer.
                Analiza a profundidad este conjunto de datos:

                CONTEXTO DEL DATASET:
                {resumen_datos_global}

                VARIABLE ENFOCADA: '{col_analisis}'
                - Registros: {total_registros:,}
                - Suma acumulada: ${suma_total:,.2f}
                - Media general: ${promedio:,.2f}
                - Mínimo: ${valor_min:,.2f} | Máximo: ${valor_max:,.2f}

                Redacta un informe con la siguiente estructura exacta:
                🎯 1. DIAGNÓSTICO DEL NEGOCIO / OPERACIÓN
                (Explica de qué trata la base de datos según sus columnas y evalúa la salud del indicador principal).

                🔍 2. HALLAZGOS Y PATRONES CRÍTICOS
                - Identifica el comportamiento de los valores más altos y más bajos con sus nombres reales.
                - Analiza la concentración o dispersión del promedio.

                ⚠️ 3. VULNERABILIDADES O RIESGOS IDENTIFICADOS
                (Menciona 2 riesgos operativos o financieros basados en las métricas observadas).

                🚀 4. RECOMENDACIONES TÁCTICAS
                - 💡 Diversificación de Fuentes: Explorar la introducción de productos, servicios o estrategias complementarias que generen ingresos durante periodos de baja demanda.
                - 💡 Optimización de Recursos: Iniciativa concreta según el promedio observado.
                - 💡 Medición Continua: Pauta para controlar umbrales y anomalías.

                Reglas de estilo:
                - Coloca las palabras clave en **negrita**.
                - Cita siempre los valores con un espacio tras el signo (ej: $ 1,500.00).
                """
                texto_ia, modelo_usado = consultar_gemini(prompt_informe)
                if texto_ia:
                    st.session_state.informe_ia = texto_ia
                    st.success(f"Informe redactado exitosamente con {modelo_usado}")
                else:
                    st.error("No se pudo conectar con el servicio de IA. Inténtalo de nuevo.")

        if st.session_state.informe_ia:
            html_formateado = formatear_texto_web(st.session_state.informe_ia)
            st.markdown(f"""
            <div class="metric-card">
                {html_formateado}
            </div>
            """, unsafe_allow_html=True)

        st.write("---")
        st.subheader("📄 Exportación del Informe en PDF")

        img_dist = crear_grafico_distribucion(df_limpio, col_analisis)
        img_line = crear_grafico_linea(df_limpio, col_analisis)

        pdf = generar_pdf_informe(
            nombre_archivo=archivo_subido.name,
            metricas=metricas_dict,
            texto_ia=st.session_state.informe_ia,
            img_buf1=img_dist,
            img_buf2=img_line
        )

        st.download_button(
            label="📥 Descargar Reporte Ejecutivo en PDF",
            data=pdf,
            file_name=f"Reporte_Ejecutivo_{col_analisis}.pdf",
            mime="application/pdf"
        )

    # ----------------------------------------------------
    # TAB 2: CHAT INTELIGENTE CON DATOS REALES
    # ----------------------------------------------------
    with tab_chat:
        st.subheader("💬 Asistente Analítico Conversacional")
        st.caption("Pregunta lo que quieras sobre cualquier columna, categoría, sucursal, producto o cifra.")

        if "mensajes" not in st.session_state:
            st.session_state.mensajes = []

        # Historial de conversación
        for m in st.session_state.mensajes:
            with st.chat_message(m["rol"]):
                st.write(m["contenido"])

        if pregunta_usuario := st.chat_input("Ej: ¿Cuál es el monto más grande, la mejor sucursal y el producto más vendido?"):
            st.session_state.mensajes.append({"rol": "user", "contenido": pregunta_usuario})
            with st.chat_message("user"):
                st.write(pregunta_usuario)

            with st.chat_message("assistant"):
                with st.spinner("Analizando la totalidad de los datos para responder con certeza..."):
                    prompt_chat = f"""
                    Eres un Asistente Senior de Inteligencia de Negocios y Ciencia de Datos.
                    El usuario te está haciendo preguntas sobre un dataset que ha subido.

                    INFORMACIÓN COMPLETA Y RESUMEN REAL DEL DATASET:
                    {resumen_datos_global}

                    PREGUNTA DEL USUARIO:
                    "{pregunta_usuario}"

                    INSTRUCCIONES DE RESPUESTA:
                    1. Revisa detenidamente el resumen estructural, los rankings por categoría, las columnas de texto y las estadísticas.
                    2. Responde con datos y NOMBRES EXACTOS (si preguntan por sucursal, producto, categoría, monto más grande, monto más bajo, etc., dilos explícitamente).
                    3. Si la información solicitada no existe en las columnas disponibles, aclara amablemente qué columnas sí existen para responder.
                    4. No pegues el símbolo '$' a números o palabras para evitar errores de LaTeX (usa '$ 100' o 'USD').
                    5. Sé conciso, directo y utiliza viñetas con emojis claros.
                    """
                    respuesta_chat, modelo_chat = consultar_gemini(prompt_chat)

                    if respuesta_chat:
                        # Reemplazo preventivo para no romper LaTeX
                        respuesta_segura = re.sub(r'\$(\d)', r'$ \1', respuesta_chat)
                        st.write(respuesta_segura)
                        st.caption(f"🤖 Respuesta basada en datos reales vía {modelo_chat}")
                        st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_segura})
                    else:
                        st.error("Los servidores de IA no respondieron. Por favor intenta de nuevo.")