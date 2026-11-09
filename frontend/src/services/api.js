// En desarrollo se usa el backend local. En GitHub Pages, si no existe
// VITE_API_URL, el mapa se sirve desde el JSON estatico incluido en public/.
const URL_BACKEND_PUBLICO = import.meta.env.VITE_API_URL?.trim();
const API_BASE_URL = (URL_BACKEND_PUBLICO || "http://127.0.0.1:8000").replace(/\/$/, "");

// El chat necesita un FastAPI operativo; Pages por si solo no lo ejecuta.
export const asistenteDisponible = import.meta.env.DEV || Boolean(URL_BACKEND_PUBLICO);

async function request(endpoint, options = {}) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Error HTTP ${response.status}`);
  }

  return response.json();
}

export async function obtenerMapa() {
  // En desarrollo, conservar el comportamiento original con FastAPI.
  if (import.meta.env.DEV) return request("/mapa");

  // Si hay un backend desplegado, intentar obtener las celdas desde alli.
  // Si no responde, el mapa publico sigue funcionando con datos estaticos.
  if (URL_BACKEND_PUBLICO) {
    try {
      return await request("/mapa");
    } catch (err) {
      console.warn("API no disponible: se usara el mapa estatico.", err);
    }
  }

  const response = await fetch(`${import.meta.env.BASE_URL}mapa.json`);
  if (!response.ok) {
    throw new Error(`No se pudo cargar mapa.json (HTTP ${response.status})`);
  }
  return response.json();
}

export function obtenerZona(gridCode) {
  return request(`/zonas/${gridCode}`);
}

export function enviarMensajeChat(payload) {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function obtenerConversacion(conversationId) {
  return request(`/conversaciones/${conversationId}`);
}

export function crearConversacion() {
  return request("/conversaciones", {
    method: "POST",
  });
}

export function listarConversaciones() {
  return request("/conversaciones");
}

export function eliminarConversacion(conversationId) {
  return request(`/conversaciones/${conversationId}`, {
    method: "DELETE",
  });
}