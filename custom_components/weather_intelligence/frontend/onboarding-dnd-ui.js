// Shared DND review UI. Authenticated saves remain in the production controller.
const SCREENS = `
<section id="dnd-options-page" hidden aria-labelledby="dnd-options-heading">
  <div class="welcome-copy"><h2 id="dnd-options-heading">Which alerts should bypass Do Not Disturb?</h2><p>Keep the default choices or choose your own.</p></div>
  <div class="welcome-actions">
    <button class="setup-choice" id="dnd-use-defaults"><strong>Use default choices</strong></button>
    <button class="setup-choice" id="dnd-choose-custom"><strong>Choose which alerts bypass DND</strong></button>
  </div>
  <button id="dnd-options-back" class="setup-back">Back</button>
</section>
<section id="dnd-customize-page" hidden aria-labelledby="dnd-customize-heading">
  <div class="welcome-copy"><h2 id="dnd-customize-heading">Choose your DND bypass alerts</h2><p>Select an alert to allow it through Do Not Disturb. Select it again to turn bypass off.</p></div>
  <div id="dnd-alert-options" class="dnd-scroll dnd-options" role="group" aria-labelledby="dnd-customize-heading" tabindex="0"></div>
  <p id="dnd-selection-count" class="setup-reassurance" role="status"></p>
  <div class="user-step-nav"><button id="dnd-customize-back" class="setup-back">Back</button><button id="dnd-customize-next" class="primary">Review choices</button></div>
</section>
<section id="dnd-confirm-page" hidden aria-labelledby="dnd-confirm-heading">
  <div class="welcome-copy"><h2 id="dnd-confirm-heading">Confirm your DND choices</h2><p id="dnd-confirm-description"></p></div>
  <div id="dnd-confirm-list" class="dnd-scroll" tabindex="0" aria-label="Alerts allowed through Do Not Disturb"></div>
  <p class="setup-reassurance" id="dnd-phone-settings-note">Phone permissions and settings must also be configured during notification setup.</p>
  <div class="user-step-nav"><button id="dnd-confirm-back" class="setup-back">Back</button><button id="dnd-confirm-next" class="primary">Confirm and continue</button></div>
</section>
<section id="daily-outlook-page" hidden aria-labelledby="daily-outlook-heading">
  <div class="welcome-copy"><h2 id="daily-outlook-heading">Would you like a daily weather outlook?</h2></div>
  <div class="welcome-actions" role="group" aria-labelledby="daily-outlook-heading"><button class="setup-choice" data-daily-outlook="yes" aria-pressed="false"><strong>Yes, send a daily outlook</strong></button><button class="setup-choice" data-daily-outlook="no" aria-pressed="false"><strong>No daily outlook</strong></button></div>
  <div id="daily-outlook-time-choice" class="device-selection" hidden><label for="daily-outlook-time">Delivery time</label><input type="time" id="daily-outlook-time" value="07:00" required><p id="daily-outlook-timezone"></p></div>
  <div class="user-step-nav"><button id="daily-outlook-back" class="setup-back">Back</button><button id="daily-outlook-next" class="primary" disabled>Next</button></div>
</section>`;

const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const list=items=>'<ul class="dnd-items">'+items.map(item=>`<li><strong>${escape(item.title)}</strong>${item.detail?`<span>${escape(item.detail)}</span>`:''}</li>`).join('')+'</ul>';
export const renderDndReviewList=list;
export function renderDndChoiceButtons(choices,selected){
  return choices.map(item=>`<button type="button" data-dnd-rule="${escape(item.id)}" aria-pressed="${selected.has(item.id)}"><strong>${escape(item.title)}</strong>${item.detail?`<span>${escape(item.detail)}</span>`:''}${item.source_note?`<span class="dnd-source-note">Source: ${escape(item.source_note)}</span>`:''}<span class="dnd-included">${selected.has(item.id)?'Bypass on ✓':'Bypass off'}</span></button>`).join('')||'<p>No alerts are selected to receive. Change your alert choices first.</p>';
}
export const DND_LIST_STYLE=`.dnd-scroll{max-height:min(36dvh,310px);overflow-y:auto;overscroll-behavior:contain;margin:0 auto 12px;border:1px solid var(--divider-color,#385267);border-radius:12px;padding:12px}
  .dnd-items{margin:0;padding-left:20px;line-height:1.4}.dnd-items li+li{margin-top:9px}.dnd-items strong{font-size:14px;font-weight:600}.dnd-items span{display:block;color:var(--secondary-text-color);font-size:13px;margin-top:3px}
  .dnd-options{display:grid;gap:8px;padding:8px}.dnd-options button{text-align:left;border-radius:8px;min-height:44px;padding:12px}.dnd-options strong{display:block;font-size:14px}.dnd-options span{display:block;font-size:13px;color:var(--secondary-text-color);margin-top:4px}.dnd-options [aria-pressed="true"]{border-color:#67e8f9;background:#67e8f912}.dnd-options [aria-pressed="true"] .dnd-included{color:#67e8f9}.dnd-source-note{font-size:12px!important}`;

export function installDndSetup(root){
  const doc=root.ownerDocument,template=doc.createElement('template');template.innerHTML=SCREENS;
  root.querySelector('#welcome-onboarding').insertBefore(template.content,root.querySelector('#notification-setup-page'));
  root.querySelector('#alert-dnd-heading').textContent='Allow alerts through Do Not Disturb?';
  root.querySelector('[data-dnd-answer="yes"]').textContent='Yes, allow bypass';
  const summary=doc.createElement('div');summary.className='dnd-default-summary';
  summary.innerHTML='<h3>Default bypass alerts</h3><div id="dnd-default-list" class="dnd-scroll" tabindex="0" aria-label="Default Do Not Disturb bypass alerts"></div>';
  root.querySelector('#alert-dnd-page > .welcome-actions').before(summary);
  const style=doc.createElement('style');
  style.textContent=`.dnd-default-summary{max-width:470px;margin:0 auto 16px}.dnd-default-summary h3{font-size:16px;margin:0 0 8px}
    #dnd-default-list{max-height:min(24dvh,190px)}
    .dnd-scroll{max-width:560px;max-height:min(36dvh,310px);overflow-y:auto;overscroll-behavior:contain;margin:0 auto 12px;border:1px solid var(--divider-color,#385267);border-radius:12px;padding:12px}
    .dnd-scroll:focus-visible{outline:3px solid #67e8f9;outline-offset:3px}.dnd-items{margin:0;padding-left:20px;line-height:1.4}.dnd-items li+li{margin-top:9px}.dnd-items strong{font-size:14px;font-weight:600}.dnd-items span{display:block;color:var(--secondary-text-color);font-size:13px;margin-top:3px}
    .dnd-options{display:grid;gap:8px;padding:8px}.dnd-options button{text-align:left;border-radius:8px;min-height:44px!important;padding:12px!important}.dnd-options strong{display:block;font-size:14px}.dnd-options span{display:block;font-size:13px;color:var(--secondary-text-color);margin-top:4px}.dnd-options [aria-pressed="true"]{border-color:#67e8f9;background:#67e8f912}.dnd-options [aria-pressed="true"] .dnd-included{color:#67e8f9}
    .dnd-options .dnd-source-note{font-size:12px}[data-daily-outlook][aria-pressed="true"]{border-color:#67e8f9;color:#67e8f9;background:#67e8f912}
    #daily-outlook-time-choice{margin-top:18px}#daily-outlook-time{font:inherit;min-height:44px;padding:8px;border:1px solid var(--divider-color,#385267);border-radius:8px;background:var(--card-background-color);color:inherit}
    #dnd-options-page .setup-back{margin-top:16px}`;
  root.append(style);
}

export function renderDndSetup(root,view={},onboarding={}){
  const choices=view.choices||[],selected=new Set(view.selected||[]),included=choices.filter(item=>selected.has(item.id));
  root.querySelector('#dnd-default-list').innerHTML=view.defaults?.length?list(view.defaults):'<p>No default bypass alerts are included in your alert choices.</p>';
  root.querySelector('#dnd-alert-options').innerHTML=renderDndChoiceButtons(choices,selected);
  root.querySelector('#dnd-selection-count').textContent=`${included.length} bypass choices selected`;
  root.querySelector('#dnd-confirm-description').textContent=included.length?'These notifications will bypass Do Not Disturb once phone setup is complete. All other notifications will respect Do Not Disturb.':'No notifications will bypass Do Not Disturb.';
  root.querySelector('#dnd-confirm-list').hidden=!included.length;
  root.querySelector('#dnd-confirm-list').innerHTML=list(included);
  root.querySelector('#dnd-phone-settings-note').hidden=!included.length;
  root.querySelector('#alert-dnd-next').disabled=typeof onboarding.alert_setup?.dnd_bypass!=='boolean';
  root.querySelectorAll('[data-daily-outlook]').forEach(button=>button.setAttribute('aria-pressed',String(onboarding.daily_outlook_enabled===(button.dataset.dailyOutlook==='yes'))));
  root.querySelector('#daily-outlook-time-choice').hidden=onboarding.daily_outlook_enabled!==true;
  root.querySelector('#daily-outlook-time').value=onboarding.daily_outlook_time||'07:00';
  root.querySelector('#daily-outlook-timezone').textContent=onboarding.home_timezone||'Home Assistant local time';
  root.querySelector('#daily-outlook-next').disabled=typeof onboarding.daily_outlook_enabled!=='boolean';
}
