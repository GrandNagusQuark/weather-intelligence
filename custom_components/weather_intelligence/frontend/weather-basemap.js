// Optional vector road layer. Never sends Person names, coordinates, or HA state.
// Like any basemap, requested tiles reveal the viewed area to its provider.
export const OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/dark";
const RUNTIME = new URL("./vendor/maplibre-gl.mjs", import.meta.url);
const WORKER = new URL("./vendor/maplibre-gl-worker.mjs?v=6.14.0", import.meta.url);
const CSS = new URL("./vendor/maplibre-gl.css", import.meta.url);

export function unclutteredStyle(style) {
  if (style?.version !== 8 || !Array.isArray(style.layers)) throw new Error("Unsupported basemap style");
  // Road shields and town names aid weather orientation; POIs and buildings do not.
  const symbolSources = new Set(["transportation_name", "place", "water_name"]);
  const layers = style.layers.filter(layer =>
    !["poi", "building", "aeroway"].includes(layer["source-layer"]) &&
    !/poi|housenumber|airport|building|railway|oneway|path/i.test(layer.id) &&
    layer.type !== "raster" &&
    (layer.type !== "symbol" || symbolSources.has(layer["source-layer"]))).map(layer => {
      const next={...layer,paint:{...layer.paint},layout:{...layer.layout}};
      if (layer.type === "background") next.paint["background-color"]="#1d2835";
      if (["landcover","landuse"].includes(layer["source-layer"]) && layer.type === "fill") next.paint["fill-color"]="#202e3b";
      if (layer["source-layer"] === "water" && layer.type === "fill") next.paint["fill-color"]="#173b51";
      if (layer["source-layer"] === "transportation" && layer.type === "line") {
        next.paint["line-color"]=/casing/.test(layer.id)?"#263d50":/motorway/.test(layer.id)?"#b5bdc2":/minor/.test(layer.id)?"#667b8b":"#8fa1ad";
        // A gentler regional view, not whole classes of roads disappearing.
        // Keep connections and closer street detail; motorways stay prominent.
        if (!/motorway|casing/.test(layer.id) && typeof (layer.paint?.["line-opacity"] ?? 1) === "number") {
          const opacity=layer.paint?.["line-opacity"] ?? 1;
          next.paint["line-opacity"]=["interpolate",["linear"],["zoom"],6,opacity*.75,10,opacity*.75,12,opacity];
        }
      }
      if (layer.type === "symbol") {
        next.paint["text-color"]=layer["source-layer"] === "transportation_name"?"#bac8d4":"#92a8ba";
        next.paint["text-halo-color"]="#1d2835"; next.paint["text-halo-blur"]=0;
        if (layer["source-layer"] === "place") delete next.layout["icon-image"];
      }
      return next;
    });
  const roadIndex=layers.findIndex(layer=>layer["source-layer"]==="transportation");
  if (roadIndex >= 0) layers.splice(roadIndex,0,{id:"weather-regional-connectors",type:"line",source:layers[roadIndex].source,
    "source-layer":"transportation",minzoom:6,maxzoom:12,
    filter:["match",["get","class"],["primary","secondary","tertiary"],true,false],
    layout:{"line-cap":"round","line-join":"round"},
    paint:{"line-color":"#788e9e","line-width":["interpolate",["linear"],["zoom"],6,.6,9,1.2,12,2],"line-opacity":["interpolate",["linear"],["zoom"],6,.64,10,.64,12,.85]}});
  const sources=Object.fromEntries(Object.entries(style.sources || {}).filter(([name])=>layers.some(layer=>layer.source===name)));
  return {...style,sources,layers};
}

export function basemapRequest(url) {
  const target = new URL(url);
  if (target.origin !== "https://tiles.openfreemap.org") throw new Error("Unexpected basemap destination");
  return {url:target.href, credentials:"omit", referrerPolicy:"no-referrer"};
}

export function vectorCamera(center, zoom) {
  // Our overlays use a 256px world at zoom0; MapLibre uses 512px.
  return {center:[center[1],center[0]], zoom:zoom-1, bearing:0, pitch:0};
}

export async function createVectorBasemap(container, shadowRoot, center, zoom, onStatus) {
  const [runtime, response] = await Promise.all([
    import(RUNTIME.href), fetch(OPENFREEMAP_STYLE, {credentials:"omit", referrerPolicy:"no-referrer"})
  ]);
  if (!response.ok) throw new Error("Road map unavailable");
  const style = unclutteredStyle(await response.json());
  if (!container.isConnected) throw new Error("Map closed");
  const link = document.createElement("link"); link.rel="stylesheet"; link.href=CSS.href; shadowRoot.prepend(link);
  runtime.setWorkerUrl(WORKER.href);
  runtime.setWorkerCount(1); // Browser work only; no map processing on the HA host.
  const map = new runtime.Map({container, style, ...vectorCamera(center,zoom),
    interactive:false, attributionControl:false, renderWorldCopies:false,
    maxTileCacheSize:64, maxTileCacheZoomLevels:3, fadeDuration:0,
    transformRequest:basemapRequest});
  map.on("error", () => onStatus("Some road-map detail unavailable."));
  map.on("idle", () => onStatus(""));
  return {sync(nextCenter,nextZoom) {map.resize(); map.jumpTo(vectorCamera(nextCenter,nextZoom));},
    remove() {map.remove(); link.remove();}};
}
