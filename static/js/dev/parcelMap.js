/**
 * Map on the parcel page: a pin at the county's map point for the parcel,
 * with FEMA's flood zones as an optional overlay.
 *
 * MapLibre GL is about 1 MB, so it is only fetched once the map card is close
 * to the viewport. Tiles come from OpenFreeMap and the overlay from FEMA's own
 * map server, both straight to the visitor's browser: nothing here reaches
 * Django or the database.
 */

// Pinned, with integrity hashes, so the CDN can't hand out anything else.
// 5.24.0 is the last release with a plain <script> build; 6.x is ESM-only.
const MAPLIBRE_VERSION = '5.24.0';
const MAPLIBRE_BASE = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist`;
const MAPLIBRE_JS = {
  url: `${MAPLIBRE_BASE}/maplibre-gl.js`,
  integrity: 'sha384-5+cfbwT0iiub6VsQAdn6yz16nr6sDiQoHx6tm4O8OVYXHYOxcffFmCJBL0dgdvGp',
};
const MAPLIBRE_CSS = {
  url: `${MAPLIBRE_BASE}/maplibre-gl.css`,
  integrity: 'sha384-uTttxo/aOKbdE5RlD/SPzSDoDmNvGlUYPjONi2MN/b7c9HPSvW07OIuyP7uL6jxK',
};

const STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
const PIN_COLOR = '#0D7377';
const START_ZOOM = 15;
const LOAD_MARGIN = '300px';

// Layer 28 is the flood hazard zones layer the stored zone was read from.
// FEMA only draws it closer than about 1:36,000, which is map zoom 13 here.
const FLOOD_LAYER_ID = 'fema-flood-zones';
const FLOOD_MIN_ZOOM = 13;
const FLOOD_TILE_URL =
  'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/export' +
  '?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256,256' +
  '&format=png32&transparent=true&layers=show:28&f=image';
const FLOOD_ATTRIBUTION = 'Flood zones: FEMA National Flood Hazard Layer';

let libraryPromise = null;

function readMapData(documentRef) {
  const el = documentRef.getElementById('parcel-map-data');
  if (!el) {
    return null;
  }
  try {
    const data = JSON.parse(el.textContent);
    return Number.isFinite(data.lat) && Number.isFinite(data.lng) ? data : null;
  } catch (error) {
    return null;
  }
}

function loadMapLibre(documentRef, windowRef) {
  if (windowRef.maplibregl) {
    return Promise.resolve(windowRef.maplibregl);
  }
  if (libraryPromise) {
    return libraryPromise;
  }
  libraryPromise = new Promise((resolve, reject) => {
    const css = documentRef.createElement('link');
    css.rel = 'stylesheet';
    css.href = MAPLIBRE_CSS.url;
    css.integrity = MAPLIBRE_CSS.integrity;
    css.crossOrigin = 'anonymous';
    documentRef.head.appendChild(css);

    const script = documentRef.createElement('script');
    script.src = MAPLIBRE_JS.url;
    script.integrity = MAPLIBRE_JS.integrity;
    script.crossOrigin = 'anonymous';
    script.onload = () =>
      windowRef.maplibregl ? resolve(windowRef.maplibregl) : reject(new Error('MapLibre did not load'));
    script.onerror = () => reject(new Error('MapLibre could not be downloaded'));
    documentRef.head.appendChild(script);
  });
  // A failed download shouldn't stick: the next attempt gets a fresh request.
  libraryPromise.catch(() => {
    libraryPromise = null;
  });
  return libraryPromise;
}

function setFloodOverlay(map, visible) {
  if (!map.getLayer(FLOOD_LAYER_ID)) {
    if (!visible) {
      return;
    }
    map.addSource(FLOOD_LAYER_ID, {
      type: 'raster',
      tiles: [FLOOD_TILE_URL],
      tileSize: 256,
      attribution: FLOOD_ATTRIBUTION,
    });
    map.addLayer({
      id: FLOOD_LAYER_ID,
      type: 'raster',
      source: FLOOD_LAYER_ID,
      minzoom: FLOOD_MIN_ZOOM,
      paint: { 'raster-opacity': 0.45 },
    });
    return;
  }
  map.setLayoutProperty(FLOOD_LAYER_ID, 'visibility', visible ? 'visible' : 'none');
}

function showFallback(container, documentRef) {
  container.classList.add('hidden');
  const fallback = documentRef.getElementById('parcel-map-fallback');
  if (fallback) {
    fallback.classList.remove('hidden');
  }
}

function drawMap(maplibregl, container, data, documentRef) {
  const center = [data.lng, data.lat];
  const map = new maplibregl.Map({
    container,
    style: STYLE_URL,
    center,
    zoom: START_ZOOM,
    // Scrolling the page past the map shouldn't zoom it.
    cooperativeGestures: true,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  new maplibregl.Marker({ color: PIN_COLOR }).setLngLat(center).addTo(map);

  const toggle = documentRef.getElementById('parcel-map-flood');
  if (toggle) {
    const apply = () => setFloodOverlay(map, toggle.checked);
    toggle.addEventListener('change', () => (map.isStyleLoaded() ? apply() : map.once('load', apply)));
    toggle.disabled = false;
    if (toggle.checked) {
      map.once('load', apply);
    }
  }
  return map;
}

function initParcelMap(documentRef = document, windowRef = window) {
  const container = documentRef.getElementById('parcel-map');
  const data = readMapData(documentRef);
  if (!container || !data) {
    return;
  }

  const start = () =>
    loadMapLibre(documentRef, windowRef)
      .then((maplibregl) => drawMap(maplibregl, container, data, documentRef))
      .catch(() => showFallback(container, documentRef));

  if (!('IntersectionObserver' in windowRef)) {
    start();
    return;
  }
  const observer = new windowRef.IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.disconnect();
        start();
      }
    },
    { rootMargin: LOAD_MARGIN }
  );
  observer.observe(container);
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => initParcelMap(document, window));
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    FLOOD_LAYER_ID,
    FLOOD_TILE_URL,
    MAPLIBRE_CSS,
    MAPLIBRE_JS,
    initParcelMap,
    loadMapLibre,
    readMapData,
    setFloodOverlay,
  };
}
