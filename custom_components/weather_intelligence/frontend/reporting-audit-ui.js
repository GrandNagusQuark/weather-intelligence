const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const RESULTS={prepared:'Prepared. Delivery is not confirmed.',accepted:'Receiver confirmed acceptance.',
  not_accepted:'Receiver did not confirm acceptance.',unconfirmed:'Delivery outcome is unknown.'};

export function auditReportTitle(report) {
  if(report.error_code)return report.error_code;
  if(report.source&&report.state)return `Outage contribution: ${report.source} · ${report.state}`;
  return 'Diagnostic report';
}

export function auditMarkup(snapshot) {
  return `<section class="wi-reporting"><h3>Reporting history</h3>
    <p>This local audit shows the exact sanitized report prepared for the developer and its delivery result. Entries are kept for ${escapeHtml(snapshot.retention_days)} days. A confirmed receipt does not mean the developer has read it. There are no raw logs here.</p>
    ${snapshot.entries.map(row=>`<article style="border-top:1px solid var(--divider-color,#536274);padding:14px 0">
      <strong>${escapeHtml(auditReportTitle(row.report))}</strong><p>${escapeHtml(row.attempted_at)}<br>${escapeHtml(RESULTS[row.result]||'Unknown outcome')}<br>Destination: ${escapeHtml(row.endpoint)}</p>
      <details><summary>View the exact report fields</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${escapeHtml(JSON.stringify(row.report,null,2))}</pre></details></article>`).join('')}
    ${snapshot.entries.length?'':'<p>No reporting attempts in this period.</p>'}
    <div class="actions"><button id="audit-previous" ${snapshot.offset===0?'disabled':''}>Previous</button><span>${snapshot.total ? `${snapshot.offset+1} to ${snapshot.offset+snapshot.entries.length} of ${snapshot.total}` : '0 entries'}</span><button id="audit-next" ${snapshot.offset+snapshot.limit>=snapshot.total?'disabled':''}>Next</button><button id="audit-back">Back to reporting settings</button></div></section>`;
}

export async function mountReportingAudit(root,load,back,offset=0) {
  root.textContent='Loading reporting history…';
  try {
    const snapshot=await load(offset);
    root.innerHTML=auditMarkup(snapshot);
    root.querySelector('#audit-previous').onclick=()=>mountReportingAudit(root,load,back,Math.max(0,offset-snapshot.limit));
    root.querySelector('#audit-next').onclick=()=>mountReportingAudit(root,load,back,offset+snapshot.limit);
    root.querySelector('#audit-back').onclick=back;
  } catch {
    root.innerHTML='<p role="alert">Reporting history could not be loaded. Try again later.</p><button id="audit-back">Back to reporting settings</button>';
    root.querySelector('#audit-back').onclick=back;
  }
}
