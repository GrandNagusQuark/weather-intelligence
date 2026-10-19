// Shared quick/guided/multiple-device UI. Real saves use authenticated HA APIs.
import {MARINE_BETA_NOTICE} from './marine-beta.js?v=2';
import {marineNearbyControls} from './marine-preferences-ui.js?v=2';
export const GUIDED_QUESTIONS = [
  {
    id: 'marine', label: 'Boating and open water',
    title: 'Do you want alerts for boating and other activities on the water?',
    description: 'Includes alerts for boating, sailing, and other time on lakes or coastal waters.',
    detail: 'Adds marine wind, wave, and navigation alerts.',
    events: ['special marine warning', 'gale warning', 'gale watch', 'storm warning', 'storm watch',
      'hazardous seas warning', 'hazardous seas watch', 'small craft advisory', 'brisk wind advisory',
      'lake wind advisory', 'low water advisory', 'heavy freezing spray warning',
      'heavy freezing spray watch', 'freezing spray advisory'],
  },
  {
    id: 'shoreline', label: 'Beaches and shorelines',
    title: 'Do you live in or visit areas near the ocean or large lakes?',
    description: 'Includes alerts for dangerous conditions along beaches and shorelines.',
    detail: 'Adds coastal and lakeshore flooding, dangerous surf, rip currents, storm surge, and tsunami alerts.',
    events: ['beach hazards statement', 'coastal flood warning', 'coastal flood advisory',
      'coastal flood watch', 'coastal flood statement', 'lakeshore flood warning',
      'lakeshore flood advisory', 'lakeshore flood watch', 'lakeshore flood statement',
      'high surf warning', 'high surf advisory', 'rip current statement', 'storm surge warning',
      'storm surge watch', 'tsunami warning', 'tsunami advisory', 'tsunami watch'],
  },
  {
    id: 'avalanche', label: 'Avalanches',
    title: 'Do you live in or visit areas where avalanches can occur?',
    description: 'Includes alerts for avalanches in steep, snow-covered mountain areas.',
    detail: 'Snow, ice, blizzard, and cold-weather alerts stay included either way.',
    events: ['avalanche warning', 'avalanche advisory', 'avalanche watch'],
  },
  {
    id: 'volcanic', label: 'Volcanic activity and ash',
    title: 'Do you live in or visit areas that could be affected by volcanic activity or ash?',
    description: 'Includes alerts for volcanic eruptions and drifting ash.',
    detail: 'Adds volcano warnings and ashfall alerts.',
    events: ['volcano warning', 'ashfall warning', 'ashfall advisory'],
  },
];

export const SETUP_CHOICES = `
  <div class="welcome-copy"><h2 id="setup-choice-heading">How would you like to set up?</h2></div>
  <div class="welcome-actions">
    <button class="setup-choice" data-setup-mode="quick" aria-pressed="false"><strong>Quick setup</strong><span>Set up your devices and receive weather notifications with recommended settings.</span></button>
    <button class="setup-choice" data-setup-mode="guided" aria-pressed="false"><strong>Guided quick setup</strong><span>Answer a few questions to tailor recommended alerts to the places you go and the things you do.</span></button>
    <button class="setup-choice" data-setup-mode="custom" aria-pressed="false"><strong>Custom setup</strong><span>Choose your alerts, devices, and preferences.</span></button>
  </div>
  <p class="setup-reassurance">You can change your choices later.</p>
  <button id="setup-choice-back" class="setup-back">Back</button>`;

const GUIDED_SCREENS = `
  <section id="multiple-device-settings-page" hidden aria-labelledby="multiple-device-settings-heading">
    <div class="welcome-copy"><h2 id="multiple-device-settings-heading">How should these devices be configured?</h2><p id="multiple-device-for" hidden></p></div>
    <div class="welcome-actions" role="group" aria-labelledby="multiple-device-settings-heading">
      <button class="setup-choice" data-multiple-settings="shared" aria-pressed="false"><strong>Same settings for all devices</strong><span>Choose your alert preferences once for all selected devices.</span></button>
      <button class="setup-choice" data-multiple-settings="individual" aria-pressed="false"><strong>Individual settings for each device</strong><span>Choose separate alert preferences for each device.</span></button>
    </div>
    <button id="multiple-device-settings-back" class="setup-back">Back</button>
  </section>
  <section id="multiple-device-select-page" hidden aria-labelledby="multiple-device-select-heading">
    <div class="welcome-copy"><h2 id="multiple-device-select-heading">Choose your devices</h2><p id="multiple-device-selection-for" hidden></p><p id="multiple-device-selection-description"></p></div>
    <div id="multiple-device-options" class="welcome-actions" role="group" aria-labelledby="multiple-device-select-heading"></div>
    <p id="multiple-device-selection-count" class="setup-reassurance" role="status"></p>
    <button class="device-help-link" data-device-help>Device not listed?</button>
    <div class="user-step-nav"><button id="multiple-device-select-back" class="setup-back">Back</button><button id="multiple-device-select-next" class="primary" disabled>Next</button></div>
  </section>
  <section id="guided-question-page" hidden aria-labelledby="guided-question-heading">
    <p class="alert-progress" id="guided-question-progress"></p>
    <div class="welcome-copy"><h2 id="guided-question-heading"></h2><p id="guided-question-description"></p></div>
    <div id="guided-marine-beta" hidden>${MARINE_BETA_NOTICE}</div>
    <div class="welcome-actions" role="group" aria-labelledby="guided-question-heading">
      <button class="setup-choice" data-guided-answer="yes" aria-pressed="false"><strong>Yes, include these alerts</strong></button>
      <button class="setup-choice" data-guided-answer="no" aria-pressed="false"><strong>No, leave these out</strong></button>
    </div>
    <p class="setup-reassurance" id="guided-question-detail"></p>
    <div class="user-step-nav"><button id="guided-question-back" class="setup-back">Back</button><button id="guided-question-next" class="primary" disabled>Next</button></div>
  </section>
  <section id="recommendations-page" hidden aria-labelledby="recommendations-heading">
    <div class="welcome-copy"><h2 id="recommendations-heading">Your alert settings</h2><p id="recommendations-device"></p><p id="recommendations-description"></p></div>
    <div class="recommendation-copy">
      <div id="recommendations-marine-beta" hidden>${MARINE_BETA_NOTICE}</div>
      <h3>Weather basics</h3>
      <p>Recommended alerts for severe storms, hail, flash flooding, fog, strong winds, hurricanes, and winter weather.</p>
      <div id="recommendations-interests" hidden><h3>Based on your answers</h3><dl id="recommendations-interest-list"></dl></div>
      <p class="setup-reassurance">Alerts apply to your selected locations, including while you travel.</p>
    </div>
    <div class="user-step-nav"><button id="recommendations-back" class="setup-back">Back</button><button id="recommendations-next" class="primary">Next</button></div>
  </section>
  <section id="guided-marine-page" hidden aria-labelledby="guided-marine-heading">
    <div class="welcome-copy"><h2 id="guided-marine-heading">When should Special Marine Warnings reach you?</h2><p>Both choices apply only when the warning covers your location.</p></div>
    ${MARINE_BETA_NOTICE}
    <div class="welcome-actions" role="group" aria-labelledby="guided-marine-heading">
      <button class="setup-choice" data-guided-marine-mode="always" aria-pressed="false"><strong>Always warn</strong><span>Include warnings whether my location is on land or water.</span></button>
      <button class="setup-choice" data-guided-marine-mode="on_water" aria-pressed="false"><strong>On or near the water</strong><span>Include warnings on mapped water, or within half a mile of a mapped shoreline away from home. Vehicle activity or Android Auto skips shoreline-only alerts, not mapped-water alerts. On-water locations qualify near home. Requires a fresh, accurate location.</span></button>
    </div>
    ${marineNearbyControls('guided')}
    <div class="user-step-nav"><button id="guided-marine-back" class="setup-back">Back</button><button id="guided-marine-next" class="primary" disabled>Next</button></div>
  </section>`;

export function recommendedAnswers(pages, interests = null) {
  const answers = {};
  for (const page of pages) {
    if (page.kind === 'transition') continue;
    const state = {enabled: !!page.recommended};
    for (const tier of ['advisory', 'watch', 'statement']) state[tier + '_enabled'] = !!page[tier]?.recommended;
    if (interests !== null) {
      for (const question of GUIDED_QUESTIONS) {
        if (typeof interests[question.id] !== 'boolean') continue;
        for (const tier of ['warning', 'advisory', 'watch', 'statement']) {
          const item = tier === 'warning' ? page : page[tier];
          if (item && (item.event_ids || [item.id]).some(event => question.events.includes(event))) {
            state[tier === 'warning' ? 'enabled' : tier + '_enabled'] = interests[question.id];
          }
        }
      }
    }
    // Preserve the existing tornado/severe-thunderstorm automatic-watch rule.
    if (page.watch_automatic) state.watch_enabled = state.enabled;
    answers[page.id] = state;
  }
  return answers;
}

export function installGuidedSetup(root) {
  root.querySelector('#setup-choice-page').innerHTML = SETUP_CHOICES;
  const template = root.ownerDocument.createElement('template');
  template.innerHTML = GUIDED_SCREENS;
  root.querySelector('#welcome-onboarding').insertBefore(template.content, root.querySelector('#alert-dnd-page'));
  const context = root.ownerDocument.createElement('p');
  context.id = 'configuration-device-context';context.className = 'alert-progress';context.hidden = true;
  root.querySelector('#welcome-onboarding > .weather-logo').after(context);
  const notificationDevices = root.ownerDocument.createElement('p');notificationDevices.id = 'notification-devices';
  root.querySelector('#notification-setup-page .welcome-copy').append(notificationDevices);
  const style = root.ownerDocument.createElement('style');
  style.textContent = `.recommendation-copy{max-width:470px;margin:0 auto;line-height:1.55}
    .recommendation-copy h3{font-size:17px;margin:18px 0 8px}.recommendation-copy p{margin:0 0 14px}
    .recommendation-copy dl{margin:0}.recommendation-copy dt{margin-top:12px;font-weight:600}
    .recommendation-copy dd{margin:2px 0 0;color:var(--secondary-text-color)}
    [data-guided-answer][aria-pressed="true"],[data-guided-marine-mode][aria-pressed="true"]{border-color:#67e8f9;background:#67e8f912;color:#67e8f9}
    #welcome-onboarding,#official-report{width:min(700px,calc(100% - 24px));max-height:calc(100dvh - 24px);padding:24px}
    #welcome-onboarding .weather-logo{width:64px;margin:4px auto 12px}
    #welcome-onboarding .welcome-copy{line-height:1.5;margin-bottom:18px}
    #welcome-onboarding .welcome-copy h2{font-size:26px;margin-bottom:12px;line-height:1.25}
    #welcome-onboarding .welcome-actions{gap:10px}
    #welcome-onboarding button:not(.device-help-link){min-height:44px;padding:11px 16px}
    #welcome-onboarding .setup-choice strong{font-size:16px}
    #welcome-onboarding .setup-choice span{font-size:14px;line-height:1.45;margin-top:4px}
    #welcome-onboarding .setup-reassurance{margin-top:14px;line-height:1.45}
    #welcome-onboarding .setup-back{margin:12px auto 0}
    #welcome-onboarding .user-step-nav{margin-top:14px;gap:12px}
    #welcome-onboarding .user-step-nav .setup-back{margin:0}
    #welcome-onboarding .device-help-link{margin-top:6px;min-height:44px}
    #welcome-onboarding .alert-progress{margin-bottom:10px;line-height:1.4}
    #welcome-onboarding .selection-hint{margin:6px auto 4px}
    #welcome-onboarding .alert-descriptions{gap:10px;margin-bottom:16px}
    #welcome-onboarding .tier-card-title{margin-bottom:6px}
    #welcome-onboarding .tier-card-copy{margin-bottom:9px;line-height:1.5}
    #welcome-onboarding .tier-card-copy:last-of-type{margin-bottom:0}
    #welcome-onboarding .card-selection{margin-top:8px}
    #welcome-onboarding .risk-label{margin-bottom:5px}
    #welcome-onboarding .intro-copy{line-height:1.5}
    #welcome-onboarding .intro-copy h3{margin:16px 0 8px}
    #welcome-onboarding .intro-copy dt{margin-top:8px}
    #welcome-onboarding .intro-copy dd{margin-bottom:9px}
    @media(max-width:560px){#welcome-onboarding,#official-report{padding:16px}#welcome-onboarding .weather-logo{width:56px;margin:2px auto 10px}#welcome-onboarding .welcome-copy h2{font-size:22px}}
    @media(max-height:650px){#welcome-onboarding{padding:16px}#welcome-onboarding .weather-logo{width:48px;margin:0 auto 8px}}`;
  root.append(style);
}
