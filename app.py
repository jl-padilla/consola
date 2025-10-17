import streamlit as st
import importlib
import pkgutil
from pathlib import Path
from datetime import datetime
import pandas as pd
import os

# ===========================
# 🔐 CONFIGURACIÓN
# ===========================
st.set_page_config(page_title="Panel de Procesos", page_icon="⚙️", layout="centered")
PASSWORD = os.getenv("APP_PASS", "1234segura")
LOG_PATH = Path("logs/registros.csv")
LOG_PATH.parent.mkdir(exist_ok=True, parents=True)
OUTPUT_PATH = Path("outputs")
OUTPUT_PATH.mkdir(exist_ok=True, parents=True)

# ===========================
# 🧩 CARGAR MÓDULOS DE PROCESOS
# ===========================
def cargar_procesos():
    procesos = {}
    for _, module_name, _ in pkgutil.iter_modules(["procesos"]):
        module = importlib.import_module(f"procesos.{module_name}")
        if hasattr(module, "run") and hasattr(module, "descripcion"):
            procesos[module_name] = module
    return procesos

PROCESOS = cargar_procesos()

# ===========================
# 🔒 LOGIN
# ===========================
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 Acceso restringido")
    clave = st.text_input("Introduce la clave de acceso:", type="password")
    if st.button("Entrar"):
        if clave == PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("❌ Clave incorrecta")
    st.stop()

# ===========================
# 🧭 INTERFAZ
# ===========================
st.sidebar.title("⚙️ Panel de Procesos")
menu = ["📊 Ver registros"] + [f"🚀 {k}" for k in PROCESOS.keys()]
opcion = st.sidebar.radio("Selecciona una opción:", menu)

usuario = st.text_input("👤 Usuario:", placeholder="Tu nombre o iniciales")

def registrar_uso(usuario, proceso, archivo, resultado):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nuevo = pd.DataFrame([[now, usuario, proceso, archivo, resultado]],
                         columns=["Fecha", "Usuario", "Proceso", "Archivo", "Resultado"])
    if LOG_PATH.exists():
        df = pd.read_csv(LOG_PATH)
        df = pd.concat([df, nuevo], ignore_index=True)
    else:
        df = nuevo
    df.to_csv(LOG_PATH, index=False)

# ===========================
# 📊 VER REGISTROS
# ===========================
if opcion == "📊 Ver registros":
    st.header("📊 Registro de uso")
    if LOG_PATH.exists():
        df = pd.read_csv(LOG_PATH)
        st.dataframe(df)
        if st.button("🧹 Limpiar registros"):
            LOG_PATH.unlink()
            st.success("Registros eliminados.")
    else:
        st.info("No hay registros aún.")
    st.stop()

# ===========================
# ⚙️ PROCESOS DINÁMICOS
# ===========================
proceso_key = opcion.replace("🚀 ", "")
mod = PROCESOS.get(proceso_key)

if not mod:
    st.error("No se encontró el proceso seleccionado.")
    st.stop()

st.header(f"🚀 {proceso_key}")
st.write(mod.descripcion())

archivo = st.file_uploader("Sube un archivo PDF para procesar:", type=["pdf"])

if archivo and usuario:
    pdf_path = Path(archivo.name)
    with open(pdf_path, "wb") as f:
        f.write(archivo.getbuffer())
    out_folder = OUTPUT_PATH / proceso_key
    out_folder.mkdir(exist_ok=True, parents=True)

    with st.spinner("Procesando..."):
        try:
            result = mod.run(pdf_path, out_folder)
            st.success("✅ Proceso completado correctamente.")

            # Mostrar resultados si los hay
            for k, v in result.items():
                st.write(f"**{k.capitalize()}:** {v}")

            # Registrar uso
            registrar_uso(usuario, proceso_key, archivo.name, "Éxito")

        except Exception as e:
            st.error(f"⚠ Error: {e}")
            registrar_uso(usuario, proceso_key, archivo.name, f"Error: {e}")
else:
    st.info("🔸 Introduce tu nombre y selecciona un archivo PDF para comenzar.")