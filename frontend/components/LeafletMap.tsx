"use client";
import { FIELD_ZH, MEASURE_ZH, ORIGIN_ZH, OWNER_ZH } from "@/lib/labels";
const fieldZh = (f: string) => String(f || "").split(".").map((t) => FIELD_ZH[t] || t).join("／");
const facilityTypeZh = (t: string) => FIELD_ZH[t] || t;
import { useEffect, useRef } from "react";
import type * as LType from "leaflet";
import { Any } from "@/lib/api";

export type MapMode = "sketch" | "zoning" | "section";
const MODES: Record<MapMode, string[]> = { sketch: ["cadastre", "section_map", "sections", "parcels", "roads"], zoning: ["zoning", "section_map", "sections"], section: ["cadastre", "section_map", "sections", "parcels", "facilities", "distance_lines"] };

export default function LeafletMap({ layers, mode, onMapClick, highlight, clickMode, className = "h-[70vh]" }: {
  layers: Any; mode: MapMode; onMapClick?: (lon: number, lat: number) => void; highlight?: { field?: string; owner?: string } | null; clickMode?: boolean; className?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LType.Map | null>(null);
  const groupsRef = useRef<Record<string, LType.LayerGroup>>({});
  const landsectRef = useRef<LType.Layer | null>(null);
  const LRef = useRef<typeof LType | null>(null);
  const clickRef = useRef(onMapClick);
  clickRef.current = onMapClick;
  const layersRef = useRef<Any>(layers);
  layersRef.current = layers;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")) as typeof LType;
      if (cancelled || !el.current || mapRef.current) return;
      LRef.current = L;
      const map = L.map(el.current).setView([25.2217, 121.6367], 16);
      L.tileLayer("/api/tiles/{z}/{x}/{y}", { maxZoom: 19, attribution: "© 國土測繪中心" }).addTo(map);   // 經後端代理與快取，會場離線時仍有預抓的底圖
      landsectRef.current = L.tileLayer("/api/tiles/{z}/{x}/{y}?layer=LANDSECT", { maxZoom: 19, opacity: 0.9, attribution: "段籍圖 © 國土測繪中心" });   // 經後端代理與快取
      ["cadastre", "section_map", "sections", "parcels", "facilities", "distance_lines", "zoning", "roads"].forEach((k) => (groupsRef.current[k] = L.layerGroup()));
      map.on("click", (e: LType.LeafletMouseEvent) => clickRef.current?.(e.latlng.lng, e.latlng.lat));
      map.on("zoomend", () => { if (layersRef.current?.cadastre?.features?.length) render(); });
      mapRef.current = map;
      render();
    })();
    return () => { cancelled = true; mapRef.current?.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function render() {
    const L = LRef.current, map = mapRef.current; if (!L || !map || !layers) return;
    const g = groupsRef.current; Object.values(g).forEach((x) => x.clearLayers());
    const inter = !clickMode;   // 點圖設定位置時，圖徵不攔截點擊、不開 popup
    const label = (latlng: LType.LatLngExpression, text: string) => L.marker(latlng, { icon: L.divIcon({ className: "lbl", html: text }), interactive: false });
    L.geoJSON(layers.zoning, { interactive: inter, style: (f: Any) => ({ color: "#555", weight: 0.5, fillColor: f.properties.color, fillOpacity: 0.45 }), onEachFeature: (f, l) => l.bindTooltip(f.properties.zone) }).addTo(g.zoning);
    L.geoJSON(layers.roads, { interactive: inter, style: { color: "#666", weight: 2 }, onEachFeature: (f, l) => l.bindTooltip(f.properties.name) }).addTo(g.roads);
    if (layers.cadastre?.features?.length) {
      L.geoJSON(layers.cadastre, { interactive: inter, style: { color: "#777", weight: 0.8, fill: true, fillOpacity: 0.02 }, onEachFeature: (f: Any, l: Any) => {
        l.bindTooltip(f.properties.label);
        if (map.getZoom() >= 17) label(l.getBounds().getCenter(), `<span style="font-size:10px;color:#444">${f.properties.lot}</span>`).addTo(g.cadastre);
      } }).addTo(g.cadastre);
    }
    if (layers.section_map?.features?.length) {
      L.geoJSON(layers.section_map, { interactive: inter, style: { color: "#8a4a4a", weight: 1.5, fill: false, dashArray: "4 4" }, onEachFeature: (f: Any, l: Any) => { l.bindTooltip(f.properties.label); label(l.getBounds().getCenter(), `<span style="color:#8a4a4a">${f.properties.section_id}</span>`).addTo(g.section_map); } }).addTo(g.section_map);
    }
    L.geoJSON(layers.sections, { interactive: inter, style: { color: "#d00", weight: 3, fill: false, dashArray: "6 4" }, onEachFeature: (f, l: Any) => {
      l.bindPopup(`<b>區段 ${f.properties.section_id}</b><br>${f.properties.range_desc || ""}<br><i>${({ draft: "範圍草稿", confirmed: "已確認" } as Any)[f.properties.status] || f.properties.status || ""}・${({ estimate_osm_block: "依路網推估之街廓", cadastre_file: "地籍圖", synthetic: "依面積合成（示意）", survey_form: "勘查表／區段圖" } as Any)[f.properties.geometry_source] || f.properties.geometry_source || ""}</i>`);
      label(l.getBounds().getCenter(), f.properties.section_id).addTo(g.sections);
    } }).addTo(g.sections);
    L.geoJSON(layers.parcels, { interactive: inter, style: (f: Any) => ({ color: f.properties.role === "subject" ? "#ea580c" : "#1f77b4", weight: 2, fillOpacity: 0.5 }),
      pointToLayer: (f: Any, ll) => L.circleMarker(ll, { radius: 7, color: f.properties.role === "subject" ? "#ea580c" : "#1f77b4", fillOpacity: 0.8 }),
      onEachFeature: (f, l) => l.bindPopup(`<b>${f.properties.label}</b><br>位置來源：${({ cadastre_file: "地籍圖", nlsc_api: "國土測繪中心地籍查詢", synthetic: "依清冊面積合成（示意，非地籍圖）", address_estimate: "依門牌路段推定（示意，非地籍圖）", estimate_osm_block: "依路網推估" } as Any)[f.properties.geometry_source] || f.properties.geometry_source || "—"}<br>${f.properties.geometry_note || ""}`) }).addTo(g.parcels);
    const hl = (p: Any) => highlight && ((!highlight.field || p.field === highlight.field || String(p.field || "").endsWith("." + highlight.field)) && (!highlight.owner || p.owner === highlight.owner));
    L.geoJSON(layers.distance_lines, { interactive: inter, style: (f: Any) => ({ color: f.properties.measure === "walking" ? "#2a9d8f" : "#e76f51", weight: hl(f.properties) ? 4 : 1.5, opacity: highlight && !hl(f.properties) ? 0.25 : 1, dashArray: f.properties.measure === "straight_estimated" ? "3 3" : undefined }),
      onEachFeature: (f, l) => l.bindTooltip(f.properties.label) }).addTo(g.distance_lines);
    L.geoJSON(layers.facilities, { interactive: inter, pointToLayer: (f: Any, ll) => L.circleMarker(ll, { radius: hl(f.properties) ? 9 : 6, color: "#333", fillColor: f.properties.scope === "regional" ? "#f2c744" : "#57b96b", fillOpacity: highlight && !hl(f.properties) ? 0.3 : 0.9 }),
      style: { color: "#333", weight: 1, fillColor: "#f2c744", fillOpacity: 0.4 },
      onEachFeature: (f, l) => l.bindPopup(`<b>${f.properties.name || "(無名)"}</b> ${facilityTypeZh(f.properties.type)}<br>${fieldZh(f.properties.field)}（${OWNER_ZH(String(f.properties.owner || ""))}）<br>距離 ${f.properties.distance_m ?? "-"} m，${MEASURE_ZH[f.properties.measure] || f.properties.measure || ""}，起點 ${ORIGIN_ZH[f.properties.origin] || f.properties.origin || ""}<br>來源：${f.properties.source || ""}${f.properties.assumed ? '<br><span style="color:#c00">量測方式為推定</span>' : ""}`) }).addTo(g.facilities);
    Object.values(g).forEach((x) => map.removeLayer(x)); MODES[mode].forEach((k) => g[k].addTo(map));
    if (mode !== "zoning") landsectRef.current?.addTo(map); else if (landsectRef.current) map.removeLayer(landsectRef.current);
    if (layers.bbox && !highlight) map.fitBounds([[layers.bbox[1], layers.bbox[0]], [layers.bbox[3], layers.bbox[2]]]);
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { render(); }, [layers, mode, highlight, clickMode]);
  useEffect(() => { if (el.current) el.current.style.cursor = clickMode ? "crosshair" : ""; }, [clickMode]);
  return <div ref={el} className={`w-full rounded-lg border border-slate-300 ${className}`} />;
}
