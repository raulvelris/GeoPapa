import { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Rectangle,
  Tooltip,
  useMap,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "./App.css";

import { obtenerMapa, asistenteDisponible } from "./services/api";
import ChatPanel from "./components/ChatPanel";

const CENTRO_PERU = [-9.19, -75.0152];

function colorRendimiento(valor) {
  if (valor < 5) return "#d73027";
  if (valor < 10) return "#fc8d59";
  if (valor < 20) return "#fee08b";
  if (valor < 30) return "#d9ef8b";
  if (valor < 50) return "#91cf60";
  return "#1a9850";
}

function AjustarMapa({ zona }) {
  const map = useMap();

  useEffect(() => {
    if (!zona) return;

    map.flyTo([zona.y, zona.x], 9, {
      duration: 0.8,
    });
  }, [zona, map]);

  return null;
}

function App() {
  const [zonas, setZonas] = useState([]);
  const [zonaSeleccionada, setZonaSeleccionada] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [chatAbierto, setChatAbierto] = useState(false);
  // Solo se utiliza en celulares. En escritorio se conserva el panel lateral.
  const [panelMovil, setPanelMovil] = useState("resumen");
  const [leyendaAbierta, setLeyendaAbierta] = useState(false);
  const inicioArrastre = useRef(null);
  const omitirClicTrasArrastre = useRef(false);

  function esPantallaMovil() {
    return typeof window !== "undefined" &&
      window.matchMedia("(max-width: 767px)").matches;
  }

  function seleccionarZona(zona) {
    setZonaSeleccionada(zona);
    setBusqueda(String(zona.grid_code));
    setError("");
    setPanelMovil("resumen");
    if (esPantallaMovil()) setChatAbierto(false);
  }

  function cerrarZona() {
    setZonaSeleccionada(null);
    setPanelMovil("resumen");
    setChatAbierto(false);
  }

  function activarChat() {
    if (esPantallaMovil()) {
      setChatAbierto(true);
      setPanelMovil("chat");
    } else {
      setChatAbierto((abierto) => !abierto);
    }
  }

  function alIniciarArrastre(evento) {
    if (evento.pointerType === "mouse" && evento.button !== 0) return;
    inicioArrastre.current = evento.clientY;
    evento.currentTarget.setPointerCapture?.(evento.pointerId);
  }

  function alTerminarArrastre(evento) {
    if (inicioArrastre.current === null) return;
    const desplazamiento = evento.clientY - inicioArrastre.current;
    inicioArrastre.current = null;
    if (Math.abs(desplazamiento) < 35) return;
    // Evita que el clic que sigue al gesto deshaga el cambio de posición.
    omitirClicTrasArrastre.current = true;
    if (desplazamiento < 0) {
      setPanelMovil((actual) =>
        actual === "resumen" ? "detalles" :
        actual === "detalles" && chatAbierto ? "chat" : actual
      );
    } else {
      setPanelMovil((actual) =>
        actual === "chat" ? "detalles" : "resumen"
      );
    }
  }

  function alPulsarAsa() {
    if (omitirClicTrasArrastre.current) {
      omitirClicTrasArrastre.current = false;
      return;
    }
    setPanelMovil((actual) =>
      actual === "chat" ? "detalles" :
      actual === "resumen" ? "detalles" : "resumen"
    );
  }

  useEffect(() => {
    async function cargarMapa() {
      try {
        setCargando(true);

        const datos = await obtenerMapa();

        setZonas(datos);
      } catch (err) {
        console.error(err);
        setError(
          "No se pudieron cargar las zonas del mapa. Verifica la conexión e inténtalo nuevamente."
        );
      } finally {
        setCargando(false);
      }
    }

    cargarMapa();
  }, []);

  const rendimientoMaximo = useMemo(() => {
    if (!zonas.length) return 0;

    return Math.max(
      ...zonas.map((zona) => zona.rendimiento_estimado_t_ha)
    );
  }, [zonas]);

  function buscarZona(event) {
    event.preventDefault();

    const codigo = Number(busqueda.trim());

    if (!codigo) return;

    const encontrada = zonas.find(
      (zona) => Number(zona.grid_code) === codigo
    );

    if (encontrada) {
      seleccionarZona(encontrada);
    } else {
      setError(`No se encontró la zona ${busqueda}.`);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Rendimiento del cultivo de papa en el Perú</h1>
          <p>
            Exploración geoespacial de estimaciones y variables
            agroecológicas
          </p>
        </div>

        <div className="header-stats">
          <span>
            <strong>{zonas.length}</strong>
            <small> celdas</small>
          </span>

          <span>
            <strong>{rendimientoMaximo.toFixed(1)}</strong>
            <small> t/ha máx.</small>
          </span>
        </div>
      </header>

      <main className="workspace">
        <section className="map-section">
          <div className="map-toolbar">
            <form onSubmit={buscarZona} className="search-form">
              <input
                type="text"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                placeholder="Buscar grid code..."
              />

              <button type="submit">Buscar</button>
            </form>

            <span className="map-status">
              {cargando
                ? "Cargando celdas..."
                : `${zonas.length} celdas cargadas`}
            </span>
          </div>

          {error && <div className="error-message">{error}</div>}

          <div className="map-wrapper">
            <MapContainer
              center={CENTRO_PERU}
              zoom={5}
              minZoom={4}
              maxZoom={13}
              preferCanvas={true}
              className="map"
            >
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              {zonas.map((zona) => {
                const bounds = [
                  [zona.limites.south, zona.limites.west],
                  [zona.limites.north, zona.limites.east],
                ];

                const seleccionada =
                  zonaSeleccionada?.grid_code === zona.grid_code;

                return (
                  <Rectangle
                    key={zona.grid_code}
                    bounds={bounds}
                    pathOptions={{
                      color: seleccionada ? "#111827" : "#ffffff",
                      weight: seleccionada ? 2 : 0.35,
                      fillColor: colorRendimiento(
                        zona.rendimiento_estimado_t_ha
                      ),
                      fillOpacity: seleccionada ? 0.95 : 0.72,
                    }}
                    eventHandlers={{
                      click: () => seleccionarZona(zona),
                    }}
                  >
                    <Tooltip sticky>
                      <strong>{zona.departamento}</strong>
                      <br />
                      {zona.provincia}
                      <br />
                      Grid: {zona.grid_code}
                      <br />
                      {zona.rendimiento_estimado_t_ha.toFixed(2)} t/ha
                    </Tooltip>
                  </Rectangle>
                );
              })}

              <AjustarMapa zona={zonaSeleccionada} />
            </MapContainer>

            <button
              type="button"
              className="legend-toggle"
              aria-expanded={leyendaAbierta}
              aria-controls="leyenda-rendimiento"
              onClick={() => setLeyendaAbierta((abierta) => !abierta)}
            >
              <span aria-hidden="true">▤</span> Leyenda
            </button>

            <div
              id="leyenda-rendimiento"
              className={`legend ${leyendaAbierta ? "legend-open" : ""}`}
            >
              <strong>Rendimiento estimado</strong>
              <small>t/ha</small>

              <div>
                <span style={{ background: "#d73027" }} />
                &lt; 5
              </div>

              <div>
                <span style={{ background: "#fc8d59" }} />
                5 – 10
              </div>

              <div>
                <span style={{ background: "#fee08b" }} />
                10 – 20
              </div>

              <div>
                <span style={{ background: "#d9ef8b" }} />
                20 – 30
              </div>

              <div>
                <span style={{ background: "#91cf60" }} />
                30 – 50
              </div>

              <div>
                <span style={{ background: "#1a9850" }} />
                ≥ 50
              </div>
            </div>
          </div>
        </section>

        <aside
          className={`side-panel ${zonaSeleccionada ? `mobile-sheet-${panelMovil}` : "mobile-sheet-empty"}`}
          aria-label="Información de la zona"
        >
          {zonaSeleccionada && (
            <div className="mobile-sheet-top">
              <button
                type="button"
                className="mobile-sheet-grip"
                aria-label={
                  panelMovil === "chat" ? "Volver a los detalles" :
                  panelMovil === "resumen" ? "Expandir panel de información" :
                  "Minimizar panel de información"
                }
                aria-expanded={panelMovil !== "resumen"}
                onPointerDown={alIniciarArrastre}
                onPointerUp={alTerminarArrastre}
                onPointerCancel={() => { inicioArrastre.current = null; }}
                onClick={alPulsarAsa}
              >
                <span aria-hidden="true" />
              </button>
              <div className="mobile-sheet-summary">
                <div className="mobile-summary-location">
                  <span>Zona {zonaSeleccionada.grid_code}</span>
                  <strong>{zonaSeleccionada.departamento} · {zonaSeleccionada.provincia}</strong>
                </div>
                <div className="mobile-summary-value">
                  <strong>{zonaSeleccionada.rendimiento_estimado_t_ha.toFixed(2)}</strong>
                  <small>t/ha</small>
                </div>
                <button
                  type="button"
                  className="mobile-summary-close"
                  onClick={cerrarZona}
                  aria-label="Cerrar zona seleccionada"
                >×</button>
                <button
                  type="button"
                  className="mobile-summary-expand"
                  onClick={() => setPanelMovil("detalles")}
                >Ver información <span aria-hidden="true">↑</span></button>
              </div>
            </div>
          )}
          <div className="mobile-sheet-content">
          {!zonaSeleccionada ? (
            <div className="empty-state">
              <div className="empty-icon">⌖</div>

              <h2>Selecciona una zona</h2>

              <p>
                Haz clic sobre una celda del mapa para consultar su
                información.
              </p>
            </div>
          ) : (
            <>
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">Zona seleccionada</span>
                  <h2>{zonaSeleccionada.grid_code}</h2>
                </div>

                <button
                  className="close-button"
                  onClick={cerrarZona}
                >
                  ×
                </button>
              </div>

              <div className="location-card">
                <span>Ubicación</span>

                <strong>
                  {zonaSeleccionada.departamento}
                </strong>

                <p>{zonaSeleccionada.provincia}</p>
              </div>

              <div className="yield-card">
                <span>Rendimiento estimado</span>

                <strong>
                  {zonaSeleccionada.rendimiento_estimado_t_ha.toFixed(2)}
                </strong>

                <small>t/ha</small>
              </div>

              <div className="details">
                <div className="detail-row">
                  <span>Longitud</span>
                  <strong>{zonaSeleccionada.x.toFixed(4)}</strong>
                </div>

                <div className="detail-row">
                  <span>Latitud</span>
                  <strong>{zonaSeleccionada.y.toFixed(4)}</strong>
                </div>

                <div className="detail-row">
                  <span>Ajuste por valor negativo</span>

                  <strong>
                    {zonaSeleccionada.ajustado_por_valor_negativo
                      ? "Sí"
                      : "No"}
                  </strong>
                </div>
              </div>

              <div className="method-note">
                <strong>Nota</strong>
                <p>
                  El valor mostrado corresponde a una estimación del
                  modelo y no representa un rendimiento real o
                  garantizado.
                </p>
              </div>
              {asistenteDisponible ? (
                <>
                  <button
                    className="chat-button chat-button-active"
                    onClick={activarChat}
                  >
                    <span className="chat-button-label-desktop">
                      {chatAbierto ? "Cerrar asistente" : "Consultar esta zona en el asistente"}
                    </span>
                    <span className="chat-button-label-mobile">Consultar con Gemini</span>
                  </button>

                  {chatAbierto && (
                    <>
                      <div className="mobile-chat-nav">
                        <button type="button" onClick={() => setPanelMovil("detalles")}>
                          <span aria-hidden="true">‹</span> Volver a la zona
                        </button>
                        <strong>Asistente Gemini</strong>
                      </div>
                      <ChatPanel
                        key={zonaSeleccionada.grid_code}
                        zona={zonaSeleccionada}
                      />
                    </>
                  )}
                </>
              ) : (
                <div className="method-note">
                  <strong>Asistente geoespacial</strong>
                  <p>
                    El mapa está disponible. Para habilitar el asistente
                    conversacional es necesario publicar FastAPI y configurar
                    la dirección de su API.
                  </p>
                </div>
              )}
            </>
          )}
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;