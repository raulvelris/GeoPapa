"""
Configuración central del backend.

No contiene lógica de negocio: solo rutas, nombres de columnas reales
del CSV y parámetros de interfaz/negocio configurables.
"""

from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Carga backend/.env antes de leer variables de entorno. Las variables ya
# definidas en el sistema tienen prioridad.
load_dotenv(BASE_DIR / ".env", override=False)

CSV_PREDICCIONES_PATH = DATA_DIR / "etapa2_predicciones_mapa.csv"
METADATA_MODELO_PATH = DATA_DIR / "etapa2_modelo_final_metadata.json"
MODELO_JOBLIB_PATH = DATA_DIR / "etapa2_modelo_final.joblib"  # se conserva, NO se carga en esta versión

# Historial conversacional local. SQLite usa la librería estándar de Python.
SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(DATA_DIR / "chat_history.db")))

COL_GRID_CODE = "grid_code"
COL_X = "x"
COL_Y = "y"
COL_PAIS = "ADM0_NAME"
COL_DEPARTAMENTO = "ADM1_NAME"
COL_PROVINCIA = "ADM2_NAME"

PREDICTORES_MODELO = [
    "tmin_media_2020_c",
    "tmax_media_2020_c",
    "prec_total_2020_mm",
    "elevacion_m",
    "ph_suelo_0_5cm",
    "carbono_organico_g_kg_0_5cm",
    "arcilla_pct_0_5cm",
    "arena_pct_0_5cm",
    "cec_cmol_kg_0_5cm",
    "x",
    "y",
    "ndvi_media_2020",
    "ndvi_p90_2020",
    "ndvi_amplitud_2020",
    "evi_media_2020",
    "evi_amplitud_2020",
    "fraccion_cultivo_2020",
]

VARIABLES_AGROECOLOGICAS = [c for c in PREDICTORES_MODELO if c not in (COL_X, COL_Y)]
assert len(VARIABLES_AGROECOLOGICAS) == 15

GRUPO_VARIABLE = {
    "tmin_media_2020_c": ("clima", "°C"),
    "tmax_media_2020_c": ("clima", "°C"),
    "prec_total_2020_mm": ("clima", "mm"),
    "elevacion_m": ("terreno", "m"),
    "ph_suelo_0_5cm": ("suelo", "pH"),
    "carbono_organico_g_kg_0_5cm": ("suelo", "g/kg"),
    "arcilla_pct_0_5cm": ("suelo", "%"),
    "arena_pct_0_5cm": ("suelo", "%"),
    "cec_cmol_kg_0_5cm": ("suelo", "cmol/kg"),
    "ndvi_media_2020": ("vegetacion", "índice"),
    "ndvi_p90_2020": ("vegetacion", "índice"),
    "ndvi_amplitud_2020": ("vegetacion", "índice"),
    "evi_media_2020": ("vegetacion", "índice"),
    "evi_amplitud_2020": ("vegetacion", "índice"),
    "fraccion_cultivo_2020": ("vegetacion", "fracción"),
}

COL_REFERENCIA_MAPSPAM = "rendimiento_referencia_mapspam_t_ha"
COL_PREDICCION_BRUTA = "prediccion_modelo_final_t_ha"
COL_RENDIMIENTO_ESTIMADO = "rendimiento_estimado_t_ha"
COL_AJUSTADO_NEGATIVO = "ajustado_por_valor_negativo"

UMBRAL_POCAS_CELDAS = int(os.getenv("UMBRAL_POCAS_CELDAS", "5"))
MENSAJE_POCAS_CELDAS = (
    "El resultado se basa en pocas celdas disponibles y debe interpretarse con cautela."
)
MENSAJE_VALOR_AJUSTADO = (
    "El valor original del modelo era negativo (no interpretable físicamente); "
    "se muestra como 0 t/ha únicamente para presentación/uso operativo. "
    "El valor bruto original se conserva para trazabilidad."
)

LIMITE_BUSQUEDA_DEFAULT = 20
LIMITE_RANKING_DEFAULT = 10
LIMITE_RANKING_MAX = 100

# ---------------------------------------------------------------------------
# Asistente conversacional (Google Gemini API)
# ---------------------------------------------------------------------------

# API key exclusiva del backend; nunca se expone al frontend.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Modelo estable con function calling y nivel gratuito disponible para nuevos
# proyectos al momento de preparar esta versión. Puede cambiarse desde .env.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Máximo de tokens de salida del LLM.
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048"))

# Timeout HTTP por llamada al servicio, en segundos. El SDK recibe milisegundos.
GEMINI_TIMEOUT_SEGUNDOS = float(os.getenv("GEMINI_TIMEOUT_SEGUNDOS", "30"))

MAX_TOOL_ITERATIONS = int(os.getenv("MAX_TOOL_ITERATIONS", "6"))
MAX_MENSAJES_HISTORIAL = int(os.getenv("MAX_MENSAJES_HISTORIAL", "12"))
