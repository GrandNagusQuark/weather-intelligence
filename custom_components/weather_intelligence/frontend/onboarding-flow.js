// Live controller: all progress comes from the authenticated, revisioned HA API.
import {GUIDED_QUESTIONS,installGuidedSetup} from './onboarding-guided-ui.js?v=7';
import {installAlertSelection,renderSelectableAlerts} from './onboarding-alert-ui.js?v=8';
import {installDndSetup,renderDndSetup} from './onboarding-dnd-ui.js?v=4';
import {installSavedDeviceSettings} from './saved-device-settings.js?v=2';
import {installExistingSetup} from './setup-edit-ui.js?v=3';
import {installNotificationSetup} from './onboarding-notifications-ui.js?v=8';
import {installMarineNearby,renderMarineNearby} from './marine-preferences-ui.js?v=2';

const STAGES={welcome:'welcome-page',choice:'setup-choice-page',device_setup:'device-setup-page',target_device_setup:'device-setup-page',accounts:'setup-users-page',single_device:'single-device-page',multiple_settings:'multiple-device-settings-page',multiple_devices:'multiple-device-select-page',single_device_setup:'single-device-setup-page',intro:'alert-introduction',alert_choices:'alert-choice-page',guided:'guided-question-page',recommendations:'recommendations-page',guided_marine:'guided-marine-page',alert_dnd:'alert-dnd-page',notification_setup:'notification-setup-page'};
const HEADINGS={welcome:'welcome-heading',choice:'setup-choice-heading',device_setup:'device-setup-heading',target_device_setup:'device-setup-heading',accounts:'setup-users-heading',single_device:'single-device-heading',multiple_settings:'multiple-device-settings-heading',multiple_devices:'multiple-device-select-heading',single_device_setup:'single-device-setup-heading',intro:'alert-introduction-heading',alert_choices:'alert-choice-heading',guided:'guided-question-heading',recommendations:'recommendations-heading',guided_marine:'guided-marine-heading',alert_dnd:'alert-dnd-heading',notification_setup:'notification-setup-heading'};
Object.assign(STAGES,{dnd_options:'dnd-options-page',dnd_customize:'dnd-customize-page',dnd_confirm:'dnd-confirm-page'});
STAGES.edit_existing='edit-existing-page';HEADINGS.edit_existing='edit-existing-heading';
Object.assign(HEADINGS,{dnd_options:'dnd-options-heading',dnd_customize:'dnd-customize-heading',dnd_confirm:'dnd-confirm-heading'});
STAGES.daily_outlook='daily-outlook-page';HEADINGS.daily_outlook='daily-outlook-heading';
STAGES.saved_settings='saved-device-settings-page';HEADINGS.saved_settings='saved-device-settings-heading';
STAGES.notification_review='notification-review-page';HEADINGS.notification_review='notification-review-heading';
STAGES.notification_complete='notification-complete-page';HEADINGS.notification_complete='notification-complete-heading';
const CONFIGURING=new Set(['single_device_setup','guided','recommendations','intro','alert_choices','guided_marine','alert_dnd','dnd_options','dnd_customize','dnd_confirm','daily_outlook']);

export function notificationRequestId() {
  // Local HTTP Home Assistant pages do not expose crypto.randomUUID.
  return [...crypto.getRandomValues(new Uint8Array(16))].map(value=>value.toString(16).padStart(2,'0')).join('');
}

// Presentation only. These classes never alter delivery or DND eligibility.
export function alertRiskPresentation(page) {
  const result={};
  for(const [tier,item] of [['warning',page],...['advisory','watch','statement'].map(tier=>[tier,page?.[tier]])]){
    if(!item||item.kind==='transition')continue;
    if(tier==='watch'||item.id.endsWith(' watch'))result[item.id]={level:'potential',label:'Possible future threat'};
    else if(item.always_life_safety||item.includes_life_safety||item.id==='high wind warning')result[item.id]={level:'danger',label:item.includes_life_safety&&!item.always_life_safety?'Can include life-threatening conditions':'Danger to life'};
    else if(tier==='advisory'||item.id.endsWith(' advisory'))result[item.id]={level:'caution',label:'Hazardous conditions'};
  }
  return result;
}

export function installProductionOnboarding(panel) {
  const root=panel.shadowRoot,q=selector=>root.querySelector(selector),escape=value=>panel._escape(value);
  const save=update=>panel._saveOnboardingProgress(update);
  const openMenu=()=>{panel._welcomeRevisit=true;panel._showSetupStage('choice');};
  const closeSetup=()=>{
    q('#welcome-onboarding').close();
    if(panel._welcomeRevisit){panel._welcomeRevisit=false;panel._load();}
  };
  const action=(name,extra={})=>save({workflow_action:name,...extra});
  installGuidedSetup(root);
  installDndSetup(root);
  const saved_settings_ui = installSavedDeviceSettings(panel, {onboarding:true,showEntry:false});
  const existing_ui=installExistingSetup(panel,{copySettings:()=>saved_settings_ui.open(),back:openMenu});
  const notification_ui = installNotificationSetup(root, {
    escape,
    send: async (name, extra) => {
      await panel._setupSaveQueue;
      const saved = await panel._hass.callWS({type:'weather_intelligence/onboarding/notifications',
        progress_user_id:panel._config.onboarding.progress_user_id||panel._config.actor.id,
        expected_revision:panel._config.onboarding.revision || 0, request_id:notificationRequestId(), action:name, ...extra});
      panel._config={...panel._config,...saved};
      panel._showSetupStage(saved.onboarding.stage);
    },
    done: () => {q('#welcome-onboarding').close();panel._load();},
    revisit: openMenu,
    about: () => panel._config.about,
    canReviewReporting: () => panel._config.actor?.is_admin===true
      && panel._config.onboarding.target_user_id===panel._config.actor.id,
    reviewReporting: () => panel._showReporting(),
  });
  const ui=installAlertSelection(root,tier=>{
    const view=panel._config.onboarding.alert_setup,key=tier==='warning'?'enabled':tier+'_enabled';
    if((tier==='warning'&&view.inclusion_fixed)||(tier==='watch'&&view.watch_automatic))return;
    panel._saveAlertPage(tier==='warning'?'answer':tier+'_answer',{[tier==='warning'?'alert_enabled':key]:!view[key]});
  });
  const bind=(selector,callback)=>q(selector).onclick=callback;
  const each=(selector,callback)=>root.querySelectorAll(selector).forEach(button=>button.onclick=()=>callback(button));
  bind('#start-onboarding',()=>panel._openWelcome());
  bind('#landing-about',()=>panel._showAbout());
  bind('#welcome-close',closeSetup);
  q('#welcome-onboarding').oncancel=event=>{event.preventDefault();closeSetup();};
  bind('#welcome-privacy',event=>{event.preventDefault();panel._showPrivacy();});
  bind('#close-report',()=>q('#official-report').close());
  bind('#begin-onboarding',()=>save({stage:'choice'}));
  bind('#edit-existing-setup',()=>panel._showSetupStage('edit_existing'));
  bind('#setup-choice-back',()=>panel._welcomeRevisit?closeSetup():save({stage:'welcome'}));
  each('[data-setup-mode]',button=>save({mode:button.dataset.setupMode,stage:'device_setup',target_user_id:panel._config.actor.id}));
  bind('#setup-other-device',()=>save({stage:'accounts',target_user_id:panel._config.actor.id}));
  bind('#device-setup-back',()=>save({stage:panel._config.onboarding.stage==='target_device_setup'?'accounts':'choice'}));
  bind('#setup-users-back',()=>save({stage:'device_setup',target_user_id:panel._config.actor.id}));
  bind('#setup-users-next',()=>save({stage:'target_device_setup'}));
  each('[data-device-count]',button=>save({device_count:button.dataset.deviceCount,stage:button.dataset.deviceCount==='single'?'single_device':'multiple_settings'}));
  each('[data-multiple-settings]',button=>save({stage:'multiple_devices',multiple_settings:button.dataset.multipleSettings}));
  const menu=()=>panel._config.onboarding.target_user_id===panel._config.actor.id?'device_setup':'target_device_setup';
  bind('#multiple-device-settings-back',()=>save({stage:menu()}));
  bind('#multiple-device-select-back',()=>save({stage:'multiple_settings'}));
  bind('#multiple-device-select-next',()=>action('configure_devices'));
  bind('#multiple-device-options',event=>{
    const button=event.target.closest('[data-select-device]');
    if(!button||!q('#multiple-device-options').contains(button))return;
    const devices=panel._config.onboarding.selected_device_ids||[],id=button.dataset.selectDevice;
    save({selected_device_ids:devices.includes(id)?devices.filter(item=>item!==id):[...devices,id]});
  });
  q('#single-device-select').onchange=event=>{if(event.target.value)save({selected_device_id:event.target.value});};
  bind('#single-device-back',()=>save({stage:menu()}));
  bind('#single-device-next',()=>action('configure_devices'));
  bind('#single-device-setup-back',()=>action('back_to_devices'));
  each('[data-device-help]',()=>panel._showDeviceHelp());
  each('[data-alert-path]',button=>save({alert_path:button.dataset.alertPath}));
  bind('#alert-path-next',()=>save({alert_action:'start'}));
  bind('#intro-back',()=>action('intro_back'));
  bind('#intro-begin',()=>action('intro_next'));
  bind('#alert-choice-back',()=>panel._saveAlertPage('previous'));
  bind('#alert-choice-next',()=>panel._saveAlertPage('next'));
  each('[data-marine-mode]',button=>panel._saveAlertPage('marine_mode',{marine_warning_mode:button.dataset.marineMode}));
  each('[data-guided-answer]',button=>action('guided_answer',{guided_question:GUIDED_QUESTIONS[panel._config.onboarding.guided_index||0].id,guided_answer:button.dataset.guidedAnswer==='yes'}));
  bind('#guided-question-back',()=>action('guided_back'));
  bind('#guided-question-next',()=>action('guided_next'));
  bind('#recommendations-back',()=>action('recommendations_back'));
  bind('#recommendations-next',()=>action('recommendations_next'));
  each('[data-guided-marine-mode]',button=>action('marine_answer',{marine_warning_mode:button.dataset.guidedMarineMode}));
  installMarineNearby(root,()=>panel._config.onboarding.alert_setup||{},(context,choices)=>{
    const marine_warning_mode=panel._config.onboarding.alert_setup?.marine_warning_mode;
    if(context==='guided')action('marine_answer',{marine_warning_mode,...choices});
    else panel._saveAlertPage('marine_mode',{marine_warning_mode,...choices});
  });
  bind('#guided-marine-back',()=>action('marine_back'));
  bind('#guided-marine-next',()=>action('marine_next'));
  each('[data-dnd-answer]',button=>save({dnd_bypass:button.dataset.dndAnswer==='yes'}));
  bind('#alert-dnd-back',()=>action('delivery_back'));
  bind('#alert-dnd-next',()=>action('delivery_next'));
  bind('#dnd-use-defaults',()=>action('dnd_default'));
  bind('#dnd-choose-custom',()=>action('dnd_custom'));
  bind('#dnd-alert-options',event=>{
    const button=event.target.closest('[data-dnd-rule]');
    if(button&&q('#dnd-alert-options').contains(button))action('dnd_toggle',{dnd_rule:button.dataset.dndRule});
  });
  bind('#dnd-customize-next',()=>action('dnd_customize_next'));
  bind('#dnd-confirm-next',()=>action('dnd_confirm_next'));
  for(const selector of ['#dnd-options-back','#dnd-customize-back','#dnd-confirm-back'])bind(selector,()=>action('dnd_back'));
  each('[data-daily-outlook]',button=>action('daily_answer',{daily_outlook_enabled:button.dataset.dailyOutlook==='yes'}));
  q('#daily-outlook-time').onchange=event=>action('daily_answer',{daily_outlook_enabled:true,daily_outlook_time:event.target.value});
  bind('#daily-outlook-back',()=>action('daily_back'));
  bind('#daily-outlook-next',()=>action('daily_next'));
  let previousStage=null;
  function render(stage=panel._config.onboarding.stage){
    const config=panel._config,o=config.onboarding,view=o.alert_setup||{},page=view.page;
    const focused=root.activeElement,focusedDevice=focused?.dataset?.selectDevice,focusedRule=focused?.dataset?.dndRule,scroll=q('#welcome-onboarding').scrollTop;
    const dndScroll=q('#dnd-alert-options').scrollTop;
    if(!STAGES[stage])stage='choice';
    panel._renderSetupAccounts(stage);panel._renderSingleDevice();panel._markSetupMode();panel._updateOnboardingEntry();
    renderSelectableAlerts(root,o,alertRiskPresentation(page));
    renderDndSetup(root,o.dnd_setup,o);
    notification_ui.render(o.notification_setup,stage);
    for(const id of new Set(Object.values(STAGES)))q('#'+id).hidden=id!==STAGES[stage];
    q('#welcome-onboarding').setAttribute('aria-labelledby',HEADINGS[stage]);
    ui.hint.hidden=stage!=='alert_choices'||page?.kind==='transition';
    const other=o.target_user_id!==config.actor.id,owner=config.target_user?.name||'selected user';
    q('#admin-edit-notice').hidden=!config.actor.is_admin||!other;
    q('#setup-other-device').hidden=!config.actor.is_admin||other;
    q('#edit-existing-setup').hidden=!(config.actor.is_admin||o.completed||o.dashboard_available||config.own_preferences_available);
    q('#setup-choice-back').textContent=panel._welcomeRevisit?'Close':'Back';
    if(stage==='edit_existing')existing_ui.render();
    for(const id of ['#device-setup-for','#single-device-for','#multiple-device-for','#multiple-device-selection-for']){
      q(id).hidden=!other;q(id).textContent=other?'Setting up for '+owner:'';
    }
    q('#device-ownership-note').hidden=other;
    const ids=o.selected_device_ids||[],devices=config.setup_devices||[];
    const selected=ids.map(id=>devices.find(device=>device.id===id)).filter(Boolean);
    const separate=o.device_count==='multiple'&&o.multiple_settings==='individual';
    const active=separate?selected.slice(o.active_device_index,o.active_device_index+1):selected;
    const names=active.map(device=>device.name).join(', ');
    saved_settings_ui.render(o,(other?owner+' · ':'')+names);
    q('#selected-device-name').textContent=names;
    q('#multiple-device-options').innerHTML=devices.map(device=>`<button class="setup-choice" data-select-device="${escape(device.id)}" aria-pressed="${ids.includes(device.id)}"><strong>${escape(device.name)}</strong>${device.platform?`<span>${escape(device.platform)}</span>`:''}</button>`).join('')||'<p>No devices are available for this account.</p>';
    root.querySelectorAll('[data-multiple-settings]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.multipleSettings===o.multiple_settings)));
    q('#multiple-device-selection-description').textContent=o.multiple_settings==='shared'?'Select at least two devices. You will choose their settings once.':'Select at least two devices. You will set up each one separately.';
    q('#multiple-device-selection-count').textContent=`${selected.length} devices selected`;
    q('#multiple-device-select-next').disabled=selected.length<2;
    const question=GUIDED_QUESTIONS[o.guided_index||0],answers=o.guided_answers||{};
    q('#guided-question-progress').textContent=`Question ${(o.guided_index||0)+1} of ${GUIDED_QUESTIONS.length}`;
    q('#guided-question-heading').textContent=question.title;q('#guided-question-description').textContent=question.description;q('#guided-question-detail').textContent=question.detail;
    q('#guided-marine-beta').hidden=!['marine','shoreline'].includes(question.id);
    root.querySelectorAll('[data-guided-answer]').forEach(button=>button.setAttribute('aria-pressed',String(answers[question.id]===(button.dataset.guidedAnswer==='yes'))));
    q('#guided-question-next').disabled=typeof answers[question.id]!=='boolean';
    q('#recommendations-device').textContent=names;
    q('#recommendations-description').textContent=o.setup_mode==='guided'?'Recommended settings, tailored by your answers.':'Recommended settings, without choosing every alert individually.';
    q('#recommendations-marine-beta').hidden=o.setup_mode==='guided'&&!answers.marine&&!answers.shoreline;
    q('#recommendations-interests').hidden=o.setup_mode!=='guided';
    q('#recommendations-interest-list').innerHTML=GUIDED_QUESTIONS.map(item=>`<dt>${escape(item.label)}</dt><dd>${answers[item.id]?'Included':'Not included'}</dd>`).join('');
    root.querySelectorAll('[data-guided-marine-mode]').forEach(button=>button.setAttribute('aria-pressed',String(view.marine_warning_mode===button.dataset.guidedMarineMode)));
    q('#guided-marine-next').disabled=!view.marine_warning_mode;
    renderMarineNearby(root,view,'guided');
    q('#configuration-device-context').hidden=(!other&&o.device_count!=='multiple')||!CONFIGURING.has(stage);
    q('#configuration-device-context').textContent=(other?owner+' · ':'')+(separate?`Device ${o.active_device_index+1} of ${selected.length} · ${names}`:o.device_count==='multiple'?`Shared settings for ${selected.length} devices`:names);
    q('#alert-dnd-next').textContent='Next';
    q('#dnd-confirm-next').textContent='Confirm and continue';
    q('#daily-outlook-next').textContent=separate&&o.active_device_index+1<selected.length?'Next device':'Next';
    q('#welcome-status').textContent='';
    if(previousStage!==stage){
      q('#welcome-onboarding').scrollTop=0;
      q('#'+STAGES[stage]+' select:not([disabled]), #'+STAGES[stage]+' button:not([hidden]):not([disabled])')?.focus({preventScroll:true});
    }else{
      q('#welcome-onboarding').scrollTop=scroll;
      q('#dnd-alert-options').scrollTop=dndScroll;
      if(focusedDevice)Array.from(root.querySelectorAll('[data-select-device]')).find(button=>button.dataset.selectDevice===focusedDevice)?.focus({preventScroll:true});
      if(focusedRule)Array.from(root.querySelectorAll('[data-dnd-rule]')).find(button=>button.dataset.dndRule===focusedRule)?.focus({preventScroll:true});
    }
    previousStage=stage;
  }
  render();
  return {render};
}
