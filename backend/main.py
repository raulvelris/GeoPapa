"""
main.py

API FastAPI. Cada endpoint es un wrapper delgado sobre las funciones ya
probadas de tools/geospatial_tools.py: no hay lógica de negocio propia
aquí, solo validación de entrada/salida (Pydantic) y traducción de
excepciones de negocio a códigos HTTP.

Reglas que esta capa respeta:
- No modifica data_service.py ni geospatial_tools.py.
- No carga ni usa etapa2_modelo_final.joblib para predecir.
- rendimiento_estimado_t_ha es el valor operativo; prediccion_modelo_final_t_ha
  (bruta) se conserva solo para trazabilidad.
- Las métricas OOF (GET /health) están completamente separadas de las
  predicciones operativas (GET /zonas, /ranking, etc.).
- ZonaNoEncontradaError / DepartamentoNoEncontradoError -> HTTP 404.
- Parámetros inválidos (tipo, rango, forma) -> HTTP 422 (validación
  automática de FastAPI/Pydantic); errores de reglas de negocio explícitas
  (ej. orden distinto de 'mayor'/'menor' si llegara a colarse) -> HTTP 400.
"""

from __future__ import annotations

import os
from typing import Literal, Optional

import config  # noqa: F401  (garantiza que .env se cargue antes de leer ALLOWED_ORIGINS)
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services import chat_service, database_service, model_service
from services.chat_service import ChatServiceError
from services.database_service import ConversacionNoEncontradaError
from services.data_service import (
    DepartamentoNoEncontradoError,
    ZonaNoEncontradaError,
    get_data_service,
)
from tools import geospatial_tools as gt

from schemas.buscar import BuscarZonasResponse
from schemas.chat import ChatRequest, ChatResponse
from schemas.comparar import CompararZonasRequest, CompararZonasResponse
from schemas.conversaciones import (
    ConversacionCreada,
    ConversacionDetalle,
    ConversacionResumen,
    EliminarConversacionResponse,
)
from schemas.estadisticas import EstadisticasDepartamentoResponse
from schemas.health import HealthResponse
from schemas.mapa import CeldaMapa
from schemas.ranking import RankingResponse
from schemas.zona import VariablesZonaResponse, ZonaCompleta

app = FastAPI(
    title="API Agroecológica - Rendimiento de Papa (Perú)",
    description=(
        "Backend de consulta geoespacial sobre estimaciones de rendimiento de "
        "papa (Etapa 2, modelo XGBoost ya entrenado y evaluado). Este servicio "
        "NO reentrena ni recalcula el modelo: únicamente sirve las "
        "estimaciones ya calculadas en etapa2_predicciones_mapa.csv."
    ),
    version="0.7.0",
)

# ---------------------------------------------------------------------------
# CORS configurable vía variable de entorno ALLOWED_ORIGINS (lista separada
# por comas). Por defecto se habilitan orígenes típicos de desarrollo local
# para poder conectar después un frontend.
# Ejemplo: ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
# ---------------------------------------------------------------------------
_DEFAULT_ORIGINS = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173"
_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crea las tablas de historial si aún no existen. No toca el dataset ni el modelo.
database_service.init_db()

# Modo público: no guardar conversaciones en SQLite ni permitir leer el
# historial compartido. El modo local original permanece sin cambios.
PUBLIC_CHAT_MODE = os.getenv("PUBLIC_CHAT_MODE", "false").lower() in ("1", "true", "yes")

def _require_private_history():
    if PUBLIC_CHAT_MODE:
        raise HTTPException(
            status_code=403,
            detail="El historial compartido está desactivado en la versión pública.",
        )


# ---------------------------------------------------------------------------
# Traducción de excepciones de negocio -> HTTP
# ---------------------------------------------------------------------------

@app.exception_handler(ZonaNoEncontradaError)
async def _handle_zona_no_encontrada(request, exc: ZonaNoEncontradaError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(DepartamentoNoEncontradoError)
async def _handle_departamento_no_encontrado(request, exc: DepartamentoNoEncontradoError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def _handle_value_error(request, exc: ValueError):
    # Errores de reglas de negocio explícitas que no alcanzó a atrapar la
    # validación de Pydantic (ej. defensivo, no debería ocurrir en la
    # práctica porque Literal/Query ya restringen los valores válidos).
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ChatServiceError)
async def _handle_chat_service_error(request, exc: ChatServiceError):
    # Problemas de configuración del asistente (p. ej. falta GEMINI_API_KEY).
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(ConversacionNoEncontradaError)
async def _handle_conversacion_no_encontrada(request, exc: ConversacionNoEncontradaError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["sistema"])
def health():
    """Confirma que el CSV y el metadata del modelo cargaron correctamente."""
    ds = get_data_service()
    info_modelo = model_service.obtener_info_modelo()
    return {
        "status": "ok",
        "n_celdas_cargadas": len(ds.df),
        "departamentos_disponibles": len(ds.departamentos_disponibles()),
        "info_modelo": info_modelo,
    }


# ---------------------------------------------------------------------------
# GET /mapa
# ---------------------------------------------------------------------------

@app.get(
    "/mapa",
    response_model=list[CeldaMapa],
    tags=["mapa"],
)
def obtener_mapa():
    """Devuelve las 1,983 celdas en formato liviano para Leaflet.

    Incluye centro, límites de la celda, ubicación administrativa y el
    rendimiento estimado operativo. No expone el DataFrame completo ni
    ejecuta nuevas predicciones.
    """
    return get_data_service().obtener_datos_mapa()


# ---------------------------------------------------------------------------
# GET /zonas/{grid_code}
# ---------------------------------------------------------------------------

@app.get("/zonas/{grid_code}", response_model=ZonaCompleta, tags=["zonas"])
def obtener_zona(
    grid_code: int = Path(..., description="Identificador de celda (grid_code)"),
):
    """Ubicación, rendimiento estimado y variables agroecológicas de una zona."""
    return gt.resumir_zona(grid_code)

# ---------------------------------------------------------------------------
# GET /zonas/{grid_code}/variables
# ---------------------------------------------------------------------------

@app.get(
    "/zonas/{grid_code}/variables",
    response_model=VariablesZonaResponse,
    tags=["zonas"],
)
def obtener_variables_zona(
    grid_code: int = Path(..., description="Identificador de celda (grid_code)"),
):
    """Únicamente las 15 variables agroecológicas disponibles para la zona."""
    return gt.obtener_variables_agroecologicas(grid_code)


# ---------------------------------------------------------------------------
# GET /buscar
# ---------------------------------------------------------------------------

@app.get("/buscar", response_model=BuscarZonasResponse, tags=["zonas"])
def buscar(
    texto: str = Query(
        ..., min_length=1, description="Departamento, provincia o grid_code exacto"
    ),
    limite: int = Query(20, gt=0, le=200, description="Máximo de resultados a devolver"),
):
    """Busca zonas por departamento, provincia (no hay nivel distrital en
    este dataset) o grid_code exacto."""
    return gt.buscar_zonas(texto=texto, limite=limite)


# ---------------------------------------------------------------------------
# GET /ranking
# ---------------------------------------------------------------------------

@app.get("/ranking", response_model=RankingResponse, tags=["ranking"])
def ranking(
    n: int = Query(10, gt=0, le=100, description="Cantidad de zonas a devolver"),
    orden: Literal["mayor", "menor"] = Query(
        "mayor", description="'mayor' o 'menor' rendimiento estimado"
    ),
    departamento: Optional[str] = Query(
        None, description="Filtrar por departamento (opcional)"
    ),
):
    """Zonas con mayor o menor rendimiento estimado, opcionalmente filtradas
    por departamento."""
    return gt.ranking_rendimiento(n=n, orden=orden, departamento=departamento)


# ---------------------------------------------------------------------------
# GET /departamentos/{departamento}/estadisticas
# ---------------------------------------------------------------------------

@app.get(
    "/departamentos/{departamento}/estadisticas",
    response_model=EstadisticasDepartamentoResponse,
    tags=["departamentos"],
)
def estadisticas_departamento(
    departamento: str = Path(..., description="Nombre del departamento (ADM1_NAME)"),
):
    """Estadísticas descriptivas del rendimiento estimado dentro del
    departamento. No son las métricas oficiales de desempeño del modelo."""
    return gt.estadisticas_departamento(departamento)


# ---------------------------------------------------------------------------
# POST /comparar-zonas
# ---------------------------------------------------------------------------

@app.post("/comparar-zonas", response_model=CompararZonasResponse, tags=["zonas"])
def comparar_zonas(body: CompararZonasRequest):
    """Compara 2 o más zonas por rendimiento estimado y variables
    agroecológicas. La validación de 'al menos 2 grid_codes' la hace
    Pydantic (422 si se envía menos de 2)."""
    return gt.comparar_zonas(body.grid_codes)


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(body: ChatRequest):
    """Asistente conversacional con historial persistente en SQLite.

    - Si llega conversation_id, el historial se recupera de SQLite.
    - Si no llega, se crea una conversación nueva automáticamente.
    - Se conserva `historial` únicamente por compatibilidad con clientes
      anteriores; al iniciar una conversación nueva se persiste como semilla.
    - El LLM sigue sin acceder al CSV/DataFrame directamente.
    """
    if PUBLIC_CHAT_MODE:
        # Modo sin persistencia: el cliente proporciona solamente sus propios
        # mensajes anteriores dentro de esta sesión del navegador.
        if body.conversation_id is not None:
            raise HTTPException(status_code=400, detail="No se admiten IDs de conversación en modo público.")
        if len(body.mensaje) > 1200:
            raise HTTPException(status_code=422, detail="Máximo 1200 caracteres por pregunta.")
        resultado = chat_service.procesar_mensaje(
            mensaje=body.mensaje,
            grid_code_contexto=body.grid_code_contexto,
            historial=[turno.model_dump() for turno in body.historial],
        )
        return {**resultado, "conversation_id": None}

    if body.conversation_id is None:
        conversation_id = database_service.crear_conversacion()
        historial = [turno.model_dump() for turno in body.historial]
        # Si un cliente antiguo envía historial, lo persistimos una sola vez
        # para que los siguientes turnos ya puedan usar conversation_id.
        for turno in historial:
            database_service.agregar_mensaje(
                conversation_id=conversation_id,
                role=turno["role"],
                content=turno["content"],
            )
    else:
        conversation_id = body.conversation_id
        # SQLite es la fuente de verdad para una conversación existente.
        historial = database_service.historial_para_llm(conversation_id)

    # El mensaje actual NO se incluye todavía en `historial`, porque
    # chat_service lo agrega por separado al construir el prompt.
    database_service.agregar_mensaje(
        conversation_id=conversation_id,
        role="user",
        content=body.mensaje,
        grid_code_contexto=body.grid_code_contexto,
    )

    resultado = chat_service.procesar_mensaje(
        mensaje=body.mensaje,
        grid_code_contexto=body.grid_code_contexto,
        historial=historial,
    )

    database_service.agregar_mensaje(
        conversation_id=conversation_id,
        role="assistant",
        content=resultado["respuesta"],
        grid_code_contexto=body.grid_code_contexto,
        metadata={
            "grid_codes_relacionados": resultado.get("grid_codes_relacionados", []),
            "tools_utilizadas": resultado.get("tools_utilizadas", []),
            "advertencias": resultado.get("advertencias", []),
        },
    )

    return {**resultado, "conversation_id": conversation_id}


# ---------------------------------------------------------------------------
# Persistencia de conversaciones (SQLite)
# ---------------------------------------------------------------------------

@app.post(
    "/conversaciones",
    response_model=ConversacionCreada,
    tags=["conversaciones"],
)
def crear_conversacion():
    """Crea una conversación vacía. `/chat` también puede crearla automáticamente."""
    _require_private_history()
    return {"conversation_id": database_service.crear_conversacion()}


@app.get(
    "/conversaciones",
    response_model=list[ConversacionResumen],
    tags=["conversaciones"],
)
def listar_conversaciones(
    limite: int = Query(50, gt=0, le=200, description="Máximo de conversaciones"),
):
    """Lista conversaciones recientes, ordenadas por última actividad."""
    _require_private_history()
    return database_service.listar_conversaciones(limite=limite)


@app.get(
    "/conversaciones/{conversation_id}",
    response_model=ConversacionDetalle,
    tags=["conversaciones"],
)
def obtener_conversacion(
    conversation_id: int = Path(..., gt=0, description="ID de conversación"),
):
    """Devuelve todos los mensajes persistidos de una conversación."""
    _require_private_history()
    return database_service.obtener_conversacion(conversation_id)


@app.delete(
    "/conversaciones/{conversation_id}",
    response_model=EliminarConversacionResponse,
    tags=["conversaciones"],
)
def eliminar_conversacion(
    conversation_id: int = Path(..., gt=0, description="ID de conversación"),
):
    """Elimina una conversación y sus mensajes mediante ON DELETE CASCADE."""
    _require_private_history()
    database_service.eliminar_conversacion(conversation_id)
    return {"eliminado": True, "conversation_id": conversation_id}
