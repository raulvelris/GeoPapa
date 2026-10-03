from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TurnoHistorial(BaseModel):
    """Compatibilidad con el modo stateless anterior.

    Cuando se envía conversation_id, SQLite pasa a ser la fuente de verdad y
    este historial no se reenvía para evitar duplicados.
    """

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    mensaje: str = Field(..., min_length=1, description="Mensaje del usuario")
    conversation_id: Optional[int] = Field(
        None,
        gt=0,
        description=(
            "ID de una conversación persistida. Si se omite, el backend crea "
            "una conversación nueva automáticamente."
        ),
    )
    grid_code_contexto: Optional[int] = Field(
        None,
        description=(
            "grid_code que el usuario está viendo actualmente en el mapa, si "
            "aplica. Permite resolver expresiones como 'esta zona' o 'aquí' "
            "sin que el modelo invente una ubicación."
        ),
    )
    historial: List[TurnoHistorial] = Field(
        default_factory=list,
        description=(
            "Compatibilidad con clientes anteriores. Solo se usa al iniciar "
            "una conversación sin conversation_id; luego SQLite conserva el historial."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "mensaje": "¿Qué características tiene esta zona?",
                    "conversation_id": None,
                    "grid_code_contexto": 4843916,
                    "historial": [],
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    respuesta: str = Field(..., description="Respuesta en lenguaje natural del asistente")
    conversation_id: int = Field(
        ..., description="ID persistente de la conversación en SQLite."
    )
    grid_codes_relacionados: List[int] = Field(
        default_factory=list,
        description="grid_codes mencionados/consultados en esta respuesta, para que el mapa los resalte.",
    )
    tools_utilizadas: List[str] = Field(
        default_factory=list, description="Nombres de las herramientas invocadas para construir la respuesta."
    )
    advertencias: List[str] = Field(
        default_factory=list,
        description="Avisos (errores de herramienta, datos no disponibles, límites alcanzados, etc.).",
    )
