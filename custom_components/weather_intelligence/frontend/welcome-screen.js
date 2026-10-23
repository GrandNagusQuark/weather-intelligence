import {DEVICE_SETUP_SCREENS} from "./device-setup.js?v=5";
import {ALERT_SETUP_SCREENS} from "./alert-setup.js?v=23";
// First-time onboarding never opens the old settings-form wizard implicitly.
export function welcomeRequired(snapshot) {
  return snapshot.onboarding ? !snapshot.onboarding.dashboard_available : !snapshot.profiles?.length;
}

export const WELCOME_SCREEN = `<style>
  :host{display:block;box-sizing:border-box;color:var(--primary-text-color);font-family:inherit}
  *{box-sizing:border-box}[hidden]{display:none!important}
  .welcome-landing{min-height:calc(100dvh - 180px);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:48px 24px;background:radial-gradient(ellipse at 50% 34%,#142f4540,transparent 60%)}
  .weather-logo{width:clamp(180px,26vw,260px);height:auto;display:block;margin:0 auto 22px}
  h1{font-size:clamp(28px,4vw,38px);font-weight:600;letter-spacing:-.025em;margin:0 0 12px}
  .welcome-tagline{max-width:400px;line-height:1.6;color:var(--secondary-text-color);margin:0 0 28px}
  button{font:inherit;cursor:pointer;border:1px solid var(--divider-color,#466079);border-radius:12px;padding:14px 24px;color:var(--primary-text-color);background:var(--card-background-color,#162536)}
  button:focus-visible{outline:3px solid #67e8f9;outline-offset:4px}
  .primary{background:#67e8f9;color:#082331;border-color:#67e8f9;font-weight:650}
  #start-onboarding{min-width:230px}
  dialog{width:min(700px,calc(100% - 32px));max-height:calc(100dvh - 48px);overflow:auto;padding:32px;border:1px solid var(--divider-color,#385267);border-radius:20px;background:var(--card-background-color,#132334);color:inherit}
  dialog::backdrop{background:#000a}dialog .weather-logo{width:100px;margin:12px auto 22px}
  .welcome-copy{text-align:center;line-height:1.6;max-width:510px;margin:0 auto 28px}.welcome-copy h2{font-size:28px;line-height:1.2;margin:0 0 16px}.welcome-copy p{color:var(--secondary-text-color)}
  .welcome-actions{display:grid;gap:14px;max-width:470px;margin:0 auto}.welcome-actions button{width:100%}
  .setup-choice{text-align:left;line-height:1.45}.setup-choice strong{display:block;font-size:17px}.setup-choice span{display:block;font-size:14px;color:var(--secondary-text-color);margin-top:5px;font-weight:400}.setup-choice[aria-pressed="true"]{border-color:#67e8f9;background:#67e8f912}.setup-choice[aria-pressed="true"] strong{color:#67e8f9}
  [data-device-count][aria-pressed="true"]{border-color:#67e8f9;color:#67e8f9;background:#67e8f912}.device-help-link{display:block;background:none;border:0;color:var(--primary-color,#67e8f9);text-decoration:underline;text-underline-offset:3px;font-size:14px;padding:8px;margin:12px auto 0}.setup-user-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;max-width:470px;margin:auto}.setup-user-tile{aspect-ratio:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;overflow-wrap:anywhere;min-width:0}.setup-user-tile[aria-pressed="true"]{border-color:#67e8f9;background:#67e8f912}.user-initials{display:grid;place-items:center;width:58px;height:58px;border-radius:50%;background:var(--secondary-background-color,#263a49);color:#67e8f9;font-size:24px}.user-step-nav{display:flex;justify-content:space-between;align-items:center;max-width:470px;margin:22px auto 0}.user-step-nav .setup-back{margin:0}
  .coming-soon button{background:var(--secondary-background-color,#25282d);color:var(--secondary-text-color,#aaa);border-color:var(--divider-color,#444)}.coming-soon small{display:block;text-align:center;color:var(--secondary-text-color);margin-top:7px;font-size:12px}.setup-reassurance{text-align:center;color:var(--secondary-text-color);font-size:14px;margin:22px 0 0}.setup-back{margin:18px auto 0;display:block;background:transparent;padding:8px 16px}
  .privacy-action{border-color:#67e8f9;color:#67e8f9;background:transparent}
  .welcome-privacy-link{display:block;width:fit-content;margin:20px auto 0;text-align:center;font-size:14px;color:#67e8f9;text-decoration:underline;text-underline-offset:3px}
  .alert-progress{text-align:center;font-size:13px;color:var(--secondary-text-color);margin:0 0 16px}.alert-explanation{max-width:470px;margin:0 auto 24px;line-height:1.6}.alert-explanation h3{font-size:16px;margin:0 0 8px}.alert-explanation p{margin:0 0 14px}.alert-action{color:var(--secondary-text-color)}.alert-included{font-size:14px}.alert-answer-buttons{max-width:470px;margin:auto;display:grid;grid-template-columns:1fr 1fr;gap:12px}.alert-answer-buttons [aria-pressed="true"],[data-dnd-answer][aria-pressed="true"]{border-color:#67e8f9;background:#67e8f912;color:#67e8f9}
  .alert-descriptions{max-width:560px;margin:0 auto 24px;display:grid;gap:12px}.alert-descriptions .alert-explanation{max-width:none;margin:0;min-width:0}.alert-descriptions.paired{grid-template-columns:1fr}.paired .alert-explanation{border:1px solid var(--divider-color,#385267);border-radius:12px;padding:16px}.alert-explanation p:last-child{margin-bottom:0}.alert-watch-choice{max-width:470px;margin:18px auto 0}.alert-watch-choice label{display:flex;align-items:center;gap:10px;min-height:44px;cursor:pointer}.alert-watch-choice input{width:20px;height:20px;accent-color:#67e8f9}.alert-watch-note{max-width:470px;margin:10px auto 16px;line-height:1.5;font-size:14px;color:var(--secondary-text-color)}.alert-watch-choice .alert-watch-note{margin-bottom:0}@media(max-width:560px){.alert-descriptions.paired{grid-template-columns:1fr}}
  .device-selection{max-width:470px;margin:0 auto}.device-selection label{display:block;margin-bottom:10px;font-size:15px}.device-selection select{display:block;width:100%;min-height:50px;font:inherit;padding:12px;border:1px solid var(--divider-color,#466079);border-radius:12px;color:var(--primary-text-color);background:var(--card-background-color,#162536)}.device-selection select:focus-visible{outline:3px solid #67e8f9;outline-offset:3px}.device-selection p{font-size:14px;line-height:1.5;color:var(--secondary-text-color)}
  .dialog-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.dialog-heading h2{margin:0}.close-dialog{display:block;margin-left:auto;padding:8px 12px;background:transparent;color:var(--secondary-text-color)}
  #welcome-status{min-height:1.4em;text-align:center}button:disabled{opacity:.5;cursor:default}a{color:#67e8f9}
  @media(max-width:560px){dialog{padding:20px}.welcome-landing{padding:32px 20px}.welcome-copy h2{font-size:24px}}
</style>
<main class="welcome-landing">
  <img class="weather-logo" src="/weather_intelligence_static/weather-logo.svg" alt="Weather Intelligence logo" width="240" height="240">
  <h1>Weather Intelligence</h1>
  <p class="welcome-tagline">Weather awareness, built around you.<br>Powered by your Home Assistant.</p>
  <button id="start-onboarding" class="primary">Start onboarding</button>
  <button id="landing-about" class="setup-back">About Weather Intelligence</button>
</main>
<dialog id="welcome-onboarding" aria-labelledby="welcome-heading">
  <button id="welcome-close" class="close-dialog" aria-label="Close welcome">Close</button>
  <img class="weather-logo" src="/weather_intelligence_static/weather-logo.svg" alt="" width="100" height="100">
  <p id="admin-edit-notice" role="note" hidden style="max-width:510px;margin:0 auto 20px;line-height:1.5">Changes you save to another user’s settings will automatically notify that user.</p>
  <section id="welcome-page"><div class="welcome-copy"><h2 id="welcome-heading">Welcome to Weather Intelligence</h2><p>We'll guide you through setup, one step at a time.</p></div>
  <div class="welcome-actions"><button id="begin-onboarding" class="primary">Begin onboarding</button></div><a id="welcome-privacy" class="welcome-privacy-link" href="#weather-intelligence-privacy">How do we manage your privacy?</a></section>
  <section id="setup-choice-page" hidden aria-labelledby="setup-choice-heading"><div class="welcome-copy"><h2 id="setup-choice-heading">How would you like to set up?</h2></div><div class="welcome-actions">
    <button class="setup-choice" data-setup-mode="quick" aria-pressed="false"><strong>Quick setup</strong><span>Set up your devices and receive weather notifications with recommended settings.</span></button>
    <button class="setup-choice" data-setup-mode="custom" aria-pressed="false"><strong>Custom setup</strong><span>Choose your alerts, devices, and preferences.</span></button>
  </div><p class="setup-reassurance">You can change your choices later.</p><button id="setup-choice-back" class="setup-back">Back</button></section>
  ${DEVICE_SETUP_SCREENS}
  ${ALERT_SETUP_SCREENS}
  <p id="welcome-status" role="status"></p>
</dialog>
<dialog id="official-report" aria-labelledby="dialog-heading"><div class="dialog-heading"><h2 id="dialog-heading">Privacy</h2><button id="close-report">Close</button></div><div id="report-content"></div></dialog>`;
