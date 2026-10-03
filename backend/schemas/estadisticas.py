from typing import Optional

from pydantic import BaseModel


class EstadisticaValor(BaseModel):
    promedio: float
    minimo: float
    maximo: float
    desviacion_estandar: float


class EstadisticasDepartamentoResponse(BaseModel):
    """Respuesta de GET /departamentos/{departamento}/estadisticas
    (estadisticas_departamento). Estas son estadísticas DESCRIPTIVAS de los
    valores dentro del departamento, no las métricas oficiales de desempeño
    del modelo (esas son exclusivamente las OOF, ver /health)."""

    departamento: str
    n_celdas: int
    rendimiento_estimado_t_ha: EstadisticaValor
    rendimiento_referencia_mapspam_t_ha: EstadisticaValor
    n_celdas_ajustadas_por_valor_negativo: int
    advertencia: Optional[str] = None
