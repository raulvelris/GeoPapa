"""
Capa conversacional sobre Google Gemini API con function calling manual.

Reglas:
- El LLM NO accede directamente al CSV/DataFrame.
- Solo puede usar las 7 funciones registradas en TOOL_DISPATCH.
- NO carga ni usa etapa2_modelo_final.joblib para generar nuevas predicciones.
- El historial llega en cada request; no se guarda estado en el servidor.
- Los resultados numéricos/geográficos proceden de las tools.
"""

from __future__ import annotations

import logging
import random
import time
from functools import lru_cache
from typing import Any, Optional

from google import genai
from google.genai import errors, types

import config
from tools import geospatial_tools as gt
from tools.geospatial_tools import DepartamentoNoEncontradoError, ZonaNoEncontradaError

logger = logging.getLogger("chat_service")


class ChatServiceError(Exception):
    """Error de configuración o comunicación con Gemini ya traducido a un
    mensaje seguro para la capa HTTP."""


SYSTEM_PROMPT = """Eres un asistente conversacional especializado en información agroecológica y estimaciones geográficas de rendimiento del cultivo de papa en Perú, para una plataforma de investigación.

REGLAS ESTRICTAS:
1. Respondes siempre en español.
2. Para CUALQUIER cifra numérica, ubicación, coordenada o variable agroecológica específica del proyecto, DEBES usar una de las herramientas disponibles. Nunca inventes un número.
3. Si una herramienta no encuentra la zona, el departamento o la variable solicitada, dilo explícitamente y sugiere una alternativa.
4. Diferencia siempre, cuando corresponda:
   - rendimiento_estimado_t_ha: valor operativo mostrado al usuario; no es exacto ni garantizado.
   - prediccion_modelo_final_t_ha_bruta: valor bruto, solo para trazabilidad cuando sea relevante.
   - rendimiento_referencia_mapspam_t_ha: dato de referencia MAPSPAM, no una predicción del modelo.
5. No recalcules MAE, RMSE ni R² a partir de las estimaciones operativas. Si te piden métricas oficiales y ninguna herramienta disponible las entrega, indícalo y remite al endpoint /health en lugar de inventar cifras.
6. No afirmes causalidad a partir de asociaciones o importancias de variables.
7. Puedes explicar conceptos agroecológicos generales usando conocimiento general, pero distingue claramente una explicación conceptual de un dato específico del dataset.
8. El dataset no tiene nivel distrital, precios de mercado, proyecciones futuras ni permite nuevas predicciones para escenarios hipotéticos. Si preguntan por eso, dilo con claridad.
9. Si el usuario usa expresiones como “esta zona”, “aquí”, “su precipitación” o “compárala”, usa el grid_code de contexto indicado en el mensaje. Si no hay contexto suficiente, pregunta en vez de asumir.
10. Sé conciso y claro.
"""


# Gemini usa "parameters" para el JSON schema de cada función.
FUNCTION_DECLARATIONS: list[dict] = [
    {
        "name": "consultar_zona",
        "description": "Devuelve ubicación, coordenadas, rendimiento estimado y variables agroecológicas de una celda por grid_code.",
        "parameters": {
            "type": "object",
            "properties": {"grid_code": {"type": "integer", "description": "Identificador de la celda"}},
            "required": ["grid_code"],
        },
    },
    {
        "name": "buscar_zonas",
        "description": "Busca celdas por departamento, provincia o grid_code exacto. No existe nivel distrital.",
        "parameters": {
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "Departamento, provincia o grid_code"},
                "limite": {"type": "integer", "description": "Máximo de resultados, por defecto 20"},
            },
            "required": ["texto"],
        },
    },
    {
        "name": "resumir_zona",
        "description": "Resumen estructurado completo de una celda: ubicación, rendimiento y variables agroecológicas.",
        "parameters": {
            "type": "object",
            "properties": {"grid_code": {"type": "integer", "description": "Identificador de la celda"}},
            "required": ["grid_code"],
        },
    },
    {
        "name": "comparar_zonas",
        "description": "Compara dos o más celdas por rendimiento estimado y variables agroecológicas.",
        "parameters": {
            "type": "object",
            "properties": {
                "grid_codes": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "description": "Lista de al menos 2 grid_codes",
                }
            },
            "required": ["grid_codes"],
        },
    },
    {
        "name": "ranking_rendimiento",
        "description": "Devuelve celdas con mayor o menor rendimiento estimado, opcionalmente filtradas por departamento.",
        "parameters": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Cantidad de resultados, por defecto 10, máximo 100"},
                "orden": {"type": "string", "enum": ["mayor", "menor"]},
                "departamento": {"type": "string", "description": "Departamento opcional"},
            },
        },
    },
    {
        "name": "obtener_variables_agroecologicas",
        "description": "Devuelve únicamente las variables agroecológicas de una celda, sin rendimiento.",
        "parameters": {
            "type": "object",
            "properties": {"grid_code": {"type": "integer", "description": "Identificador de la celda"}},
            "required": ["grid_code"],
        },
    },
    {
        "name": "estadisticas_departamento",
        "description": "Estadísticas descriptivas del rendimiento estimado y de referencia dentro de un departamento.",
        "parameters": {
            "type": "object",
            "properties": {"departamento": {"type": "string", "description": "Nombre del departamento"}},
            "required": ["departamento"],
        },
    },
]

TOOLS_GEMINI = [types.Tool(function_declarations=FUNCTION_DECLARATIONS)]


def _validar_grid_code(args: dict) -> int:
    if "grid_code" not in args or args["grid_code"] is None:
        raise ValueError("Falta el argumento obligatorio 'grid_code'.")
    try:
        return int(args["grid_code"])
    except (TypeError, ValueError):
        raise ValueError(f"'grid_code' debe ser un entero. Se recibió: {args.get('grid_code')!r}")


def _tool_consultar_zona(args: dict) -> dict:
    return gt.consultar_zona(_validar_grid_code(args))


def _tool_buscar_zonas(args: dict) -> dict:
    texto = args.get("texto")
    if not texto or not isinstance(texto, str) or not texto.strip():
        raise ValueError("'texto' es obligatorio y debe ser una cadena no vacía.")
    limite = args.get("limite", config.LIMITE_BUSQUEDA_DEFAULT)
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        raise ValueError("'limite' debe ser un entero.")
    if limite <= 0:
        raise ValueError("'limite' debe ser mayor que 0.")
    return gt.buscar_zonas(texto=texto, limite=limite)


def _tool_resumir_zona(args: dict) -> dict:
    return gt.resumir_zona(_validar_grid_code(args))


def _tool_comparar_zonas(args: dict) -> dict:
    grid_codes = args.get("grid_codes")
    if not isinstance(grid_codes, list) or len(grid_codes) < 2:
        raise ValueError("'grid_codes' debe ser una lista con al menos 2 elementos.")
    try:
        grid_codes = [int(gc) for gc in grid_codes]
    except (TypeError, ValueError):
        raise ValueError("Todos los elementos de 'grid_codes' deben ser enteros.")
    return gt.comparar_zonas(grid_codes)


def _tool_ranking_rendimiento(args: dict) -> dict:
    n = args.get("n", config.LIMITE_RANKING_DEFAULT)
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise ValueError(f"'n' debe ser un entero. Se recibió: {n!r}")
    if n <= 0:
        raise ValueError("'n' debe ser mayor que 0.")
    orden = args.get("orden", "mayor")
    if orden not in ("mayor", "menor"):
        raise ValueError("'orden' debe ser 'mayor' o 'menor'.")
    return gt.ranking_rendimiento(n=n, orden=orden, departamento=args.get("departamento"))


def _tool_obtener_variables_agroecologicas(args: dict) -> dict:
    return gt.obtener_variables_agroecologicas(_validar_grid_code(args))


def _tool_estadisticas_departamento(args: dict) -> dict:
    departamento = args.get("departamento")
    if not departamento or not isinstance(departamento, str) or not departamento.strip():
        raise ValueError("'departamento' es obligatorio y debe ser una cadena no vacía.")
    return gt.estadisticas_departamento(departamento)


TOOL_DISPATCH = {
    "consultar_zona": _tool_consultar_zona,
    "buscar_zonas": _tool_buscar_zonas,
    "resumir_zona": _tool_resumir_zona,
    "comparar_zonas": _tool_comparar_zonas,
    "ranking_rendimiento": _tool_ranking_rendimiento,
    "obtener_variables_agroecologicas": _tool_obtener_variables_agroecologicas,
    "estadisticas_departamento": _tool_estadisticas_departamento,
}


def _extraer_grid_codes(nombre_tool: str, resultado: dict) -> set[int]:
    encontrados: set[int] = set()
    try:
        if nombre_tool in ("consultar_zona", "resumir_zona"):
            encontrados.add(int(resultado["ubicacion"]["grid_code"]))
        elif nombre_tool == "obtener_variables_agroecologicas":
            encontrados.add(int(resultado["grid_code"]))
        elif nombre_tool in ("buscar_zonas", "ranking_rendimiento"):
            for r in resultado.get("resultados", []):
                encontrados.add(int(r["grid_code"]))
        elif nombre_tool == "comparar_zonas":
            for z in resultado.get("zonas", []):
                encontrados.add(int(z["ubicacion"]["grid_code"]))
    except (KeyError, TypeError, ValueError):
        pass
    return encontrados


def _ejecutar_tool(nombre: str, args: dict) -> tuple[dict, bool, set[int]]:
    funcion = TOOL_DISPATCH.get(nombre)
    if funcion is None:
        logger.warning("Gemini solicitó una herramienta no registrada: %s", nombre)
        return {"detail": f"Herramienta '{nombre}' no está disponible en este sistema."}, True, set()
    try:
        resultado = funcion(args)
        return resultado, False, _extraer_grid_codes(nombre, resultado)
    except (ValueError, ZonaNoEncontradaError, DepartamentoNoEncontradoError) as e:
        return {"detail": str(e)}, True, set()
    except Exception:
        logger.exception("Error inesperado ejecutando la tool '%s' con args=%s", nombre, args)
        return {"detail": "Ocurrió un error interno al ejecutar la herramienta."}, True, set()


@lru_cache(maxsize=1)
def _get_client() -> "genai.Client":
    if not config.GEMINI_API_KEY:
        raise ChatServiceError(
            "El asistente conversacional no está configurado: falta la variable de entorno GEMINI_API_KEY."
        )
    return genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=int(config.GEMINI_TIMEOUT_SEGUNDOS * 1000)),
    )


def _recortar_historial(historial: Optional[list[dict]]) -> list[dict]:
    historial = historial or []
    saneado = []
    for turno in historial:
        role = turno.get("role")
        content = turno.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            saneado.append({"role": role, "content": content.strip()})
    if len(saneado) > config.MAX_MENSAJES_HISTORIAL:
        saneado = saneado[-config.MAX_MENSAJES_HISTORIAL:]
    return saneado


def _construir_mensaje_usuario(mensaje: str, grid_code_contexto: Optional[int]) -> str:
    if grid_code_contexto is None:
        return mensaje
    return (
        f"[Contexto del mapa: el usuario está viendo actualmente la zona grid_code={int(grid_code_contexto)}. "
        "Si el mensaje usa expresiones como 'esta zona', 'aquí', 'su' u otras referencias a la zona actual, "
        f"usa ese grid_code al invocar las herramientas.]\n\n{mensaje}"
    )


def _historial_a_contents(historial: list[dict], mensaje_actual: str) -> list[types.Content]:
    contents: list[types.Content] = []
    for turno in historial:
        role = "user" if turno["role"] == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=turno["content"])])
        )
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=mensaje_actual)]))
    return contents


def _extraer_texto_respuesta(respuesta) -> str:
    partes_texto: list[str] = []
    try:
        content = respuesta.candidates[0].content
        for part in content.parts or []:
            text = getattr(part, "text", None)
            if text:
                partes_texto.append(text)
    except (AttributeError, IndexError, TypeError):
        pass
    return "\n".join(partes_texto).strip()


def _extraer_function_calls(respuesta) -> list:
    calls = []
    try:
        for part in respuesta.candidates[0].content.parts or []:
            if getattr(part, "function_call", None) is not None:
                calls.append(part.function_call)
    except (AttributeError, IndexError, TypeError):
        pass
    return calls


def _finish_reason(respuesta) -> str:
    try:
        return str(respuesta.candidates[0].finish_reason)
    except (AttributeError, IndexError, TypeError):
        return "desconocido"


def _respuesta_error_api(mensaje: str, advertencia: str, grid_codes, tools, advertencias) -> dict:
    return {
        "respuesta": mensaje,
        "grid_codes_relacionados": sorted(grid_codes),
        "tools_utilizadas": tools,
        "advertencias": advertencias + [advertencia],
    }


def _generar_con_reintentos(client, contents, generation_config):
    """Llama a Gemini con reintentos a nivel de aplicación para errores transitorios.

    El SDK ya puede reintentar internamente, pero este segundo nivel evita que un
    pico corto de demanda (503) llegue inmediatamente al usuario final.
    """
    max_intentos = 3
    codigos_reintentables = {408, 429, 500, 502, 503, 504}

    for intento in range(max_intentos):
        try:
            return client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=generation_config,
            )
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if code not in codigos_reintentables or intento == max_intentos - 1:
                raise

            # 1.0s, 2.0s aprox., con un poco de jitter para evitar reintentos simultáneos.
            espera = (2 ** intento) + random.uniform(0.15, 0.65)
            logger.warning(
                "Gemini API devolvió %s. Reintento %s/%s en %.2fs...",
                code,
                intento + 1,
                max_intentos - 1,
                espera,
            )
            time.sleep(espera)


def procesar_mensaje(
    mensaje: str,
    grid_code_contexto: Optional[int] = None,
    historial: Optional[list[dict]] = None,
) -> dict:
    historial_saneado = _recortar_historial(historial)
    mensaje_usuario = _construir_mensaje_usuario(mensaje, grid_code_contexto)
    contents = _historial_a_contents(historial_saneado, mensaje_usuario)

    tools_utilizadas: list[str] = []
    grid_codes_relacionados: set[int] = set()
    if grid_code_contexto is not None:
        try:
            grid_codes_relacionados.add(int(grid_code_contexto))
        except (TypeError, ValueError):
            pass
    advertencias: list[str] = []

    client = _get_client()
    generation_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=TOOLS_GEMINI,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=config.GEMINI_MAX_OUTPUT_TOKENS,
    )

    for _ in range(config.MAX_TOOL_ITERATIONS):
        try:
            respuesta = _generar_con_reintentos(
                client=client,
                contents=contents,
                generation_config=generation_config,
            )
        except errors.APIError as e:
            code = getattr(e, "code", None)
            logger.error("Error de Gemini API (%s): %s", code, e)
            return _respuesta_error_api(
                "Hubo un problema al contactar al asistente conversacional. Por favor intenta nuevamente más tarde.",
                f"Error de Gemini API ({code if code is not None else 'sin código'}).",
                grid_codes_relacionados,
                tools_utilizadas,
                advertencias,
            )
        except TimeoutError:
            logger.error("Timeout al llamar a Gemini API.")
            return _respuesta_error_api(
                "El asistente tardó demasiado en responder. Por favor intenta nuevamente en unos segundos.",
                "Timeout de Gemini API.",
                grid_codes_relacionados,
                tools_utilizadas,
                advertencias,
            )
        except Exception as e:
            logger.exception("Error inesperado de comunicación con Gemini: %s", e)
            return _respuesta_error_api(
                "Hubo un problema al contactar al asistente conversacional.",
                "Error de comunicación con Gemini API.",
                grid_codes_relacionados,
                tools_utilizadas,
                advertencias,
            )

        # Es esencial conservar el Content devuelto por el modelo antes de
        # responder a sus function calls; esto mantiene firmas/thought metadata.
        try:
            model_content = respuesta.candidates[0].content
        except (AttributeError, IndexError, TypeError):
            model_content = None

        function_calls = _extraer_function_calls(respuesta)
        if not function_calls:
            texto_final = _extraer_texto_respuesta(respuesta)
            if not texto_final:
                advertencias.append(
                    f"Gemini no devolvió texto final (finish_reason={_finish_reason(respuesta)})."
                )
                texto_final = "No pude generar una respuesta para esta consulta. ¿Puedes reformularla?"
            return {
                "respuesta": texto_final,
                "grid_codes_relacionados": sorted(grid_codes_relacionados),
                "tools_utilizadas": tools_utilizadas,
                "advertencias": advertencias,
            }

        if model_content is not None:
            contents.append(model_content)

        response_parts: list[types.Part] = []
        for fc in function_calls:
            nombre = getattr(fc, "name", "") or ""
            args = dict(getattr(fc, "args", {}) or {})
            tools_utilizadas.append(nombre)

            resultado, es_error, encontrados = _ejecutar_tool(nombre, args)
            grid_codes_relacionados.update(encontrados)
            if es_error:
                advertencias.append(f"{nombre}: {resultado.get('detail', 'error desconocido')}")

            payload = {"ok": not es_error, "resultado": resultado}

            # Gemini 3 exige que cada FunctionResponse conserve el id exacto
            # de la FunctionCall correspondiente. El modelo_content completo ya
            # fue agregado arriba, por lo que también se preserva thought_signature.
            call_id = getattr(fc, "id", None)
            # Compatibilidad con google-genai: el helper
            # Part.from_function_response() no acepta `id` en algunas
            # versiones, aunque FunctionResponse sí expone ese campo.
            # Construimos el Part explícitamente para conservar el id.
            function_response = types.FunctionResponse(
                name=nombre,
                response=payload,
                id=call_id,
            )
            response_parts.append(
                types.Part(function_response=function_response)
            )

        # Para generateContent con Gemini 3, la respuesta de función se devuelve
        # como contenido del usuario, manteniendo el mismo orden de las llamadas.
        contents.append(types.Content(role="user", parts=response_parts))

    advertencias.append(
        f"Se alcanzó el máximo de {config.MAX_TOOL_ITERATIONS} iteraciones de herramientas sin respuesta final."
    )
    return {
        "respuesta": (
            "No pude completar tu consulta en el número de pasos permitido. "
            "¿Puedes reformularla de forma más específica?"
        ),
        "grid_codes_relacionados": sorted(grid_codes_relacionados),
        "tools_utilizadas": tools_utilizadas,
        "advertencias": advertencias,
    }
