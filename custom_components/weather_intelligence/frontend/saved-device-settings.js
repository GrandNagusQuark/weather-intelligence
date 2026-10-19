// Portable preferences stay on Home Assistant; enrollment is never copied.
const escape_text = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));

export function saved_setting_options(settings = []) {
  return settings.map(item => `<option value="${escape_text(item.id)}">${escape_text(item.name)}</option>`).join('');
}

export function installSavedDeviceSettings(panel, {onboarding = false} = {}) {
  const root = panel.shadowRoot;
  const doc = root.ownerDocument;
  const template = doc.createElement('template');
  template.innerHTML = `<style>
    #saved-device-settings-manager{width:min(620px,calc(100% - 32px));max-height:85dvh;overflow:auto;border:1px solid var(--divider-color,#385267);border-radius:16px;padding:24px;background:var(--card-background-color,#132334);color:var(--primary-text-color)}
    #saved-device-settings-manager::backdrop{background:#0009}.saved-settings-controls{display:grid;gap:12px;max-width:470px;margin:0 auto}.saved-settings-controls label{display:grid;gap:6px}.saved-settings-controls select,.saved-settings-controls input{box-sizing:border-box;width:100%;font:inherit;min-height:44px;padding:9px;border:1px solid var(--divider-color,#466079);border-radius:8px;background:var(--card-background-color,#162536);color:inherit}.saved-settings-actions{display:flex;flex-wrap:wrap;gap:8px}.saved-settings-actions button{min-height:44px}.saved-settings-note{font-size:13px;line-height:1.5;color:var(--secondary-text-color)}
  </style><dialog id="saved-device-settings-manager" aria-labelledby="saved-settings-manager-heading">
    <div class="dialog-heading"><h2 id="saved-settings-manager-heading">Saved device settings</h2><button id="saved-settings-close">Close</button></div>
    <p class="saved-settings-note">Settings stay in Home Assistant. Each device's latest settings update automatically. Save a named version to keep it unchanged.</p>
    <div class="saved-settings-controls"><label>Saved settings<select id="saved-settings-version"></select></label>
      <label>Name for a saved version<input id="saved-settings-name" maxlength="80" autocomplete="off"></label>
      <div class="saved-settings-actions"><button id="saved-settings-save">Save named version</button><button id="saved-settings-rename">Rename</button><button id="saved-settings-delete">Delete</button></div>
      <label>Device to restore settings to<select id="saved-settings-target"></select></label>
      <button id="saved-settings-restore" class="primary">Restore settings and review</button>
      <p class="saved-settings-note">Copying or restoring preferences does not copy phone identity, permissions, or notification enrollment.</p>
      <p id="saved-settings-manager-status" role="status"></p>
    </div></dialog>`;
  root.append(template.content);
  const query = selector => root.querySelector(selector);
  const entry = doc.createElement('button');
  entry.id = 'manage-saved-device-settings';
  entry.textContent = 'Saved device settings';
  if (onboarding) {
    entry.className = 'setup-back';
    query('#start-onboarding').after(entry);
    const screen = doc.createElement('section');
    screen.id = 'saved-device-settings-page';
    screen.hidden = true;
    screen.setAttribute('aria-labelledby', 'saved-device-settings-heading');
    screen.innerHTML = `<div class="welcome-copy"><h2 id="saved-device-settings-heading">Use saved settings?</h2><p id="saved-device-settings-context"></p></div>
      <div class="saved-settings-controls"><label>Copy settings from<select id="copy-saved-settings-select"></select></label>
      <p id="copy-saved-settings-empty" class="saved-settings-note">No saved device settings yet.</p>
      <button id="copy-saved-settings-apply" class="primary">Use saved settings</button><button id="copy-saved-settings-fresh">Start fresh</button></div>
      <button id="copy-saved-settings-back" class="setup-back">Back</button>`;
    query('#welcome-onboarding').insertBefore(screen, query('#welcome-status'));
    query('#copy-saved-settings-apply').onclick = () => panel._saveOnboardingProgress({workflow_action:'saved_settings_apply', saved_settings_id:query('#copy-saved-settings-select').value, saved_settings_revision:panel._config.onboarding.saved_settings_revision});
    query('#copy-saved-settings-fresh').onclick = () => panel._saveOnboardingProgress({workflow_action:'saved_settings_fresh'});
    query('#copy-saved-settings-back').onclick = () => panel._saveOnboardingProgress({workflow_action:'saved_settings_back'});
  } else {
    query('[data-group="general"]').append(entry);
  }
  let manager_view = {settings:[], devices:[]};
  let busy = false;
  function render_manager(preferred_id) {
    const selected_id = preferred_id || query('#saved-settings-version').value;
    const target_id = query('#saved-settings-target').value || panel._config.onboarding?.selected_device_id;
    query('#saved-settings-version').innerHTML = saved_setting_options(manager_view.settings) || '<option value="">No saved settings yet</option>';
    if (manager_view.settings.some(item => item.id === selected_id)) query('#saved-settings-version').value = selected_id;
    query('#saved-settings-target').innerHTML = manager_view.devices.map(item => `<option value="${escape_text(item.id)}">${escape_text(item.name)}</option>`).join('') || '<option value="">No available devices</option>';
    if (manager_view.devices.some(item => item.id === target_id)) query('#saved-settings-target').value = target_id;
    const selected = manager_view.settings.find(item => item.id === query('#saved-settings-version').value);
    query('#saved-settings-save').disabled = !selected;
    query('#saved-settings-rename').disabled = !selected || selected.automatic;
    query('#saved-settings-delete').disabled = !selected || selected.automatic;
    query('#saved-settings-restore').disabled = !selected || !manager_view.devices.length;
  }
  async function manage(action) {
    if (busy) return;
    busy = true;
    query('#saved-settings-manager-status').textContent = 'Loading…';
    try {
      const result = await panel._hass.callWS({type:'weather_intelligence/device_settings', action,
        ...(action === 'list' ? {} : {expected_revision:manager_view.revision, expected_onboarding_revision:manager_view.onboarding_revision,
          settings_id:query('#saved-settings-version').value, device_id:query('#saved-settings-target').value, name:query('#saved-settings-name').value})});
      if (result.onboarding_snapshot) {
        query('#saved-device-settings-manager').close();
        panel._config = {...panel._config, ...result.onboarding_snapshot};
        panel._profilesDirty = false;
        panel._renderWelcome();
        panel._openWelcome();
        return;
      }
      manager_view = result;
      render_manager();
      query('#saved-settings-manager-status').textContent = action === 'list' ? '' : 'Saved.';
    } catch (error) {
      query('#saved-settings-manager-status').textContent = error.message || 'Could not update saved settings.';
    } finally { busy = false; }
  }
  entry.onclick = () => {query('#saved-device-settings-manager').showModal();manage('list');};
  query('#saved-device-settings-manager').addEventListener('close', async () => {
    try {
      const snapshot = await panel._hass.callWS({type:'weather_intelligence/onboarding/get'});
      for (const key of ['onboarding','actor','target_user','setup_devices','setup_users']) panel._config[key] = snapshot[key];
      if (root.querySelector('#welcome-onboarding')) panel._onboardingFlow?.render();
    } catch (_error) { /* The next authenticated setup save still checks revisions. */ }
  });
  query('#saved-settings-close').onclick = () => query('#saved-device-settings-manager').close();
  query('#saved-settings-version').onchange = () => render_manager();
  query('#saved-settings-save').onclick = () => manage('save_named');
  query('#saved-settings-rename').onclick = () => manage('rename');
  query('#saved-settings-delete').onclick = () => {if (confirm('Delete this saved version? This cannot be undone.')) manage('delete');};
  query('#saved-settings-restore').onclick = () => {
    if (panel._profilesDirty && !confirm('Discard unsaved user-setting edits before restoring saved settings?')) return;
    manage('restore');
  };
  return {render(onboarding_state, device_names) {
    if (!onboarding) return;
    const settings = onboarding_state.saved_device_settings || [];
    const selected_id = query('#copy-saved-settings-select').value;
    query('#copy-saved-settings-select').innerHTML = saved_setting_options(settings) || '<option value="">No saved settings</option>';
    if (settings.some(item => item.id === selected_id)) query('#copy-saved-settings-select').value = selected_id;
    query('#copy-saved-settings-select').disabled = !settings.length;
    query('#copy-saved-settings-apply').disabled = !settings.length;
    query('#copy-saved-settings-empty').hidden = !!settings.length;
    query('#saved-device-settings-context').textContent = onboarding_state.device_count === 'multiple' && onboarding_state.multiple_settings === 'shared' ? `One saved set will apply to all selected devices: ${device_names}.` : device_names;
  }};
}
