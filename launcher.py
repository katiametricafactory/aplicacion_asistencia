import sys
import subprocess
import os
import webbrowser
import time

# Detectar si está compilado con PyInstaller
if hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

os.chdir(base_path)

# 🟢 Asume que aplicacion.py está incluido en la raíz del ejecutable
script_path = os.path.join(base_path, 'aplicacion.py')

print("🔎 Verificando rutas...")
print(f"📂 Base: {base_path}")
print(f"🐍 Ejecutable de Python: python")
print(f"📄 Script Streamlit: {script_path}")
print("")

if not os.path.isfile(script_path):
    print(f"❌ ERROR: No se encontró el archivo {script_path}")
    input("Presiona una tecla para salir...")
    sys.exit(1)

print("🚀 Ejecutando la aplicación Streamlit...")
print("⏳ Espera unos segundos...")

try:
    subprocess.Popen([
        'python', '-m', 'streamlit', 'run', script_path,
        '--server.headless', 'true'
    ])
except Exception as e:
    print(f"❌ ERROR al lanzar Streamlit: {e}")
    input("Presiona una tecla para salir...")
    sys.exit(1)

time.sleep(2)
print("🌐 Abriendo navegador en http://localhost:8501 ...")
webbrowser.open("http://localhost:8501")
input("Presiona una tecla para finalizar...")
