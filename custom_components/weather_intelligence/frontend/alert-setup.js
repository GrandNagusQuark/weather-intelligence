// Each alert's authored criteria and saved answer come from the authenticated API.
// All 106 catalog entries completed their first copy review.
import {MARINE_BETA_NOTICE,isMarinePage} from './marine-beta.js?v=2';
import {marineNearbyControls,renderMarineNearby} from './marine-preferences-ui.js?v=2';
export const ALERT_CHOICE_SCREEN = `<section id="alert-choice-page" hidden aria-labelledby="alert-choice-heading">
  <p id="alert-choice-progress" class="alert-progress"></p>
  <div class="welcome-copy"><h2 id="alert-choice-heading"></h2><p id="alert-life-included" class="alert-included" hidden>The life-threatening cases are already included. This choice adds the other alerts of this type.</p></div>
  <div id="marine-beta-notice" hidden>${MARINE_BETA_NOTICE}</div>
  <div id="alert-description-panels" class="alert-descriptions">
    <section class="alert-explanation"><h3 id="alert-warning-label">When this alert applies</h3><p id="alert-choice-conditions"></p><p id="alert-tornado-evidence" hidden></p><p id="alert-tornado-threat" hidden></p></section>
    <section id="alert-advisory-panel" class="alert-explanation" hidden><h3>Advisory</h3><p id="alert-advisory-conditions"></p></section>
    <section id="alert-watch-panel" class="alert-explanation" hidden><h3>Watch</h3><p id="alert-watch-conditions"></p></section>
    <section id="alert-statement-panel" class="alert-explanation" hidden><h3>Statement</h3><p id="alert-statement-conditions"></p></section>
  </div>
  <p id="alert-warning-included" class="alert-watch-note" hidden>Warnings are included in your life-threatening alerts.</p>
  <p id="alert-pair-confirm" class="alert-watch-note" hidden>Confirm this combined alert choice to continue. Your previous choices have not changed.</p>
  <div id="alert-answer-group" class="alert-answer-buttons" role="group" aria-label="Include this alert">
    <button data-alert-answer="yes" aria-pressed="false">Yes, include this</button><button data-alert-answer="no" aria-pressed="false">No, skip this</button>
  </div>
  <div id="alert-advisory-choice" class="alert-watch-choice" hidden><label><input id="alert-include-advisory" type="checkbox"> Include advisories too</label></div>
  <div id="alert-watch-choice" class="alert-watch-choice" hidden><label><input id="alert-include-watch" type="checkbox"> Include watches too</label><p id="alert-watch-automatic" class="alert-watch-note" hidden>Watches are included automatically with these warnings.</p></div>
  <div id="alert-statement-choice" class="alert-watch-choice" hidden><label><input id="alert-include-statement" type="checkbox"> Include statements too</label></div>
  <div id="marine-warning-choice" hidden>
    <div class="welcome-copy"><h3>When should we warn you?</h3><p>Both choices apply only when the warning covers your location.</p></div>
    <div class="welcome-actions" role="group" aria-label="Special Marine Warning location preference">
      <button class="setup-choice" data-marine-mode="always" aria-pressed="false"><strong>Always warn</strong><span>Warn me whether my location is on land or water.</span></button>
      <button class="setup-choice" data-marine-mode="on_water" aria-pressed="false"><strong>On or near the water</strong><span>Warn me on mapped water, or within half a mile of a mapped shoreline away from home. Vehicle activity or Android Auto skips shoreline-only alerts, not mapped-water alerts. On-water locations qualify near home. Requires a fresh, accurate location.</span></button>
    </div>
  </div>
  <div id="marine-nearby-card-settings" hidden>${marineNearbyControls('custom')}</div>
  <div class="user-step-nav"><button id="alert-choice-back" class="setup-back">Back</button><button id="alert-choice-next" class="primary">Next</button></div>
</section>`;

export const ALERT_SETUP_SCREENS = `${ALERT_CHOICE_SCREEN}
<section id="alert-dnd-page" hidden aria-labelledby="alert-dnd-heading">
  <div class="welcome-copy"><h2 id="alert-dnd-heading">Allow life-threatening alerts through Do Not Disturb?</h2><p>We'll guide you through the device settings at the end of setup.</p></div>
  <div class="welcome-actions"><button data-dnd-answer="yes" aria-pressed="false">Yes, allow urgent alerts</button><button data-dnd-answer="no" aria-pressed="false">No, respect Do Not Disturb</button></div>
  <div class="user-step-nav"><button id="alert-dnd-back" class="setup-back">Back</button><button id="alert-dnd-next" class="primary" disabled>Next</button></div>
</section>
<section id="notification-setup-page" hidden aria-labelledby="notification-setup-heading">
  <div class="welcome-copy"><h2 id="notification-setup-heading">Notification setup</h2><p>Coming soon.</p></div>
  <button id="notification-setup-back" class="setup-back">Back</button>
</section>`;

export function renderAlertSetup(root, onboarding) {
  const view=onboarding.alert_setup || {};
  const page=view.page;
  const intro=page?.kind==="transition";
  const tiers=["advisory","watch","statement"];
  const paired=tiers.some(tier=>page?.[tier]);
  const confirm=!!view.confirm_pair || !!view.confirm_tiers?.length;
  root.querySelector("#alert-choice-progress").textContent=page?`Step ${view.page_index+1} of ${view.page_count}`:"";
  root.querySelector("#alert-choice-heading").textContent=page?.title || "Choose your alerts";
  root.querySelector("#marine-beta-notice").hidden=!isMarinePage(page);
  root.querySelector("#alert-choice-conditions").textContent=page?.conditions || "";
  root.querySelector("#alert-description-panels").classList.toggle("paired",paired);
  const label=root.querySelector("#alert-warning-label");
  label.textContent=paired?"Warning":"When this alert applies";
  label.hidden=intro;
  for(const [field,id,prefix] of [["evidence","evidence","Evidence"],["damage_threat","threat","Damage threat"]]) {
    const element=root.querySelector(`#alert-tornado-${id}`);
    element.hidden=!page?.[field];
    element.textContent=page?.[field]?`${prefix}: ${page[field]}`:"";
  }
  for(const tier of tiers) {
    const item=page?.[tier];
    root.querySelector(`#alert-${tier}-panel`).hidden=!item;
    root.querySelector(`#alert-${tier}-conditions`).textContent=item?.conditions || "";
    root.querySelector(`#alert-${tier}-choice`).hidden=!item;
    const control=root.querySelector(`#alert-include-${tier}`);
    control.checked=!!view[`${tier}_enabled`];
    control.indeterminate=!!view.confirm_tiers?.includes(tier);
    control.disabled=!item || (tier==="watch" && !!view.watch_automatic);
  }
  root.querySelector("#alert-watch-automatic").hidden=!view.watch_automatic;
  root.querySelector("#alert-pair-confirm").hidden=!confirm;
  root.querySelector("#alert-warning-included").hidden=!view.inclusion_fixed || !paired;
  root.querySelector("#alert-life-included").hidden=onboarding.alert_path!=="life_plus" || !page?.includes_life_safety;
  root.querySelectorAll("[data-alert-answer]").forEach(button=>{
    button.setAttribute("aria-pressed",String(!view.confirm_pair && view.enabled===(button.dataset.alertAnswer==="yes")));
    button.textContent=paired?(button.dataset.alertAnswer==="yes"?"Yes, include warnings":"No, skip this hazard"):(button.dataset.alertAnswer==="yes"?"Yes, include this":"No, skip this");
  });
  const marinePage=page?.id==="special marine warning";
  root.querySelector("#alert-answer-group").hidden=intro || !!view.inclusion_fixed;
  root.querySelector("#marine-warning-choice").hidden=!marinePage || !view.enabled;
  root.querySelectorAll("[data-marine-mode]").forEach(button=>button.setAttribute("aria-pressed",String(view.marine_warning_mode===button.dataset.marineMode)));
  root.querySelector('#marine-nearby-card-settings').hidden=!marinePage;
  renderMarineNearby(root,view,'custom');
  root.querySelector("#alert-choice-next").disabled=!page || confirm || (marinePage && view.enabled && !["always","on_water"].includes(view.marine_warning_mode));
  root.querySelectorAll("[data-dnd-answer]").forEach(button=>button.setAttribute("aria-pressed",String(view.dnd_bypass===(button.dataset.dndAnswer==="yes"))));
  const dndNext=root.querySelector("#alert-dnd-next");
  if(dndNext)dndNext.disabled=typeof view.dnd_bypass!=="boolean";
}
