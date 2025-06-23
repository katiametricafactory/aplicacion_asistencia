import streamlit as st
import streamlit.components.v1 as components
import os

st.set_page_config(page_title="Informe de Asistencia", layout="wide")

st.markdown("""
    <style>
        .main {
            background: linear-gradient(135deg, #8B0000, #FF6347);
            min-height: 100vh;
        }
        .encabezado {
            background-color: #003366;
            padding: 25px 0;
            text-align: center;
            box-shadow: 0 3px 8px rgba(0, 0, 0, 0.3);
            margin-bottom: 0;
        }
        .encabezado h1 {
            color: white;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-weight: 700;
            font-size: 50px;
            margin: 0;
            letter-spacing: 1.1px;
        }
        .stTabs [role="tablist"] {
            background-color: #e6e6e6;
            border-radius: 5px 5px 0 0;
            padding: 5px 0;
            justify-content: center;
            margin-top: 0;
            box-shadow: inset 0 -2px 3px rgb(0 0 0 / 0.1);
        }
        div[role="presentation"][aria-hidden="true"] {
            display: none !important;
        }
        .stTabs [role="tab"] {
            font-weight: 600;
            font-size: 30px;
            padding: 10px 28px;
            margin: 0 6px;
            border-radius: 8px 8px 0 0;
            color: #222;
            background-color: transparent;
            border: none;
            transition: all 0.25s ease;
        }
        .stTabs [role="tab"]:hover:not([aria-selected="true"]) {
            background-color: #d0d7e6;
            cursor: pointer;
            color: #003366;
        }
        .stTabs [aria-selected="true"] {
            background-color: white;
            color: #003366;
            font-weight: 700;
            box-shadow: inset 0 -4px 0 0 #003366;
            border-bottom: none !important;
        }
        iframe {
            width: 100% !important;
            height: 1000px !important;
            border: none;
            border-radius: 6px;
            box-shadow: 0 6px 16px rgba(0,0,0,0.12);
            display: block;
            margin: 0 auto;
        }
    </style>

    <div class="encabezado">
        <h1>Informe de Asistencia e Faltas</h1>
    </div>
""", unsafe_allow_html=True)

# Ruta donde se crean los HTMLs generados

base_path = os.path.dirname(os.path.abspath(__file__))
carpeta_resultados = os.path.abspath(os.path.join(base_path, '..', 'informe_asistencia'))


# Pestañas e informes a mostrar
tabs = st.tabs([
    "📈 Análise Temporal (horas)",
    "📋 Táboa por Clases NON dadas",
    "🚨 Alertas Alumnos +2 faltas",
    "📊 Gráfico +2 faltas"
])

archivos_html = [
    "analisis_asistencia_completo.html",
    "tabla_faltas_alumnos_por_profesor.html",
    "alertas_faltas_por_profesor.html",
    "grafico_barras_alertas_ordenado_filtrable.html"
]

# Mostrar cada archivo HTML en su pestaña
for tab, archivo in zip(tabs, archivos_html):
    with tab:
        ruta_html = os.path.join(carpeta_resultados, archivo)
        if os.path.exists(ruta_html):
            with open(ruta_html, 'r', encoding='utf-8') as f:
                html = f.read()
                components.html(html, height=1000, scrolling=True)
        else:
            st.warning(f"⚠️ No se encontró el archivo: {archivo}")