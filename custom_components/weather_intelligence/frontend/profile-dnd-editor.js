import {DND_LIST_STYLE,renderDndChoiceButtons,renderDndReviewList} from './onboarding-dnd-ui.js?v=4';
import {MARINE_BETA_NOTICE,isMarinePage} from './marine-beta.js?v=2';

export function receivedDndChoices(catalog,events){
  const received=new Set(events);
  return catalog.filter(rule=>(rule.events || [rule.event]).some(event=>received.has(event)));
}

export class DndPreferencesDraft {
  constructor(profile,catalog,events){
    this.choices=receivedDndChoices(catalog,events);
    this.enabled=!!profile.critical_notifications_enabled;
    this.outageEnabled=profile.outage_dnd_enabled===true;
    this.canEnable=!!profile.automatic_official_warning_notifications&&!!profile.legacy_notify_service;
    this.legacy=!Array.isArray(profile.dnd_rule_ids);
    this.selected=new Set((profile.dnd_rule_ids || []).filter(id=>this.choices.some(rule=>rule.id===id)));
    this.reviewed=false;
  }
  useDefaults(){this.selected=new Set(this.choices.filter(rule=>rule.default).map(rule=>rule.id));this.legacy=false;this.reviewed=false;}
  customize(){if(this.legacy)this.useDefaults();this.reviewed=false;}
  toggle(id){
    const rule=this.choices.find(item=>item.id===id);if(!rule)return;
    if(this.selected.has(id))this.selected.delete(id);
    else{
      for(const other of this.choices)if(other.event===rule.event&&(rule.scope==='all'||other.scope==='all'))this.selected.delete(other.id);
      this.selected.add(id);
    }
    this.reviewed=false;
  }
  setEnabled(enabled){if(enabled&&!this.canEnable)throw new Error('Complete notification setup before enabling bypass.');this.enabled=enabled;this.reviewed=false;}
  review(){if(this.legacy)throw new Error('Choose defaults or customize to replace the legacy policy.');this.reviewed=true;}
  changes(){
    if(!this.reviewed)throw new Error('Review your DND choices before applying.');
    return {dnd_bypass:this.enabled,dnd_rule_ids:this.choices.filter(rule=>this.selected.has(rule.id)).map(rule=>rule.id),dnd_confirmed:true,outage_dnd_enabled:this.enabled&&this.outageEnabled};
  }
}

export class ProfileDndEditor {
  constructor(parent){
    const host=parent.ownerDocument.createElement('div');parent.append(host);this.root=host;
    host.innerHTML=`<style>${DND_LIST_STYLE}.profile-dnd-master{display:flex;align-items:center;gap:10px;margin:16px 0}.profile-dnd-master input{width:auto;min-height:24px}.profile-dnd-options{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.profile-dnd-warning{padding:12px;border:1px solid var(--divider-color);border-radius:8px}.profile-dnd-risk{color:var(--error-color,#ff8c8c);font-weight:600}</style>
      <dialog id="profile-dnd-dialog" aria-labelledby="profile-dnd-heading"><div class="editor-heading"><h2 id="profile-dnd-heading">Do Not Disturb</h2><button id="profile-dnd-cancel">Cancel</button></div>
      <p>Choose which of this device’s enabled alerts may bypass Do Not Disturb. Ordinary alert choices remain separate.</p>
      <p id="profile-dnd-owner-notice" class="editor-note" hidden>Saving changes to another user’s settings will notify that user and include your administrator name.</p>
      <p id="profile-dnd-legacy" class="profile-dnd-warning" hidden>This device uses an older automatic-severity policy. It stays unchanged unless you choose defaults or customize, review, and save a new list.</p>
      <button id="profile-dnd-enabled" class="profile-dnd-master" type="button" aria-pressed="false">Bypass Do Not Disturb — Off</button>
      <p id="profile-dnd-risk" class="profile-dnd-risk" role="note" hidden>Selected alerts will be sent using DND bypass. They may interrupt this user’s phone even during Do Not Disturb.</p>
      <button id="profile-outage-enabled" type="button" aria-pressed="false">Outage bypass during severe weather: Off</button>
      <p>A corroborated NWS access problem may bypass Do Not Disturb only when the last available official Tornado or Severe Thunderstorm watch or warning covers a fresh current location and applies now or within two hours. The alert must be unexpired and confirmed within the last two hours. Newer changes may be unavailable during the outage. A daily outlook alone does not qualify. Phone permission is still required.</p>
      <p id="profile-dnd-setup" role="status"></p>
      <p id="profile-dnd-unavailable" hidden>Complete this device’s notification setup before enabling bypass. You can still edit its list or turn bypass off.</p>
      <div id="profile-dnd-beta" hidden>${MARINE_BETA_NOTICE}</div>
      <div id="profile-dnd-controls" class="profile-dnd-options"><button id="profile-dnd-defaults">Use default choices</button><button id="profile-dnd-customize">Customize bypass choices</button></div>
      <div id="profile-dnd-list" class="dnd-scroll dnd-options" role="group" aria-label="Device DND bypass choices"></div>
      <div id="profile-dnd-review" hidden><p id="profile-dnd-confirmation"></p><div id="profile-dnd-summary" class="dnd-scroll"></div><p>Phone permissions and system settings must also allow bypass. Applying here updates the editor draft; Save changes commits it.</p></div>
      <div class="user-step-nav"><button id="profile-dnd-back" hidden>Back to choices</button><button id="profile-dnd-next" class="primary">Review choices</button></div></dialog>`;
    this.dialog=host.querySelector('#profile-dnd-dialog');
    const q=selector=>host.querySelector(selector);this.q=q;
    q('#profile-dnd-cancel').onclick=()=>this.dialog.close();
    q('#profile-dnd-defaults').onclick=()=>{this.draft.useDefaults();this.render();};
    q('#profile-dnd-customize').onclick=()=>{this.draft.customize();this.render();};
    q('#profile-dnd-enabled').onclick=()=>{this.draft.setEnabled(!this.draft.enabled);this.render();};
    q('#profile-outage-enabled').onclick=()=>{this.draft.outageEnabled=!this.draft.outageEnabled;this.draft.reviewed=false;this.render();};
    q('#profile-dnd-back').onclick=()=>{this.draft.reviewed=false;this.render();};
    q('#profile-dnd-next').onclick=()=>{
      if(!this.draft.reviewed){this.draft.review();this.render();}
      else{this.onApply(this.draft.changes());this.dialog.close();}
    };
  }
  open(profile,catalog,events,{apply,notice=false,setup='unverified'}){
    this.draft=new DndPreferencesDraft(profile,catalog,events);this.onApply=apply;
    this.setup=setup;
    this.q('#profile-dnd-owner-notice').hidden=!notice;this.render();this.dialog.showModal();
  }
  render(focusRule=null){
    const model=this.draft,review=model.reviewed;
    this.q('#profile-dnd-enabled').setAttribute('aria-pressed',String(model.enabled));
    this.q('#profile-dnd-enabled').textContent=`Bypass Do Not Disturb — ${model.enabled?'On':'Off'}`;
    this.q('#profile-dnd-enabled').disabled=review||(!model.canEnable&&!model.enabled);
    this.q('#profile-dnd-risk').hidden=!model.enabled;
    this.q('#profile-outage-enabled').setAttribute('aria-pressed',String(model.enabled&&model.outageEnabled));
    this.q('#profile-outage-enabled').textContent=`Outage bypass during severe weather: ${model.enabled&&model.outageEnabled?'On':'Off'}`;
    this.q('#profile-outage-enabled').disabled=review||!model.enabled;
    this.q('#profile-dnd-setup').textContent=this.setup==='user_confirmed'?'A previous bypass test was confirmed by the user. Current phone permissions cannot be verified remotely.':this.setup==='incomplete'?'DND bypass setup not completed. Check this phone’s notification settings and complete its bypass test.':'DND bypass setup unverified. Check this phone’s Critical Alerts or notification-channel permissions; this switch cannot grant them.';
    this.q('#profile-dnd-legacy').hidden=!model.legacy;
    this.q('#profile-dnd-unavailable').hidden=model.canEnable;
    this.q('#profile-dnd-controls').hidden=review;
    this.q('#profile-dnd-list').hidden=review||model.legacy;
    this.q('#profile-dnd-beta').hidden=!model.choices.some(rule=>isMarinePage({id:rule.event}));
    const list=this.q('#profile-dnd-list'),scroll=list.scrollTop;
    list.innerHTML=renderDndChoiceButtons(model.choices,model.selected);list.scrollTop=scroll;
    list.querySelectorAll('[data-dnd-rule]').forEach(button=>{
      button.onclick=()=>{model.toggle(button.dataset.dndRule);this.render(button.dataset.dndRule);};
      if(button.dataset.dndRule===focusRule)button.focus({preventScroll:true});
    });
    this.q('#profile-dnd-review').hidden=!review;
    const selected=model.choices.filter(rule=>model.selected.has(rule.id));
    this.q('#profile-dnd-confirmation').textContent=(model.enabled&&selected.length?'After saving, these selected notifications will request DND bypass. The phone must also permit it; all other notifications use normal delivery.':'No selected hazard notifications will request DND bypass after you save.')+(model.enabled&&model.outageEnabled?' Corroborated outage notices will also request bypass during locally verified severe weather now or within two hours.':' Outage notices will not request bypass.');
    this.q('#profile-dnd-summary').innerHTML=renderDndReviewList(model.enabled?selected:[]);
    this.q('#profile-dnd-back').hidden=!review;
    this.q('#profile-dnd-next').disabled=model.legacy;
    this.q('#profile-dnd-next').textContent=review?'Apply to settings draft':'Review choices';
  }
}
