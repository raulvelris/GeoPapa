# Backend geoespacial + Gemini

Backend FastAPI para consultar las estimaciones geográficas del rendimiento de papa y ofrecer un asistente conversacional con **Google Gemini API** mediante function calling.

## Principios mantenidos

- El LLM no accede directamente al CSV ni al DataFrame.
- Solo puede usar las 7 tools de `tools/geospatial_tools.py`.
- No se generan nuevas predicciones y no se usa el `.joblib` para inferencia.
- `rendimiento_estimado_t_ha` es el valor operativo para presentación.
- El valor bruto se conserva para trazabilidad.
- MAE/RMSE/R² oficiales siguen siendo exclusivamente OOF.
- El historial se recibe en cada request; SQLite todavía no está implementado.

## Datos esperados en `data/`

- `etapa2_predicciones_mapa.csv`
- `etapa2_modelo_final_metadata.json`
- `etapa2_modelo_final.joblib` (artefacto de trazabilidad; no se carga para predecir)

## Instalación en Windows (CMD)

```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

Edita `.env` y coloca tu API key de Google AI Studio:

```env
GEMINI_API_KEY=TU_API_KEY_REAL
GEMINI_MODEL=gemini-3.5-flash-lite
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

## Ejecutar

```bat
uvicorn main:app --reload --port 8000
```

Abrir:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## Prueba rápida del chat

Desde Swagger (`/docs`) ejecuta `POST /chat` con:

```json
{
  "mensaje": "¿Cuál es el rendimiento estimado de la zona 4843916?",
  "grid_code_contexto": null,
  "historial": []
}
```

La respuesta debe conservar esta forma:

```json
{
  "respuesta": "...",
  "grid_codes_relacionados": [4843916],
  "tools_utilizadas": ["consultar_zona"],
  "advertencias": []
}
```

## Notas

El modelo de Gemini está configurable desde `.env`. Si tu proyecto de Google AI Studio no tiene acceso al modelo por defecto, cambia `GEMINI_MODEL` por otro modelo con function calling habilitado en tu cuenta.


## Nota Gemini 3 / google-genai

Este backend requiere `google-genai>=2.25,<3.0` para devolver `FunctionResponse` con el `id` de la llamada original. En Gemini 3 se conserva además el `Content` completo del modelo para mantener `thought_signature`, y las respuestas de función se agregan con rol `user`.

## Historial persistente con SQLite (v0.6)

Esta versión guarda conversaciones y mensajes en `data/chat_history.db` usando
`sqlite3` de la librería estándar de Python; no requiere instalar una dependencia
adicional. El archivo se crea automáticamente al iniciar FastAPI y está ignorado
por Git.

Flujo recomendado del frontend:

1. Primer mensaje: `POST /chat` con `conversation_id: null`. La respuesta devuelve
   un `conversation_id` nuevo.
2. Mensajes siguientes: reutilizar ese `conversation_id`; ya no es necesario
   reenviar el historial completo.
3. `GET /conversaciones` lista chats recientes.
4. `GET /conversaciones/{id}` recupera sus mensajes.
5. `DELETE /conversaciones/{id}` elimina el chat y sus mensajes.

Prueba sin consumir Gemini:

```bat
python tests\test_sqlite_historial.py
```
