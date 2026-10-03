from pydantic import BaseModel


class MetricasOOF(BaseModel):
    """Métricas oficiales de validación espacial Out-Of-Fold. Provienen
    ÚNICAMENTE de etapa2_modelo_final_metadata.json; nunca se recalculan
    en este backend."""

    mae_t_ha: float
    rmse_t_ha: float
    r2: float


class InfoModelo(BaseModel):
    modelo: str
    conjunto_variables: str
    n_observaciones: int
    n_grupos_espaciales: int
    metricas_oof: MetricasOOF


class HealthResponse(BaseModel):
    status: str
    n_celdas_cargadas: int
    departamentos_disponibles: int
    info_modelo: InfoModelo
