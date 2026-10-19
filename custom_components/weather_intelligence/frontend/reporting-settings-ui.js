import {mountReportingAudit} from './reporting-audit-ui.js?v=1';
const escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;')
  .replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');

export const REPORTING_DISCLOSURE='Optional error reports contain software versions, a time rounded to the minute, a fixed error category, component, severity and safe exception type. For a phone related error, platform, OS version and Companion app version are included when known. Unknown device details are not guessed. Reports exclude names, locations, entity names, device IDs, serial numbers, MAC and IP addresses, credentials, raw logs and tracebacks. The project destination sends these reports through Cloudflare to the maintainer’s private Home Assistant inbox. Reports and the local sending history are kept for 30 days. Cloudflare processes the connection IP and handles network records under its own policies. This does not guarantee anonymity. Reporting is off unless an administrator agrees for this Home Assistant installation. Reporting never controls weather alert delivery.';
export const OUTAGE_REPORTING_NOTICE='Outage contributions have a separate choice that can be turned off without disabling ordinary error reports. Only after you agree, this installation creates a random ID to group NWS alert feed failures, significant delays and recoveries. A delay is significant at five minutes from the stated issue time to first receipt by this integration during continuous monitoring of the same area. This does not measure phone arrival time. That ID can link contributions from this installation, so the reports are pseudonymous rather than completely anonymous. The ID is not added to ordinary error reports or used to track other activity. Contributions contain only that ID, the source label, unavailable, delayed or recovered, a time rounded to the minute and the schema version. Records and local sending history are kept for 30 days. Turning participation off deletes the active local ID. Previously received records expire within 30 days and recent observations stop counting after 15 minutes. Enabling it again creates a new ID. Receiving service status does not require contributing reports. Status checks still disclose network metadata to Cloudflare. Error reporting must be enabled before you can choose to participate.';
const REPORTING_STYLE='<style>.wi-reporting{line-height:1.5;overflow-wrap:anywhere}.wi-reporting input{box-sizing:border-box;width:100%;padding:10px;margin:8px 0;background:var(--card-background-color,#18232e);color:inherit;border:1px solid var(--divider-color,#536274);border-radius:8px;font:inherit}.wi-reporting pre{white-space:pre-wrap;overflow-wrap:anywhere}.wi-reporting .actions{display:flex;flex-wrap:wrap;gap:10px}.wi-reporting button{min-height:44px;padding:10px 14px;font:inherit}.wi-reporting button:disabled{opacity:.55}</style>';

export function reportingForm(snapshot) {
  return `${REPORTING_STYLE}<section class="wi-reporting"><h3>Optional error reporting</h3><p>${REPORTING_DISCLOSURE}</p>
    <p>Reporting is ${snapshot.config.enabled?'on':'off'}. ${escapeHtml(snapshot.last_result)}.</p>
    <p>Accepted: ${escapeHtml(snapshot.sent)}. Failed: ${escapeHtml(snapshot.failed)}. Suppressed: ${escapeHtml(snapshot.dropped)}.</p>
    <label>Reporting destination<input id="reporting-endpoint" type="url" autocomplete="off" spellcheck="false" value="${escapeHtml(snapshot.config.endpoint)}" placeholder="https://your-domain/v1/errors"></label>
    <p>The project destination is ready. You can review it before agreeing or choose a destination you operate. Saving a destination with reporting off does not send a test report.</p>
    <details><summary>Separate outage contributions</summary><p>${OUTAGE_REPORTING_NOTICE}</p></details>
    <div class="actions"><button id="reporting-review">Review and enable</button><button id="reporting-save-off">Save with reporting off</button></div>
    <p id="reporting-result" role="status"></p></section>`;
}

export function reportingReview(endpoint,preview) {
  return `${REPORTING_STYLE}<section class="wi-reporting"><h3>Confirm error reporting</h3><p>Send the following diagnostic fields to:</p>
    <p><strong>${escapeHtml(endpoint)}</strong></p><pre>${escapeHtml(JSON.stringify(preview,null,2))}</pre>
    <p>This is an example, not a report from your installation.</p><p>${REPORTING_DISCLOSURE}</p>
    <p>Only enable a destination you trust. Review its privacy notice and any downstream service before continuing.</p>
    <div class="actions"><button id="reporting-enable">Enable reporting to this destination</button><button id="reporting-back">Back</button></div><p id="reporting-result" role="status"></p></section>`;
}

export function mountReporting(root,snapshot,save,loadAudit,openOutages) {
  let endpoint=snapshot.config.endpoint||snapshot.default_endpoint||'';
  const draw=()=>{
    root.innerHTML=reportingForm({...snapshot,config:{...snapshot.config,endpoint}});
    if(loadAudit){
      const history=root.ownerDocument.createElement('button');
      history.textContent='View reporting history';history.id='reporting-history';
      history.onclick=()=>mountReportingAudit(root,loadAudit,draw);
      root.querySelector('.actions').append(history);
    }
    if(openOutages){
      const outages=root.ownerDocument.createElement('button');
      outages.textContent='Outage participation';outages.id='reporting-outages';
      outages.onclick=openOutages;root.querySelector('.actions').append(outages);
    }
    root.querySelector('#reporting-save-off').onclick=()=>commit(false);
    root.querySelector('#reporting-review').onclick=()=>{
      endpoint=root.querySelector('#reporting-endpoint').value.trim();
      if(!endpoint){root.querySelector('#reporting-result').textContent='Enter the reporting destination first.';return;}
      try{endpoint=new URL(endpoint).href;}catch{root.querySelector('#reporting-result').textContent='Enter a valid reporting destination.';return;}
      root.innerHTML=reportingReview(endpoint,snapshot.preview);
      root.querySelector('#reporting-enable').onclick=()=>commit(true);
      root.querySelector('#reporting-back').onclick=draw;
    };
  };
  const commit=async enabled=>{
    if(!enabled)endpoint=root.querySelector('#reporting-endpoint').value.trim();
    root.querySelectorAll('button,input').forEach(node=>node.disabled=true);
    try{
      snapshot=await save({expected_config:snapshot.config,endpoint,enabled,
        consent:enabled,consent_endpoint:enabled?endpoint:'',policy_version:snapshot.config.policy_version});
      endpoint=snapshot.config.endpoint;draw();root.querySelector('#reporting-result').textContent='Reporting settings saved.';
    }catch{
      root.querySelector('#reporting-result').textContent='Could not save reporting settings. Check the destination or reopen this screen.';
      root.querySelectorAll('button,input').forEach(node=>node.disabled=false);
    }
  };
  draw();
}
