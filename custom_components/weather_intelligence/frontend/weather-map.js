// Small client-only map. NOAA renders radar; we draw official GeoJSON polygons.
// No radar processing, location history, or developer telemetry on the HA host.
import {createVectorBasemap} from "./weather-basemap.js?v=2";
import {RadarOverlay, radarFrameLabel} from "./radar-overlay.js?v=1";
const NOAA_WARNINGS = "https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer/0/query";
const NOAA_WARNING_AREAS = "https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer/1/query";
const NOAA_REFERENCE = "https://mapservices.weather.noaa.gov/static/rest/services/nws_reference_maps/nws_reference_map/MapServer";
const CENSUS_ROAD_TILES = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/tile";
const WORLD = 40075016.68557849;
const SVG_NS = "http://www.w3.org/2000/svg";
const RADAR_OPACITY_KEY = "weather-intelligence.radar-opacity";

export function radarOpacity(value) {
  if (value === null || value === undefined || String(value).trim() === "") return 65;
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, Math.round(number))) : 65;
}

// Request real display pixels, not just CSS pixels. NOAA accepts up to 4096
// pixels on either axis. Bound the whole frame as well, including wrapped parts,
// so a wide/high-density display cannot allocate an unbounded radar image.
// Supersampling improves presentation; it does not add detail to the 1 km data.
export function radarImageSize(width, height, pixelRatio = 1) {
  const cssWidth = Math.max(1, Number.isFinite(width) ? width : 1);
  const cssHeight = Math.max(1, Number.isFinite(height) ? height : 1);
  const desiredScale = Math.max(2, Math.min(3, Number.isFinite(pixelRatio) ? pixelRatio : 1));
  const scale = Math.min(desiredScale, 4096 / cssWidth, 4096 / cssHeight,
    Math.sqrt(4194304 / (cssWidth * cssHeight)));
  return {width: Math.max(1, Math.floor(cssWidth * scale)),
    height: Math.max(1, Math.floor(cssHeight * scale))};
}

export function warningStyle(event) {
  const name = String(event || "Unnamed official warning");
  if (/watch$/i.test(name)) return {label:name,color:/tornado/i.test(name)?"#ff8383":/thunderstorm/i.test(name)?"#ffe23a":"#a8baca",dash:"2 5",priority:-1};
  if (/^wind advisory$/i.test(name)) return {label:"Wind advisory",color:"#4ea5ff",dash:"6 4",priority:0};
  if (/tornado/i.test(name)) return {label:"Tornado",color:"#ff4444",priority:4};
  if (/thunderstorm/i.test(name)) return {label:"Severe storm",color:"#ffe23a",priority:3};
  if (/flash flood/i.test(name)) return {label:"Flash flood",color:"#36c774",priority:2};
  const color = /flood/i.test(name)?"#36c774":/snow|winter|blizzard|ice|freeze|cold/i.test(name)?"#becbff":/heat|fire|red flag/i.test(name)?"#ffa76c":/wind/i.test(name)?"#4ea5ff":"#f3a8ff";
  return {label:name,color,priority:1};
}

function selectedEventWhere(selected) {
  if (!Array.isArray(selected)) return ""; // Unreviewed legacy profile: preserve its prior broad map.
  if (!selected.length) return " AND 1=0";
  return ` AND prod_type IN (${selected.map(name=>`'${String(name).replaceAll("'","''")}'`).join(",")})`;
}

export function stormWarningWhere(selected = null) {
  return "sig = 'W' AND (msg_type IS NULL OR msg_type <> 'CAN')" + selectedEventWhere(selected);
}

export function warningAreaWhere(selected = null) {
  const products=Array.isArray(selected) ? "(sig IN ('Y','A'))" : "(sig = 'Y' AND prod_type = 'Wind Advisory')";
  return `(msg_type IS NULL OR msg_type <> 'CAN') AND ((sig = 'W' AND phenom NOT IN ('TO','SV','FF','SQ','MA')) OR ${products})` + selectedEventWhere(selected);
}

// Independent of the viewport: only public event/expiry metadata, never geometry,
// a household point, or one request per pan. Keep this filter aligned with polygons.
export function warningLegendQuery(where) {
  return new URLSearchParams({f:"json",where,outFields:"objectid,prod_type,expiration",
    returnGeometry:"false",resultRecordCount:"1000",orderByFields:"objectid"});
}

export function activeLegendStyles(records, now = Date.now()) {
  const entries = new Map();
  for (const record of records) {
    const name = record.prod_type, expires = Date.parse(record.expiration);
    if (typeof name !== "string" || !name.trim() || !Number.isFinite(expires)) {
      throw new Error("Coverage legend metadata incomplete");
    }
    if (expires <= now) continue;
    const style = warningStyle(name);
    entries.set(style.label,style);
  }
  return [...entries.values()].sort((a,b)=>b.priority-a.priority || a.label.localeCompare(b.label));
}

export async function warningLegendRecords(url, where, signal, fetcher = fetch) {
  const records = [], ids = new Set();
  for (let page = 0; page < 20; page++) {
    const params = warningLegendQuery(where); params.set("resultOffset",String(records.length));
    const response = await fetcher(`${url}?${params}`,{signal});
    if (!response.ok) throw new Error("Coverage legend unavailable");
    const body = await response.json();
    if (!Array.isArray(body.features)) throw new Error("Coverage legend metadata incomplete");
    for (const feature of body.features) {
      const record = feature.attributes || {};
      if (!Number.isInteger(record.objectid) || ids.has(record.objectid)) throw new Error("Coverage legend metadata incomplete");
      ids.add(record.objectid); records.push(record);
    }
    if (!body.exceededTransferLimit && body.features.length < 1000) {
      activeLegendStyles(records); // Validate every row, not just currently active ones.
      return records;
    }
    if (!body.features.length) break;
  }
  throw new Error("Coverage legend metadata incomplete");
}

export function roadTilePlan(center, zoom, width, height, pixelRatio = 1) {
  const z = Math.max(4,Math.min(19,Math.ceil(zoom+Math.log2(Math.max(1,Math.min(2,pixelRatio)))))), scale = 2 ** (zoom-z), size = 256*scale, count = 2 ** z;
  const point = projectPoint(...center,z), origin = [point[0]-width/(2*scale),point[1]-height/(2*scale)], tiles = [];
  for (let y=Math.max(0,Math.floor(origin[1]/256)-1); y<=Math.min(count-1,Math.floor((origin[1]+height/scale)/256)+1); y++) {
    for (let x=Math.floor(origin[0]/256)-1; x<=Math.floor((origin[0]+width/scale)/256)+1; x++) {
      const wrapped=((x%count)+count)%count;
      tiles.push({key:`${z}/${y}/${wrapped}`,z,x:wrapped,y,left:(x*256-origin[0])*scale,top:(y*256-origin[1])*scale,size});
    }
  }
  return tiles.sort((a,b)=>Math.hypot(a.left+size/2-width/2,a.top+size/2-height/2)-Math.hypot(b.left+size/2-width/2,b.top+size/2-height/2));
}

export function markerCode(index) {
  let value = Math.max(0, Math.floor(index)) + 1, label = "";
  do {value--; label = String.fromCharCode(65 + value % 26) + label; value = Math.floor(value / 26);} while (value);
  return label;
}

export async function warningFeatures(url, query, signal, fetcher = fetch) {
  const features = [];
  for (let page = 0; page < 10; page++) {
    const params = new URLSearchParams(query);
    params.set("resultOffset",String(features.length)); params.set("orderByFields","objectid");
    const response = await fetcher(`${url}?${params}`,{signal});
    if (!response.ok) throw new Error("Warning source unavailable");
    const body = await response.json();
    if (!Array.isArray(body.features)) throw new Error("Warning picture unavailable");
    features.push(...body.features);
    const limited = body.exceededTransferLimit || body.properties?.exceededTransferLimit;
    if (!limited && body.features.length < 200) return features;
    if (!body.features.length) throw new Error("Warning picture incomplete");
  }
  throw new Error("Warning picture incomplete — zoom in for a smaller area");
}

export function projectPoint(latitude, longitude, zoom) {
  const size = 256 * 2 ** zoom;
  const lat = Math.max(-85, Math.min(85, latitude)) * Math.PI / 180;
  return [(longitude + 180) / 360 * size,
    (1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * size];
}

export function unprojectPoint(x, y, zoom) {
  const size = 256 * 2 ** zoom;
  const latitude = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / size))) * 180 / Math.PI;
  return [Math.max(-85, Math.min(85, latitude)), x / size * 360 - 180];
}

export function nearestLongitude(longitude, center) {return longitude+360*Math.round((center-longitude)/360);}

// Split requests at the date line; ArcGIS queries always use canonical bounds.
export function wrappedViewParts(bbox,width) {
  const result=[],span=bbox[2]-bbox[0];
  for(let world=Math.floor((bbox[0]+WORLD/2)/WORLD);world<=Math.floor((bbox[2]+WORLD/2)/WORLD);world++){
    const left=Math.max(bbox[0],world*WORLD-WORLD/2),right=Math.min(bbox[2],world*WORLD+WORLD/2);
    if(right<=left)continue;
    result.push({bbox:[left-world*WORLD,bbox[1],right-world*WORLD,bbox[3]],left:(left-bbox[0])/span*width,width:(right-left)/span*width});
  }
  return result;
}

export function gestureView(center, zoom, startOffset, endOffset, scale = 1) {
  const nextZoom = Math.max(4, Math.min(18, zoom + Math.log2(Math.max(.01, scale))));
  const world = projectPoint(...center, zoom), factor = 2 ** (nextZoom - zoom);
  return {zoom: nextZoom, center: unprojectPoint(
    (world[0] + startOffset[0]) * factor - endOffset[0],
    (world[1] + startOffset[1]) * factor - endOffset[1], nextZoom)};
}

export function polygonPath(geometry, toPixel, centerLongitude = 0) {
  const polygons = geometry?.type === "Polygon" ? [geometry.coordinates] :
    geometry?.type === "MultiPolygon" ? geometry.coordinates : [];
  return polygons.flatMap(polygon => polygon.map(ring => {
    if(!ring.length)return '';
    let previous=ring[0][0],west=Infinity,east=-Infinity;
    const continuous=ring.map(point=>{
      const longitude=nearestLongitude(point[0],previous);previous=longitude;
      west=Math.min(west,longitude);east=Math.max(east,longitude);return [longitude,point[1]];
    });
    // Real state/coastal rings can exceed the engine's function argument limit.
    // Never spread their vertices into Math.min/Math.max.
    const middle=(west+east)/2;
    const shift=360*Math.round((centerLongitude-middle)/360);
    return continuous.map(([lon,lat],i)=>{
    const point=[lon+shift,lat];
    const [x, y] = toPixel(point[1], point[0]);
    return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ") + " Z";})).join(" ");
}

export function linePath(geometry,toPixel) {
  const lines=geometry?.type==="LineString" ? [geometry.coordinates] : geometry?.type==="MultiLineString" ? geometry.coordinates : [];
  return lines.map(line=>line.map((point,i)=>{const [x,y]=toPixel(point[1],point[0]); return `${i?"L":"M"}${x.toFixed(1)},${y.toFixed(1)}`;}).join(" ")).join(" ");
}

export function countyContains(geometry, longitude, latitude) {
  const polygons = geometry?.type === "Polygon" ? [geometry.coordinates] : geometry?.type === "MultiPolygon" ? geometry.coordinates : [];
  return polygons.some(polygon => {
    let inside = false;
    for (const ring of polygon) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > latitude) !== (yj > latitude) && longitude < (xj - xi) * (latitude - yi) / (yj - yi) + xi) inside = !inside;
      }
    }
    return inside;
  });
}

export class WeatherRadarMap extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._zoom = 8;
    this._center = [39.5, -98];
    this._warnings = [];
    this._people = [];
    this._fallback = [];
    this._counties = [];
    this._states = [];
    this._legendRecords = null;
    this._legendState = "loading";
    this._roadTileCache = new Map();
    this._statuses = {radar: "Loading radar…", warnings: "Loading warning polygons…", base: ""};
  }

  connectedCallback() {
    this.shadowRoot.innerHTML = `<style>
      :host{display:block}.map{height:390px;position:relative;overflow:hidden;border-radius:12px;background:#1e2b38;isolation:isolate;touch-action:pan-y;user-select:none}.map.dragging{cursor:grabbing}@media(hover:hover){.map{cursor:grab}}
      .tiles,.radar,.polygons,.people{position:absolute;inset:0;pointer-events:none}.tiles img{position:absolute;width:256px;height:256px;max-width:none}
      .radar img,.radar-frame,.tiles img{position:absolute;left:0;top:0;max-width:none;transform-origin:0 0}.tiles img{opacity:.78}.radar img{opacity:var(--radar-opacity,.65)}.polygons svg{width:100%;height:100%;overflow:visible}.polygons path.warning{pointer-events:visiblePainted;cursor:pointer}
      .tiles.census{filter:invert(1) hue-rotate(180deg) saturate(.65) brightness(1.05);mix-blend-mode:screen}
      .controls{position:absolute;top:10px;left:10px;display:flex;gap:5px;flex-wrap:wrap;max-width:80%}button{background:#172330;color:white;border:1px solid #607080;border-radius:6px;padding:8px 11px;cursor:pointer}
      .radar-controls{display:flex;align-items:center;gap:8px;max-width:310px;margin-top:5px;font-size:12px;color:var(--secondary-text-color)}.radar-controls label{white-space:nowrap}.radar-controls input{flex:1;min-width:50px;width:140px;height:32px;margin:0;accent-color:var(--primary-color,#55b6ff);touch-action:pan-y}.radar-controls output{min-width:4ch;text-align:right;font-variant-numeric:tabular-nums}.radar-controls input:focus-visible{outline:2px solid var(--primary-color,#76caff);outline-offset:2px}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;border:0}
      .person{position:absolute;transform:translate(-50%,-50%);border-radius:50%;border:1px solid white;background:#136db5;color:white;width:20px;height:20px;padding:0;line-height:20px;text-align:center;font:600 11px/20px system-ui;white-space:nowrap;box-shadow:0 0 2px #233544;pointer-events:auto;cursor:pointer}
      .person.stale,.key-marker.stale{background:#526579;border-style:dashed}.home-marker{position:absolute;transform:translate(-50%,-50%);font:bold 20px system-ui;color:#c9ddf0;text-shadow:0 0 2px #0e1a25}
      .people-key{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-top:8px;color:var(--primary-text-color)}.key-marker{display:inline-block;border-radius:50%;background:#136db5;color:white;width:20px;height:20px;font:600 11px/20px system-ui;text-align:center;margin-right:5px}
      .key-entry{display:inline-flex;align-items:center;background:none;border:0;padding:0;color:var(--primary-text-color);font:inherit;cursor:pointer}.key-entry:hover{text-decoration:underline}.key-entry:focus-visible{outline:2px solid var(--primary-color)}
      .attribution{position:absolute;bottom:0;right:0;background:#172330e8;color:#fff;padding:4px 7px;font:11px system-ui}.attribution a{color:#c9e9ff}
      .status{font-size:12px;margin-top:8px;color:var(--secondary-text-color);line-height:18px}.status>div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.status>div:empty{display:none}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-top:8px}.legend[hidden],.legend-note[hidden]{display:none}.legend span:before{content:"";display:inline-block;width:14px;border-top:3px solid var(--line);margin-right:5px;vertical-align:middle}.legend span.advisory:before{border-top-style:dashed}.legend-note{font-size:12px;margin-top:8px;color:var(--secondary-text-color)}
      .selection{min-height:1.2em;font-size:13px;padding-top:7px}.selection a{color:var(--primary-color)}@media(max-width:560px){.map{height:320px}}
      .gesture-hint{position:absolute;bottom:26px;left:50%;transform:translateX(-50%);background:#172330eb;color:white;padding:7px 12px;border-radius:8px;font:13px system-ui;pointer-events:none;white-space:nowrap}.gesture-hint[hidden]{display:none}.interaction-help{font-size:12px;margin-top:8px;color:var(--secondary-text-color)}
      @media(prefers-reduced-motion:reduce){.tiles,.radar,.polygons,.people{transition:none!important}}
    </style><div class="map" role="region" tabindex="0" aria-label="Weather radar and official warning polygons" aria-describedby="interaction-help">
      <div class="tiles" role="img" aria-label="Roads and streets"></div><div class="radar"></div><div class="polygons"></div><div class="people"></div>
      <div class="controls"><button data-zoom="1" aria-label="Zoom in">+</button><button data-zoom="-1" aria-label="Zoom out">−</button></div>
      <div class="gesture-hint" hidden></div>
      <div class="attribution"></div></div>
      <div class="radar-controls" title="Saved in this browser. Changes only the radar, not warnings or markers.">
        <label for="radar-opacity">Radar opacity</label>
        <input id="radar-opacity" type="range" min="0" max="100" step="1" value="65" aria-valuetext="65 percent" aria-describedby="radar-opacity-help">
        <output id="radar-opacity-value" for="radar-opacity">65%</output>
      </div>
      <span class="sr-only" id="radar-opacity-help">Saved in this browser. Changes only the radar, not warnings or markers.</span>
      <div class="interaction-help" id="interaction-help">Drag to pan · Shift + scroll to zoom · On phones, use two fingers to move or pinch to zoom.</div>
      <div class="interaction-help">Map warnings may appear after official issuance. Follow the official alert.</div>
      <div class="people-key" aria-label="Person marker key"></div>
      <div class="legend-note" role="status"></div><div class="legend" aria-label="Active alert types across U.S. coverage" hidden></div>
      <div class="status" role="status"><div data-map-status="radar"></div><div data-map-status="warnings"></div><div data-map-status="base"></div></div><div class="selection"></div>`;
    this.shadowRoot.querySelectorAll("[data-zoom]").forEach(button => button.onclick = () => {
      this._changeZoom(Number(button.dataset.zoom));
    });
    this._initRadarOpacity();
    this._vectorEnabled = this.getAttribute("basemap") === "openfreemap";
    const attribution = this.shadowRoot.querySelector(".attribution");
    attribution.innerHTML = this._vectorEnabled ? `Radar/boundaries: NOAA/NWS · <a href="https://openfreemap.org/" target="_blank" rel="noopener noreferrer">OpenFreeMap</a> · <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener noreferrer">© OpenMapTiles</a> · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap</a>` : "Radar/boundaries: NOAA/NWS · Roads: U.S. Census Bureau";
    this.shadowRoot.querySelector(".tiles").classList.toggle("census",!this._vectorEnabled);
    if (this._vectorEnabled) this._initVectorBasemap();
    const map = this.shadowRoot.querySelector(".map");
    map.addEventListener("wheel", event => this._handleWheel(event), {passive:false});
    map.addEventListener("pointerdown", event => this._startDrag(event));
    map.addEventListener("touchstart", event => this._startTouch(event), {passive:false});
    map.addEventListener("touchmove", event => this._moveTouch(event), {passive:false});
    map.addEventListener("touchend", event => this._endTouch(event));
    map.addEventListener("touchcancel", () => this._endTouch(null, true));
    map.addEventListener("click", event => {
      if (Date.now() < (this._suppressClickUntil || 0)) {event.preventDefault(); event.stopPropagation();}
    }, true);
    map.addEventListener("keydown", event => {
      if (event.target !== map || event.ctrlKey || event.altKey || event.metaKey) return;
      const offsets = {ArrowLeft:[100,0], ArrowRight:[-100,0], ArrowUp:[0,100], ArrowDown:[0,-100]};
      if (offsets[event.key]) {
        event.preventDefault(); this._center = gestureView(this._center, this._zoom, [0,0], offsets[event.key]).center; this._loadView();
      } else if (["+","=","-"].includes(event.key)) {event.preventDefault(); this._changeZoom(event.key === "-" ? -1 : 1);}
    });
    this._resize = new ResizeObserver(() => {clearTimeout(this._resizeTimer); this._resizeTimer = setTimeout(() => this._loadView(), 250);});
    this._resize.observe(this.shadowRoot.querySelector(".map"));
    this._legendSignature = null;
    this._loadLegend();
    this._timer = setInterval(() => {if (!document.hidden && this.offsetParent !== null) {this._loadView(); this._loadLegend();}}, 300000);
    this._radarTimer = setInterval(() => {
      if (!document.hidden && this.offsetParent !== null && !this._drag && !this._touchGesture && !this._zoomMotion) this._refreshRadar();
    }, 60000);
    this._legendExpiryTimer = setInterval(() => this._drawLegend(), 60000);
  }

  disconnectedCallback() {clearInterval(this._timer); clearInterval(this._radarTimer); this._radarRenderer?.dispose(); this._radarRenderer=null; clearInterval(this._legendExpiryTimer); this._legendRequest?.abort(); clearTimeout(this._resizeTimer); clearTimeout(this._hintTimer); clearTimeout(this._zoomTimer); clearTimeout(this._panFetchTimer); clearTimeout(this._tileTimer); cancelAnimationFrame(this._panFrame); this._zoomMotion = null; this._endDrag(null, true); this._touchGesture = null; this._resize?.disconnect(); this._request?.abort(); this._vectorMap?.remove(); this._vectorMap=null;}

  _initRadarOpacity() {
    let saved;
    try { saved = window.localStorage.getItem(RADAR_OPACITY_KEY); } catch (_error) { /* Browser storage may be disabled. */ }
    this._setRadarOpacity(saved);
    this.shadowRoot.querySelector("#radar-opacity").oninput = event => this._setRadarOpacity(event.target.value, true);
  }

  _setRadarOpacity(value, persist = false) {
    const percent = radarOpacity(value), slider = this.shadowRoot.querySelector("#radar-opacity");
    this.shadowRoot.querySelector(".radar").style.setProperty("--radar-opacity", String(percent / 100));
    slider.value = String(percent);
    slider.setAttribute("aria-valuetext", `${percent} percent`);
    this.shadowRoot.querySelector("#radar-opacity-value").textContent = `${percent}%`;
    if (persist) {
      try { window.localStorage.setItem(RADAR_OPACITY_KEY, String(percent)); } catch (_error) { /* Keep the current-page choice usable. */ }
    }
  }

  _refreshRadar() {
    const {width,height,bbox}=this._view();
    if (width<1 || height<1) return;
    if(this._radarProduct) {
      this._statuses.radar=radarFrameLabel(this._radarProduct)+(this._radarFailed ? ' Refresh unavailable — older image retained.' : '');
      this._status();
    }
    const view={center:[...this._center],zoom:this._zoom,width,height,bbox,
      regions:wrappedViewParts(bbox,width),imageSize:radarImageSize(width,height,window.devicePixelRatio||1)};
    this._radarLoading=this._loadRadar(view);
  }

  async _loadRadar(view) {
    const request=this._radarGeneration=(this._radarGeneration||0)+1;
    this._radarRenderer ||= new RadarOverlay();
    try {
      const product=await this._radarRenderer.load(view);
      if(request!==this._radarGeneration || !this.isConnected)return;
      const root=this.shadowRoot.querySelector('.radar');
      root.replaceChildren(product.frame);this._radarExtent=view;this._radarProduct=product;this._radarFailed=false;
      this._positionRaster(root,view,this._renderedVectorView||this._rasterView());
      this._statuses.radar=radarFrameLabel(product);this._status();
    } catch (_error) {
      if(request!==this._radarGeneration || !this.isConnected)return;
      this._radarFailed=true;
      this._statuses.radar=this._radarProduct ? `${radarFrameLabel(this._radarProduct)} Refresh unavailable — older image retained; do not infer clear weather.` : 'Radar unavailable — not an indication of clear weather.';
      this._status();
    }
  }

  async _loadLegend() {
    this._legendRequest?.abort();
    const controller = this._legendRequest = new AbortController();
    const timeout = setTimeout(()=>controller.abort(),15000);
    this._drawLegend();
    try {
      const parts = await Promise.all([
        warningLegendRecords(NOAA_WARNINGS,stormWarningWhere(this._selectedEvents),controller.signal),
        warningLegendRecords(NOAA_WARNING_AREAS,warningAreaWhere(this._selectedEvents),controller.signal),
      ]);
      if (!this.isConnected || this._legendRequest !== controller) return;
      this._legendRecords = parts.flat(); this._legendState = "ready";
    } catch (_error) {
      if (!this.isConnected || this._legendRequest !== controller) return;
      this._legendRecords = null; this._legendState = "unavailable";
    } finally {
      clearTimeout(timeout);
      if (this.isConnected && this._legendRequest === controller) this._drawLegend();
    }
  }

  _drawLegend() {
    const legend = this.shadowRoot.querySelector(".legend"), note = this.shadowRoot.querySelector(".legend-note");
    if (!legend || !note) return;
    const entries = this._legendState === "ready" ? activeLegendStyles(this._legendRecords || []) : [];
    const message = this._legendState === "unavailable" ? "Alert legend unavailable — active types across U.S. coverage could not be checked." :
      this._legendState === "loading" ? "Checking alert types across U.S. coverage…" : entries.length ? "Active alert types across U.S. coverage:" : "";
    note.hidden = !message;
    if (note.textContent !== message) note.textContent = message;
    legend.hidden = !entries.length;
    const signature = JSON.stringify(entries);
    if (signature === this._legendSignature) return;
    this._legendSignature = signature; legend.replaceChildren();
    for (const style of entries) {
      const label = document.createElement("span"); label.textContent = style.label; label.style.setProperty("--line",style.color);
      if (style.dash) label.classList.add("advisory"); legend.append(label);
    }
  }

  async _initVectorBasemap() {
    this._statuses.roads="Loading roads and streets…"; this._status();
    try {
      const basemap = await createVectorBasemap(this.shadowRoot.querySelector(".tiles"),this.shadowRoot,this._center,this._zoom,text=>{
        if (!this.isConnected) return;
        this._statuses.roads=text; this._status();
      },(center,zoom)=>{
        if(!this.isConnected)return;
        const {width,height}=this._view();
        this._renderedVectorView={center,zoom,width,height};
        this._positionRaster(this.shadowRoot.querySelector('.radar'),this._radarExtent,this._renderedVectorView);
        this._positionOverlays(this._renderedVectorView);
      });
      if (!this.isConnected) {basemap.remove(); return;}
      this._vectorMap=basemap; this._renderRoadTiles();
    } catch (_error) {
      if (this.isConnected) {this._statuses.roads="Road map unavailable — radar and warnings are separate sources."; this._status();}
    }
  }

  _changeZoom(direction, offset = [0,0]) {
    this._animateZoom(direction * .25, offset);
  }

  _animateZoom(amount, offset) {
    if (this._drag || this._touchGesture) return;
    const map = this.shadowRoot.querySelector(".map");
    const motion = this._zoomMotion || {center:[...this._center], zoom:this._zoom, target:this._zoom, offset,
      anchor:[offset[0]+map.clientWidth/2, offset[1]+map.clientHeight/2]};
    const next = Math.max(4, Math.min(18, motion.target + amount));
    if (next === motion.target) return;
    motion.target = next; this._zoomMotion = motion;
    const scale = 2 ** (next - motion.zoom);
    this._transformLayers(motion.anchor[0] * (1-scale), motion.anchor[1] * (1-scale), scale, true);
    clearTimeout(this._zoomTimer); this._zoomTimer = setTimeout(() => this._finishZoom(), 220);
  }

  _finishZoom() {
    clearTimeout(this._zoomTimer);
    const motion = this._zoomMotion; this._zoomMotion = null;
    if (!motion) return;
    const view = gestureView(motion.center, motion.zoom, motion.offset, motion.offset, 2 ** (motion.target-motion.zoom));
    this._center = view.center; this._zoom = view.zoom; this._transformLayers(); this._loadView();
  }

  _showGestureHint(text) {
    const hint = this.shadowRoot.querySelector(".gesture-hint"); hint.textContent = text; hint.hidden = false;
    clearTimeout(this._hintTimer); this._hintTimer = setTimeout(() => {hint.hidden = true;}, 1800);
  }

  _handleWheel(event) {
    if (!event.shiftKey || event.ctrlKey || event.metaKey) {
      if (!event.ctrlKey && !event.metaKey) this._showGestureHint("Hold Shift to zoom");
      return; // Ordinary scrolling belongs to the page, never the map.
    }
    event.preventDefault();
    const delta = event.deltaY || event.deltaX;
    if (!delta || this._drag || this._touchGesture) return;
    const rect = this.shadowRoot.querySelector(".map").getBoundingClientRect();
    const pixels = delta * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
    this._animateZoom(Math.max(-.3, Math.min(.3, -pixels * .002)), [event.clientX - rect.left - rect.width / 2, event.clientY - rect.top - rect.height / 2]);
  }

  _transformLayers(dx = 0, dy = 0, scale = 1, animate = false) {
    this.shadowRoot.querySelectorAll(".tiles,.radar,.polygons,.people").forEach(layer => {
      layer.style.transition = animate ? "transform 170ms ease-out" : "";
      layer.style.transformOrigin = "0 0"; layer.style.transform = dx || dy || scale !== 1 ? `translate(${dx}px,${dy}px) scale(${scale})` : "";
    });
  }

  _startDrag(event) {
    if (event.pointerType === "touch" || event.button !== 0 || event.target.closest?.("button,a") || this._touchGesture) return;
    this._finishZoom();
    this._endDrag(null, true);
    this._drag = {pointerId:event.pointerId, x:event.clientX, y:event.clientY, dx:0, dy:0, center:[...this._center], moved:false};
    this._dragMove = move => {
      const drag = this._drag; if (!drag || move.pointerId !== drag.pointerId) return;
      drag.dx = move.clientX - drag.x; drag.dy = move.clientY - drag.y;
      if (!drag.moved && Math.hypot(drag.dx, drag.dy) < 4) return;
      drag.moved = true; move.preventDefault();
      this.shadowRoot.querySelector(".map").classList.add("dragging");
      this._center = gestureView(drag.center,this._zoom,[0,0],[drag.dx,drag.dy]).center;
      this._queuePanDraw(); this._schedulePanFetch();
    };
    this._dragEnd = end => {if (end.pointerId === this._drag?.pointerId) this._endDrag(end, end.type === "pointercancel");};
    this._dragBlur = () => this._endDrag(null, true);
    window.addEventListener("pointermove", this._dragMove, {passive:false});
    window.addEventListener("pointerup", this._dragEnd); window.addEventListener("pointercancel", this._dragEnd); window.addEventListener("blur", this._dragBlur);
  }

  _endDrag(_event, cancel = false) {
    window.removeEventListener("pointermove", this._dragMove); window.removeEventListener("pointerup", this._dragEnd);
    window.removeEventListener("pointercancel", this._dragEnd); window.removeEventListener("blur", this._dragBlur);
    const drag = this._drag; this._drag = null;
    if (!drag) return;
    clearTimeout(this._panFetchTimer); this._panFetchTimer = null;
    this.shadowRoot.querySelector(".map")?.classList.remove("dragging"); this._transformLayers();
    if (drag.moved) this._suppressClickUntil = Date.now() + 200;
    if (drag.moved) {if (cancel) this._center = drag.center; this._queuePanDraw(); if (!cancel) this._loadView();}
  }

  _mapTouches(event) {
    const map = this.shadowRoot.querySelector(".map");
    return Array.from(event.touches || []).filter(touch => map.contains(touch.target));
  }

  _touchPoints(touches) {
    const rect = this.shadowRoot.querySelector(".map").getBoundingClientRect();
    return {mid:[(touches[0].clientX + touches[1].clientX) / 2 - rect.left, (touches[0].clientY + touches[1].clientY) / 2 - rect.top],
      distance:Math.max(1, Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY)), rect};
  }

  _startTouch(event) {
    const touches = this._mapTouches(event);
    if (touches.length !== 2) {
      if (touches.length > 2) this._endTouch(null, true);
      else if (!event.target.closest?.("button,a")) this._showGestureHint("Use two fingers to move the map");
      return; // One finger remains normal page scrolling.
    }
    event.preventDefault(); this._endDrag(null, true);
    this._finishZoom();
    const point = this._touchPoints(touches);
    this._touchGesture = {ids:touches.map(touch=>touch.identifier), start:point.mid, end:point.mid, distance:point.distance, scale:1,
      center:[...this._center], zoom:this._zoom, width:point.rect.width, height:point.rect.height};
    this.shadowRoot.querySelector(".gesture-hint").hidden = true;
  }

  _moveTouch(event) {
    const gesture = this._touchGesture; if (!gesture) return;
    const touches = this._mapTouches(event).filter(touch => gesture.ids.includes(touch.identifier));
    if (touches.length !== 2 || event.touches.length > 2) {this._endTouch(null, true); return;}
    event.preventDefault(); const point = this._touchPoints(touches); gesture.end = point.mid;
    gesture.scale = Math.max(2 ** (4 - gesture.zoom), Math.min(2 ** (18 - gesture.zoom), point.distance / gesture.distance));
    const origin=[gesture.width/2,gesture.height/2];
    const view=gestureView(gesture.center,gesture.zoom,gesture.start.map((v,i)=>v-origin[i]),gesture.end.map((v,i)=>v-origin[i]),gesture.scale);
    this._center=view.center; this._zoom=view.zoom; this._queuePanDraw(); this._schedulePanFetch();
  }

  _endTouch(event, cancel = false) {
    const gesture = this._touchGesture; if (!gesture) return;
    if (event && this._mapTouches(event).some(touch => gesture.ids.includes(touch.identifier)) && this._mapTouches(event).length >= 2) return;
    this._touchGesture = null; this._transformLayers(); this._suppressClickUntil = Date.now() + 200;
    clearTimeout(this._panFetchTimer); this._panFetchTimer = null;
    if (cancel) {this._center=gesture.center; this._zoom=gesture.zoom; this._queuePanDraw(); return;}
    const origin = [gesture.width / 2, gesture.height / 2];
    const view = gestureView(gesture.center, gesture.zoom, gesture.start.map((v,i)=>v-origin[i]), gesture.end.map((v,i)=>v-origin[i]), gesture.scale);
    if (gesture.scale !== 1 || Math.hypot(gesture.end[0]-gesture.start[0], gesture.end[1]-gesture.start[1]) > 2) {
      this._zoom = view.zoom; this._center = view.center; this._loadView();
    }
  }

  set data(value) {
    if (!this._home && value.map_center) {this._home = [...value.map_center]; this._center = [...this._home];}
    const selected=Array.isArray(value.map_alert_events)?[...value.map_alert_events]:null;
    const choicesChanged=JSON.stringify(selected)!==JSON.stringify(this._selectedEvents ?? null);
    this._selectedEvents=selected;
    const fingerprint = JSON.stringify([value.people,value.users,value.home_marker,value.monitored_polygons,selected]);
    if (fingerprint === this._dataFingerprint) return;
    this._dataFingerprint = fingerprint;
    const users = value.users || value.people || [];
    this._people = (value.people || []).map((person, index) => {
      const userIndex = users.findIndex(user => user.profile_id === person.profile_id);
      return {...person,marker_code:markerCode(userIndex < 0 ? index : userIndex)};
    });
    this._fallback = value.monitored_polygons || [];
    this._homeMarker = value.home_marker;
    this._mapUsers=users.map((user,index)=>({...user,marker_code:markerCode(index)})).filter(user=>user.map_visible!==false);
    this._drawPeopleKey();
    if (choicesChanged) {
      this._warnings=[]; this._legendRecords=null; this._legendState="loading";
      this._loadLegend(); this._loadView();
    }
    this._drawOverlays();
  }

  focusPerson(profileId) {
    const person = this._people.find(p => p.profile_id === profileId);
    if (person) {this._finishZoom(); this._center = [person.latitude, person.longitude]; this._zoom = 10.5; this._loadView();}
  }

  _positionRaster(root, source, target) {
    const image = root.querySelector(".radar-frame") || root.querySelector("img"); if (!image || !source) return;
    const scale = 2 ** (target.zoom-source.zoom);
    const before = projectPoint(...source.center,source.zoom), after = projectPoint(...target.center,target.zoom);
    const dx = (before[0]-source.width/2)*scale-after[0]+target.width/2;
    const dy = (before[1]-source.height/2)*scale-after[1]+target.height/2;
    image.style.width = `${source.width}px`; image.style.height = `${source.height}px`;
    image.style.transform = `translate(${dx}px,${dy}px) scale(${scale})`;
  }

  _rasterView() {const {width,height}=this._view(); return {center:[...this._center],zoom:this._zoom,width,height};}

  _positionOverlays(target) {
    this._drawPeople(target);
    const source=this._overlayExtent;if(!source)return;
    const scale=2**(target.zoom-source.zoom),before=projectPoint(...source.center,source.zoom),after=projectPoint(...target.center,target.zoom);
    const dx=(before[0]-source.width/2)*scale-after[0]+target.width/2,dy=(before[1]-source.height/2)*scale-after[1]+target.height/2;
    for(const layer of this.shadowRoot.querySelectorAll('.polygons')){
      layer.style.transformOrigin='0 0';layer.style.transform=`translate(${dx}px,${dy}px) scale(${scale})`;
    }
  }

  _queuePanDraw() {
    if (this._panFrame) return;
    this._panFrame=requestAnimationFrame(()=>{
      this._panFrame=null; if (!this.isConnected) return;
      this._renderRoadTiles();
      if(!this._vectorEnabled){
        const view=this._rasterView();
        this._positionRaster(this.shadowRoot.querySelector(".radar"),this._radarExtent,view);
        this._positionOverlays(view);
      }
    });
  }

  _schedulePanFetch() {
    // Existing geometry follows the camera immediately. Refresh once on release,
    // not while dragging, which used to rebuild the entire SVG mid-gesture.
  }

  _renderRoadTiles() {
    if (this._vectorEnabled) {this._vectorMap?.sync(this._center,this._zoom); return;}
    const root=this.shadowRoot.querySelector(".tiles"), {width,height}=this._view();
    const plan=roadTilePlan(this._center,this._zoom,width,height,window.devicePixelRatio || 1), needed=new Set(plan.map(tile=>tile.key));
    this._visibleRoadTiles=needed;
    const now=Date.now(), allowRequests=now-(this._lastTileRequestAt || 0)>=100;
    let deferred=false, requested=false;
    for (const tile of plan) {
      let cached=this._roadTileCache.get(tile.key);
      if (!cached) {
        if (!allowRequests) {deferred=true; continue;}
        const image=document.createElement("img"); image.alt=""; image.setAttribute("aria-hidden","true"); image.decoding="async";
        cached={image,state:"loading"}; this._roadTileCache.set(tile.key,cached); requested=true;
        image.onload=()=>{cached.state="loaded"; this._roadStatus();};
        image.onerror=()=>{cached.state="failed"; this._roadStatus();};
        image.src=`${CENSUS_ROAD_TILES}/${tile.key}`;
      }
      cached.image.style.cssText=`left:${tile.left}px;top:${tile.top}px;width:${tile.size}px;height:${tile.size}px;`;
      if (cached.image.parentNode!==root) root.append(cached.image);
    }
    if (requested) this._lastTileRequestAt=now;
    for (const [key,cached] of this._roadTileCache) {
      if (!needed.has(key)) {cached.image.remove(); if (this._roadTileCache.size>128) this._roadTileCache.delete(key);}
    }
    if (deferred && !this._tileTimer) this._tileTimer=setTimeout(()=>{this._tileTimer=null; if(this.isConnected)this._renderRoadTiles();},100);
    this._roadStatus();
  }

  _roadStatus() {
    const states=[...(this._visibleRoadTiles || [])].map(key=>this._roadTileCache.get(key)?.state);
    this._statuses.roads=states.includes("failed") ? "Some road/street tiles unavailable." : states.some(state=>state!=="loaded") ? "Loading roads and streets…" : "";
    this._status();
  }

  _view() {
    const map = this.shadowRoot.querySelector(".map");
    const width = Math.round(map.clientWidth), height = Math.round(map.clientHeight);
    const center = projectPoint(...this._center, this._zoom);
    const origin = [center[0] - width / 2, center[1] - height / 2];
    const size = 256 * 2 ** this._zoom;
    const bbox = [origin[0] / size * WORLD - WORLD / 2,
      WORLD / 2 - (origin[1] + height) / size * WORLD,
      (origin[0] + width) / size * WORLD - WORLD / 2,
      WORLD / 2 - origin[1] / size * WORLD];
    return {width, height, origin, bbox};
  }

  async _loadView() {
    if (!this.isConnected || document.hidden || this.offsetParent === null || this._zoomMotion || this._drag || this._touchGesture) return;
    const {width, height, origin, bbox} = this._view();
    if (width < 1 || height < 1) return;
    const generation = this._generation = (this._generation || 0) + 1;
    this._requestInFlight=true;
    this._request?.abort();
    const controller = this._request = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const view = {center:[...this._center],zoom:this._zoom,width,height};
    const radarRoot = this.shadowRoot.querySelector(".radar");
    this._positionRaster(radarRoot,this._radarExtent,view);
    this._statuses = {radar: this._statuses.radar || "", warnings: "Updating warning polygons…", base: "", roads:this._statuses.roads || ""};
    this._status();
    this._renderRoadTiles();
    const referenceRequest = this._loadReference(bbox, width, height, generation, controller.signal, view);
    this._warnings = this._warnings.filter(feature => {const until=Date.parse(feature.properties?.expiration); return !Number.isFinite(until) || until>Date.now();});
    this._drawOverlays();
    const regions=wrappedViewParts(bbox,width);
    this._refreshRadar();
    try {
      const parts=await Promise.all(regions.flatMap(region=>{
      const query = new URLSearchParams({f: "geojson", where: stormWarningWhere(this._selectedEvents), geometry: region.bbox.join(","), geometryType: "esriGeometryEnvelope", inSR: "3857", outSR: "4326", spatialRel: "esriSpatialRelIntersects", outFields: "objectid,prod_type,expiration,cap_id,url", returnGeometry: "true", resultRecordCount: "200", geometryPrecision:"5"});
      const areaQuery = new URLSearchParams(query);
      areaQuery.set("where",warningAreaWhere(this._selectedEvents));
      return [warningFeatures(NOAA_WARNINGS,query,controller.signal),warningFeatures(NOAA_WARNING_AREAS,areaQuery,controller.signal)];}));
      if (generation !== this._generation) return;
      this._warnings = parts.flat().filter(feature => {
        const until = Date.parse(feature.properties?.expiration);
        return !Number.isFinite(until) || until > Date.now();
      });
      this._statuses.warnings = "";
      this._drawOverlays();
    } catch (_error) {
      if (generation !== this._generation) return;
      this._warnings = [];
      this._statuses.warnings = "Regional polygons unavailable — showing monitored-alert outlines only.";
      this._drawOverlays();
    } finally {await referenceRequest; clearTimeout(timeout); if (generation === this._generation) {this._requestInFlight=false; this._status();}}
  }

  _drawOverlays() {
    if (!this.shadowRoot.querySelector(".map")) return;
    if(this._drag||this._touchGesture){this._drawPeople(this._renderedVectorView||this._rasterView());return;}
    const {width, height, origin} = this._view();
    const toPixel = (lat, lon) => {const p = projectPoint(lat, lon, this._zoom); return [p[0] - origin[0], p[1] - origin[1]];};
    const svg = document.createElementNS(SVG_NS, "svg"); svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const labels = [];
    for (const [kind, boundaries] of [["county", this._counties], ["state", this._states]]) {
      if (kind === "county" && this._zoom < 7) continue;
      for (const feature of boundaries) {
        const bold = kind === "county" && this._people.some(person => countyContains(feature.geometry, person.longitude, person.latitude));
        const path = document.createElementNS(SVG_NS, "path"); path.setAttribute("d", polygonPath(feature.geometry, toPixel,this._center[1])); path.setAttribute("fill", "none");
        path.setAttribute("stroke", bold ? "#d1e0eb" : kind === "state" ? "#91a6b9" : "#586b7d");
        path.setAttribute("stroke-width", bold ? "2.5" : kind === "state" ? "1.8" : ".8"); svg.append(path);
        const props = feature.properties || {};
        const name = kind === "county" ? props.countyname : props.state;
        if (name && (kind === "state" || this._zoom >= 8) && Number.isFinite(props.lat) && Number.isFinite(props.lon)) {
          const [x, y] = toPixel(props.lat, nearestLongitude(props.lon,this._center[1]));
          if (x > 20 && x < width - 20 && y > 45 && y < height - 20 && !labels.some(p => Math.abs(p[0] - x) < 65 && Math.abs(p[1] - y) < 18)) {
            const text = document.createElementNS(SVG_NS, "text"); text.setAttribute("x", x); text.setAttribute("y", y); text.setAttribute("text-anchor", "middle"); text.setAttribute("fill", "#c9d7e3"); text.setAttribute("font-size", kind === "state" ? "13" : "10"); text.setAttribute("font-family", "system-ui"); text.setAttribute("paint-order", "stroke"); text.setAttribute("stroke", "#1e2b38"); text.setAttribute("stroke-width", "2.5"); text.textContent = name; svg.append(text); labels.push([x, y]);
          }
        }
      }
    }
    const eventName = feature => feature.properties?.prod_type || feature.properties?.event || "Unnamed official warning";
    const features = (this._warnings.length ? this._warnings : this._fallback).filter(feature=>
      (!Array.isArray(this._selectedEvents) || this._selectedEvents.includes(eventName(feature))) &&
      (!feature.properties?.expiration || Date.parse(feature.properties.expiration)>Date.now()));
    for (const feature of [...features].sort((a,b)=>warningStyle(eventName(a)).priority-warningStyle(eventName(b)).priority)) {
      const event = eventName(feature), style=warningStyle(event);
      const path = document.createElementNS(SVG_NS, "path");
      path.classList.add("warning");
      path.setAttribute("d", polygonPath(feature.geometry, toPixel,this._center[1]));
      const color = style.color;
      path.setAttribute("fill", color); path.setAttribute("fill-opacity", ".07"); path.setAttribute("fill-rule", "evenodd"); path.setAttribute("stroke", color); path.setAttribute("stroke-width", "2.5");
      if (style.dash) path.setAttribute("stroke-dasharray",style.dash);
      const title = document.createElementNS(SVG_NS, "title"); title.textContent = event; path.append(title);
      path.onclick = () => {this.shadowRoot.querySelector(".selection").textContent = `${event}. Follow the official alert; radar is context only.`;};
      svg.append(path);
    }
    this.shadowRoot.querySelector(".polygons").replaceChildren(svg);
    this._overlayExtent=this._rasterView();
    this._positionOverlays(this._vectorEnabled?(this._renderedVectorView||this._overlayExtent):this._overlayExtent);
  }

  _drawPeople(view) {
    const people=this.shadowRoot.querySelector('.people');if(!people)return;
    // Reproject only a handful of points, not every warning vertex. Markers keep
    // their size and can enter the viewport during a drag or a repeated world.
    people.style.transform='';people.replaceChildren();
    const {width,height,zoom,center}=view,origin=projectPoint(...center,zoom);
    const toPixel=(lat,lon)=>{const p=projectPoint(lat,nearestLongitude(lon,center[1]),zoom);return [p[0]-origin[0]+width/2,p[1]-origin[1]+height/2];};
    if (this._homeMarker) {
      const [x, y] = toPixel(...this._homeMarker);
      if (x >= 0 && x <= width && y >= 0 && y <= height) {
        const marker = document.createElement("span"); marker.className='home-marker';marker.textContent = "✳"; marker.title = "Designated home";
        marker.style.left=`${x}px`;marker.style.top=`${y}px`;
        people.append(marker);
      }
    }
    for (const person of this._people) {
      const [x, y] = toPixel(person.latitude,person.longitude);
      if (x < 0 || x > width || y < 0 || y > height) continue;
      const marker = document.createElement("button"); marker.className = `person${person.location_stale?' stale':''}`; marker.type="button";
      const label=this._personLabel(person);
      marker.textContent = person.marker_code; marker.title = label; marker.setAttribute("aria-label",label);
      marker.onclick=()=>this.focusPerson(person.profile_id);
      marker.style.left = `${x}px`; marker.style.top = `${y}px`; people.append(marker);
    }
  }

  _personLabel(person) {
    if(!person.location_stale)return person.name;
    const updated=Date.parse(person.location_updated_at);
    return `${person.name} · Last known location${Number.isFinite(updated)?' · '+new Date(updated).toLocaleString():''}`;
  }

  _drawPeopleKey() {
    const key=this.shadowRoot.querySelector('.people-key');if(!key)return;
    key.replaceChildren();
    for(const user of this._mapUsers || this._people){
      const person=this._people.find(p=>p.profile_id===user.profile_id);
      const entry=document.createElement(person?'button':'span'),badge=document.createElement('span');entry.className='key-entry';
      if(person){entry.type='button';entry.setAttribute('aria-label',`Center map on ${user.name}`);entry.onclick=()=>this.focusPerson(user.profile_id);entry.title=this._personLabel(person);}
      badge.className=`key-marker${person?.location_stale?' stale':''}`;badge.textContent=person?.marker_code||user.marker_code;
      const label=`${user.name}${!person?' · Location unavailable':person.location_stale?' · Last known location':''}`;
      entry.append(badge,document.createTextNode(label));key.append(entry);
    }
  }

  async _loadReference(bbox, width, height, generation, signal, view) {
    const key = `${this._zoom}/${bbox.join(",")}`;
    if (this._referenceKey === key) return;
    this._referenceKey = null;
    this._statuses.base = "Updating county/state boundaries…"; this._status();
    try {
      const layers = this._zoom >= 7 ? [2,3] : [3];
      const results = await Promise.all(layers.map(async layer => {
        const parts=await Promise.all(wrappedViewParts(bbox,width).map(async region=>{
        const query = new URLSearchParams({f:"geojson",where:"1=1",geometry:region.bbox.join(","),geometryType:"esriGeometryEnvelope",inSR:"3857",outSR:"4326",outFields:layer===2?"countyname,state,fips,lat,lon":"state,name,lat,lon",returnGeometry:"true",resultRecordCount:layer===2?"500":"60",geometryPrecision:"5"});
        const response = await fetch(`${NOAA_REFERENCE}/${layer}/query?${query}`, {signal});
        if (!response.ok) throw new Error("Reference map unavailable");
        const body = await response.json();
        if (!Array.isArray(body.features) || body.exceededTransferLimit) throw new Error("Reference map incomplete");
        return body.features;}));
        return [layer, parts.flat()];
      }));
      if (generation !== this._generation) return;
      this._referenceKey = key;
      this._counties = results.find(pair => pair[0]===2)?.[1] || [];
      this._states = results.find(pair => pair[0]===3)?.[1] || [];
      this._statuses.base = "";
      this._drawOverlays(); this._status();
    } catch (_error) {if (generation === this._generation) {this._statuses.base = this._states.length ? "Boundary refresh unavailable — previous outlines retained." : "County/state boundaries unavailable."; this._status();}}
  }

  _status() {
    const rows={radar:this._statuses.radar || "",warnings:this._statuses.warnings || "",base:[this._statuses.base,this._statuses.roads,this._statuses.connectors].filter(Boolean).join(" ")};
    for(const [key,text] of Object.entries(rows)) {
      const row=this.shadowRoot.querySelector(`[data-map-status="${key}"]`); if(!row || row.textContent===text)continue;
      row.textContent=text; row.title=text;
    }
  }
}
if (!customElements.get("weather-radar-map")) customElements.define("weather-radar-map", WeatherRadarMap);
