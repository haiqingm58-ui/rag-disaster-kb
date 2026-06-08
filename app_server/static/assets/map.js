const LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function eventPoints(events) {
  return (Array.isArray(events) ? events : []).filter((event) => {
    const lat = event.latitude;
    const lng = event.longitude;
    // Explicit null/undefined check — Number(null) is 0 which would pass isFinite.
    if (lat == null || lng == null) return false;
    return Number.isFinite(Number(lat)) && Number.isFinite(Number(lng));
  });
}

function levelColor(event) {
  const text = `${event.risk || ""} ${event.warning_level || ""}`.toLowerCase();
  if (text.includes("red") || text.includes("红")) return "#d62728";
  if (text.includes("orange") || text.includes("橙") || text.includes("critical") || text.includes("high")) return "#f97316";
  if (text.includes("yellow") || text.includes("黄") || text.includes("moderate")) return "#facc15";
  if (text.includes("blue") || text.includes("蓝") || text.includes("水位") || text.includes("雨量")) return "#2563eb";
  if (`${event.event_type || ""}`.includes("滑坡") || `${event.event_type_group || ""}`.includes("landslide")) return "#7c3aed";
  return "#0f9f8f";
}

function renderFallback(container, events = [], message = "地图视图即将支持事件空间分布展示") {
  const eventCount = Array.isArray(events) ? events.length : 0;
  container.classList.remove("is-leaflet");
  container.innerHTML = `
    <div class="map-card">
      <span class="eyebrow">Map Preview</span>
      <h3>${escapeHtml(message)}</h3>
      <p>当前保留事件列表和坐标卡片。Leaflet 加载成功后会在这里展示事件空间分布。</p>
      <div class="map-card-stats">
        <span>${eventCount}</span>
        <small>当前筛选事件</small>
      </div>
    </div>
  `;
}

function ensureLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (window.__georiskLeafletPromise) return window.__georiskLeafletPromise;
  window.__georiskLeafletPromise = new Promise((resolve, reject) => {
    if (!document.querySelector(`link[href="${LEAFLET_CSS_URL}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = LEAFLET_CSS_URL;
      document.head.appendChild(link);
    }
    const script = document.createElement("script");
    script.src = LEAFLET_JS_URL;
    script.async = true;
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error("Leaflet 加载失败"));
    document.head.appendChild(script);
  });
  return window.__georiskLeafletPromise;
}

function geoPrecisionLabel(precision) {
  const labels = {
    exact_point: "📍 精确坐标",
    county: "📌 区县级定位",
    city: "📌 市级定位",
    province: "📌 省级定位",
    town: "📌 乡镇级定位",
  };
  return labels[precision] || "⚠️ 未知精度";
}

function isSystemInferred(event) {
  // Coordinates inferred from place names by the system (not official exact points).
  return event.geo_precision && event.geo_precision !== "exact_point";
}

function popupHtml(event) {
  const link = event.url ? `<a href="${escapeHtml(event.url)}" target="_blank" rel="noopener noreferrer">查看原文</a>` : "";
  const precision = geoPrecisionLabel(event.geo_precision);
  const inferredNote = isSystemInferred(event)
    ? '<p class="geo-warning">⚠️ 坐标为系统根据地名推断，非官方精确点位</p>'
    : "";
  return `
    <strong>${escapeHtml(event.title || "灾害信息")}</strong>
    <p>${escapeHtml(event.event_type || event.event_type_group || "灾害")} · ${escapeHtml(event.risk || "未知等级")}</p>
    <p>${escapeHtml(event.time || "时间未知")} · ${escapeHtml(event.source || "未知来源")}</p>
    <p>${precision}</p>
    <p>${escapeHtml(event.summary || event.place || "")}</p>
    ${inferredNote}
    ${link}
  `;
}

function renderLeaflet(container, events) {
  const points = eventPoints(events);
  if (!points.length) {
    renderFallback(container, events, "当前筛选事件暂无可展示坐标");
    return;
  }
  container.classList.add("is-leaflet");
  container.innerHTML = '<div class="leaflet-map" aria-label="长沙周边灾害事件地图"></div>';
  const mapEl = container.querySelector(".leaflet-map");
  const map = L.map(mapEl, {scrollWheelZoom: false}).setView([28.2282, 112.9388], 9);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  points.forEach((event) => {
    L.circleMarker([Number(event.latitude), Number(event.longitude)], {
      radius: 8,
      color: levelColor(event),
      fillColor: levelColor(event),
      fillOpacity: 0.82,
      weight: 2,
    }).addTo(map).bindPopup(popupHtml(event));
  });
  const bounds = L.latLngBounds(points.map((event) => [Number(event.latitude), Number(event.longitude)]));
  if (points.length > 1) map.fitBounds(bounds.pad(0.18));
  setTimeout(() => map.invalidateSize(), 0);
}

window.GeoRiskMap = {
  renderPlaceholder(container, events = []) {
    if (!container) return;
    if (!eventPoints(events).length) {
      renderFallback(container, events, "当前筛选事件暂无可展示坐标");
      return;
    }
    ensureLeaflet()
      .then(() => renderLeaflet(container, events))
      .catch(() => renderFallback(container, events));
  },
};
