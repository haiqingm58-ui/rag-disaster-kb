window.GeoRiskMap = {
  renderPlaceholder(container, events = []) {
    if (!container) return;
    const eventCount = Array.isArray(events) ? events.length : 0;
    container.innerHTML = `
      <div class="map-card">
        <span class="eyebrow">Map Preview</span>
        <h3>地图视图即将支持事件空间分布展示</h3>
        <p>当前保留事件列表和坐标卡片。后续可在这里接入 Leaflet，并复用现有事件经纬度数据。</p>
        <div class="map-card-stats">
          <span>${eventCount}</span>
          <small>当前筛选事件</small>
        </div>
      </div>
    `;
  },
};
