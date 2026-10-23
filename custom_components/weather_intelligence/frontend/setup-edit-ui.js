// One entry for changes to existing devices. Opening an editor never saves.
export function installExistingSetup(panel,{copySettings,back}) {
  const root=panel.shadowRoot,doc=root.ownerDocument,section=doc.createElement('section');
  section.id='edit-existing-page';section.hidden=true;
  section.setAttribute('aria-labelledby','edit-existing-heading');
  section.innerHTML=`<div class="welcome-copy"><h2 id="edit-existing-heading">Choose a device</h2><p id="existing-device-context">Keep your existing setup and change just what you need.</p></div>
    <div id="existing-device-picker" class="welcome-actions"></div>
    <div id="existing-setup-actions" class="welcome-actions" hidden>
      <button class="setup-choice" data-existing-action="alerts"><strong>Weather alerts</strong><span>Choose alerts for a saved device or an unfinished setup.</span></button>
      <button class="setup-choice" data-existing-action="dnd"><strong>Notification settings</strong><span>Review Do Not Disturb bypass and marine notification choices.</span></button>
      <button class="setup-choice" data-existing-action="mobile"><strong>Mobile alert permissions</strong><span>Review phone permissions and sound setup.</span></button>
      <button class="setup-choice" data-existing-action="copy"><strong>Use saved settings on another device</strong><span>Copy preferences, then review that device's notification setup.</span></button>
      <button class="setup-choice" data-existing-action="remove"><strong>Remove an enrolled device</strong><span>Stop Weather Intelligence delivery to a device.</span></button>
    </div>
    <p id="existing-setup-status" role="status"></p><button id="existing-setup-back" class="setup-back">Back</button>`;
  root.querySelector('#welcome-onboarding').insertBefore(section,root.querySelector('#welcome-status'));
  const q=selector=>section.querySelector(selector);
  let busy=false,selected=null,snapshot=null,generation=0;
  function choose(profile){
    if(profile.unfinished_setup){
      return run(async()=>{
        const saved=await panel._hass.callWS({type:'weather_intelligence/onboarding/get',...profile.unfinished_setup});
        panel._config={...panel._config,...saved};
        panel._showSetupStage(saved.onboarding.stage);
      });
    }
    selected=profile;q('#existing-device-picker').hidden=true;q('#existing-setup-actions').hidden=false;
    q('#edit-existing-heading').textContent='What would you like to change?';
    q('#existing-device-context').textContent=profile.name || 'Selected device';
    q('#existing-setup-status').textContent='';
  }
  function showDevices(){
    selected=null;q('#existing-setup-actions').hidden=true;q('#existing-device-picker').hidden=false;
    q('#edit-existing-heading').textContent='Choose a device';
    q('#existing-device-context').textContent=panel._config.actor.is_admin?'Choose any household device, including an unfinished setup.':'Choose the device you want to edit.';
    q('#existing-setup-status').textContent=snapshot?.profiles.length?'':'No device setup is saved yet. Choose Quick setup or Custom setup to select a device.';
    q('#existing-device-picker').innerHTML=(snapshot?.profiles||[]).map((profile,index)=>`<button class="setup-choice" data-existing-device="${index}">${panel._escape(profile.name || 'Device')}</button>`).join('');
    q('#existing-device-picker').querySelectorAll('[data-existing-device]').forEach(button=>button.onclick=()=>choose(snapshot.profiles[Number(button.dataset.existingDevice)]));
  }
  async function reset(){
    const current=++generation;snapshot=null;showDevices();q('#existing-setup-status').textContent='Loading saved devices…';
    try{
      const reply=await panel._hass.callWS({type:'weather_intelligence/preferences/get'});
      if(current!==generation)return;
      const unfinished=reply.unfinished_setups||[],pending=new Set(unfinished.map(item=>item.companion_device_id).filter(Boolean));
      snapshot={...reply,profiles:[...reply.profiles.filter(profile=>!pending.has(profile.companion_device_id)),...unfinished]};showDevices();
    }catch(error){if(current===generation)q('#existing-setup-status').textContent=error.message || 'Could not load devices. Go back and try again.';}
  }
  async function run(callback){
    if(busy)return;
    busy=true;section.querySelectorAll('button').forEach(button=>button.disabled=true);
    try{await callback();}catch(error){q('#existing-setup-status').textContent=error.message || 'Could not open these settings. Try again.';}
    finally{busy=false;section.querySelectorAll('button').forEach(button=>button.disabled=false);}
  }
  section.querySelectorAll('[data-existing-action]').forEach(button=>button.onclick=()=>run(async()=>{
    const action=button.dataset.existingAction;
    if(!selected)return;
    if(action==='copy'){copySettings();return;}
    if(action==='alerts'||action==='dnd'){
      panel._alertEditor.openProfiles({...snapshot,profiles:[selected]},draft=>panel._saveExistingAlertPreferences(draft),{initialSection:action});
    }else if(action==='mobile')await panel._openMobilePermissions(selected);
    else if(action==='remove'){
      if(!confirm(`Remove ${selected.name || 'this device'} from Weather Intelligence? Its saved preferences will remain available, but delivery to this device will stop.`))return;
      await panel._hass.callWS({type:'weather_intelligence/preferences/remove',profile_id:selected.profile_id,expected_profile:selected});
      root.querySelector('#welcome-onboarding').close();await panel._load();
    }
  }));
  q('#existing-setup-back').onclick=()=>selected?showDevices():back();
  return {render:reset};
}
