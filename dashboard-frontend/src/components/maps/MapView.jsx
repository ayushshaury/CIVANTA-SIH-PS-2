import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import Card from "../ui/Card";
import { Layers, AlertTriangle, Activity, Route, Filter } from "lucide-react";
import { roadRisk, incidentsSimulated, roadWithTerrain, gpsSimulated } from "../../data/mockData";

// --- Layer config -----------------------------------------------------------

const severityColors = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#eab308",
};

// disruption_risk_score ranges 0–4 in the dataset; map it to a green→red scale
const riskColorScale = ["#10b981", "#84cc16", "#f59e0b", "#f97316", "#ef4444"];

function riskColor(score) {
  const idx = Math.max(
    0,
    Math.min(riskColorScale.length - 1, Math.round(score ?? 0))
  );
  return riskColorScale[idx];
}

const layerToggles = [
  { key: "risk", label: "Road Risk", icon: AlertTriangle },
  { key: "incidents", label: "Incidents", icon: Activity },
  { key: "gps", label: "GPS Traces", icon: Route },
];

const incidentFilters = [
  { key: "all", label: "All", color: "#64748b" },
  { key: "Pending", label: "Pending", color: "#f59e0b" },
  { key: "In Progress", label: "In Progress", color: "#3b82f6" },
  { key: "Resolved", label: "Resolved", color: "#10b981" },
  { key: "high-priority", label: "High Priority", color: "#ef4444" },
];

// Corridor from the dataset metadata (Assam–Arunachal Pradesh, Guwahati→Itanagar)
const CORRIDOR_CENTER = [26.4, 92.5];
const CORRIDOR_ZOOM = 7;

// ---------------------------------------------------------------------------

export default function MapView({
  riskData = roadRisk,
  incidentsData = incidentsSimulated,
  terrainData = roadWithTerrain,
  gpsData = gpsSimulated,
  height = "500px",
  interactive = true,
}) {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const riskLayerRef = useRef(null);
  const incidentLayerRef = useRef(null);
  const gpsLayerRef = useRef(null);
  const hasFitBoundsRef = useRef(false);

  const [activeLayers, setActiveLayers] = useState({
    risk: true,
    incidents: false,
    gps: false,
  });
  const [activeIncidentFilter, setActiveIncidentFilter] = useState("all");

  // road_id -> { lat, lng, name, type } lookup, built once from terrain data
  const roadLookup = useMemo(() => {
    const lookup = {};
    terrainData.forEach((r) => {
      lookup[r.road_id] = {
        lat: r.latitude,
        lng: r.longitude,
        name: r.road_name || r.road_ref || r.road_id,
        type: r.road_type,
      };
    });
    return lookup;
  }, [terrainData]);

  // Incidents don't carry coordinates directly — join them via road_id
  const incidentsWithCoords = useMemo(() => {
    return incidentsData
      .map((inc) => {
        const road = roadLookup[inc.road_id];
        if (!road) return null;
        return { ...inc, lat: road.lat, lng: road.lng, roadName: road.name };
      })
      .filter(Boolean);
  }, [incidentsData, roadLookup]);

  // Incidents narrowed by the status/priority filter bar
  const filteredIncidents = useMemo(() => {
    return incidentsWithCoords.filter((inc) => {
      if (activeIncidentFilter === "all") return true;
      if (activeIncidentFilter === "high-priority") {
        return inc.priority === "High";
      }
      return inc.status === activeIncidentFilter;
    });
  }, [incidentsWithCoords, activeIncidentFilter]);

  // GPS points -> one polyline per road/vehicle, ordered by point_seq.
  // Rendered as routes rather than 22k individual markers for performance.
  const gpsRoutes = useMemo(() => {
    const grouped = {};
    gpsData.forEach((p) => {
      if (!grouped[p.road_id]) grouped[p.road_id] = [];
      grouped[p.road_id].push(p);
    });

    return Object.entries(grouped).map(([road_id, points]) => {
      const sorted = [...points].sort((a, b) => a.point_seq - b.point_seq);
      const avgSpeed =
        sorted.reduce((sum, p) => sum + (p.speed_kmph || 0), 0) /
        sorted.length;

      return {
        road_id,
        avgSpeed,
        pointCount: sorted.length,
        latlngs: sorted.map((p) => [p.latitude, p.longitude]),
      };
    });
  }, [gpsData]);

  // Create map
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = L.map(mapRef.current, {
      center: CORRIDOR_CENTER,
      zoom: CORRIDOR_ZOOM,
      zoomControl: true,
      scrollWheelZoom: interactive,
      preferCanvas: true,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    mapInstanceRef.current = map;

    setTimeout(() => {
      map.invalidateSize();
    }, 100);

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [interactive]);

  // Road risk layer
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (riskLayerRef.current) {
      riskLayerRef.current.remove();
      riskLayerRef.current = null;
    }

    if (!activeLayers.risk) return;

    const layer = L.layerGroup();
    const points = [];

    riskData.forEach((r) => {
      const lat = r.records__latitude;
      const lng = r.records__longitude;
      if (lat == null || lng == null) return;
      points.push([lat, lng]);

      const marker = L.circleMarker([lat, lng], {
        radius: 5,
        fillColor: riskColor(r.disruption_risk_score),
        color: "#ffffff",
        weight: 1,
        opacity: 0.9,
        fillOpacity: 0.75,
      });

      marker.bindPopup(`
        <div style="font-family: Arial; min-width: 210px;">
          <div style="font-weight: 600; margin-bottom: 4px;">
            ${r.records__road_name || r.records__road_id}
          </div>
          <div style="font-size: 12px; color: #475569;">
            Type: ${r.records__road_type || "—"}
          </div>
          <div style="font-size: 12px; color: #475569;">
            Risk score: <b>${r.disruption_risk_score}</b> / 4
          </div>
          <div style="font-size: 12px; color: #475569;">
            Slope: ${r.records__slope_deg?.toFixed(2)}°
          </div>
          <div style="font-size: 12px; color: #475569;">
            Rainfall (7d): ${r.records__rainfall_7d_mm} mm
          </div>
          <div style="font-size: 12px; color: #475569;">
            Landslide history: ${r.records__historical_landslide_count}
            (nearest ${r.records__nearest_landslide_distance_km} km)
          </div>
        </div>
      `);

      layer.addLayer(marker);
    });

    layer.addTo(map);
    riskLayerRef.current = layer;

    if (!hasFitBoundsRef.current && points.length > 0) {
      map.fitBounds(L.latLngBounds(points).pad(0.1));
      hasFitBoundsRef.current = true;
    }
  }, [activeLayers.risk, riskData]);

  // Incidents layer
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (incidentLayerRef.current) {
      incidentLayerRef.current.remove();
      incidentLayerRef.current = null;
    }

    if (!activeLayers.incidents) return;

    const layer = L.layerGroup();

    filteredIncidents.forEach((inc) => {
      const color = severityColors[inc.severity] || "#64748b";

      const marker = L.circleMarker([inc.lat, inc.lng], {
        radius: 8,
        fillColor: color,
        color: "#ffffff",
        weight: 2,
        opacity: 1,
        fillOpacity: 0.9,
      });

      marker.bindPopup(`
        <div style="font-family: Arial; min-width: 210px;">
          <div style="font-size: 11px; color: #64748b;">
            ${inc.incident_id}
          </div>
          <div style="font-weight: 600; margin: 4px 0; text-transform: capitalize;">
            ${inc.incident_type.replace(/_/g, " ")}
          </div>
          <div style="font-size: 12px; color: #475569;">
            📍 ${inc.roadName}
          </div>
          <div style="font-size: 12px; color: #475569; margin-top: 4px;">
            ${inc.description}
          </div>
          <div style="margin-top: 6px;">
            <b style="text-transform: capitalize;">${inc.severity}</b>
            severity · <b>${inc.priority}</b> priority
          </div>
          <div style="margin-top: 2px; font-size: 12px; color: #475569;">
            Status: <b>${inc.status}</b>
          </div>
          <div style="margin-top: 4px; font-size: 11px; color: #94a3b8;">
            ${inc.timestamp}
          </div>
        </div>
      `);

      layer.addLayer(marker);
    });

    layer.addTo(map);
    incidentLayerRef.current = layer;
  }, [activeLayers.incidents, filteredIncidents]);

  // GPS traces layer (rendered as per-road polylines, not per-point markers)
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (gpsLayerRef.current) {
      gpsLayerRef.current.remove();
      gpsLayerRef.current = null;
    }

    if (!activeLayers.gps) return;

    const layer = L.layerGroup();

    gpsRoutes.forEach((route) => {
      const polyline = L.polyline(route.latlngs, {
        color: "#4f46e5",
        weight: 2,
        opacity: 0.55,
      });

      polyline.bindPopup(`
        <div style="font-family: Arial; min-width: 190px;">
          <div style="font-weight: 600;">${route.road_id}</div>
          <div style="font-size: 12px; color: #475569;">
            Avg speed: ${route.avgSpeed.toFixed(1)} km/h
          </div>
          <div style="font-size: 12px; color: #475569;">
            ${route.pointCount} GPS points
          </div>
        </div>
      `);

      layer.addLayer(polyline);
    });

    layer.addTo(map);
    gpsLayerRef.current = layer;
  }, [activeLayers.gps, gpsRoutes]);

  const toggleLayer = (key) => {
    setActiveLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const anyLayerActive =
    activeLayers.risk || activeLayers.incidents || activeLayers.gps;

  return (
    <div className="space-y-4">
      {/* Data layer toggles */}
      <Card className="p-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 px-2">
          <Layers className="h-4 w-4" />
          Data Layers:
        </div>

        {layerToggles.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => toggleLayer(key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold ${
              activeLayers[key]
                ? "bg-brand-600 text-white"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}

        {activeLayers.gps && (
          <span className="ml-auto text-[11px] text-amber-600">
            {gpsRoutes.length} routes — large dataset, may be slow on
            low-end devices
          </span>
        )}
      </Card>

      {/* MAP */}
      <div
        className="relative rounded-2xl overflow-hidden border border-slate-200 shadow-soft"
        style={{ height }}
      >
        <div
          ref={mapRef}
          style={{
            height: "100%",
            width: "100%",
            minHeight: "600px",
          }}
        />

        {/* Legend — one Status-Legend-style card per active layer */}
        {anyLayerActive && (
          <div className="absolute bottom-4 left-4 z-[400] space-y-3">
            {activeLayers.risk && (
              <div className="bg-white/95 backdrop-blur rounded-xl shadow-card p-3 max-w-[220px]">
                <div className="text-sm font-bold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Layers className="h-3.5 w-3.5" />
                  Risk Legend
                </div>
                <div className="flex items-center gap-1">
                  {riskColorScale.map((c, i) => (
                    <span
                      key={i}
                      className="h-2.5 w-4 rounded-sm"
                      style={{ background: c }}
                      title={`Score ${i}`}
                    />
                  ))}
                </div>
                <div className="flex justify-between text-[10px] text-slate-500 mt-0.5">
                  <span>Low</span>
                  <span>High</span>
                </div>
              </div>
            )}

            {activeLayers.incidents && (
              <div className="bg-white/95 backdrop-blur rounded-xl shadow-card p-3 max-w-[220px]">
                <div className="text-sm font-bold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Layers className="h-3.5 w-3.5" />
                  Incident Legend
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {Object.entries(severityColors).map(([sev, color]) => (
                    <div key={sev} className="flex items-center gap-2 text-xs text-slate-600">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ background: color }}
                      />
                      <span className="capitalize">{sev}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeLayers.incidents && (
              <div className="bg-white/95 backdrop-blur rounded-xl shadow-card p-3 max-w-[220px]">
                <div className="text-sm font-bold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Filter className="h-3.5 w-3.5" />
                  Incident Filter
                </div>
                <div className="flex flex-col gap-1">
                  {incidentFilters.map((filter) => (
                    <button
                      key={filter.key}
                      onClick={() => setActiveIncidentFilter(filter.key)}
                      className={`flex items-center gap-2 text-xs px-1.5 py-1 rounded-md text-left transition ${
                        activeIncidentFilter === filter.key
                          ? "bg-slate-100 font-semibold text-slate-900"
                          : "text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      <span
                        className="h-2.5 w-2.5 rounded-full shrink-0"
                        style={{ background: filter.color }}
                      />
                      {filter.label}
                    </button>
                  ))}
                </div>
                <div className="mt-1 pt-1.5 border-t border-slate-100 text-[10px] text-slate-500">
                  <span className="font-semibold text-slate-700">
                    {filteredIncidents.length}
                  </span>{" "}
                  matching
                </div>
              </div>
            )}

            {activeLayers.gps && (
              <div className="bg-white/95 backdrop-blur rounded-xl shadow-card p-3 max-w-[220px]">
                <div className="text-sm font-bold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Layers className="h-3.5 w-3.5" />
                  GPS Legend
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-600">
                  <span
                    className="h-0.5 w-4 rounded"
                    style={{ background: "#4f46e5" }}
                  />
                  Vehicle route
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}