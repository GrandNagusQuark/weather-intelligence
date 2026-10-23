const validId=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);

export function reportingIdentity(snapshot) {
  if(!validId(snapshot.installation_id))return '<section class="reporting-identity"><h4>Your installation ID</h4><p>No installation ID has been generated. One is created only after you accept error reporting.</p></section>';
  return `<section class="reporting-identity"><h4>Your installation ID</h4><p>This random number groups reports from this installation. Error reports and optional outage contributions use the same number.</p>
    <textarea id="reporting-installation-id" aria-label="Your installation ID" readonly rows="2" style="box-sizing:border-box;width:100%;font:inherit;resize:none;overflow-wrap:anywhere">${snapshot.installation_id}</textarea>
    <button id="reporting-copy-id" type="button">Copy ID</button><p id="reporting-copy-result" role="status"></p></section>`;
}

export function bindReportingIdentity(root,snapshot) {
  if(!validId(snapshot.installation_id))return;
  root.querySelector('#reporting-copy-id').onclick=async()=>{
    const result=root.querySelector('#reporting-copy-result');
    try {
      await globalThis.navigator.clipboard.writeText(snapshot.installation_id);
      result.textContent='Installation ID copied.';
    } catch {
      root.querySelector('#reporting-installation-id').select();
      result.textContent='ID selected. Use your device’s Copy option to copy it.';
    }
  };
}
