import {OUTAGE_REPORTING_NOTICE} from './reporting-settings-ui.js?v=5';
const LABELS={unknown:'Not enough current information',available:'Maintainer source check succeeded',
  possible_outage:'Possible service access problem',corroborated_outage:'Shared service access problem corroborated',
  possible_delay:'Possible alert feed delay',corroborated_delay:'Shared alert feed delay corroborated'};

export function serviceStatusText(status) {
  if(!status||!LABELS[status.state]||!Number.isFinite(Date.parse(status.expires_at))||Date.parse(status.expires_at)<=Date.now())return LABELS.unknown;
  return LABELS[status.state];
}

export function mountOutages(root,snapshot,save,back,configureBypass) {
  const draw=()=>{
    root.innerHTML=`<section style="line-height:1.5"><h3>Outage participation</h3><p>${OUTAGE_REPORTING_NOTICE}</p>
      <p>Participation is <strong>${snapshot.config.enabled?'on':'off'}</strong>. ${snapshot.identity_created?'A random outage ID is saved locally.':'No active outage ID is saved locally.'}</p>
      <p>Outage checks run in the background. Notices use normal delivery unless you separately allow bypass during locally verified severe weather. Phone permission is still required.</p>
      <button id="outage-review">${snapshot.config.enabled?'Review participation':'Review and participate'}</button>
      <button id="outage-off">Keep outage participation off</button><button id="outage-back">Back</button>
      <p id="outage-result" role="status"></p></section>`;
    root.querySelector('#outage-back').onclick=back;
    root.querySelector('#outage-off').onclick=()=>commit(false);
    root.querySelector('#outage-review').onclick=()=>{
      root.innerHTML=`<h3>Confirm outage participation</h3><p>${OUTAGE_REPORTING_NOTICE}</p>
        <p>Sent fields: schema version, random installation ID, NWS alert source label, unavailable, delayed or recovered, and a time rounded to the minute. No locations, phone details or raw errors are included.</p>
        <p>A delay means an alert first reached this integration at least five minutes after its stated issue time while the area was already being monitored. Startup, travel, polling gaps, incomplete feeds and uncertain clocks are excluded. This does not measure when a phone received the notification.</p>
        <p>Destination: https://reports.weatherintelligence.app/v1/outages</p>
        <button id="outage-confirm">Agree and enable outage participation</button><button id="outage-cancel">Cancel</button><p id="outage-result" role="status"></p>`;
      root.querySelector('#outage-confirm').onclick=()=>commit(true);
      root.querySelector('#outage-cancel').onclick=draw;
    };
  };
  const commit=async enabled=>{
    root.querySelectorAll('button').forEach(node=>node.disabled=true);
    try{
      snapshot=await save({expected_config:snapshot.config,enabled,consent:enabled,policy_version:1});
      draw();root.querySelector('#outage-result').textContent='Outage participation saved.';
      if(enabled&&configureBypass){
        root.innerHTML=`<h3>Allow outage notices to bypass Do Not Disturb during severe weather?</h3>
          <p>This is a separate choice for each enrolled phone. A corroborated outage and an unexpired local official Tornado or Severe Thunderstorm watch or warning applying now or within two hours are both required. Its last confirmation must be within two hours and location must be fresh. Newer alert changes may be unavailable. Other outage notices use normal delivery.</p>
          <button id="outage-bypass-review">Review device bypass choices</button><button id="outage-bypass-skip">Keep my current bypass choices</button>`;
        root.querySelector('#outage-bypass-review').onclick=configureBypass;
        root.querySelector('#outage-bypass-skip').onclick=back;
      }
    }catch{
      root.querySelector('#outage-result').textContent='Could not save. Enable error reporting first or reopen this screen.';
      root.querySelectorAll('button').forEach(node=>node.disabled=false);
    }
  };
  draw();
}
