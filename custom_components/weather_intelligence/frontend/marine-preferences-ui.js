// Shared onboarding/editor controls. Saves stay in their authenticated controllers.
export const marineNearbyControls=context=>`<section class="marine-nearby-controls"><h3>Nearby-water heads-ups — Early state</h3>
  <button type="button" class="setup-choice" data-marine-nearby data-marine-context="${context}" aria-pressed="false">Nearby-water heads-ups — Off</button>
  <label>Nearby-water distance (miles)<input type="number" min="0.1" max="100" step="0.1" value="10" data-marine-radius data-marine-context="${context}"></label>
  <p>While fresh GPS confidently places you on mapped water, include selected alerts nearby on the same water or connected by documented navigation channels. Default: 10 miles. Unrelated nearby waters do not qualify.</p>
  <small>These are Weather Intelligence heads-ups outside the official warning boundary, not a navigation service. They do not request DND bypass. Charted connections do not establish that a lock is open or a route is safe.</small>
  <small>These heads-ups are in an early state and require usable alert polygons and regional water maps. Zone-only alerts still use normal location delivery. Missing or incomplete maps can prevent nearby heads-ups; they never establish that conditions are safe.</small>
  <small>Regional maps are downloaded and cached on Home Assistant. The providers receive a coarse map region, not your exact GPS, identity or device details.</small></section>`;

export function renderMarineNearby(root,view={},context='custom'){
  root.querySelectorAll(`[data-marine-nearby][data-marine-context="${context}"]`).forEach(button=>{
    const enabled=view.marine_nearby_enabled===true;
    button.setAttribute('aria-pressed',String(enabled));button.textContent=`Nearby-water heads-ups — ${enabled?'On':'Off'}`;
    button.disabled=context!=='editor'&&!view.marine_warning_mode;
  });
  root.querySelectorAll(`[data-marine-radius][data-marine-context="${context}"]`).forEach(input=>{
    input.value=view.marine_nearby_miles??10;
    input.disabled=context!=='editor'&&!view.marine_warning_mode;
  });
}

export function installMarineNearby(root,getView,save){
  root.querySelectorAll('[data-marine-nearby]').forEach(button=>button.onclick=()=>{
    const view=getView(button.dataset.marineContext);
    save(button.dataset.marineContext,{marine_nearby_enabled:!view.marine_nearby_enabled,marine_nearby_miles:view.marine_nearby_miles??10});
  });
  root.querySelectorAll('[data-marine-radius]').forEach(input=>input.onchange=()=>{
    if(!input.reportValidity())return;
    const view=getView(input.dataset.marineContext);
    save(input.dataset.marineContext,{marine_nearby_enabled:view.marine_nearby_enabled===true,marine_nearby_miles:Number(input.value)});
  });
}
