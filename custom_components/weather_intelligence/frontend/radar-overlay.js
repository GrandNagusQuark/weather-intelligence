// Browser-only NOAA imagery. Cache by the source's published scan, never by
// the time the page was refreshed. No raw radar processing or telemetry.
const MOSAIC = 'https://mapservices.weather.noaa.gov/eventdriven/rest/services/radar/radar_base_reflectivity_time/ImageServer';
const GEOSERVER = 'https://opengeo.ncep.noaa.gov/geoserver';
const STATIONS = 'https://api.weather.gov/radar/stations';
const MINUTE = 60000;
const MAX_SCAN_AGE = 15 * MINUTE;
const WORLD = 40075016.68557849;

export function preferDetailedRadar(zoom, previous = false) {
  return previous ? zoom > 8 : zoom >= 8.5;
}

export function radarFrameLabel(frame, now = Date.now()) {
  const age = Math.max(0, Math.floor((now - frame.scanTime) / MINUTE));
  const time = new Date(frame.scanTime).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
  return `${frame.label} · ${frame.kind === 'detail' ? 'scan' : 'mosaic'} ${time} · ${age < 1 ? 'less than 1 minute' : `${age} minute${age === 1 ? '' : 's'}`} old${now - frame.scanTime > MAX_SCAN_AGE ? ' — delayed imagery; do not rely on this as current weather.' : ''}${frame.fallback ? ' · Detailed radar unavailable for this view.' : ''}`;
}

export function radarStations(body) {
  if (!Array.isArray(body?.features) || body.features.length > 500) throw new Error('Invalid radar station directory');
  return body.features.filter(f => f.properties?.stationType === 'WSR-88D' && /^[A-Z][A-Z0-9]{3}$/.test(f.properties.id)
    && f.geometry?.type === 'Point' && f.geometry.coordinates?.length >= 2
    && Number.isFinite(f.geometry.coordinates[0]) && Math.abs(f.geometry.coordinates[0]) <= 180
    && Number.isFinite(f.geometry.coordinates[1]) && Math.abs(f.geometry.coordinates[1]) <= 90)
    .map(f => ({id:f.properties.id,lon:f.geometry.coordinates[0],lat:f.geometry.coordinates[1]}));
}

function distance(a, b) {
  const rad = Math.PI / 180, lat = (b[0]-a[0])*rad, lon = (b[1]-a[1])*rad;
  const h = Math.sin(lat/2)**2 + Math.cos(a[0]*rad)*Math.cos(b[0]*rad)*Math.sin(lon/2)**2;
  return 12742 * Math.asin(Math.sqrt(Math.min(1,h)));
}

export function stationForView(stations, view) {
  const point = (x,y) => [Math.atan(Math.sinh(y/(WORLD/(2*Math.PI))))*180/Math.PI,x/WORLD*360];
  const [left,bottom,right,top] = view.bbox;
  const corners = [point(left,bottom),point(left,top),point(right,bottom),point(right,top)];
  // Be conservative about single-site coverage. A blank area beyond a radar's
  // usable range must not replace the mosaic and look like clear weather.
  return stations.filter(s => corners.every(p => distance([s.lat,s.lon],p) <= 220))
    .sort((a,b) => distance([a.lat,a.lon],view.center)-distance([b.lat,b.lon],view.center))[0];
}

export function mosaicScans(body, now = Date.now()) {
  if (body?.error || body?.exceededTransferLimit || !Array.isArray(body?.features) || !body.features.length || body.features.length > 20) throw new Error('Mosaic metadata unavailable');
  return body.features.map(f => {
    const a = f.attributes || {}, points = f.geometry?.rings?.flat();
    if (!Number.isInteger(a.objectid) || !Number.isFinite(a.idp_validtime) || a.idp_validtime > now+2*MINUTE
      || !points?.length || points.length > 1000 || points.some(p => !Number.isFinite(p[0]) || !Number.isFinite(p[1]))) throw new Error('Invalid mosaic metadata');
    const x=points.map(p=>p[0]),y=points.map(p=>p[1]);
    return {id:a.objectid,time:a.idp_validtime,bbox:[Math.min(...x),Math.min(...y),Math.max(...x),Math.max(...y)]};
  });
}

export function stationScanTime(xml, station, now = Date.now(), Parser = DOMParser) {
  const doc = new Parser().parseFromString(xml,'application/xml');
  if (doc.getElementsByTagName('parsererror').length) throw new Error('Invalid radar metadata');
  const name = `${station.toLowerCase()}_sr_bref`;
  const layer = [...doc.getElementsByTagNameNS('*','Layer')].find(layer => [...layer.children].some(c => c.localName === 'Name' && c.textContent.trim().split(':').at(-1) === name));
  const dimension = layer && [...layer.children].find(c => c.localName === 'Dimension' && c.getAttribute('name') === 'time');
  const stamp = Date.parse(dimension?.getAttribute('default'));
  if (!Number.isFinite(stamp) || stamp > now+2*MINUTE || now-stamp > MAX_SCAN_AGE) throw new Error('Detailed radar scan unavailable or delayed');
  return stamp;
}

const intersects = (a,b) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];

export class RadarOverlay {
  constructor({fetcher = (...args)=>fetch(...args), createElement = tag=>document.createElement(tag), now = ()=>Date.now(), parseStationTime = stationScanTime} = {}) {
    Object.assign(this,{fetcher,createElement,now,parseStationTime});
    this.metadata=new Map(); this.frames=new Map(); this.pending=new Map(); this.controllers=new Set(); this.detailed=false; this.disposed=false;
  }

  async _text(url) {
    if (this.disposed) throw new Error('Map closed');
    const controller=new AbortController(); this.controllers.add(controller);
    const timer=setTimeout(()=>controller.abort(),12000);
    try {
      const response=await this.fetcher(url,{signal:controller.signal,cache:'no-cache',credentials:'omit'});
      if (!response.ok) throw new Error('Radar metadata unavailable');
      const text=await response.text();
      if (text.length>1500000) throw new Error('Radar metadata too large');
      return text;
    } finally {clearTimeout(timer);this.controllers.delete(controller);}
  }

  async _memo(key, lifetime, load) {
    const existing=this.metadata.get(key);
    if (existing?.until>this.now()) return existing.promise;
    const entry={until:this.now()+lifetime};
    entry.promise=load().catch(error=>{entry.until=this.now()+30000;throw error;});
    this.metadata.delete(key); this.metadata.set(key,entry);
    while(this.metadata.size>12)this.metadata.delete(this.metadata.keys().next().value);
    return entry.promise;
  }

  async _mosaicPlan(view) {
    const params=new URLSearchParams({f:'json',where:'category=1 AND idp_current_forecast=1',outFields:'objectid,idp_validtime',returnGeometry:'true',outSR:'3857',resultRecordCount:'20'});
    const all=await this._memo('mosaic',MINUTE,async()=>mosaicScans(JSON.parse(await this._text(`${MOSAIC}/query?${params}&_check=${Math.floor(this.now()/MINUTE)}`)),this.now()));
    const scans=all.filter(s=>view.regions.some(r=>intersects(s.bbox,r.bbox)));
    if (!scans.length) throw new Error('No radar mosaic coverage for this view');
    const ids=scans.map(s=>s.id).sort((a,b)=>a-b), scanTime=Math.min(...scans.map(s=>s.time));
    if (this.now()-scanTime>4*60*MINUTE) throw new Error('Radar mosaic expired');
    return {kind:'mosaic',label:'NOAA radar mosaic',scanTime,identity:ids.join(','),url:(part,size)=>{
      const params=new URLSearchParams({f:'image',bbox:part.bbox.join(','),bboxSR:'3857',imageSR:'3857',size:`${size.width},${size.height}`,format:'png32',transparent:'true',
        mosaicRule:JSON.stringify({mosaicMethod:'esriMosaicLockRaster',lockRasterIds:ids,mosaicOperation:'MT_FIRST'})});
      return `${MOSAIC}/exportImage?${params}`;
    }};
  }

  async _detailPlan(view) {
    const stations=await this._memo('stations',6*60*MINUTE,async()=>radarStations(JSON.parse(await this._text(STATIONS))));
    const station=stationForView(stations,view);
    if (!station) throw new Error('No single radar covers this view');
    const id=station.id.toLowerCase(), endpoint=`${GEOSERVER}/${id}/ows`;
    const scanTime=await this._memo(id,MINUTE,async()=>this.parseStationTime(await this._text(`${endpoint}?service=WMS&request=GetCapabilities&version=1.3.0&_check=${Math.floor(this.now()/MINUTE)}`),station.id,this.now()));
    if (this.now()-scanTime>MAX_SCAN_AGE) throw new Error('Detailed radar scan delayed');
    return {kind:'detail',label:`Super-resolution reflectivity · ${station.id}`,scanTime,identity:`${id}:${scanTime}`,url:(part,size)=>{
      const params=new URLSearchParams({service:'WMS',version:'1.1.1',request:'GetMap',layers:`${id}_sr_bref`,styles:'',srs:'EPSG:3857',bbox:part.bbox.join(','),width:String(size.width),height:String(size.height),format:'image/png',transparent:'true',time:new Date(scanTime).toISOString()});
      return `${endpoint}?${params}`;
    }};
  }

  _prune() {
    for (const [key,entry] of this.frames) if (entry.until<=this.now()) this.frames.delete(key);
    let pixels=[...this.frames.values()].reduce((sum,e)=>sum+e.pixels,0);
    while(this.frames.size>8 || pixels>16*1024*1024) {
      const key=this.frames.keys().next().value; pixels-=this.frames.get(key).pixels;this.frames.delete(key);
    }
  }

  _frame(plan,view) {
    if (this.disposed) return Promise.reject(new Error('Map closed'));
    this._prune();
    const key=JSON.stringify([plan.kind,plan.identity,view.bbox.map(n=>Number(n.toFixed(2))),view.width,view.height,view.imageSize]);
    const cached=this.frames.get(key);
    if(cached){this.frames.delete(key);this.frames.set(key,cached);return Promise.resolve(cached.result);}
    if(this.pending.has(key))return this.pending.get(key).promise;
    // Bound simultaneous downloads during repeated gestures as well as memory.
    while(this.pending.size>=4)this.pending.values().next().value.cancel();
    const frame=this.createElement('div');frame.className='radar-frame';
    const images=[],entry={};let timer,settled=false,pixels=0;
    entry.promise=new Promise((resolve,reject)=>{
      const finish=error=>{
        if(settled)return;settled=true;clearTimeout(timer);this.pending.delete(key);
        for(const image of images){image.onload=null;image.onerror=null;if(error)image.src='';}
        if(error){reject(error);return;}
        const result={frame,kind:plan.kind,label:plan.label,scanTime:plan.scanTime};
        this.frames.set(key,{result,pixels,until:Math.min(this.now()+10*MINUTE,plan.scanTime+4*60*MINUTE)});this._prune();resolve(result);
      };
      entry.cancel=()=>finish(new Error('Radar request superseded'));
      timer=setTimeout(()=>finish(new Error('Radar image timed out')),15000);
      let remaining=view.regions.length;
      for(const part of view.regions){
        const size={width:Math.max(1,Math.round(part.width/view.width*view.imageSize.width)),height:view.imageSize.height};pixels+=size.width*size.height;
        const image=this.createElement('img');images.push(image);image.alt='Latest available NOAA radar reflectivity';image.decoding='async';
        image.style.left=`${part.left}px`;image.style.width=`${part.width}px`;image.style.height=`${view.height}px`;frame.append(image);
        image.onload=async()=>{
          try {if(image.decode)await image.decode();if(!settled && !--remaining)finish();}
          catch {finish(new Error('Radar image could not be decoded'));}
        };
        image.onerror=()=>finish(new Error('Radar image unavailable'));image.src=plan.url(part,size);
      }
    });
    this.pending.set(key,entry);return entry.promise;
  }

  async load(view) {
    this.detailed=preferDetailedRadar(view.zoom,this.detailed);
    const detailed=this.detailed;
    // Prepare both near the switch point. Keep the old displayed frame until the
    // requested product is decoded; never blank the map to begin a download.
    const mosaic=this._mosaicPlan(view).then(plan=>this._frame(plan,view)).catch(()=>null);
    const detail=view.zoom>=8 ? this._detailPlan(view).then(plan=>this._frame(plan,view)).catch(()=>null) : Promise.resolve(null);
    const result=detailed ? await detail : await mosaic;
    if(result)return result;
    const fallback=await mosaic;
    if(fallback)return {...fallback,fallback:detailed};
    throw new Error('Radar unavailable');
  }

  dispose() {
    this.disposed=true;for(const controller of this.controllers)controller.abort();
    for(const entry of [...this.pending.values()])entry.cancel();
    this.frames.clear();this.metadata.clear();
  }
}
