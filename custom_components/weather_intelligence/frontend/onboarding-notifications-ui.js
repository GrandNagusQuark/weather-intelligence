import './android-sound-guide.js?v=4';
import {ABOUT_STYLE,renderSources} from './about-ui.js?v=1';
import {REPORTING_DISCLOSURE,OUTAGE_REPORTING_NOTICE} from './reporting-settings-ui.js?v=8';

export const NOTIFICATION_SCREENS = `
<style>
  .notification-copy{max-width:490px;margin:0 auto;text-align:left;line-height:1.45}
  .notification-copy h3{font-size:17px;margin:12px 0 8px}.notification-copy p{margin:10px 0}
  .notification-copy ol{padding-left:22px}.notification-copy li{margin:7px 0}
  .notification-copy details{margin:12px 0}.notification-copy summary{cursor:pointer;color:var(--primary-color)}
  .notification-copy .notification-note{font-size:13px;color:var(--secondary-text-color)}
  .notification-copy .notification-check{display:flex;align-items:flex-start;gap:10px;margin:16px 0}
  .notification-copy input{width:20px;height:20px;flex-shrink:0}.notification-copy button{min-height:44px}
  .notification-review-device{border:1px solid var(--divider-color);border-radius:12px;padding:12px;margin:10px 0}
  #notification-status{font-size:13px;min-height:1em}#notification-person{width:100%;min-height:44px}
  #notification-setup-page .user-step-nav,#notification-review-page .user-step-nav{position:sticky;bottom:0;background:var(--card-background-color,#132334);padding:12px 0;z-index:2;gap:12px}
</style>
<section id="notification-setup-page" hidden aria-labelledby="notification-setup-heading">
  <p class="alert-progress" id="notification-progress"></p>
  <div class="welcome-copy"><h2 id="notification-setup-heading">Notification setup</h2><p id="notification-phone"></p></div>
  <div class="notification-copy" id="notification-body"></div>
  <p class="notification-copy notification-note" id="notification-next-help" role="status"></p>
  <div class="user-step-nav"><button id="notification-setup-back" class="setup-back">Back</button><button id="notification-next" class="primary">Next</button></div>
</section>
<section id="notification-review-page" hidden aria-labelledby="notification-review-heading">
  <div class="welcome-copy"><h2 id="notification-review-heading">Ready to enable your alerts?</h2><p>Review the phones and settings below.</p></div>
  <div class="notification-copy"><div id="notification-review-devices"></div><label id="notification-person-label">Home Assistant person<select id="notification-person"></select></label><p id="notification-person-help" class="notification-note"></p>
    <p>Finishing enables real weather notifications on these phones. Phone permissions remain controlled by each phone.</p></div>
  <div class="user-step-nav"><button id="notification-review-back" class="setup-back">Back</button><button id="notification-finish" class="primary">Enable alerts and finish</button></div>
</section>
<section id="notification-complete-page" hidden aria-labelledby="notification-complete-heading">
  <div class="welcome-copy"><h2 id="notification-complete-heading">Onboarding complete</h2><p id="notification-complete-message">Your device choices are saved.</p><p id="notification-restart-note">Please restart Home Assistant to finish applying your setup. If you have already restarted since saving, you do not need to restart again.</p><p>Weather Intelligence supplements your other warning sources.</p></div>
  <style>${ABOUT_STYLE}</style><div class="notification-copy"><details id="notification-source-directory"><summary>Sources of alert information</summary><div id="notification-sources"></div></details></div>
  <div class="notification-copy" id="notification-reporting-offer" hidden>
    <h3>Would you like to share error reports?</h3>
    <p>This optional choice applies to this Home Assistant installation. It is separate from phone setup and does not affect weather alerts.</p>
    <details><summary>What is shared and how it is used</summary><p>${REPORTING_DISCLOSURE}</p><h4>Separate outage contributions</h4><p>${OUTAGE_REPORTING_NOTICE}</p></details>
    <button id="notification-reporting-review">Review optional error reporting</button>
    <p class="notification-note">You can choose Done without enabling reporting. Any existing reporting choice is preserved.</p>
  </div>
  <p class="notification-copy notification-note" id="notification-reporting-administrator" hidden>Optional reporting is a separate choice for the Home Assistant installation administrator. Setting up this phone does not enable it.</p>
  <div class="user-step-nav"><button id="notification-revisit" class="setup-back">Review or change setup</button><button id="notification-done" class="primary">Done</button></div>
</section><p id="notification-status" role="status"></p>`;

export function notificationPhase(device) {
  if (!device || device.error) return 'unavailable';
  if (!device.permissions) return 'permissions';
  if (!device.test_confirmed) return 'test';
  if (device.dnd?.length && !device.critical_confirmed) return 'critical';
  return 'ready';
}

export function installNotificationSetup(root, {send, escape, done, revisit=()=>{}, about=()=>null, canReviewReporting=()=>false, reviewReporting=()=>{}}) {
  const placeholder = root.querySelector('#notification-setup-page');
  const template = root.ownerDocument.createElement('template');
  template.innerHTML = NOTIFICATION_SCREENS;
  placeholder.replaceWith(template.content);
  const q = selector => root.querySelector(selector);
  let current = null, stage = null, busy = false, message = '', person_id = '';
  const attempted = new Set();
  async function act(action, extra = {}) {
    if (busy || !current?.device) return;
    busy = true; message = '';
    if(action==='simplify_channel')attempted.delete(current.device.id);
    render(current, stage);
    try { await send(action, {device_id: current.device.id, ...extra}); }
    catch (error) { message = error.message || 'Could not save this step. Please try again.'; }
    finally { busy = false; render(current, stage); }
  }
  q('#notification-setup-back').onclick = () => act('back');
  q('#notification-review-back').onclick = () => act('back');
  q('#notification-next').onclick = () => act('next');
  q('#notification-finish').onclick = () => act('finish', {person_id});
  q('#notification-done').onclick = done;
  q('#notification-revisit').onclick = revisit;
  q('#notification-reporting-review').onclick = reviewReporting;
  q('#notification-person').onchange = event => { person_id = event.target.value; render(current, stage); };
  q('#notification-body').onclick = event => {
    const button = event.target.closest('[data-notification-action]');
    if (button) act(button.dataset.notificationAction, button.hasAttribute('data-confirm') ? {value:true} : button.hasAttribute('data-value') ? {value:button.dataset.value === 'true'} : {});
  };
  q('#notification-body').onchange = event => {
    if (event.target.id === 'notification-permissions') act('permissions', {value:event.target.checked});
  };
  function render(view, next_stage) {
    if(next_stage==='notification_complete'){
      q('#notification-sources').innerHTML=renderSources(about(),{expanded:true});
      q('#notification-reporting-offer').hidden=!canReviewReporting();
      q('#notification-reporting-administrator').hidden=canReviewReporting();
      q('#notification-complete-message').textContent = view?.activation === 'active'
        ? 'Your device choices are saved and weather notifications are enabled.'
        : view?.activation === 'failed'
        ? 'Your choices are saved, but automatic activation did not complete. Restart Home Assistant before relying on these settings for alerts.'
        : 'Your device choices are saved. Restart Home Assistant to finish applying your setup.';
    }
    if (!view) return;
    current = view; stage = next_stage;
    const device = view.device;
    if (!device) return;
    const phase = notificationPhase(device);
    q('#notification-progress').textContent = `Phone ${view.index + 1} of ${view.count}`;
    q('#notification-phone').textContent = device.name;
    let body = '';
    if (!view.can_manage) {
      body = '<p>Only this account or an active administrator can configure this phone. Sign in with the appropriate account to continue.</p>';
    } else if (phase === 'unavailable') {
      body = `<p>${escape(device.error || 'Choose an available phone to continue.')}</p>`;
    } else if (phase === 'permissions') {
      const dnd = device.dnd?.length > 0;
      if (device.platform === 'android') {
        body = `<h3>Choose your phone settings</h3><p><strong>Samsung phone with no Notification categories option?</strong> First open <strong>Settings → Notifications → Advanced settings</strong> and turn on <strong>Manage notification categories for each app</strong>. Then return to Home Assistant’s notification settings. Other Android phones may call these channels or notification types.</p><ol><li>On <strong>${escape(device.name)}</strong>, allow Home Assistant notifications.</li>${dnd ? `<li>Weather Siren uses Companion’s alarm audio channel, shown on Android as <strong>${escape(device.urgent_channel)}</strong>. Open <strong>Settings → Apps → Home Assistant → Notifications → Notification categories</strong>, choose that category, select <strong>Alert</strong>, and choose a sound.</li><li>In the phone’s Do Not Disturb settings, allow <strong>Alarms</strong>. Do not add Home Assistant as an app-wide exception. Only the alerts you selected for bypass use this alarm route; routine Weather Intelligence notifications stay on normal channels.</li>` : '<li>Normal phone sound and Do Not Disturb settings apply.</li><li>The ordinary test on the next screen creates the Weather Alerts category. You can change its sound in notification settings afterward.</li>'}</ol>
          ${dnd ? '<p>If the alarm category is missing, use Create siren category below when it is safe to make sound. Companion creates or restores it when a notification arrives. Opening this screen does not send anything.</p>' : ''}
          ${device.urgent_channel&&device.urgent_channel!=='alarm_stream'&&dnd?'<p>This saved custom category does not have Companion’s alarm audio behavior. Restore the alarm route, then review its sound and phone settings.</p><button data-notification-action="simplify_channel">Restore alarm siren route</button>':''}
          <p class="notification-note">Samsung may not show an Ignore DND switch for individual categories. This route uses alarm audio, not an exception for all Home Assistant notifications. It still depends on the phone allowing alarms during DND. Confirm both tone and speech with the DND test before relying on it.</p>
          <p class="notification-note">Pop-up notifications and lock-screen visibility are optional but recommended. Showing content on the lock screen also makes it readable to others.</p>
          ${dnd ? `<details><summary>Show the illustrated Android guide</summary><android-sound-guide channel-name="${escape(device.urgent_channel)}"></android-sound-guide></details>` : ''}`;
      } else if (device.platform === 'ios') {
        body = `<h3>Choose your iPhone settings</h3><ol><li>Open <strong>iPhone Settings → Notifications → Home Assistant</strong> and turn on <strong>Allow Notifications</strong> and <strong>Sounds</strong>.</li><li>${dnd ? 'Allow Critical Alerts so your chosen bypass alerts can sound during Focus or silent mode.' : 'Weather Intelligence will not request DND bypass. Your normal Focus and sound settings apply.'}</li></ol><p class="notification-note">Lock Screen and Banners are optional but recommended. For spoken alerts, enable Announce Notifications for Home Assistant where your iPhone supports it.</p>`;
      } else body = '<p>This setup currently supports Android phones and iPhones.</p>';
      body += `<p class="notification-note">${device.setup_status === 'uncertain' ? 'Setup delivery could not be confirmed. Check the phone or retry below.' : device.setup_status === 'sent' ? 'The setup notification was sent. Check the phone to confirm it arrived.' : device.platform === 'android' ? 'No setup notification is sent automatically. Creating the siren category may play its saved sound.' : 'Preparing the setup notification…'}</p>
        ${device.platform === 'android' ? (dnd ? '<button data-notification-action="retry_prepare">Create siren category (may play sound)</button>' : '') : device.setup_attempted ? '<button data-notification-action="retry_prepare">Resend setup notification</button>' : ''}
        <label class="notification-check"><input id="notification-permissions" type="checkbox">I have configured these notification settings on this phone.</label>`;
      if (!device.setup_attempted && device.platform !== 'android') body = `<p>Preparing notification setup for this phone…</p>${attempted.has(device.id) && !busy ? '<button data-notification-action="retry_prepare">Retry setup notification</button>' : ''}`;
    } else if (phase === 'test') {
      body = `<h3>Check that notifications arrive</h3><p>Send a clearly labeled test to <strong>${escape(device.name)}</strong>. This test uses normal notification settings.</p>
        <button data-notification-action="test">${device.test_sent ? 'Send another test' : 'Send test notification'}</button>
        ${device.test_sent ? '<p>Did it arrive on this phone?</p><button class="primary" data-notification-action="confirm_test" data-confirm>I received the test</button>' : ''}
        <p class="notification-note">Sending is not proof of delivery. If it does not arrive, check notification permissions and the phone’s connection before retrying.</p><button data-notification-action="permissions" data-value="false">Review phone settings</button>`;
    } else if (phase === 'critical') {
      body = `<h3>Check Do Not Disturb bypass</h3><p>Turn on Do Not Disturb${device.platform === 'ios' ? ' or Focus' : ''} and lock <strong>${escape(device.name)}</strong>. This test can sound loudly${device.platform === 'android' ? ' and speak' : ''}, even when the phone is silenced.</p>
        <button data-notification-action="test_critical">Send DND bypass test</button>
        ${device.critical_sent ? `<p>Did you hear the test while Do Not Disturb was on?</p><button class="primary" data-notification-action="confirm_critical" data-confirm>${device.platform === 'android' ? 'I heard the tone and speech during DND' : 'I heard the DND bypass test'}</button>` : ''}
        <p class="notification-note">Only start the test when it is safe to make sound. Turn DND back to your preferred setting afterward.</p><button data-notification-action="permissions" data-value="false">Review phone settings</button>`;
    } else {
      body = '<h3>This phone is ready</h3><p>You confirmed its notification settings and test results.</p><p>Continue to the next phone or review your choices before enabling alerts.</p>';
    }
    // Do not replace an open illustrated guide when its automatic setup send returns.
    const retry_setup = !device.setup_attempted && attempted.has(device.id) && !busy;
    const body_key = JSON.stringify([device.id, phase, device.urgent_channel, device.setup_status, device.test_sent, device.critical_sent, view.can_manage, retry_setup]);
    if (q('#notification-body').dataset.renderKey !== body_key) {
      const guide_open = q('#notification-body details')?.open;
      q('#notification-body').innerHTML = body;
      q('#notification-body').dataset.renderKey = body_key;
      if (guide_open && q('#notification-body details')) q('#notification-body details').open = true;
    }
    q('#notification-next').disabled = busy || !view.can_manage || !device.ready;
    q('#notification-next').textContent = view.index + 1 < view.count ? 'Next phone' : 'Review choices';
    q('#notification-next-help').textContent = !view.can_manage ? 'Sign in as this account or an administrator to continue.' : ({
      permissions:'After configuring the phone, select the confirmation checkbox above to continue.',
      test:'After the test arrives, select I received the test. Then continue to the next step.',
      critical:'After the DND test, confirm that you heard both tone and speech. If bypass cannot be verified, go Back and change your DND choices.',
      ready:view.index + 1 < view.count?'This phone is ready. Select Next phone to finish the remaining phone checks.':'This phone is ready. Select Review choices below, then Enable alerts and finish.',
      unavailable:'Resolve the phone setup issue above before continuing.'
    })[phase];
    q('#notification-setup-back').disabled = busy;
    q('#notification-review-back').disabled = busy;
    q('#notification-review-devices').innerHTML = (view.devices || []).map(phone => `<section class="notification-review-device"><h3>${escape(phone.name)}</h3><p>${phone.ready ? 'Phone setup and tests confirmed.' : 'Phone setup needs review.'}</p><details><summary>Do Not Disturb choices</summary>${phone.dnd?.length ? '<ul>' + phone.dnd.map(title => `<li>${escape(title)}</li>`).join('') + '</ul>' : '<p>Respect Do Not Disturb.</p>'}</details><p>Daily outlook: ${phone.daily_outlook ? escape(phone.daily_time) + ' · Home Assistant time' : 'Off'}</p></section>`).join('');
    if (!person_id || !(view.people || []).some(person => person.id === person_id)) person_id = view.person_id || '';
    q('#notification-person-label').hidden = (view.people || []).length < 2;
    q('#notification-person').innerHTML = '<option value="">Choose a linked person</option>' + (view.people || []).map(person => `<option value="${escape(person.id)}">${escape(person.name)}</option>`).join('');
    q('#notification-person').value = person_id;
    q('#notification-person-help').textContent = !view.people?.length ? 'The selected account needs a linked Home Assistant Person for location-based alerts. An administrator can link one under Settings → People.' : '';
    q('#notification-finish').disabled = busy || !view.can_manage || !person_id || !view.devices?.every(phone => phone.ready);
    q('#notification-status').hidden = !['notification_setup', 'notification_review'].includes(stage);
    q('#notification-status').textContent = message || (busy ? 'Saving…' :
      (phase === 'test' && device.test_status === 'uncertain') || (phase === 'critical' && device.critical_status === 'uncertain')
      ? 'Test delivery is uncertain. Check the phone before retrying.' : '');
    const permission_check = q('#notification-body').querySelector('#notification-permissions');
    if (permission_check) permission_check.checked = device.permissions === true;
    q('#notification-body').querySelectorAll('button,input').forEach(control => {control.disabled = busy || !view.can_manage;});
    if (!busy && stage === 'notification_setup' && view.can_manage && !device.error && !device.setup_attempted && !attempted.has(device.id)) {
      attempted.add(device.id);
      queueMicrotask(() => act('prepare'));
    }
  }
  return {render};
}
