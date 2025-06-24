import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import numpy as np
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import plotly.colors as pc
import streamlit as st
import bcrypt
import os


PASSWORD = os.environ.get("PLAIN_PASSWORD") # Aquí recuperas el secreto

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔐 Acceso restringido")
        password_input = st.text_input("Introduce la contraseña:", type="password")
        if st.button("Entrar"):
            if password_input == PASSWORD:
                st.session_state["authenticated"] = True
                st.experimental_rerun()
            else:
                st.error("❌ Contraseña incorrecta")
        st.stop()

check_password()

# --- Contenido principal de la app ---
st.title("🎓 Informe de Asistencia")
st.write("¡Bienvenido! Ya has accedido a la aplicación protegida.")

st.set_page_config(page_title="Informe de Asistencia", layout="wide")
st.title("📁 Subida dos ficheiros dos Profesores y Xeneración de Informes")

DEFAULT_MONTH_ORDER = ['Setembro', 'Octubre', 'Noviembre', 'Decembro', 'Xaneiro', 'Febreiro', 'Marzo', 'Abril', 'Mayo', 'Xuño']


class SheetProcessor:
    def __init__(self):
        self.month_names = DEFAULT_MONTH_ORDER

    def find_user_column(self, df):
        posibles = ['Usuario', 'Profesor', 'usuario', 'profesor', 'USUARIO', 'PROFESOR']
        for col in posibles:
            if col in df.columns and not df[col].dropna().empty:
                return col
        return None

    def process_excel(self, file_path):
        prof_name = None
        results, total_hours, dfs_combined = {}, {}, []
        with pd.ExcelFile(file_path) as xls:
            nombre_archivo = os.path.basename(file_path)
            nombre_profesor = os.path.splitext(nombre_archivo)[0].replace(' Asistencia', '')

            for hoja in xls.sheet_names:
                df = pd.read_excel(file_path, sheet_name=hoja)
                if df.empty:
                    continue

                df_copy = df.copy()
                df_copy['Mes'], df_copy['Profesor'], df_copy['Archivo_Original'] = hoja, nombre_profesor, nombre_archivo
                dfs_combined.append(df_copy)

                if hoja not in self.month_names:
                    continue

                col_realizada = next((c for c in df.columns if 'realizada' in c.lower() or '?' in c.lower()), None)
                col_duracion = next((c for c in df.columns if 'duracion' in c.lower() or 'duración' in c.lower()), None)
                if not (col_realizada and col_duracion):
                    continue

                df = df.dropna(subset=[col_realizada, col_duracion])
                try:
                    df[col_duracion] = pd.to_timedelta(df[col_duracion]).dt.total_seconds() / 3600
                except:
                    df[col_duracion] = df[col_duracion].astype(str).str.extract('(\d+:\d+(?::\d+)?)')
                    df[col_duracion] = pd.to_timedelta(df[col_duracion]).dt.total_seconds() / 3600

                user_col = self.find_user_column(df)
                if not user_col:
                    continue

                if not prof_name:
                    prof_name = df[user_col].dropna().iloc[0]

                if prof_name not in results:
                    results[prof_name] = {m: 0 for m in self.month_names}
                    total_hours[prof_name] = {m: 0 for m in self.month_names}

                total = df.groupby(user_col)[col_duracion].sum()
                total_hours[prof_name][hoja] = total.get(prof_name, 0)

                faltas = df[df[col_realizada].astype(str).str.upper().str.strip() == 'NO']
                faltas_sum = faltas.groupby(user_col)[col_duracion].sum()
                results[prof_name][hoja] = faltas_sum.get(prof_name, 0)

        return results, total_hours, dfs_combined

    def aggregate(self, all_results, total_hours_by_prof):
        profs_data = {}
        for f, results in all_results.items():
            for prof, faltas in results.items():
                faltas_mes = [faltas.get(m, 0) for m in self.month_names]
                total_faltas = sum(faltas_mes)
                total_prog = sum(total_hours_by_prof.get(f, {}).get(prof, {}).get(m, 0) for m in self.month_names)
                pct = (total_faltas / total_prog * 100) if total_prog else 0
                prof_norm = ' '.join(str(prof).split())
                if prof_norm not in profs_data:
                    profs_data[prof_norm] = {
                        'profesor': prof_norm,
                        'horas_no_dadas_por_mes': faltas_mes,
                        'total_horas_no_dadas': total_faltas,
                        'total_horas_prog': total_prog,
                        'porcentaje': pct
                    }
                else:
                    d = profs_data[prof_norm]
                    d['total_horas_no_dadas'] += total_faltas
                    d['total_horas_prog'] += total_prog
                    d['porcentaje'] = (d['total_horas_no_dadas'] / d['total_horas_prog'] * 100) if d['total_horas_prog'] else 0
                    for i, h in enumerate(faltas_mes):
                        d['horas_no_dadas_por_mes'][i] += h
        return list(profs_data.values())

    def calcular_metrica(self, datos):
        if not datos:
            return pd.DataFrame()
        avg = sum(d['total_horas_prog'] for d in datos) / len(datos)
        filas = []
        for d in datos:
            factor = d['total_horas_prog'] / avg if avg else 1
            idx = d['porcentaje'] / np.sqrt(factor) if factor else 0
            row = [d['profesor']] + d['horas_no_dadas_por_mes'] + [d['total_horas_no_dadas'], round(d['porcentaje'], 2), round(idx, 2), round(d['total_horas_prog'], 1)]
            filas.append(row)
        cols = ['Usuario'] + self.month_names + ['Total Horas No Dadas', 'Porcentaje No Asistencia (%)', 'Índice Ponderado', 'Total Horas Programadas']
        return pd.DataFrame(filas, columns=cols).sort_values('Índice Ponderado')

def generar_htmls(df_final, df_combined, df_reincidentes, carpeta_destino):
    # === HTML 1: analisis_asistencia_completo.html ===
    meses = ['Setembro', 'Octubre', 'Noviembre', 'Decembro', 'Xaneiro', 'Febreiro', 'Marzo', 'Abril', 'Mayo', 'Xuño']
    nombres_personalizados = ['Set', 'Oct', 'Nov', 'Dec', 'Xan', 'Feb', 'Mar', 'Abr', 'Mai', 'Xuñ']
    mapa_meses = dict(zip(meses, nombres_personalizados))

    df_final['Nombre'] = df_final['Usuario'].apply(lambda x: x.split()[0])
    colores = pc.qualitative.Plotly
    num_colores = len(colores)

    fig = make_subplots(rows=1, cols=2, subplot_titles=('Evolución Mensual de faltas por Profesor', 'Promedio Xeral de Faltas'))
    for idx, (_, fila) in enumerate(df_final.iterrows()):
        color = colores[idx % num_colores]
        fig.add_trace(
            go.Scatter(
                x=nombres_personalizados,
                y=fila[meses],
                name=fila['Nombre'],
                mode='lines+markers',
                line=dict(color=color),
                marker=dict(color=color),
                visible='legendonly'
            ),
            row=1, col=1
        )

    promedios = df_final[meses].mean()
    fig.add_trace(
        go.Scatter(
            x=nombres_personalizados,
            y=promedios,
            name='Promedio General',
            mode='lines+markers',
            line=dict(color='darkblue', width=3),
            text=[f'{v:.1f}' for v in promedios],
            textposition='top center'
        ),
        row=1, col=2
    )

    resumen = (
        "Promedios por mes:\n" +
        ', '.join([f"{mapa_meses.get(m, m)}: {promedios[m]:.1f}" for m in meses]) +
        f"\n\nMes con máis ausencias: {mapa_meses.get(promedios.idxmax(), promedios.idxmax())} ({promedios.max():.2f} h)" +
        f"\nMes con menos ausencias: {mapa_meses.get(promedios.idxmin(), promedios.idxmin())} ({promedios.min():.2f} h)"
    )
    fig.add_annotation(
        text=f"<b>Resumen estatístico</b><br>{resumen.replace(chr(10), '<br>')}",
        xref='paper', yref='paper',
        x=0.5, y=1.5,
        showarrow=False,
        align='left',
        font=dict(size=12, color='black'),
        bordercolor='gray',
        borderwidth=1,
        borderpad=10,
        bgcolor='white',
        opacity=0.95
    )
    fig.update_layout(height=750, width=1200, showlegend=True, margin=dict(t=220))

    # Gráfico de barras filtrable
    df_largo = df_final.melt(id_vars=['Usuario', 'Nombre'], value_vars=meses, var_name='Mes', value_name='Horas')
    df_largo['Mes_Corto'] = df_largo['Mes'].map(mapa_meses)
    df_json = json.dumps(df_largo.to_dict('records'), ensure_ascii=False)
    nombres_unicos = sorted(df_largo['Nombre'].unique())
    meses_opts = '\n'.join([f'<option value="{m}">{mapa_meses[m]}</option>' for m in meses])
    nombres_opts = '\n'.join([f'<option value="{n}">{n}</option>' for n in nombres_unicos])

    with open(os.path.join(carpeta_destino, 'analisis_asistencia_completo.html'), 'w', encoding='utf-8') as f:
        f.write(f"""
<html>
<head>
    <meta charset="utf-8">
    <title>Informe de Asistencia</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: Arial; margin: 30px; background: #f9f9f9; }}
        .filters {{ margin-top: 50px; display: flex; gap: 20px; }}
        select {{ padding: 6px 12px; font-size: 14px; border-radius: 5px; }}
        .chart-container {{ margin-top: 30px; }}
    </style>
</head>
<body>
    <div>{fig.to_html(full_html=False, include_plotlyjs='cdn')}</div>

    <div class="filters">
        <label><b>Profesor:</b>
            <select id="usuario-select" onchange="actualizarGrafico()">
                <option value="Todos">Todos</option>
                {nombres_opts}
            </select>
        </label>
        <label><b>Mes:</b>
            <select id="mes-select" onchange="actualizarGrafico()">
                <option value="Todos">Todos</option>
                {meses_opts}
            </select>
        </label>
    </div>

    <div class="chart-container">
        <div id="grafico-barras"></div>
    </div>

<script>
    var datos = {df_json};

    function actualizarGrafico() {{
        var usuario = document.getElementById('usuario-select').value;
        var mes = document.getElementById('mes-select').value;

        var filtrado = datos.filter(d =>
            (usuario === 'Todos' || d.Nombre === usuario) &&
            (mes === 'Todos' || d.Mes === mes)
        );

        var agrupado = {{}};
        filtrado.forEach(d => {{
            if (!agrupado[d.Nombre]) agrupado[d.Nombre] = 0;
            agrupado[d.Nombre] += d.Horas;
        }});

        var usuarios = Object.keys(agrupado);
        var horas = Object.values(agrupado);

        var barra = {{
            type: 'bar',
            x: usuarios,
            y: horas,
            text: horas.map(h => h.toFixed(1) + ' h'),
            textposition: 'auto',
            marker: {{ color: '#1f77b4' }}
        }};

        var layout = {{
            title: 'Horas no dadas por Profesor',
            yaxis: {{ title: 'Horas' }},
            xaxis: {{ title: '', tickangle: -45 }},
            height: 400
        }};

        Plotly.newPlot('grafico-barras', [barra], layout);
    }}

    actualizarGrafico();
</script>
</body>
</html>
""")

    # === HTML 2 === con filtros e interacción ===
    df_combined['F. Clase'] = pd.to_datetime(df_combined['F. Clase'], errors='coerce')
    df_combined['Mes'] = df_combined['F. Clase'].dt.month
    df_combined['Año'] = df_combined['F. Clase'].dt.year
    df_combined['Mes_Nombre'] = df_combined['F. Clase'].dt.strftime('%B')

    df_combined['Profesor'] = df_combined['Profesor'].fillna(df_combined['Usuario'])
    df_combined = df_combined[
        df_combined['¿Realizada?'].str.upper().str.strip() == 'NO'
    ]

    df_reincidentes_html = df_combined.groupby(
        ['Profesor', 'Mes', 'Año', 'Descripción Clase', 'Mes_Nombre']
    ).size().reset_index(name='Num_Faltas')

    todos_meses = ['September', 'October', 'November', 'December', 'January', 'February', 'March', 'April', 'May', 'Xuño']
    nombres_personalizados = ['Setembro', 'Outubre', 'Novembro', 'Decembro', 'Xaneiro', 'Febreiro', 'Marzo', 'Abril', 'Maio', 'Xuño']
    mapa_meses_personalizados = dict(zip(todos_meses, nombres_personalizados))

    df_reincidentes_html['Mes_Nombre_Personalizado'] = df_reincidentes_html['Mes_Nombre'].map(
        mapa_meses_personalizados
    ).fillna(df_reincidentes_html['Mes_Nombre'])

    profesores = sorted(df_reincidentes_html['Profesor'].unique())
    profesores_options = '\n'.join([f'<option value="{p}">{p}</option>' for p in profesores])

    meses_unicos = sorted(df_reincidentes_html['Mes_Nombre'].unique())
    meses_options = '\n'.join([
        f'<option value="{m}">{mapa_meses_personalizados.get(m, m)}</option>'
        for m in meses_unicos
    ])

    data_json = json.dumps(df_reincidentes_html.to_dict('records'), ensure_ascii=False)

    html_content = f"""
<html>
<head>
    <title>Táboa de Faltas por Profesor</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .filters {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            align-items: center;
        }}
        select {{
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            min-width: 200px;
            background-color: white;
        }}
        .chart-container {{
            margin-top: 20px;
            padding: 15px;
            background-color: white;
            border-radius: 8px;
        }}
        label {{
            font-weight: bold;
            color: #333;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="filters">
            <div>
                <label>Profesor:</label>
                <select id="profesor-select" onchange="updatePlot()">
                    <option value="Todos">Todos os Profesores</option>
                    {profesores_options}
                </select>
            </div>
            <div>
                <label>Mes:</label>
                <select id="mes-select" onchange="updatePlot()">
                    <option value="Todos">Todos os Meses</option>
                    {meses_options}
                </select>
            </div>
        </div>
        <div class="chart-container">
            <div id="tabla"></div>
        </div>
        <div class="chart-container">
            <div id="grafico"></div>
        </div>
    </div>

<script>
    var data = {data_json};

    function filterData(profesor, mes) {{
        return data.filter(function(row) {{
            return (profesor === 'Todos' || row['Profesor'] === profesor) &&
                   (mes === 'Todos' || row['Mes_Nombre'] === mes);
        }});
    }}

    function updatePlot() {{
        var profesor = document.getElementById('profesor-select').value;
        var mes = document.getElementById('mes-select').value;
        var filteredData = filterData(profesor, mes);

        var tabla = {{
            type: 'table',
            header: {{
                values: ['Profesor', 'Mes', 'Ano', 'Descripción Clase', 'Número de Faltas'],
                align: 'left',
                font: {{color: 'white', size: 12}},
                fill: {{color: '#1f77b4'}},
                line: {{color: 'white', width: 1}}
            }},
            cells: {{
                values: [
                    filteredData.map(row => row['Profesor']),
                    filteredData.map(row => row['Mes_Nombre']),
                    filteredData.map(row => row['Año']),
                    filteredData.map(row => row['Descripción Clase']),
                    filteredData.map(row => row['Num_Faltas'])
                ],
                align: 'left',
                font: {{size: 11}},
                height: 30,
                fill: {{color: ['rgba(242, 242, 242, 0.5)', 'white']}},
                line: {{color: '#ccc', width: 1}}
            }}
        }};

        Plotly.newPlot('tabla', [tabla], {{
            height: 500,
            margin: {{t: 10, b: 10}}
        }});

        var profesores = [...new Set(filteredData.map(row => row['Profesor']))];
        var faltas = profesores.map(p =>
            filteredData
                .filter(row => row['Profesor'] === p)
                .reduce((sum, row) => sum + row['Num_Faltas'], 0)
        );

        var total_faltas = faltas.reduce((a, b) => a + b, 0);

        var barras = {{
            type: 'bar',
            x: profesores,
            y: faltas,
            text: faltas,
            textposition: 'auto',
            marker: {{
                color: '#1f77b4',
                opacity: 0.8
            }}
        }};

        var layout = {{
            height: 450,
            margin: {{t: 80, b: 40, l: 60, r: 40}},
            yaxis: {{
                title: 'Número de Faltas',
                gridcolor: '#eee'
            }},
            xaxis: {{
                title: '',
                tickangle: -45
            }},
            plot_bgcolor: 'white',
            paper_bgcolor: 'white',
            annotations: [
                {{
                    text: '<b>Total de Faltas: ' + total_faltas + '</b>',
                    xref: 'paper',
                    yref: 'paper',
                    x: 0.5,
                    y: 1.15,
                    showarrow: false,
                    font: {{size: 14, color: 'black'}},
                    align: 'center'
                }}
            ]
        }};

        Plotly.newPlot('grafico', [barras], layout);
    }}

    updatePlot();
</script>
</body>
</html>
"""

    with open(os.path.join(carpeta_destino, 'tabla_faltas_alumnos_por_profesor.html'), 'w', encoding='utf-8') as f:
        f.write(html_content)

    # === HTML 3: Alertas Alumnos +2 faltas (interactivo) ===
    df_combined['F. Clase'] = pd.to_datetime(df_combined['F. Clase'], errors='coerce')
    df_combined['Mes'] = df_combined['F. Clase'].dt.month
    df_combined['Año'] = df_combined['F. Clase'].dt.year
    df_combined['Mes_Nombre'] = df_combined['F. Clase'].dt.strftime('%B')

    # Traducción de meses
    mapa_meses = {
        'September': 'Setembro', 'October': 'Outubre', 'November': 'Novembro',
        'December': 'Decembro', 'January': 'Xaneiro', 'February': 'Febreiro',
        'March': 'Marzo', 'April': 'Abril', 'May': 'Maio'
    }
    df_combined['Mes_Nombre_Personalizado'] = df_combined['Mes_Nombre'].map(mapa_meses).fillna(df_combined['Mes_Nombre'])

    # Unificar profesor
    df_combined['Profesor'] = df_combined['Profesor'].fillna(df_combined['Usuario'])

    # Filtrar clases no realizadas
    alumnos_reincidentes = df_combined[df_combined['¿Realizada?'].str.upper().str.strip() == 'NO']

    # Agrupar por clase/profesor/mes/año y contar faltas
    faltas_por_mes = alumnos_reincidentes.groupby(
        ['Profesor', 'Descripción Clase', 'Mes_Nombre_Personalizado', 'Año']
    ).size().reset_index(name='Num_Faltas')

    # Filtrar solo con 2 o más faltas
    alertas = faltas_por_mes[faltas_por_mes['Num_Faltas'] >= 2]

    # Convertir a JSON y crear opciones
    data_json = json.dumps(alertas.to_dict('records'), ensure_ascii=False)
    profesores = sorted(alertas['Profesor'].unique())
    meses = sorted(alertas['Mes_Nombre_Personalizado'].unique())
    mes_options = '\n'.join([f'<option value="{m}">{m}</option>' for m in meses])

    # Generar HTML final
    html_content = f"""
<html>
<head>
    <meta charset="utf-8">
    <title>Alertas de Faltas por Profesor</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            padding: 20px;
            background-color: #f8f8f8;
        }}
        h2 {{
            color: #333;
        }}
        .filters {{
            margin-bottom: 20px;
        }}
        .prof-section {{
            margin-top: 40px;
        }}
        .prof-section h3 {{
            color: #003366;
        }}
    </style>
</head>
<body>

<h2>📋 Grupos con 2 o más faltas en un mismo mes</h2>

<div class="filters">
    <label><b>Filtrar por mes:</b></label>
    <select id="mes-select" onchange="actualizarTodasLasTablas()">
        <option value="Todos">Todos</option>
        {mes_options}
    </select>
</div>

<div id="contenedor-tablas"></div>

<script>
    var data = {data_json};

    function generarID(nombre) {{
        return nombre.replace(/\\s+/g, '_').replace(/[^a-zA-Z0-9_]/g, '');
    }}

    function crearTabla(profesor, registros) {{
        const div = document.createElement('div');
        div.className = 'prof-section';
        const idTabla = "tabla-" + generarID(profesor);
        div.innerHTML = "<h3>" + profesor + "</h3><div id='" + idTabla + "'></div>";
        document.getElementById('contenedor-tablas').appendChild(div);

        var tabla = {{
            type: 'table',
            header: {{
                values: ['Descripción Clase', 'Mes', 'Año', 'Nº Faltas'],
                align: 'left',
                fill: {{ color: '#003366' }},
                font: {{ color: 'white', size: 12 }}
            }},
            cells: {{
                values: [
                    registros.map(r => r['Descripción Clase']),
                    registros.map(r => r['Mes_Nombre_Personalizado']),
                    registros.map(r => r['Año']),
                    registros.map(r => r['Num_Faltas'])
                ],
                align: 'left',
                fill: {{ color: [['#f9f9f9', 'white']] }},
                font: {{ size: 11 }}
            }}
        }};

        Plotly.newPlot(idTabla, [tabla], {{
            margin: {{ t: 10 }}
        }});
    }}

    function actualizarTodasLasTablas() {{
        const mes = document.getElementById('mes-select').value;
        const contenedor = document.getElementById('contenedor-tablas');
        contenedor.innerHTML = '';

        const agrupado = {{}};
        data.forEach(r => {{
            if (mes !== 'Todos' && r['Mes_Nombre_Personalizado'] !== mes) return;
            if (!agrupado[r['Profesor']]) agrupado[r['Profesor']] = [];
            agrupado[r['Profesor']].push(r);
        }});

        Object.keys(agrupado).forEach(profesor => {{
            crearTabla(profesor, agrupado[profesor]);
        }});
    }}

    actualizarTodasLasTablas();
</script>

</body>
</html>
"""

    with open(os.path.join(carpeta_destino, 'alertas_faltas_por_profesor.html'), 'w', encoding='utf-8') as f:
        f.write(html_content)

    # === HTML 4: Gráfico de Alertas Ordenadas (interactivo con filtros) ===
    df_combined['F. Clase'] = pd.to_datetime(df_combined['F. Clase'])
    df_combined['Mes_Nombre'] = df_combined['F. Clase'].dt.strftime('%B')

    mapa_meses = {
        'September': 'Setembro', 'October': 'Outubre', 'November': 'Novembro',
        'December': 'Decembro', 'January': 'Xaneiro', 'February': 'Febreiro',
        'March': 'Marzo', 'April': 'Abril', 'May': 'Maio'
    }
    df_combined['Mes_Nombre_Personalizado'] = df_combined['Mes_Nombre'].map(mapa_meses).fillna(df_combined['Mes_Nombre'])
    df_combined['Profesor'] = df_combined['Profesor'].fillna(df_combined['Usuario'])

    alumnos_reincidentes = df_combined[df_combined['¿Realizada?'].str.upper().str.strip() == 'NO']
    faltas_por_mes = alumnos_reincidentes.groupby(
        ['Profesor', 'Descripción Clase']
    ).agg({'Duración': 'count'}).reset_index().rename(columns={'Duración': 'Num_Faltas'})

    alertas_sorted = faltas_por_mes.sort_values(by='Num_Faltas', ascending=False)
    data_json = json.dumps(alertas_sorted.to_dict('records'), ensure_ascii=False)
    profesores = sorted(alertas_sorted['Profesor'].unique())
    prof_opts = '\n'.join([f'<option value="{p}">{p}</option>' for p in profesores])

    html = f"""
<html>
<head>
    <meta charset="utf-8">
    <title>Gráfico de Alertas Ordenadas</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: Arial;
            padding: 30px;
            background-color: #f5f5f5;
        }}
        select {{
            padding: 8px 12px;
            font-size: 14px;
            margin-right: 15px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>

<h2>🔻 Grupos con faltas (ordenados)</h2>

<label><b>Filtrar por profesor:</b></label>
<select id="prof-select" onchange="filtrarGrafico()">
    <option value="Todos">Todos</option>
    {prof_opts}
</select>

<label><b>Mínimo de faltas:</b></label>
<select id="min-faltas" onchange="filtrarGrafico()">
    <option value="2">+2</option>
    <option value="3">+3</option>
    <option value="5">+5</option>
    <option value="8">+8</option>
    <option value="10">+10</option>
    <option value="15">+15</option>
</select>

<div id="grafico"></div>

<script>
    const datos = {data_json};
    const colores = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
        '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
        '#bcbd22', '#17becf'
    ];

    const profesoresUnicos = [...new Set(datos.map(d => d.Profesor))];
    const mapaColores = {{}};
    profesoresUnicos.forEach((prof, i) => {{
        mapaColores[prof] = colores[i % colores.length];
    }});

    function filtrarGrafico() {{
        const prof = document.getElementById("prof-select").value;
        const minFaltas = parseInt(document.getElementById("min-faltas").value);

        let datos_filtrados = datos.filter(d =>
            d.Num_Faltas >= minFaltas &&
            (prof === "Todos" || d.Profesor === prof)
        );

        datos_filtrados.sort((a, b) => b.Num_Faltas - a.Num_Faltas);

        let trazas = [];

        if (prof === "Todos") {{
            profesoresUnicos.forEach(p => {{
                const datos_prof = datos_filtrados.filter(d => d.Profesor === p);
                if (datos_prof.length > 0) {{
                    trazas.push({{
                        type: 'bar',
                        name: p,
                        x: datos_prof.map(d => d['Descripción Clase']),
                        y: datos_prof.map(d => d['Num_Faltas']),
                        text: datos_prof.map(d => d['Num_Faltas']),
                        textposition: 'outside',
                        marker: {{ color: mapaColores[p] }}
                    }});
                }}
            }});
        }} else {{
            trazas.push({{
                type: 'bar',
                name: prof,
                x: datos_filtrados.map(d => d['Descripción Clase']),
                y: datos_filtrados.map(d => d['Num_Faltas']),
                text: datos_filtrados.map(d => d['Num_Faltas']),
                textposition: 'outside',
                marker: {{ color: mapaColores[prof] }}
            }});
        }}

        const layout = {{
            title: '',
            yaxis: {{ title: 'Número de Faltas' }},
            xaxis: {{
                title: '',
                tickangle: -30,
                automargin: true,
                tickfont: {{ size: 11 }}
            }},
            height: 900,
            margin: {{ b: 250 }},
            barmode: 'group',
            showlegend: false,
            legend: {{
                orientation: "h",
                xanchor: "center",
                x: 0.5,
                y: 1.1
            }}
        }};

        
        Plotly.newPlot('grafico', trazas, layout, {{ responsive: true }});
    }}

    filtrarGrafico();
</script>

</body>
</html>
"""

    with open(os.path.join(carpeta_destino, "grafico_barras_alertas_ordenado_filtrable.html"), "w", encoding="utf-8") as f:
        f.write(html)

uploaded_files = st.file_uploader("Sube los archivos (Excel o ZIP):", type=["xlsx", "xls", "zip"], accept_multiple_files=True)
if uploaded_files:
    processor = SheetProcessor()
    all_results, total_hours_by_prof, dfs_combined = {}, {}, []

    with tempfile.TemporaryDirectory() as temp_dir:
        for f in uploaded_files:
            if f.name.endswith(".zip"):
                with zipfile.ZipFile(f) as z:
                    z.extractall(temp_dir)
                    for ef in z.namelist():
                        p = os.path.join(temp_dir, ef)
                        if p.endswith((".xlsx", ".xls")):
                            r, t, dfs = processor.process_excel(p)
                            all_results[ef], total_hours_by_prof[ef] = r, t
                            dfs_combined.extend(dfs)
            else:
                p = os.path.join(temp_dir, f.name)
                with open(p, "wb") as out: out.write(f.read())
                r, t, dfs = processor.process_excel(p)
                all_results[f.name], total_hours_by_prof[f.name] = r, t
                dfs_combined.extend(dfs)

        if dfs_combined:
            df_combined = pd.concat(dfs_combined, ignore_index=True)
            df_combined['F. Clase'] = pd.to_datetime(df_combined['F. Clase'], errors='coerce')

            df_faltas = df_combined[df_combined['¿Realizada?'].str.upper().str.strip() == 'NO'].copy()
            df_faltas['Mes'] = df_faltas['F. Clase'].dt.month
            df_faltas['Año'] = df_faltas['F. Clase'].dt.year
            df_faltas['Mes_Nombre'] = df_faltas['F. Clase'].dt.strftime('%B')

            reincidentes = df_faltas.groupby(['Profesor', 'Mes', 'Año', 'Descripción Clase', 'Mes_Nombre']).size().reset_index(name='Num_Faltas')

            
            df_final = processor.calcular_metrica(processor.aggregate(all_results, total_hours_by_prof))

            carpeta_resultados = 'informe_asistencia'
            os.makedirs(carpeta_resultados, exist_ok=True)

            combined_path = os.path.join(carpeta_resultados, "asistencia_combinada.xlsx")
            df_combined.to_excel(combined_path, index=False)

            csv_path = os.path.join(carpeta_resultados, "resultado_asistencia_2025.csv")
            df_final.to_csv(csv_path, index=False)

            reincidentes_path = os.path.join(carpeta_resultados, "alumnos_reincidentes.xlsx")
            reincidentes.to_excel(reincidentes_path, index=False)

            generar_htmls(df_final, df_combined, reincidentes, carpeta_resultados)

            st.success("✅ Procesamiento completo y archivos generados.")
            st.download_button("⬇️ Descargar CSV Métricas Finales", data=open(csv_path, "rb").read(), file_name="resultado_asistencia_2025.csv", mime="text/csv")
            st.download_button("⬇️ Descargar Excel Combinado", data=open(combined_path, "rb").read(), file_name="asistencia_combinada.xlsx")
            st.download_button("⬇️ Descargar Excel Reincidentes", data=open(reincidentes_path, "rb").read(), file_name="alumnos_reincidentes.xlsx")
else:
    st.info("Sube archivos para comenzar.")
