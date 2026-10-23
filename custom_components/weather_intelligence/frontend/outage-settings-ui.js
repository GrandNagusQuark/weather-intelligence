import {OUTAGE_REPORTING_NOTICE} from './reporting-settings-ui.js?v=8';
import {reportingIdentity,bindReportingIdentity} from './reporting-identity-ui.js?v=1';
const LABELS={unknown:'Not enough current information',available:'Maintainer source check succeeded',
  possible_outage:'Possible service access problem',corroborated_outage:'Shared service access problem corroborated',
  possible_delay:'Possible alert feed delay',corroborated_delay:'Shared alert feed delay corroborated'};

export function serviceStatusText(status) {
  if(!status||!LABELS[status.state]||!Number.isFinite(Date.parse(status.expires_at))||Date.parse(status.expires_at)<=Date.now())return LABELS.unknown;
  return LABELS[status.state];
}

export function mountOutages(root,snapshot,save,back,configureBypass,reviewReporting) {
  const draw=()=>{
    root.innerHTML=`<section style="line-height:1.5"><h3>Outage participation</h3><p>${OUTAGE_REPORTING_NOTICE}</p>
      <p>Participation is <strong>${snapshot.config.enabled?'on':'off'}</strong>.</p>
      ${reportingIdentity(snapshot)}
      <p>Sent fields: schema version, random installation ID, NWS alert source label, unavailable, delayed or recovered, and a time rounded to the minute. A delay means an alert first reached this integration at least five minutes after its stated issue time during continuous monitoring. This does not measure when a phone received the notification.</p>
      <p>Destination: https://reports.weatherintelligence.app/v1/outages</p>
      ${snapshot.reporting_enabled===false?'<p>Error reporting is off. Accept error reporting first if you want to share outage contributions. You can still receive outage notices without contributing.</p><button id="outage-change-reporting">Change error reporting choice</button>':''}
      <p>Outage checks run in the background. Notices use normal delivery unless you separately allow bypass during locally verified severe weather. Phone permission is still required.</p>
      <div class="actions" style="display:flex;gap:10px;margin-top:16px"><button id="outage-accept" class="primary" ${snapshot.reporting_enabled===false?'disabled':''}>Accept</button><button id="outage-decline">Decline</button></div>
      <p id="outage-result" role="status"></p></section>`;
    bindReportingIdentity(root,snapshot);
    if(snapshot.reporting_enabled===false&&reviewReporting)root.querySelector('#outage-change-reporting').onclick=reviewReporting;
    root.querySelector('#outage-accept').onclick=()=>{if(snapshot.reporting_enabled!==false)return commit(true);};
    root.querySelector('#outage-decline').onclick=()=>commit(false);
  };
  let saving=false;
  const commit=async enabled=>{
    if(saving)return;
    saving=true;
    root.querySelectorAll('button').forEach(node=>node.disabled=true);
    try{
      snapshot=await save({expected_config:snapshot.config,enabled,consent:enabled,policy_version:1});
      if(!enabled){back();return;}
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
    }finally{saving=false;}
  };
  draw();
}
