// Reloaded for every test: the module remembers a download in progress.
let FLOOD_LAYER_ID;
let FLOOD_TILE_URL;
let MAPLIBRE_CSS;
let MAPLIBRE_JS;
let initParcelMap;
let readMapData;
let setFloodOverlay;

beforeEach(() => {
  jest.resetModules();
  ({
    FLOOD_LAYER_ID,
    FLOOD_TILE_URL,
    MAPLIBRE_CSS,
    MAPLIBRE_JS,
    initParcelMap,
    readMapData,
    setFloodOverlay,
  } = require('../parcelMap.js'));
});

const PARCEL = { lat: 27.965853, lng: -82.800103 };

function renderCard(data = PARCEL) {
  document.head.innerHTML = '';
  document.body.innerHTML = `
    <div id="parcel-map"></div>
    <p id="parcel-map-fallback" class="hidden"></p>
    <input type="checkbox" id="parcel-map-flood" disabled>
    <script id="parcel-map-data" type="application/json">${JSON.stringify(data)}</script>
  `;
}

function fakeMapLibre() {
  const layers = {};
  const map = {
    addControl: jest.fn(),
    addSource: jest.fn(),
    addLayer: jest.fn((layer) => {
      layers[layer.id] = layer;
    }),
    getLayer: jest.fn((id) => layers[id]),
    setLayoutProperty: jest.fn(),
    isStyleLoaded: jest.fn(() => true),
    once: jest.fn(),
  };
  const marker = { setLngLat: jest.fn(() => marker), addTo: jest.fn(() => marker) };
  return {
    map,
    marker,
    Map: jest.fn(() => map),
    Marker: jest.fn(() => marker),
    NavigationControl: jest.fn(),
  };
}

// A window stand-in with no IntersectionObserver, so the map starts at once.
function windowWith(maplibregl) {
  return { maplibregl };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('readMapData', () => {
  test('reads the coordinates the page was given', () => {
    renderCard();
    expect(readMapData(document)).toEqual(PARCEL);
  });

  test('is null when the page has no coordinates', () => {
    document.body.innerHTML = '';
    expect(readMapData(document)).toBeNull();
  });

  test('is null when a coordinate is missing or not a number', () => {
    renderCard({ lat: null, lng: -82.8 });
    expect(readMapData(document)).toBeNull();
  });
});

describe('initParcelMap', () => {
  test('centers the map and the pin on the parcel', async () => {
    renderCard();
    const lib = fakeMapLibre();

    initParcelMap(document, windowWith(lib));
    await settle();

    const options = lib.Map.mock.calls[0][0];
    expect(options.center).toEqual([PARCEL.lng, PARCEL.lat]);
    expect(options.style).toBe('https://tiles.openfreemap.org/styles/liberty');
    expect(options.cooperativeGestures).toBe(true);
    expect(lib.marker.setLngLat).toHaveBeenCalledWith([PARCEL.lng, PARCEL.lat]);
    expect(lib.marker.addTo).toHaveBeenCalledWith(lib.map);
  });

  test('does nothing on a page without the map card', () => {
    document.body.innerHTML = '';
    const lib = fakeMapLibre();

    initParcelMap(document, windowWith(lib));

    expect(lib.Map).not.toHaveBeenCalled();
  });

  test('waits until the card is near the viewport before fetching the library', () => {
    renderCard();
    let onIntersect;
    const observer = { observe: jest.fn(), disconnect: jest.fn() };
    const windowRef = {
      IntersectionObserver: jest.fn((callback) => {
        onIntersect = callback;
        return observer;
      }),
    };

    initParcelMap(document, windowRef);

    expect(observer.observe).toHaveBeenCalledWith(document.getElementById('parcel-map'));
    expect(document.head.querySelector('script')).toBeNull();

    onIntersect([{ isIntersecting: false }]);
    expect(document.head.querySelector('script')).toBeNull();

    onIntersect([{ isIntersecting: true }]);
    expect(observer.disconnect).toHaveBeenCalled();
    const script = document.head.querySelector('script');
    expect(script.src).toBe(MAPLIBRE_JS.url);
    expect(script.integrity).toBe(MAPLIBRE_JS.integrity);
    expect(script.crossOrigin).toBe('anonymous');
    const css = document.head.querySelector('link[rel="stylesheet"]');
    expect(css.href).toBe(MAPLIBRE_CSS.url);
    expect(css.integrity).toBe(MAPLIBRE_CSS.integrity);
  });

  test('shows the OpenStreetMap link when the library cannot be downloaded', async () => {
    renderCard();

    initParcelMap(document, {});
    document.head.querySelector('script').onerror();
    await settle();

    expect(document.getElementById('parcel-map').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('parcel-map-fallback').classList.contains('hidden')).toBe(false);
  });

  test('the flood checkbox turns the FEMA overlay on and off', async () => {
    renderCard();
    const lib = fakeMapLibre();
    initParcelMap(document, windowWith(lib));
    await settle();
    const toggle = document.getElementById('parcel-map-flood');
    expect(toggle.disabled).toBe(false);
    expect(lib.map.addLayer).not.toHaveBeenCalled();

    toggle.checked = true;
    toggle.dispatchEvent(new Event('change'));

    expect(lib.map.addSource).toHaveBeenCalledWith(
      FLOOD_LAYER_ID,
      expect.objectContaining({ type: 'raster', tiles: [FLOOD_TILE_URL], tileSize: 256 })
    );
    expect(lib.map.addLayer).toHaveBeenCalledTimes(1);

    toggle.checked = false;
    toggle.dispatchEvent(new Event('change'));

    expect(lib.map.setLayoutProperty).toHaveBeenLastCalledWith(FLOOD_LAYER_ID, 'visibility', 'none');
    expect(lib.map.addLayer).toHaveBeenCalledTimes(1);
  });
});

describe('setFloodOverlay', () => {
  test('hiding an overlay that was never shown adds nothing', () => {
    const { map } = fakeMapLibre();

    setFloodOverlay(map, false);

    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.setLayoutProperty).not.toHaveBeenCalled();
  });

  test("asks FEMA's map server for the flood hazard zones layer", () => {
    expect(FLOOD_TILE_URL).toContain('hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/export');
    expect(FLOOD_TILE_URL).toContain('bbox={bbox-epsg-3857}');
    expect(FLOOD_TILE_URL).toContain('layers=show:28');
  });
});
