// Shared onboarding UI; persistence and authorization belong to the HA backend.
import {renderAlertSetup} from './alert-setup.js?v=23';

export const ALERT_INTRO_SCREEN = `
  <section id="alert-introduction" hidden aria-labelledby="alert-introduction-heading">
    <div class="welcome-copy"><h2 id="alert-introduction-heading">Understanding your alerts</h2><p>Learn what the alert types and colors mean before choosing your alert preferences.</p></div>
    <div class="intro-copy">
      <h3>What the message means</h3>
      <dl>
        <dt>Warning</dt><dd>Hazardous conditions are happening or expected.</dd>
        <dt>Advisory</dt><dd>Hazardous conditions, generally below the related warning level.</dd>
        <dt>Watch</dt><dd>Warning-level conditions are possible, but the location or timing may still be uncertain.</dd>
      </dl>
      <p>Outlooks give earlier heads-ups. Statements provide information or updates.</p>
      <h3>How we highlight risk</h3>
      <ul class="risk-legend">
        <li class="risk-danger"><span class="risk-dot" aria-hidden="true"></span><span><strong>Red</strong> — Dangerous or potentially life-threatening</span></li>
        <li class="risk-caution"><span class="risk-dot" aria-hidden="true"></span><span><strong>Yellow</strong> — Hazardous, generally lower risk</span></li>
        <li class="risk-potential"><span class="risk-dot" aria-hidden="true"></span><span><strong>White</strong> — A possible or developing threat</span></li>
      </ul>
      <p class="intro-caption">Colors are Weather Intelligence's guide, not official NWS categories. Message type alone doesn't determine risk. A white watch may concern future life-threatening weather.</p>
    </div>
    <div class="user-step-nav"><button id="intro-back" class="setup-back">Back</button><button id="intro-begin" class="primary">Continue</button></div>
  </section>`;

export const ALERT_SELECTION_STYLE = `
  .risk-danger{color:#ff9b9b}.risk-caution{color:#ffe08a}.risk-potential{color:#edf2f7}
  .risk-label{display:block;font-size:13px;font-weight:500;margin-bottom:8px}
  .intro-copy{max-width:560px;margin:0 auto;line-height:1.55}
  .intro-copy h3{font-size:17px;margin:20px 0 10px}.intro-copy p{margin:0 0 12px}
  .intro-copy dl{margin:0}.intro-copy dt{font-weight:600;margin-top:10px}.intro-copy dd{margin:2px 0 12px}
  .risk-legend{list-style:none;padding:0;margin:0;display:grid;gap:10px}
  .risk-legend li{display:flex;align-items:baseline;gap:10px}
  .risk-dot{display:inline-block;flex:0 0 10px;width:10px;height:10px;border-radius:50%;background:currentColor}
  .intro-caption{color:var(--secondary-text-color);font-size:14px;margin-top:18px!important}
  .selection-hint{text-align:center;font-size:13px;line-height:1.5;color:var(--secondary-text-color);margin:12px auto 4px;max-width:470px}
  .tier-card{display:block;width:100%;text-align:left;font-weight:400;cursor:pointer}
  .tier-card-title{display:block;font-size:16px;font-weight:650;margin:0 0 8px}
  .tier-card-copy{display:block;margin:0 0 14px}.tier-card-copy:last-of-type{margin-bottom:0}
  .alert-source-note{display:block;font-size:12px;line-height:1.4;color:var(--secondary-text-color);margin-top:10px}
  .tier-card[aria-pressed="true"]{outline:2px solid #67e8f9;outline-offset:0;background:#67e8f90b}
  .card-selection{display:block;font-size:13px;color:var(--secondary-text-color);margin-top:12px}
  .tier-card[aria-pressed="true"] .card-selection{color:#67e8f9}
  .tier-card:disabled{opacity:1}
`;

export function installAlertSelection(root, onToggle) {
  const doc=root.ownerDocument,dialog=root.querySelector('#welcome-onboarding');
  const style=doc.createElement('style');style.textContent=ALERT_SELECTION_STYLE;root.append(style);
  const template=doc.createElement('template');template.innerHTML=ALERT_INTRO_SCREEN;
  dialog.insertBefore(template.content,root.querySelector('#alert-choice-page'));
  const hint=doc.createElement('p');hint.className='selection-hint';hint.hidden=true;
  hint.textContent='Select a card to turn its notifications on or off.';
  dialog.insertBefore(hint,dialog.querySelector('.weather-logo'));
  installTierCards(root,onToggle);
  return {intro:root.querySelector('#alert-introduction'),hint};
}

export function installTierCards(root,onToggle) {
  const doc=root.ownerDocument;
  for(const tier of ['warning','advisory','watch','statement']){
    const original=tier==='warning'?root.querySelector('#alert-choice-conditions').parentElement:root.querySelector('#alert-'+tier+'-panel');
    const card=doc.createElement('button');card.type='button';card.className=original.className+' tier-card';
    if(original.id)card.id=original.id;
    for(const child of Array.from(original.children)){
      const span=doc.createElement('span');
      for(const attribute of child.attributes)span.setAttribute(attribute.name,attribute.value);
      span.classList.add(child.tagName==='H3'?'tier-card-title':'tier-card-copy');
      span.textContent=child.textContent;card.append(span);
    }
    const heading=card.querySelector('.tier-card-title');heading.id ||= tier+'-card-title';
    const status=doc.createElement('span');status.className='card-selection';status.id=tier+'-selection-status';card.append(status);
    const source_note=doc.createElement('span');source_note.className='alert-source-note';source_note.hidden=true;card.append(source_note);
    card.setAttribute('aria-labelledby',heading.id+' '+status.id);
    card.onclick=()=>onToggle(tier);original.replaceWith(card);
  }
}

export function renderSelectableAlerts(root, onboarding, riskAssignments={}) {
  renderAlertSetup(root,onboarding);
  const view=onboarding.alert_setup,page=view.page;
  root.querySelector('#alert-answer-group').hidden=true;
  for(const tier of ['advisory','watch','statement'])root.querySelector('#alert-'+tier+'-choice').hidden=true;
  for(const tier of ['warning','advisory','watch','statement']){
    const panel=tier==='warning'?root.querySelector('#alert-choice-conditions').parentElement:root.querySelector('#alert-'+tier+'-panel');
    const item=tier==='warning'?page:page?.[tier],included=!!view[tier==='warning'?'enabled':tier+'_enabled'];
    const automatic=tier==='watch'&&!!view.watch_automatic,information=page?.kind==='transition';
    panel.classList.remove('risk-danger','risk-caution','risk-potential');panel.querySelector('.risk-label')?.remove();
    const fixed=tier==='warning'&&!!view.inclusion_fixed;
    panel.setAttribute('aria-pressed',String(!information&&included));panel.disabled=automatic||information||fixed;
    const status=panel.querySelector('.card-selection');status.hidden=information;
    const source_note=panel.querySelector('.alert-source-note');source_note.textContent=item?.source_note?'Source: '+item.source_note:'';source_note.hidden=information||!item?.source_note;
    status.textContent=fixed?'Included in life-threatening alerts':automatic?(included?'Included automatically with warnings':'Automatically follows warnings'):included?'Included ✓':'Not included';
    const risk=item&&riskAssignments[item.id];
    if(risk&&!information){
      panel.classList.add('risk-'+risk.level);
      const label=root.ownerDocument.createElement('span');label.className='risk-label';label.textContent=risk.label;
      panel.querySelector('.tier-card-title').after(label);
    }
  }
}
