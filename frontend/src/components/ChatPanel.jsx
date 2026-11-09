import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
    enviarMensajeChat,
    listarConversaciones,
    obtenerConversacion,
    eliminarConversacion,
} from "../services/api";

// En la web pública los mensajes viven solo en esta pestaña.
// No se muestra ni consulta una base de datos compartida de conversaciones.
const MODO_CHAT_PUBLICO = import.meta.env.VITE_PUBLIC_CHAT_MODE === "true";

function ChatPanel({ zona }) {
    const [mensajes, setMensajes] = useState([]);
    const [texto, setTexto] = useState("");
    const [conversationId, setConversationId] = useState(null);
    const [enviando, setEnviando] = useState(false);
    const [error, setError] = useState("");
    const [historialAbierto, setHistorialAbierto] = useState(false);
    const [conversaciones, setConversaciones] = useState([]);
    const [idPorEliminar, setIdPorEliminar] = useState(null);
    const [eliminandoId, setEliminandoId] = useState(null);

    const finChatRef = useRef(null);

    useEffect(() => {
        if (!historialAbierto) {
            finChatRef.current?.scrollIntoView({ behavior: "smooth" });
        }
    }, [mensajes, enviando, historialAbierto]);

    async function enviar(event) {
        event.preventDefault();

        const mensaje = texto.trim();

        if (!mensaje || enviando) return;

        setMensajes((actuales) => [
        ...actuales,
        {
            role: "user",
            content: mensaje,
        },
        ]);

        setTexto("");
        setError("");
        setEnviando(true);

        try {
        const respuesta = await enviarMensajeChat({
            mensaje,
            conversation_id: MODO_CHAT_PUBLICO ? null : conversationId,
            grid_code_contexto: zona.grid_code,
            ...(MODO_CHAT_PUBLICO ? {
              historial: mensajes.map(({ role, content }) => ({ role, content })),
            } : {}),
        });

        if (!conversationId && respuesta.conversation_id) {
            setConversationId(respuesta.conversation_id);
        }

        setMensajes((actuales) => [
            ...actuales,
            {
            role: "assistant",
            content: respuesta.respuesta,
            tools: respuesta.tools_utilizadas || [],
            },
        ]);
    } catch (err) {
        console.error(err);

        setError(
            "No se pudo contactar al asistente. Verifica que el backend esté ejecutándose."
        );
    } finally {
      setEnviando(false);
    }
  }

async function cargarHistorial() {
    if (historialAbierto) {
        setHistorialAbierto(false);
        setIdPorEliminar(null);
        return;
    }
    setError("");
    setIdPorEliminar(null);
    try {
        const datos = await listarConversaciones();
        setConversaciones(datos);
        setHistorialAbierto(true);
    } catch (err) {
        console.error(err);
        setError("No se pudo cargar el historial de conversaciones.");
    }
}

function nuevaConversacion() {
    setConversationId(null);
    setMensajes([]);
    setTexto("");
    setError("");
    setHistorialAbierto(false);
    setIdPorEliminar(null);
}

async function abrirConversacion(id) {
    try {
        const conversacion = await obtenerConversacion(id);

        setConversationId(conversacion.id);

        setMensajes(
        conversacion.mensajes.map((m) => ({
            role: m.role,
            content: m.content,
            tools: m.metadata?.tools_utilizadas || [],
        }))
        );

        setHistorialAbierto(false);
        setIdPorEliminar(null);
    } catch (err) {
        console.error(err);
        setError("No se pudo abrir la conversación.");
    }
}

async function confirmarEliminacion(id) {
    if (eliminandoId !== null || enviando) return;
    setEliminandoId(id);
    setError("");

    try {
        // FastAPI ya incluye DELETE /conversaciones/{id} y SQLite elimina
        // sus mensajes mediante ON DELETE CASCADE.
        await eliminarConversacion(id);
        setConversaciones((actuales) => actuales.filter((c) => c.id !== id));
        setIdPorEliminar(null);

        // Si era la conversación abierta, evitar que el usuario continúe
        // sobre un ID que ya no existe en el servidor.
        if (conversationId === id) {
            setConversationId(null);
            setMensajes([]);
            setTexto("");
        }
    } catch (err) {
        console.error(err);
        setError("No se pudo eliminar la conversación. Vuelve a intentarlo.");
    } finally {
        setEliminandoId(null);
    }
}

  return (
    <div className="chat-panel">
        <div className="chat-panel-header">
            <div>
                <span className="eyebrow">Asistente geoespacial</span>

                <strong>
                    Consulta sobre la zona {zona.grid_code}
                </strong>

                <div className="chat-actions">
                <button type="button" onClick={nuevaConversacion}>
                    + Nueva
                </button>

                {!MODO_CHAT_PUBLICO && (
                  <button
                    type="button"
                    onClick={cargarHistorial}
                    aria-pressed={historialAbierto}
                  >
                    {historialAbierto ? "Volver al chat" : "Historial"}
                  </button>
                )}
                </div>              
            </div>
        </div>

        {historialAbierto && (
        <div className="chat-history chat-history-view">
            <div className="chat-history-title">
            Conversaciones anteriores
            </div>

            {conversaciones.length === 0 ? (
            <p>No hay conversaciones guardadas.</p>
            ) : (
            conversaciones.slice(0, 10).map((conv) => (
                <div className="chat-history-row" key={conv.id}>
                    <button
                        className="chat-history-open"
                        type="button"
                        disabled={eliminandoId !== null}
                        onClick={() => abrirConversacion(conv.id)}
                    >
                        <strong title={conv.titulo || `Conversación ${conv.id}`}>
                            {conv.titulo || `Conversación ${conv.id}`}
                        </strong>
                        <small>#{conv.id}</small>
                    </button>

                    {idPorEliminar !== conv.id && (
                        <button
                            className="chat-history-delete"
                            type="button"
                            disabled={enviando || eliminandoId !== null}
                            aria-label={`Eliminar conversación ${conv.id}`}
                            title="Eliminar conversación"
                            onClick={() => {
                                setIdPorEliminar(conv.id);
                                setError("");
                            }}
                        >
                            <span aria-hidden="true">×</span>
                        </button>
                    )}

                    {idPorEliminar === conv.id && (
                        <div className="chat-history-confirm" role="group" aria-label={`Confirmar eliminación de conversación ${conv.id}`}>
                            <p>¿Eliminar definitivamente esta conversación y todos sus mensajes? Se borrará para todos y no se puede deshacer.</p>
                            <div className="chat-history-confirm-actions">
                                <button
                                    type="button"
                                    disabled={eliminandoId !== null}
                                    onClick={() => setIdPorEliminar(null)}
                                >
                                    Cancelar
                                </button>
                                <button
                                    className="chat-history-confirm-delete"
                                    type="button"
                                    disabled={eliminandoId !== null || enviando}
                                    onClick={() => confirmarEliminacion(conv.id)}
                                >
                                    {eliminandoId === conv.id ? "Eliminando..." : "Sí, eliminar"}
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            ))
            )}
        </div>
        )}

        <div className={`chat-messages ${historialAbierto ? "chat-screen-hidden" : ""}`}>
            {mensajes.length === 0 && (
            <div className="chat-welcome">
                <strong>¿Qué deseas conocer?</strong>

                <p>
                Puedes preguntar por el rendimiento, clima, suelo,
                vegetación o características de esta zona.
                </p>

                <button
                type="button"
                onClick={() =>
                    setTexto("¿Qué características tiene esta zona?")
                }
                >
                ¿Qué características tiene esta zona?
                </button>

                <button
                type="button"
                onClick={() =>
                    setTexto(
                    "¿Cuál es el rendimiento estimado de esta zona?"
                    )
                }
                >
                ¿Cuál es su rendimiento estimado?
                </button>

                <button
                type="button"
                onClick={() =>
                    setTexto(
                    "¿Cuáles son sus variables agroecológicas?"
                    )
                }
                >
                Ver variables agroecológicas
                </button>
            </div>
            )}

            {mensajes.map((mensaje, index) => (
            <div
                key={index}
                className={`chat-message ${
                mensaje.role === "user"
                    ? "chat-message-user"
                    : "chat-message-assistant"
                }`}
            >
                <div className="chat-role">
                {mensaje.role === "user"
                    ? "Tú"
                    : "Asistente"}
                </div>

                <div className="chat-content">
                {mensaje.role === "assistant" ? (
                    <ReactMarkdown>
                    {mensaje.content}
                    </ReactMarkdown>
                ) : (
                    mensaje.content
                )}
                </div>

                {mensaje.tools?.length > 0 && (
                <div className="chat-tools">
                    Fuente: {mensaje.tools.join(", ")}
                </div>
                )}
            </div>
            ))}

            {enviando && (
            <div className="chat-message chat-message-assistant">
                <div className="chat-role">
                Asistente
                </div>

                <div className="chat-content chat-loading">
                Consultando datos...
                </div>
            </div>
            )}

            <div ref={finChatRef} />
        </div>

        {error && (
            <div className="chat-error">
                {error}
            </div>
        )}

        <form className={`chat-form ${historialAbierto ? "chat-screen-hidden" : ""}`} onSubmit={enviar}>
            <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Pregunta sobre esta zona..."
            rows="3"
            disabled={enviando}
            onKeyDown={(e) => {
                if (
                e.key === "Enter" &&
                !e.shiftKey
                ) {
                e.preventDefault();
                enviar(e);
                }
            }}
        />

        <button
          type="submit"
          disabled={!texto.trim() || enviando}
        >
          {enviando
            ? "Consultando..."
            : "Enviar"}
        </button>
      </form>
    </div>
  );
}

export default ChatPanel;