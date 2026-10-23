import {ALERT_CHOICE_SCREEN} from './alert-setup.js?v=23';
import {ALERT_SELECTION_STYLE,installTierCards,renderSelectableAlerts} from './onboarding-alert-ui.js?v=8';
import {alertRiskPresentation} from './onboarding-flow.js?v=19';
import {profileAlertEvents,tierEvents,tierState,toggleProfileTier,renderProfileAlertGrid} from './profile-alert-choices.js?v=4';
import {ProfileDndEditor} from './profile-dnd-editor.js?v=4';
import {marineNearbyControls,installMarineNearby,renderMarineNearby} from './marine-preferences-ui.js?v=2';
import {MARINE_BETA_NOTICE} from './marine-beta.js?v=2';

const EDITOR_STYLE=`
  :host{font:inherit;color:var(--primary-text-color)}[hidden]{display:none!important}*{box-sizing:border-box}
  dialog{width:min(760px,calc(100% - 28px));max-height:calc(100dvh - 40px);overflow:auto;padding:24px;border:1px solid var(--divider-color,#385267);border-radius:16px;background:var(--card-background-color,#132334);color:inherit}dialog::backdrop{background:#0009}
  h2{font-size:24px;margin:0}h3{font-size:17px;margin:18px 0 10px}p{line-height:1.5}small{display:block;margin-top:6px;color:var(--secondary-text-color)}
  button,input{font:inherit;color:inherit;background:var(--card-background-color,#162536);border:1px solid var(--divider-color,#466079);border-radius:10px;padding:12px;min-height:44px}button{cursor:pointer}button:focus-visible,input:focus-visible{outline:3px solid var(--primary-color,#67e8f9);outline-offset:2px}button:disabled{cursor:default;opacity:.6}input{width:100%}
  .editor-heading,.user-step-nav{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}.user-step-nav{margin:20px 0 0}.primary{background:var(--primary-color,#67e8f9);color:var(--text-primary-color,#082331);font-weight:600}.editor-note{padding:12px;border:1px solid var(--divider-color);border-radius:8px}
  .hazard-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.hazard-grid button{text-align:start;overflow-wrap:anywhere;min-width:0}.hazard-grid small{font-size:12px}.hazard-scroll{max-height:50dvh;overflow-y:auto;padding:2px 4px 8px;overscroll-behavior:contain}.editor-status{min-height:1.4em}
  .alert-descriptions{display:grid;gap:12px}.alert-explanation{padding:16px;border:1px solid var(--divider-color,#466079);border-radius:12px}.welcome-copy{text-align:center;line-height:1.5}.welcome-copy h2{margin:16px 0}.welcome-actions{display:grid;gap:10px}.weather-logo{display:block;width:64px;height:64px;margin:6px auto 12px}.tier-card-title{text-align:start}.tier-card-copy{line-height:1.5}.setup-choice[aria-pressed="true"]{outline:2px solid var(--primary-color,#67e8f9)}
  @media(max-width:560px){dialog{padding:18px}.hazard-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:340px){.hazard-grid{grid-template-columns:1fr}}
`;

export class ProfileAlertEditor {
  constructor(parent,{escape}) {
    this.escape=escape;
    this.host=parent.ownerDocument.createElement('div');parent.append(this.host);
    this.root=this.host.attachShadow({mode:'open'});
    this.root.innerHTML=`<style>${EDITOR_STYLE}${ALERT_SELECTION_STYLE}</style>
      <dialog id="profile-alert-grid" aria-labelledby="profile-grid-heading"><div class="editor-heading"><h2 id="profile-grid-heading">Notification settings</h2><button id="profile-grid-cancel">Cancel</button></div><p id="profile-edit-notice" class="editor-note" role="note" hidden>Changes you save to another user’s settings will automatically notify that user. The notice includes your administrator name.</p><p id="profile-device-name"></p><div id="profile-devices"></div><section id="profile-dnd-settings"><button id="profile-dnd-open" aria-haspopup="dialog">Edit Do Not Disturb bypass</button><small id="profile-dnd-state"></small></section><label id="hazard-filter-label">Find a hazard<input id="hazard-filter" type="search"></label><div id="profile-grid-content" class="hazard-scroll"></div><p id="profile-edit-status" class="editor-status" role="status"></p><div class="user-step-nav"><span>Changes apply only when saved.</span><button id="profile-grid-apply" class="primary">Save changes</button></div></dialog>
      <dialog id="profile-alert-hazard" aria-labelledby="alert-choice-heading"><img class="weather-logo" src="/weather_intelligence_static/weather-logo.svg" alt="Weather Intelligence">${ALERT_CHOICE_SCREEN}</dialog>`;
    this.root.querySelector('#profile-dnd-settings').insertAdjacentHTML('beforeend','<button id="profile-marine-open" aria-haspopup="dialog">Marine settings — Early state</button>');
    const marineDialog=this.host.ownerDocument.createElement('dialog');marineDialog.id='profile-marine-dialog';marineDialog.setAttribute('aria-label','Marine notification settings');
    marineDialog.innerHTML=`<h2>Marine notifications — Early state</h2>${MARINE_BETA_NOTICE}${marineNearbyControls('editor')}<div class="user-step-nav"><button id="profile-marine-cancel">Cancel</button><button id="profile-marine-apply" class="primary">Apply to settings draft</button></div>`;this.root.append(marineDialog);
    this.root.querySelector('#profile-marine-open').onclick=()=>{this.marineDialogDraft={...this.marineNearby};renderMarineNearby(marineDialog,this.marineDialogDraft,'editor');marineDialog.showModal();};
    this.root.querySelector('#profile-marine-cancel').onclick=()=>marineDialog.close();
    this.root.querySelector('#profile-marine-apply').onclick=()=>{if(!marineDialog.querySelector('[data-marine-radius]').reportValidity())return;this.marineNearby={...this.marineDialogDraft};marineDialog.close();this.renderGrid();};
    installMarineNearby(this.root,context=>context==='editor'?this.marineDialogDraft:this.pageNearby,(context,choices)=>{
      if(context==='editor'){this.marineDialogDraft=choices;renderMarineNearby(marineDialog,choices,'editor');}
      else{this.pageNearby=choices;this.renderPage();}
    });
    this.grid=this.root.querySelector('#profile-alert-grid');this.popup=this.root.querySelector('#profile-alert-hazard');
    this.dndEditor=new ProfileDndEditor(this.root);
    installTierCards(this.popup,tier=>{toggleProfileTier(this.page,tier,this.pageSelected,this.pageReviewed);this.renderPage();});
    this.popup.querySelector('#alert-choice-page').hidden=false;
    this.popup.querySelector('#alert-choice-back').onclick=()=>this.popup.close();
    this.popup.querySelector('#alert-choice-next').onclick=()=>{
      const changed=this.selected.size!==this.pageSelected.size||[...this.selected].some(event=>!this.pageSelected.has(event));
      this.selected=this.pageSelected;
      if(changed&&this.dndChanges)this.dndNeedsReview=true;
      for(const event of this.pageReviewed)this.reviewed.add(event);
      this.marineMode=this.pageMarineMode;this.marineNearby={...this.pageNearby};this.popup.close();this.renderGrid();
    };
    this.popup.querySelectorAll('[data-marine-mode]').forEach(button=>button.onclick=()=>{this.pageMarineMode=button.dataset.marineMode;this.renderPage();});
    this.root.querySelector('#profile-grid-cancel').onclick=()=>this.grid.close();
    this.grid.addEventListener('cancel',event=>{if(this.busy)event.preventDefault();});
    this.root.querySelector('#hazard-filter').oninput=()=>this.renderGrid();
    this.root.querySelector('#profile-grid-apply').onclick=()=>this.apply();
    this.root.querySelector('#profile-dnd-open').onclick=()=>this.openDnd();
  }

  open(profile,pages,choices,{apply,applyLabel='Apply to profile',notice=false,dndCatalog=[],dndSetup='unverified'}) {
    this.profile=structuredClone(profile);this.pages=pages;this.choices=choices;this.onApply=apply;
    this.dndCatalog=dndCatalog;this.dndSetup=dndSetup;this.notice=notice;this.dndChanges=null;this.dndNeedsReview=false;
    this.marineNearby={marine_nearby_enabled:profile.marine_nearby_enabled===true,marine_nearby_miles:profile.marine_nearby_miles??10};
    this.selected=new Set(profileAlertEvents(profile,choices));this.reviewed=new Set();this.marineMode=profile.marine_warning_mode || 'always';
    this.root.querySelector('#profile-devices').innerHTML='';
    this.root.querySelector('#profile-device-name').textContent=profile.name || 'Selected device';
    this.root.querySelector('#profile-edit-notice').hidden=!notice;
    this.root.querySelector('#profile-grid-apply').textContent=applyLabel;this.root.querySelector('#profile-grid-apply').hidden=false;
    this.root.querySelector('#hazard-filter-label').hidden=false;this.root.querySelector('#hazard-filter').value='';
    this.root.querySelector('#profile-dnd-settings').hidden=false;
    this.root.querySelector('#profile-edit-status').textContent='';this.renderGrid();
    if(!this.grid.open)this.grid.showModal();
  }

  openProfiles(snapshot,save,{initialSection='alerts'}={}) {
    const choose=profile=>{
      this.open(profile,snapshot.pages,snapshot.choices,{apply:save,applyLabel:'Save changes',notice:snapshot.notice_profile_ids.includes(profile.profile_id),dndCatalog:snapshot.dnd_catalog,dndSetup:snapshot.dnd_setup?.[profile.profile_id]});
      if(initialSection==='dnd')this.openDnd();
    };
    if(snapshot.profiles.length===1){choose(snapshot.profiles[0]);return;}
    this.root.querySelector('#profile-device-name').textContent=snapshot.profiles.length?'Choose the device you want to edit.':'No device settings yet. Complete device onboarding first.';
    this.root.querySelector('#profile-devices').innerHTML=`<div class="hazard-grid">${snapshot.profiles.map((profile,index)=>`<button type="button" data-device-index="${index}">${this.escape(profile.name || 'Device')}</button>`).join('')}</div>`;
    this.root.querySelector('#profile-devices').querySelectorAll('[data-device-index]').forEach(button=>button.onclick=()=>choose(snapshot.profiles[Number(button.dataset.deviceIndex)]));
    this.root.querySelector('#profile-grid-content').innerHTML='';this.root.querySelector('#profile-grid-apply').hidden=true;
    this.root.querySelector('#hazard-filter-label').hidden=true;this.root.querySelector('#profile-edit-notice').hidden=true;
    this.root.querySelector('#profile-dnd-settings').hidden=true;
    this.root.querySelector('#profile-edit-status').textContent='';
    if(!this.grid.open)this.grid.showModal();
  }

  renderGrid() {
    const enabled=this.dndChanges?this.dndChanges.dnd_bypass:this.profile.critical_notifications_enabled;
    this.root.querySelector('#profile-dnd-state').textContent=this.dndNeedsReview?'Alert choices changed. Review your DND bypass list again before saving.':`Bypass ${enabled?'on':'off'}${this.dndChanges?' — reviewed draft':''}. Phone settings must also allow it.`;
    this.root.querySelector('#profile-grid-apply').disabled=!!this.dndNeedsReview;
    this.root.querySelector('#profile-grid-content').innerHTML=renderProfileAlertGrid(this.pages,this.selected,this.escape,this.root.querySelector('#hazard-filter').value);
    this.root.querySelector('#profile-grid-content').querySelectorAll('[data-hazard]').forEach(button=>button.onclick=()=>this.openPage(button.dataset.hazard));
  }

  openDnd() {
    const profile={...this.profile,...(this.dndChanges?{critical_notifications_enabled:this.dndChanges.dnd_bypass,dnd_rule_ids:this.dndChanges.dnd_rule_ids,outage_dnd_enabled:this.dndChanges.outage_dnd_enabled}:{})};
    this.dndEditor.open(profile,this.dndCatalog,[...this.selected],{notice:this.notice,setup:this.dndSetup,apply:changes=>{
      this.dndChanges=changes;this.dndNeedsReview=false;this.renderGrid();
    }});
  }

  openPage(id) {
    this.page=this.pages.find(page=>page.id===id);if(!this.page)return;
    this.pageSelected=new Set(this.selected);this.pageReviewed=new Set();this.pageMarineMode=this.marineMode;
    this.pageNearby={...this.marineNearby};
    this.renderPage();this.popup.showModal();
  }

  renderPage() {
    const view={page:this.page,enabled:tierState(this.page,'warning',this.pageSelected)==='on',watch_automatic:this.page.watch_automatic,marine_warning_mode:this.pageMarineMode,...this.pageNearby};
    for(const tier of ['advisory','watch','statement'])view[tier+'_enabled']=tierState(this.page,tier,this.pageSelected)==='on';
    renderSelectableAlerts(this.popup,{alert_path:'choose_all',alert_setup:view},alertRiskPresentation(this.page));
    this.popup.querySelector('#alert-choice-progress').hidden=true;
    this.popup.querySelector('#alert-choice-back').textContent='Cancel';this.popup.querySelector('#alert-choice-next').textContent='Apply choices';
    for(const tier of ['warning','advisory','watch','statement']){
      const panel=tier==='warning'?this.popup.querySelector('#alert-choice-conditions').parentElement:this.popup.querySelector('#alert-'+tier+'-panel');
      if(tierState(this.page,tier,this.pageSelected)==='mixed'){
        panel.setAttribute('aria-pressed','mixed');panel.querySelector('.card-selection').textContent='Mixed choices — unchanged until selected';
      }
      if(tierState(this.page,tier,this.pageSelected)!=='off'&&tierEvents(this.page,tier).some(event=>this.profile.life_safety_events?.includes(event))&&!tierEvents(this.page,tier).some(event=>this.pageReviewed.has(event)))
        panel.querySelector('.card-selection').textContent='Included for life-threatening cases';
    }
  }

  async apply() {
    if(this.busy||this.dndNeedsReview)return;
    this.busy=true;this.root.querySelector('#profile-grid-apply').disabled=true;this.root.querySelector('#profile-grid-cancel').disabled=true;
    try{
      await this.onApply({profile:this.profile,alert_events:[...this.selected],reviewed_event_ids:[...this.reviewed],marine_warning_mode:this.marineMode,...this.marineNearby,...(this.dndChanges||{})});
      this.grid.close();
    }catch(error){this.root.querySelector('#profile-edit-status').textContent=error.message || 'Could not save. Your draft is still here.';}
    finally{this.busy=false;this.root.querySelector('#profile-grid-apply').disabled=false;this.root.querySelector('#profile-grid-cancel').disabled=false;}
  }
}
