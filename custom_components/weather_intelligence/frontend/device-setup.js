// Production screens; account/role data always comes from authenticated HA.
export const DEVICE_SETUP_SCREENS = `<section id="device-setup-page" hidden aria-labelledby="device-setup-heading">
  <div class="welcome-copy"><h2 id="device-setup-heading">Device setup</h2><p id="device-setup-for" hidden></p></div>
  <div class="welcome-actions"><button data-device-count="single">Set up a single device</button><button data-device-count="multiple">Set up multiple devices</button><button id="setup-other-device" hidden>Set up someone else's device</button></div>
  <p class="setup-reassurance" id="device-ownership-note">Non-admin users can only set up their own devices.</p>
  <button class="setup-back" id="device-setup-back">Back</button>
</section>
<section id="single-device-page" hidden aria-labelledby="single-device-heading">
  <div class="welcome-copy"><h2 id="single-device-heading">Set up a single device</h2><p id="single-device-for" hidden></p></div>
  <div class="device-selection"><label for="single-device-select">Choose your device</label><select id="single-device-select"><option value="">Select a device</option></select><p id="single-device-empty" hidden>No devices are available for this account.</p><p id="single-device-unavailable" hidden>Your previously selected device is no longer available. Choose another device.</p></div>
  <button class="device-help-link" data-device-help>Device not listed?</button>
  <div class="user-step-nav"><button class="setup-back" id="single-device-back">Back</button><button id="single-device-next" class="primary" disabled>Next</button></div>
</section>
<section id="single-device-setup-page" hidden aria-labelledby="single-device-setup-heading">
  <div class="welcome-copy"><h2 id="single-device-setup-heading">Choose your alerts</h2><p id="selected-device-name"></p></div>
  <div class="welcome-actions">
    <button class="setup-choice" data-alert-path="life_only" aria-pressed="false"><strong>Life-threatening alerts only</strong></button>
    <button class="setup-choice" data-alert-path="life_plus" aria-pressed="false"><strong>Life-threatening alerts plus additional alerts</strong><span>Choose additional alerts one page at a time.</span></button>
    <button class="setup-choice" data-alert-path="all" aria-pressed="false"><strong>All alerts</strong><span>Every supported alert type.</span></button>
    <button class="setup-choice" data-alert-path="choose_all" aria-pressed="false"><strong>Choose all alerts page by page</strong><span>Decide individually which alerts you want.</span></button>
  </div>
  <div class="user-step-nav"><button class="setup-back" id="single-device-setup-back">Back</button><button id="alert-path-next" class="primary" disabled>Next</button></div>
</section>
<section id="setup-users-page" hidden aria-labelledby="setup-users-heading">
  <div class="welcome-copy"><h2 id="setup-users-heading">Whose device are you setting up?</h2></div>
  <div id="setup-user-tiles" class="setup-user-tiles" role="group" aria-label="Home Assistant users"></div>
  <div class="user-step-nav"><button class="setup-back" id="setup-users-back">Back</button><button id="setup-users-next" class="primary" disabled>Next</button></div>
</section>`;

export const DEVICE_HELP = `<h3>Device not listed?</h3><p>To appear in device setup, a device needs to be registered with the Home Assistant Companion app on this installation.</p><ul><li>Open the Companion app on that device and sign in to this Home Assistant server.</li><li>Use the Home Assistant account that owns the device.</li><li>If you just added the device, finish Companion setup, then reopen Weather Intelligence.</li></ul><p>Devices on a different server or under a different account won’t appear in your own-device list.</p>`;

export function accountTiles(users, selected, escape) {
  return users.map(user=>{
    const initials=user.name.trim().split(/\s+/).slice(0,2).map(word=>Array.from(word)[0]||"").join("").toUpperCase();
    return `<button class="setup-user-tile" data-setup-user="${escape(user.id)}" aria-pressed="${user.id===selected}"><span class="user-initials" aria-hidden="true">${escape(initials)}</span><span>${escape(user.name)}</span></button>`;
  }).join("") || '<p>No other active Home Assistant users are available.</p>';
}
