/* Leaflet wrapper. Loaded only on pages with maps. Tiles come from the admin setting
   MAP_TILE_URL, attribution is always shown, and tiles are never pre-fetched or cached. */
(function () {
  "use strict";
  if (!window.L) return;

  function readJSON(id) {
    var el = id && document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function init(el) {
    if (el._kdMap) return;
    var cfg = readJSON(el.getAttribute("data-config")) || {};
    var center = [parseFloat(el.dataset.lat || cfg.lat || 7.95), parseFloat(el.dataset.lng || cfg.lng || -1.03)];
    var zoom = parseInt(el.dataset.zoom || cfg.zoom || 14, 10);
    var map = L.map(el, { scrollWheelZoom: false, zoomControl: true, attributionControl: true }).setView(center, zoom);
    el._kdMap = map;
    L.tileLayer(el.dataset.tiles, { maxZoom: 19, attribution: el.dataset.attribution, crossOrigin: false }).addTo(map);
    map.attributionControl.setPrefix(false);

    var approxRadius = parseInt(el.dataset.approxRadius || "300", 10);
    if (el.dataset.mode === "approx") {
      L.circle(center, { radius: approxRadius, color: "currentColor", weight: 1, fillOpacity: 0.2, className: "text-primary" }).addTo(map);
    } else if (el.dataset.mode === "pin") {
      L.marker(center).addTo(map);
    }

    var rings = (el.dataset.rings || "").split(",").filter(Boolean);
    rings.forEach(function (r) {
      L.circle(center, { radius: parseInt(r, 10), weight: 1, fill: false, dashArray: "4 6", className: "text-base-content" }).addTo(map)
        .bindTooltip(r >= 1000 ? (r / 1000) + " km" : r + " m");
    });

    var items = readJSON(el.dataset.items) || [];
    var bounds = [];
    items.forEach(function (it) {
      var ll = [it.lat, it.lng];
      bounds.push(ll);
      var popup = '<a class="link font-semibold" href="' + it.url + '"></a><div class="text-xs opacity-70"></div>';
      var layer = it.approx
        ? L.circle(ll, { radius: approxRadius, weight: 1, fillOpacity: 0.15, className: "text-primary" })
        : L.circleMarker(ll, { radius: 8, weight: 2, fillOpacity: 0.8, className: "text-accent" });
      layer.addTo(map).bindPopup(function () {
        var div = document.createElement("div");
        div.innerHTML = popup;
        div.querySelector("a").textContent = it.title;
        div.querySelector("div").textContent = it.info || "";
        return div;
      });
    });
    if (bounds.length > 1 && el.dataset.fit !== "false") map.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });

    if (el.dataset.mode === "pick") {
      var latInput = document.getElementById(el.dataset.latInput);
      var lngInput = document.getElementById(el.dataset.lngInput);
      var marker = null;
      if (latInput && latInput.value && lngInput.value) {
        marker = L.marker([parseFloat(latInput.value), parseFloat(lngInput.value)], { draggable: true }).addTo(map);
        map.setView(marker.getLatLng(), 16);
      }
      function set(ll) {
        if (!marker) { marker = L.marker(ll, { draggable: true }).addTo(map); marker.on("dragend", function () { set(marker.getLatLng()); }); }
        marker.setLatLng(ll);
        latInput.value = ll.lat.toFixed(6);
        lngInput.value = ll.lng.toFixed(6);
      }
      if (marker) marker.on("dragend", function () { set(marker.getLatLng()); });
      map.on("click", function (e) { set(e.latlng); });
    }
    setTimeout(function () { map.invalidateSize(); }, 200);
  }

  function initAll(scope) {
    (scope || document).querySelectorAll("[data-kd-map]").forEach(init);
  }
  document.addEventListener("DOMContentLoaded", function () { initAll(); });
  document.addEventListener("htmx:afterSettle", function (ev) { initAll(ev.target); });
  initAll();
})();
