from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ConversacionCreada(BaseModel):
    conversation_id: int


class ConversacionResumen(BaseModel):
    id: int
    titulo: str
    total_mensajes: int
    created_at: str
    updated_at: str


class MensajePersistido(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    grid_code_contexto: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: str


class ConversacionDetalle(BaseModel):
    id: int
    titulo: str
    created_at: str
    updated_at: str
    mensajes: List[MensajePersistido] = Field(default_factory=list)


class EliminarConversacionResponse(BaseModel):
    eliminado: bool
    conversation_id: int
