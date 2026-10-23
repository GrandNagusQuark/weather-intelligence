import {reportingIdentity,bindReportingIdentity} from './reporting-identity-ui.js?v=1';
const escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;')
  .replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');

export const REPORTING_DISCLOSURE='Optional error reports help the maintainer find and fix bugs. If an administrator agrees, this installation creates a random number so repeated errors from one installation can be grouped together. It is not a Home Assistant account number or a phone identifier. Every error report includes the Weather Intelligence and Home Assistant versions, a time rounded to the minute, a fixed error category, component, severity, recognizable exception types and their causes. Fixed explanations come from the published source code. Reports include module/function/line locations and HTTP status, OS error or process exit codes only when the failure supplies them. Absolute filesystem paths, local variables, source lines and raw exception messages are excluded. It also includes the platform, OS version and Companion app version of enrolled phones when their registrations supply them, even when the error comes from a server or weather source. Up to eight distinct software combinations are included without names, device counts or phone identifiers. Missing registration details are marked as unavailable rather than guessed. This is installation context, not evidence that a phone caused the error. Reports exclude names, locations, entity names, hardware identifiers, serial numbers, MAC and IP addresses, credentials, raw logs and tracebacks. The random number links reports from the same installation, so they are pseudonymous rather than anonymous. Administrators can review the exact prepared reports, destination and delivery results in the local audit log for 30 days. The project destination sends reports through Cloudflare to the maintainer’s private Home Assistant inbox, where records are also kept for 30 days. Cloudflare processes the connection IP under its own policies. Reporting is off by default and never controls weather alert delivery. Existing consent must be reviewed before these updated fields are sent.';
export const OUTAGE_REPORTING_NOTICE='Outage contributions help spot shared weather feed failures and delays. They have a separate choice that can be turned off without disabling ordinary error reports. With your agreement, they use the same random installation number as error reports to group NWS alert feed failures, significant delays and recoveries. A delay is significant at five minutes from the stated issue time to first receipt by this integration during continuous monitoring of the same area. This does not measure phone arrival time. Contributions contain only the installation number, source label, unavailable, delayed or recovered, a time rounded to the minute and schema version. They contain no location or alert content. The number can link reports from the same installation, so they are pseudonymous. Records and local sending history are kept for 30 days. Turning outage participation off stops contributions but keeps the number while error reporting remains enabled. Turning error reporting off removes the active local number and stops both kinds of reports. Previously received records expire within 30 days and recent outage observations stop counting after 15 minutes. Receiving service status does not require contributing reports. Status checks still disclose network metadata to Cloudflare. Error reporting must be enabled before you can choose to participate.';
const REPORTING_STYLE='<style>.wi-reporting{line-height:1.5;overflow-wrap:anywhere}.wi-reporting input{box-sizing:border-box;width:100%;padding:10px;margin:8px 0;background:var(--card-background-color,#18232e);color:inherit;border:1px solid var(--divider-color,#536274);border-radius:8px;font:inherit}.wi-reporting pre{white-space:pre-wrap;overflow-wrap:anywhere}.wi-reporting .actions{display:flex;flex-wrap:wrap;gap:10px}.wi-reporting button{min-height:44px;padding:10px 14px;font:inherit}.wi-reporting button:disabled{opacity:.55}</style>';

export function reportingForm(snapshot) {
  return `${REPORTING_STYLE}<section class="wi-reporting"><h3>Optional error reporting</h3><p>${REPORTING_DISCLOSURE}</p>
    <p>Reports also include fixed error explanations from the published code, exception causes, module/function/line locations, and HTTP status, OS error or process exit codes when the failure provides them. Absolute paths, local variables, source lines and raw exception messages are excluded.</p>
    ${snapshot.consent_review_required?'<p role="alert"><strong>Reporting is paused.</strong> Review the updated diagnostic details, installation ID and software versions before choosing whether to resume reporting. Your previous consent did not include all these fields.</p>':''}
    <p>Reporting is ${snapshot.config.enabled?'on':'off'}. ${escapeHtml(snapshot.last_result)}.</p>
    ${reportingIdentity(snapshot)}
    <p>Reports go to <strong>${escapeHtml(snapshot.config.endpoint)}</strong>.</p>
    <details><summary>Example report and destination options</summary><pre>${escapeHtml(JSON.stringify(snapshot.preview,null,2))}</pre><p>This is an example, not a report from your installation. Only accept a destination you trust.</p>
    <label>Reporting destination<input id="reporting-endpoint" type="url" autocomplete="off" spellcheck="false" value="${escapeHtml(snapshot.config.endpoint)}" placeholder="https://your-domain/v1/errors"></label></details>
    <p>Accept turns on optional error reporting. Decline turns it off. Next, choose whether to share outage reports. Your weather alerts work either way. The diagnostic audit log is available on the main Weather Intelligence page.</p>
    <div class="actions"><button id="reporting-accept" class="primary">Accept</button><button id="reporting-decline">Decline</button></div>
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
    bindReportingIdentity(root,snapshot);
    root.querySelector('#reporting-accept').onclick=()=>commit(true);
    root.querySelector('#reporting-decline').onclick=()=>commit(false);
  };
  let saving=false;
  const commit=async enabled=>{
    if(saving)return;
    endpoint=root.querySelector('#reporting-endpoint').value.trim();
    if(enabled&&!endpoint){root.querySelector('#reporting-result').textContent='Enter the reporting destination first.';return;}
    if(endpoint){try{endpoint=new URL(endpoint).href;}catch{root.querySelector('#reporting-result').textContent='Enter a valid reporting destination.';return;}}
    saving=true;
    root.querySelectorAll('button,input').forEach(node=>node.disabled=true);
    try{
      snapshot=await save({expected_config:snapshot.config,endpoint,enabled,
        consent:enabled,consent_endpoint:enabled?endpoint:'',policy_version:snapshot.config.policy_version});
      endpoint=snapshot.config.endpoint;
      if(openOutages)await openOutages();
      else {draw();root.querySelector('#reporting-result').textContent='Reporting settings saved.';}
    }catch{
      root.querySelector('#reporting-result').textContent='Could not save reporting settings. Check the destination or reopen this screen.';
      root.querySelectorAll('button,input').forEach(node=>node.disabled=false);
    }finally{saving=false;}
  };
  draw();
}
