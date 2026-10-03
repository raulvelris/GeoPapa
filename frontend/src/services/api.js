const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

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

export function obtenerMapa() {
  return request("/mapa");
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