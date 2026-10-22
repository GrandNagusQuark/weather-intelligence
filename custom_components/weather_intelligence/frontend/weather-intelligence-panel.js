import "./weather-map.js?v=individual-alerts-1";
import {AndroidOnboarding, ANDROID_SOUND_STEPS} from "./android-onboarding.js?v=2";
import {WELCOME_SCREEN, welcomeRequired} from "./welcome-screen.js?v=35";
import {installProductionOnboarding} from "./onboarding-flow.js?v=15";
import {installSavedDeviceSettings} from "./saved-device-settings.js?v=1";
import {renderAdminActionNotice} from "./admin-action-notice.js?v=1";
import {ProfileAlertEditor} from "./profile-alert-editor.js?v=10";
import {DEVICE_HELP, accountTiles} from "./device-setup.js?v=5";
import {renderAlertSetup} from "./alert-setup.js?v=23";
import {PANEL_NAVIGATION, openHomeAssistantMenu, returnToWeatherIntelligence} from "./panel-navigation.js?v=2";
import {renderAbout} from "./about-ui.js?v=2";
import {mountReporting,REPORTING_DISCLOSURE,OUTAGE_REPORTING_NOTICE} from "./reporting-settings-ui.js?v=6";
import {mountOutages} from "./outage-settings-ui.js?v=4";
import {FEEDBACK_BAR,mountFeedback} from "./feedback-ui.js?v=1";

export function overviewSummary(summary) {
  // Compatibility with the older API wording; health belongs outside the forecast.
  return String(summary || "").replace(/\s*Some coverage is unavailable\.\s*$/, "")
    .replace(/No current weather concerns listed\.\s*$/, "No current weather concerns.").trim() || "Today's forecast is not available yet.";
}

export function sourceHealthNote(outlook) {
  const states=Object.values(outlook.sources || {});
  return states.some(state=>state === "degraded" || state === "stale") ? "Some enabled weather sources are unavailable or outdated." : "";
}

export function selectedAlertEvents(profile, choices) {
  // Opening existing setup is not permission to replace its saved choices.
  if (Array.isArray(profile.alert_events)) return [...profile.alert_events];
  const families=profile.hazard_families || [];
  return choices.filter(choice=>!families.length || families.includes(choice.family)).map(choice=>choice.value);
}

export function recommendedAlertEvents(choices) {
  return choices.filter(choice=>choice.default).map(choice=>choice.value);
}

function newProfileId() {
  // Home Assistant is also commonly accessed over a local HTTP connection,
  // where randomUUID is unavailable but getRandomValues is supported.
  return [...crypto.getRandomValues(new Uint8Array(16))].map(value=>value.toString(16).padStart(2,"0")).join("");
}

export function enqueueOnboardingSave(previous, save) {
  return Promise.resolve(previous).catch(()=>{}).then(save);
}

class WeatherIntelligencePanel extends HTMLElement {
  constructor() {super(); this.attachShadow({mode:"open"});}
  set narrow(value) {this._narrow=Boolean(value);this.toggleAttribute("narrow",this._narrow);}
  get narrow() {return this._narrow;}
  set hass(value) {
    this._hass = value;
    if (!this._loaded) this._load();
    else if (this._config) this._updateMapPeople();
  }

  connectedCallback() {
    this._refreshTimer = setInterval(() => {
      if (!document.hidden && this._config && !welcomeRequired(this._config) && this.isConnected) this._refreshDashboard();
    }, 30000);
  }

  disconnectedCallback() {clearInterval(this._refreshTimer);}

  async _load() {
    this._loaded = true;
    this.shadowRoot.innerHTML=PANEL_NAVIGATION+'<p role="status">Loading Weather Intelligence…</p>';
    this._bindNavigation();
    try {
      const setup=await this._hass.callWS({type:"weather_intelligence/onboarding/get"});
      this._config=setup.actor.is_admin && setup.onboarding.dashboard_available ? {...await this._hass.callWS({type:"weather_intelligence/config/get"}),actor:setup.actor,setup_users:setup.setup_users,setup_devices:setup.setup_devices,target_user:setup.target_user,onboarding:setup.onboarding,admin_notice:setup.admin_notice} : setup;
      this._render();
    } catch (error) {
      this._loaded = false;
      this.shadowRoot.innerHTML = `${PANEL_NAVIGATION}<ha-alert alert-type="error">Unable to load Weather Intelligence. Check your connection and Home Assistant sign-in.</ha-alert>`;
      this._bindNavigation();
    }
  }

  _render() {
    const c = this._config;
    if (welcomeRequired(c)) {this._renderWelcome();return;}
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;padding:24px;max-width:1000px;margin:auto;color:var(--primary-text-color)}
      h1{font-size:28px} ha-card{display:block;padding:20px;margin:16px 0;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
      label{display:block;margin:10px 0}input,select{box-sizing:border-box;width:100%;padding:10px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:inherit}
      .check{display:flex;gap:9px;align-items:center}.check input{width:auto}.profile{border-top:1px solid var(--divider-color);padding-top:16px;margin-top:16px}.actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.danger{color:var(--error-color)}button{padding:10px 16px;border:0;border-radius:8px;cursor:pointer;color:var(--primary-text-color);background:var(--secondary-background-color);font:inherit}.primary{background:var(--primary-color);color:var(--text-primary-color)}
      .mobile-setup{border-top:1px solid var(--divider-color);padding-top:14px;margin-top:14px}.steps{line-height:1.55}.setup-result{min-height:1.4em}
      small{color:var(--secondary-text-color)}
      [hidden]{display:none!important}h2{font-size:20px;margin:0 0 14px}h3{margin:0 0 10px}.heading{display:flex;align-items:center;justify-content:space-between;gap:12px}
      .user-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.user-grid ha-card{margin:0;min-width:0}.badge{font-size:12px;border-radius:20px;padding:5px 10px;background:var(--secondary-background-color);white-space:nowrap}
      .alert-row{border-top:1px solid var(--divider-color);padding-top:12px;margin-top:12px}.alert-row.critical{border-left:3px solid var(--error-color);padding-left:10px}.ack{font-size:13px}.ack.yes{color:var(--success-color,#2d9b61)}
      .text-button{background:none;padding:0;color:var(--primary-color);font:inherit;text-align:left}.outlook{border-top:1px solid var(--divider-color);padding:14px 0}.outlook:first-child{border:0}.outlook summary{cursor:pointer;font-weight:600}.outlook p{margin:8px 0}.report-item{margin:14px 0}.report-item small{display:block;margin:5px 0}
      .bottom-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;width:100%;margin:24px 0}.bottom-actions button{width:100%;min-width:0}dialog{box-sizing:border-box;max-width:780px;width:calc(100% - 32px);max-height:85vh;border:1px solid var(--divider-color);border-radius:12px;padding:24px;background:var(--card-background-color,#fff);color:var(--primary-text-color)}dialog::backdrop{background:#0008}dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.5}a{color:var(--primary-color)}.steps li{margin-bottom:8px}
      .privacy-button{display:block;width:100%;padding:14px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);font-size:14px;margin:12px 0 26px}
      #android-onboarding{max-width:620px}.setup-progress{color:var(--secondary-text-color);font-size:13px}.setup-modes{display:grid;grid-template-columns:1fr 1fr;gap:12px}.setup-nav{border-top:1px solid var(--divider-color);padding-top:16px}.setup-nav .primary{margin-left:auto}#setup-status{min-height:1.4em}button:disabled{opacity:.55;cursor:default}dt{color:var(--secondary-text-color);margin-top:10px}dd{margin:3px 0 12px}
      @media(max-width:560px){:host{padding:14px}.user-grid,.bottom-actions{grid-template-columns:1fr}ha-card{padding:16px}.heading{align-items:flex-start}h1{font-size:24px}}
    </style>${PANEL_NAVIGATION}${FEEDBACK_BAR}
    <h1>Weather Intelligence</h1>${renderAdminActionNotice(c.admin_notice,value=>this._escape(value))}
    <div id="overview-view">
      <ha-card><div class="heading"><h2>Radar &amp; warning polygons</h2><small>Latest available NOAA/NWS data</small></div><weather-radar-map basemap="openfreemap"></weather-radar-map></ha-card>
      <p id="overview-health" role="status"></p>
      <h2>Your household</h2><div id="user-grid" class="user-grid"></div>
      <ha-card><h2>Your day today</h2><div id="outlooks"></div></ha-card>
      <div class="bottom-actions"><button data-view="general">Settings</button><button data-view="users">User settings</button><button data-view="onboarding" class="primary">Review setup or add devices</button></div>
      <div class="actions"><button id="about-button">About Weather Intelligence</button></div>
      <button id="privacy-button" class="privacy-button">How do we manage your privacy?</button>
    </div>
    <div id="settings-view" hidden><div class="actions"><button data-view="overview">← Back to overview</button><h2 id="settings-heading">Set up weather alerts</h2></div>
    <p role="note" data-group="users">Changes you save to another user’s settings will automatically notify that user.</p>
    <ha-card data-group="general"><h2>Daily safety briefing</h2><div class="grid"><label>Delivery time<input id="briefing-time" type="time" value="${this._escape(c.briefing_time)}"></label></div></ha-card>
    <ha-card data-group="general"><h2>Official supplemental sources</h2>
      ${this._sourceCheck("mrms_hail_tracking_enabled", "NOAA MRMS radar hail tracking")}
      ${this._sourceCheck("spc_outlooks_enabled", "SPC convective and fire outlooks")}
      ${this._sourceCheck("wssi_enabled", "NWS Winter Storm Severity Index")}
      ${this._sourceCheck("airnow_enabled", "EPA AirNow")}
      <label>AirNow API key <input id="airnow-key" type="password" autocomplete="new-password" placeholder="${c.sources.airnow_api_key_configured ? "Configured — leave blank to keep" : "Optional credential"}"></label>
      ${this._sourceCheck("uv_enabled", "Official UV product")}
      <small>Unavailable or unconfigured sources are shown honestly and never interpreted as low risk.</small>
    </ha-card>
    <ha-card data-group="general"><h2>Developer error forwarding</h2>
      <p>Maintainer reports use a separate destination and explicit consent.</p><button id="reporting-settings">Configure optional error reporting</button>
      <label class="check"><input id="mqtt-error-logging" type="checkbox" ${c.developer_logging.configured ? "checked" : ""}>Send Weather Intelligence errors over MQTT</label>
      <label>MQTT topic<input id="mqtt-error-topic" value="${this._escape(c.developer_logging.topic)}"></label>
      <small>Publishes redacted, non-retained JSON at QoS 1. Published: ${c.developer_logging.published_errors}; failed publishes: ${c.developer_logging.failed_publishes}.${c.developer_logging.last_failure ? " " + this._escape(c.developer_logging.last_failure) : ""}</small>
    </ha-card>
    <ha-card data-group="users"><h2>Household users</h2><div id="profiles"></div><button id="add">Add person</button></ha-card>
    <ha-card data-group="users"><h2>Mobile alert setup</h2><p>Finish permissions on each phone, then send a safe test before relying on critical alerts.</p><div id="mobile-setup"></div></ha-card>
    <div class="actions"><button id="save" class="primary">Save changes</button><span id="result" role="status"></span></div></div>
    <dialog id="official-report" aria-labelledby="dialog-heading"><div class="heading"><h2 id="dialog-heading">Official report</h2><button id="close-report">Close</button></div><div id="report-content"></div></dialog>
    <dialog id="android-onboarding" aria-labelledby="android-setup-heading"></dialog>`;
    this._bindNavigation();
    this.shadowRoot.querySelector('#give-feedback').onclick=()=>this._showFeedback();
    this._alertEditor=new ProfileAlertEditor(this.shadowRoot,{escape:value=>this._escape(value)});
    this._renderProfiles();
    installSavedDeviceSettings(this);
    this._renderMobileSetup();
    this.shadowRoot.querySelector("#add").onclick = () => { this._profilesDirty=true;c.profiles.push(this._newProfile()); this._renderProfiles(); };
    this.shadowRoot.querySelector("#save").onclick = () => this._save();
    this.shadowRoot.querySelectorAll("[data-view]").forEach(button => button.onclick = () => this._switchView(button.dataset.view));
    this.shadowRoot.querySelector("#close-report").onclick = () => this.shadowRoot.querySelector("#official-report").close();
    this.shadowRoot.querySelector("#privacy-button").onclick = () => this._showPrivacy();
    this.shadowRoot.querySelector("#about-button").onclick = () => this._showAbout();
    this.shadowRoot.querySelector("#reporting-settings").onclick = () => this._showReporting();
    this._renderDashboard();
    this._switchView(new URLSearchParams(window.location.search).has("mobile_setup") ? "onboarding" : this._view || "overview");
  }

  _switchView(view) {
    if (welcomeRequired(this._config)) {this._openWelcome();return;}
    if(view==="onboarding"){this._revisitOnboarding();return;}
    this._view = view;
    this.shadowRoot.querySelector("#overview-view").hidden = view !== "overview";
    this.shadowRoot.querySelector("#settings-view").hidden = view === "overview";
    this.shadowRoot.querySelectorAll("[data-group]").forEach(card => card.hidden =
      view === "overview" || !(card.dataset.group === view || (view === "onboarding" && card.dataset.group === "users")));
    this.shadowRoot.querySelector("#settings-heading").textContent = view === "general" ? "Settings" : view === "users" ? "User settings" : "Set up weather alerts";
    if (view === "overview") this._refreshDashboard();
  }

  async _startAndroidSetup(profileId) {
    if (welcomeRequired(this._config)) {this._openWelcome();return;}
    if(this._openingSetup)return;
    if(this._profilesDirty && !confirm("Discard unsaved user-setting edits before opening guided onboarding?"))return;
    this._openingSetup=true;
    try {
      const snapshot=await this._hass.callWS({type:"weather_intelligence/config/get"});
      if(this._profilesDirty){this._config.profiles=snapshot.profiles;this._profilesDirty=false;this._renderProfiles();this._renderMobileSetup();}
      const requested=profileId || new URLSearchParams(window.location.search).get("mobile_setup");
      if(snapshot.profiles.find(p=>p.profile_id===requested)?.mobile_platform==="ios") {this._switchView("users");return;}
      const dialog=this.shadowRoot.querySelector("#android-onboarding");
      if(dialog.open)return;
      this._androidSetup=new AndroidOnboarding(dialog,{
        snapshot,newProfile:()=>this._newProfile(),escape:value=>this._escape(value),
        save:async(profile,expected)=>{
          const reply=await this._hass.callWS({type:"weather_intelligence/config/profile/update",profile,expected_profile:expected});
          const saved=reply.profile;
          const index=this._config.profiles.findIndex(p=>p.profile_id===saved.profile_id);
          index<0?this._config.profiles.push(saved):this._config.profiles.splice(index,1,saved);
          this._renderProfiles();this._renderMobileSetup();await this._refreshDashboard();return saved;
        },
        send:(id,action,expected)=>this._hass.callWS({type:"weather_intelligence/mobile_setup/android",profile_id:id,action,expected_profile:expected}),
      });
      this._androidSetup.open(requested);
    }catch(error){this.shadowRoot.querySelector("#overview-health").textContent="Could not open setup: "+(error.message||"Check the connection.");}
    finally{this._openingSetup=false;}
  }

  async _revisitOnboarding() {
    if(this._openingSetup)return;
    if(this._profilesDirty&&!confirm("Discard unsaved user-setting edits before opening onboarding?"))return;
    this._openingSetup=true;
    try {
      const setup=await this._hass.callWS({type:"weather_intelligence/onboarding/get"});
      this._config={...this._config,...setup};
      this._profilesDirty=false;this._welcomeRevisit=true;
      this._renderWelcome();this._openWelcome();
    }catch(error){this.shadowRoot.querySelector('#overview-health').textContent=error.message||'Could not open onboarding.';}
    finally{this._openingSetup=false;}
  }

  async _refreshDashboard() {
    if (welcomeRequired(this._config)) return;
    if (this._refreshing) return;
    this._refreshing = true;
    try {
      this._config.dashboard = await this._hass.callWS({type:"weather_intelligence/dashboard/get"});
      this._renderDashboard();
    } catch (_error) {
      this.shadowRoot.querySelector("#overview-health").textContent = "Overview unavailable. Existing cards may be outdated; check official weather sources.";
    } finally {this._refreshing = false;}
  }

  _renderDashboard() {
    if (welcomeRequired(this._config)) return;
    const d = this._config.dashboard || {users:[],outlooks:[],source_health:"starting"};
    const healthy = d.source_health === "healthy";
    this.shadowRoot.querySelector("#overview-health").textContent = healthy ? `Official alert source available · checked ${this._friendlyTime(d.generated_at)}` : "Weather coverage incomplete or outdated. No alerts shown does not mean no risk.";
    this.shadowRoot.querySelector("#user-grid").innerHTML = d.users.map(user => `<ha-card><div class="heading"><h3>${this._escape(user.name)}</h3><span class="badge">${user.presence === "home" ? "Home" : user.presence === "away" ? "Away" : "Location unavailable"}</span></div>
      <small>${user.automatic_alerts ? "Automatic alerts on" : "Automatic alerts off"}${user.critical_alerts ? " · Critical alerts on" : ""}</small>
      ${user.alerts.length ? user.alerts.map(alert => `<div class="alert-row ${alert.priority === "critical" ? "critical" : ""}"><button class="text-button" data-report="${this._escape(alert.report_id)}">${this._escape(alert.event)}</button><p>${this._escape(alert.action)}</p><p class="ack ${alert.acknowledged ? "yes" : ""}">Acknowledged: ${alert.acknowledged ? "Yes" : "No"}${alert.acknowledged_at ? " · " + this._friendlyTime(alert.acknowledged_at) : ""}</p>${!alert.ack_available ? "<small>No acknowledgement button was attached to the earlier notification.</small>" : ""}</div>`).join("") : `<p>${user.coverage_current ? "No current relevant alerts." : "Current alert coverage is uncertain."}</p>`}
      ${user.map_visible ? `<button class="text-button" data-map-person="${this._escape(user.profile_id)}">View available location on map</button>` : ""}</ha-card>`).join("") || `<ha-card><h3>No one is enrolled</h3><p>Add each user explicitly in onboarding. Automatic and critical alerts start off.</p><button data-empty-setup class="primary">Set up a user</button></ha-card>`;
    const open = new Set([...this.shadowRoot.querySelectorAll("#outlooks details[open]")].map(el => el.dataset.scope));
    const outlooks = d.outlooks.map(outlook => {
      const facts = [...(outlook.weather_details || [])];
      if (outlook.scope === "home") {
        const sun = outlook.sun_times || {};
        for (const [attribute,label] of [["sunrise","Sunrise"],["sunset","Sunset"]]) {
          const value=sun[attribute];
          if (value && Number.isFinite(Date.parse(value))) facts.push(`${label}: ${new Date(value).toLocaleTimeString([], {hour:"numeric",minute:"2-digit",timeZone:sun.time_zone})}.`);
        }
      }
      return {...outlook,summary:overviewSummary(outlook.summary),health_note:sourceHealthNote(outlook),weather_details:facts};
    });
    this.shadowRoot.querySelector("#outlooks").innerHTML = outlooks.map(outlook => `<section class="outlook"><h3>${this._escape(outlook.name)}</h3><p>${this._escape(outlook.summary)}</p>${outlook.items.length || outlook.weather_details.length || outlook.health_note ? `<details data-scope="${this._escape(outlook.scope)}" ${open.has(outlook.scope) ? "open" : ""}><summary>More details</summary><small>Updated ${this._friendlyTime(outlook.generated_at)}${outlook.health_note ? " · " + this._escape(outlook.health_note) : ""}</small>${outlook.weather_details.map(fact=>`<p>${this._escape(fact)}</p>`).join("")}${outlook.items.map(item => `<div class="report-item"><strong>${this._escape(item.headline)}</strong><p>${this._escape(item.detail)}</p><small>${this._escape(item.source)}${item.valid_to ? " · Valid until " + this._friendlyTime(item.valid_to) : ""}</small><button class="text-button" data-report="${this._escape(item.report_id)}">Read official report</button></div>`).join("")}</details>` : ""}</section>`).join("") || "<p>The first safety summary is not available yet.</p>";
    this.shadowRoot.querySelectorAll("[data-report]").forEach(button => button.onclick = () => this._openReport(button.dataset.report));
    this.shadowRoot.querySelector("[data-empty-setup]")?.addEventListener("click", () => this._switchView("onboarding"));
    this.shadowRoot.querySelectorAll("[data-map-person]").forEach(button => button.onclick = () => {
      this._updateMapPeople();
      this.shadowRoot.querySelector("weather-radar-map").focusPerson(button.dataset.mapPerson);
      this.shadowRoot.querySelector("weather-radar-map").scrollIntoView({behavior:"smooth"});
    });
    this._updateMapPeople();
  }

  _updateMapPeople() {
    const map = this.shadowRoot.querySelector("weather-radar-map");
    if (!map || !this._config?.dashboard) return;
    const people = [];
    for (const user of this._config.dashboard.users) {
      const profile = this._config.profiles.find(p => p.profile_id === user.profile_id);
      const state = this._hass.states?.[profile?.person_entity];
      if (!user.map_visible || !state || ["unavailable","unknown"].includes(state.state)) continue;
      const age = Date.now() - Date.parse(state.last_reported || state.last_updated);
      const lat = state.attributes?.latitude, lon = state.attributes?.longitude;
      if (!Number.isFinite(age) || age < 0 || age > 900000 || typeof lat !== "number" || typeof lon !== "number" || Math.abs(lat) > 90 || Math.abs(lon) > 180) continue;
      people.push({profile_id:user.profile_id,name:user.name,latitude:lat,longitude:lon});
    }
    map.data = {...this._config.dashboard,people};
  }

  _renderWelcome() {
    this.shadowRoot.innerHTML = PANEL_NAVIGATION+FEEDBACK_BAR+renderAdminActionNotice(this._config.admin_notice,value=>this._escape(value))+WELCOME_SCREEN;
    this._bindNavigation();
    this.shadowRoot.querySelector('#give-feedback').onclick=()=>this._showFeedback();
    this._onboardingFlow=installProductionOnboarding(this);
    this._alertEditor=new ProfileAlertEditor(this.shadowRoot,{escape:value=>this._escape(value)});
    if(this._config.actor?.is_admin){
      const reportingButton=this.ownerDocument.createElement('button');
      reportingButton.textContent='Optional error reporting';reportingButton.onclick=()=>this._showReporting();
      this.shadowRoot.querySelector('.welcome-landing').append(reportingButton);
    }
    if(this._config.own_preferences_available){
      const button=this.ownerDocument.createElement('button');button.textContent='Notification settings';
      button.style.marginTop='16px';button.onclick=async()=>{
        button.disabled=true;
        try{
          const snapshot=await this._hass.callWS({type:'weather_intelligence/preferences/get'});
          this._alertEditor.openProfiles(snapshot,async draft=>{
            const dnd=draft.dnd_confirmed?{dnd_bypass:draft.dnd_bypass,dnd_rule_ids:draft.dnd_rule_ids,dnd_confirmed:true,outage_dnd_enabled:draft.outage_dnd_enabled}:{};
            await this._hass.callWS({type:'weather_intelligence/preferences/update',profile_id:draft.profile.profile_id,expected_profile:draft.profile,alert_events:draft.alert_events,reviewed_event_ids:draft.reviewed_event_ids,marine_warning_mode:draft.marine_warning_mode,marine_nearby_enabled:draft.marine_nearby_enabled,marine_nearby_miles:draft.marine_nearby_miles,...dnd});
          });
        }catch(error){button.textContent=error.message || 'Could not open notification settings. Try again.';}
        finally{button.disabled=false;}
      };
      this.shadowRoot.querySelector('.welcome-landing').append(button);
    }
  }

  _openWelcome() {
    const dialog=this.shadowRoot.querySelector("#welcome-onboarding");
    if(this._welcomeRevisit || this._config.onboarding?.completed)this._showSetupStage("setup_menu");
    else if(this._config.onboarding?.initiated || this._welcomeInitiated)this._showSetupStage(this._config.onboarding.stage || "choice");
    if(dialog && !dialog.open)dialog.showModal();
  }

  _beginWelcome() {
    this._welcomeInitiated=true;
    this._updateOnboardingEntry();
    this._showWelcomePage(true);
    this._saveSetupMode();
  }

  _updateOnboardingEntry() {
    const resume=this._config.onboarding?.initiated || this._welcomeInitiated;
    this.shadowRoot.querySelector("#start-onboarding").textContent=this._config.onboarding?.completed?"Review setup or add devices":resume?"Resume onboarding":"Start onboarding";
  }

  _showWelcomePage(choices) {
    this._showSetupStage(choices?"choice":"welcome");
  }

  _showSetupStage(stage) {
    if(this._onboardingFlow){this._onboardingFlow.render(stage);return;}
    const dialog=this.shadowRoot.querySelector("#welcome-onboarding");
    if(stage==="accounts" && !this._config.actor?.is_admin)stage="device_setup";
    const pages={welcome:"welcome-page",choice:"setup-choice-page",device_setup:"device-setup-page",accounts:"setup-users-page",target_device_setup:"device-setup-page",single_device:"single-device-page",single_device_setup:"single-device-setup-page",alert_choices:"alert-choice-page",alert_dnd:"alert-dnd-page",notification_setup:"notification-setup-page"};
    if(!pages[stage])stage="choice";
    for(const id of new Set(Object.values(pages)))this.shadowRoot.querySelector(`#${id}`).hidden=id!==pages[stage];
    const headings={welcome:"welcome-heading",choice:"setup-choice-heading",device_setup:"device-setup-heading",accounts:"setup-users-heading",target_device_setup:"device-setup-heading",single_device:"single-device-heading",single_device_setup:"single-device-setup-heading",alert_choices:"alert-choice-heading",alert_dnd:"alert-dnd-heading",notification_setup:"notification-setup-heading"};
    dialog.setAttribute("aria-labelledby",headings[stage]);
    this._renderSetupAccounts(stage);
    this._renderSingleDevice();
    renderAlertSetup(this.shadowRoot,this._config.onboarding);
    this.shadowRoot.querySelector("#welcome-status").textContent="";
    dialog.scrollTop=0;
    this.shadowRoot.querySelector(`#${pages[stage]} select:not([disabled]), #${pages[stage]} button:not([hidden]):not([disabled])`)?.focus();
  }

  _renderSingleDevice() {
    const other=this._config.onboarding.target_user_id!==this._config.actor.id;
    const label=this.shadowRoot.querySelector("#single-device-for");
    label.hidden=!other;label.textContent=other?`Device for ${this._config.target_user?.name || "selected user"}`:"";
    const devices=this._config.setup_devices || [];
    const selected=this._config.onboarding.selected_device_id;
    const device=devices.find(item=>item.id===selected);
    const select=this.shadowRoot.querySelector("#single-device-select");
    select.innerHTML=`<option value="" disabled ${selected?"":"selected"}>${devices.length?"Select a device":"No devices available"}</option>`+devices.map(device=>`<option value="${this._escape(device.id)}">${this._escape(device.name)}${device.platform?` — ${this._escape(device.platform)}`:""}</option>`).join("");
    if(selected)select.value=selected;
    select.disabled=!devices.length;
    this.shadowRoot.querySelector("#single-device-empty").hidden=!!devices.length;
    this.shadowRoot.querySelector("#single-device-unavailable").hidden=!this._config.onboarding.selected_device_unavailable;
    this.shadowRoot.querySelector("#single-device-next").disabled=!device;
    this.shadowRoot.querySelector("#selected-device-name").textContent=device?`${device.name}${device.platform?` — ${device.platform}`:""}`:"";
    this.shadowRoot.querySelectorAll("[data-alert-path]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.alertPath===this._config.onboarding.alert_path)));
    this.shadowRoot.querySelector("#alert-path-next").disabled=!this._config.onboarding.alert_path;
  }

  _saveAlertPage(action,extra={}) {
    const event=this._config.onboarding.alert_setup?.page?.id;
    if(event)return this._saveOnboardingProgress({alert_action:action,alert_event:event,...extra});
  }

  _renderSetupAccounts(stage=this._config.onboarding?.stage) {
    const actor=this._config.actor;
    if(!actor)return;
    const other=stage==="target_device_setup";
    this.shadowRoot.querySelector("#setup-other-device").hidden=!actor.is_admin || other;
    const label=this.shadowRoot.querySelector("#device-setup-for");
    label.hidden=!other;label.textContent=other?`Devices for ${this._config.target_user?.name || "selected user"}`:"";
    this.shadowRoot.querySelector("#device-ownership-note").hidden=other;
    const selected=this._config.onboarding.target_user_id;
    const tiles=this.shadowRoot.querySelector("#setup-user-tiles");
    tiles.innerHTML=actor.is_admin?accountTiles(this._config.setup_users || [],selected,value=>this._escape(value)):"";
    tiles.querySelectorAll("[data-setup-user]").forEach(button=>button.onclick=()=>this._saveOnboardingProgress({stage:"accounts",target_user_id:button.dataset.setupUser}));
    this.shadowRoot.querySelector("#setup-users-next").disabled=!actor.is_admin || !selected || selected===actor.id;
    this.shadowRoot.querySelectorAll("[data-device-count]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.deviceCount===this._config.onboarding.device_count)));
  }

  _showDeviceHelp() {
    this.shadowRoot.querySelector("#dialog-heading").textContent="Device setup help";
    this.shadowRoot.querySelector("#report-content").innerHTML=DEVICE_HELP;
    this.shadowRoot.querySelector("#official-report").showModal();
  }

  _markSetupMode() {
    this.shadowRoot.querySelectorAll("[data-setup-mode]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.setupMode===this._config.onboarding?.setup_mode)));
  }

  _saveSetupMode(mode) {
    return this._saveOnboardingProgress({...(mode?{mode}:{}),stage:mode==="quick"?"device_setup":"choice",...(mode==="quick"?{target_user_id:this._config.actor.id}:{})});
  }

  _saveOnboardingProgress(update) {
    // Never drop a choice made while initiation or a previous choice is saving.
    this._setupSaveQueue=enqueueOnboardingSave(this._setupSaveQueue,async()=>{
      try {
        const saved=await this._hass.callWS({type:"weather_intelligence/onboarding/update",expected_revision:this._config.onboarding.revision || 0,...update});
        this._config={...this._config,...saved};
        this._markSetupMode();
        this._updateOnboardingEntry();
        this.shadowRoot.querySelector("#welcome-status").textContent="";
        this._showSetupStage(saved.onboarding.stage);
        // Saved device selection is progress only, not delivery enrollment.
      }catch(error){this.shadowRoot.querySelector("#welcome-status").textContent=error.message||"Could not save your progress. Please try again.";}
    });
    return this._setupSaveQueue;
  }

  _bindNavigation() {
    const menu=this.shadowRoot.querySelector("#wi-menu");
    if(menu)menu.onclick=()=>openHomeAssistantMenu(this);
  }

  async _openReport(reportId) {
    this.shadowRoot.querySelector("#dialog-heading").textContent = "Official report";
    const dialog = this.shadowRoot.querySelector("#official-report"), root = this.shadowRoot.querySelector("#report-content");
    root.textContent = "Loading official report…";
    if (!dialog.open) dialog.showModal();
    try {
      const report = await this._hass.callWS({type:"weather_intelligence/dashboard/report",report_id:reportId});
      if (!dialog.open) return;
      root.innerHTML = `<h3>${this._escape(report.title)}</h3><small>${this._escape(report.source)}${report.issued_at ? " · Issued " + this._friendlyTime(report.issued_at) : ""}</small>${report.complete ? "" : "<p>Available source summary only; a full announcement was not supplied by this feed.</p>"}<pre>${this._escape(report.text)}</pre><a href="${this._escape(report.url)}" target="_blank" rel="noopener noreferrer">Open official source</a>`;
    } catch (_error) {root.textContent = "The official report is unavailable right now. Follow the current official alert and try again later.";}
  }

  _showAbout() {
    this.shadowRoot.querySelector("#dialog-heading").textContent = "About Weather Intelligence";
    this.shadowRoot.querySelector("#report-content").innerHTML = renderAbout(this._config.about);
    const dialog=this.shadowRoot.querySelector("#official-report");
    if(!dialog.open)dialog.showModal();
  }

  async _showFeedback() {
    const dialog=this.shadowRoot.querySelector('#official-report');
    const root=this.shadowRoot.querySelector('#report-content');
    this.shadowRoot.querySelector('#dialog-heading').textContent='Give feedback';
    root.textContent='Loading feedback…';
    if(!dialog.open)dialog.showModal();
    try{
      const snapshot=await this._hass.callWS({type:'weather_intelligence/feedback/get'});
      if(dialog.open)mountFeedback(root,snapshot,
        draft=>this._hass.callWS({type:'weather_intelligence/feedback/prepare',...draft}),
        consent=>this._hass.callWS({type:'weather_intelligence/feedback/send',...consent}));
    }catch{root.textContent='Feedback is unavailable. Sign in with an active Home Assistant account and try again.';}
  }

  async _showReporting() {
    const dialog=this.shadowRoot.querySelector('#official-report');
    const root=this.shadowRoot.querySelector('#report-content');
    this.shadowRoot.querySelector('#dialog-heading').textContent='Optional error reporting';
    root.textContent='Loading reporting settings…';
    if(!dialog.open)dialog.showModal();
    try{
      const snapshot=await this._hass.callWS({type:'weather_intelligence/reporting/get'});
      if(dialog.open)mountReporting(root,snapshot,
        settings=>this._hass.callWS({type:'weather_intelligence/reporting/update',...settings}),
        offset=>this._hass.callWS({type:'weather_intelligence/reporting/audit',offset}),()=>this._showOutages());
    }catch{root.textContent='Could not open reporting settings. An administrator account is required.';}
  }

  async _showOutages() {
    const dialog=this.shadowRoot.querySelector('#official-report');
    const root=this.shadowRoot.querySelector('#report-content');
    this.shadowRoot.querySelector('#dialog-heading').textContent='Outage participation';
    root.textContent='Loading outage settings…';
    if(!dialog.open)dialog.showModal();
    try{
      const snapshot=await this._hass.callWS({type:'weather_intelligence/outages/get'});
      if(dialog.open)mountOutages(root,snapshot,
        settings=>this._hass.callWS({type:'weather_intelligence/outages/update',...settings}),()=>this._showReporting(),async()=>{
          const preferences=await this._hass.callWS({type:'weather_intelligence/preferences/get'});
          dialog.close();
          this._alertEditor.openProfiles(preferences,async draft=>{
            const dnd=draft.dnd_confirmed?{dnd_bypass:draft.dnd_bypass,dnd_rule_ids:draft.dnd_rule_ids,dnd_confirmed:true,outage_dnd_enabled:draft.outage_dnd_enabled}:{};
            await this._hass.callWS({type:'weather_intelligence/preferences/update',profile_id:draft.profile.profile_id,
              expected_profile:draft.profile,alert_events:draft.alert_events,reviewed_event_ids:draft.reviewed_event_ids,
              marine_warning_mode:draft.marine_warning_mode,...dnd});
          });
        });
    }catch{root.textContent='Could not open outage settings. An administrator account is required.';}
  }

  _showPrivacy() {
    this.shadowRoot.querySelector("#dialog-heading").textContent = "Privacy";
    const dialog = this.shadowRoot.querySelector("#official-report");
    this.shadowRoot.querySelector("#report-content").innerHTML = `<h3>Your data and optional reports</h3>
      <p>Optional reports help me fix bugs and spot problems with weather feeds. They use limited diagnostic details rather than names, locations or hardware identifiers. Here is what stays local, what services receive and what you can choose to share.</p>
      <p>Weather Intelligence runs inside your Home Assistant. It does not include a developer analytics service or send your household locations, profiles, or alerts to the project developers.</p>
      <h4>Location and visibility</h4><p>Alert routing reads location supplied by the Home Assistant Person entities you enroll; we do not add independent phone tracking. On-water checks compare those locations locally with public water maps. For opted-in water filtering, nearby-water heads-ups or on-water DND rules, regional USGS water maps and, where needed, USACE charted channels are downloaded using coarse map regions rather than exact device coordinates or identities. A bounded cache remains on Home Assistant and drops regions no longer requested. The old worldwide map is no longer bundled; regional coverage is incomplete. Results are estimates, not navigation guidance; stale, inaccurate or shoreline-overlapping fixes may be unavailable. Marine real-time notifications are in an early state and require further testing. The on-or-near-water preference can also qualify a fresh fix within half a mile of mapped shore away from zone.home. Fresh device-linked vehicle activity suppresses that proximity shortcut, but cannot reliably distinguish a boat from a road vehicle. Android Auto alone does not silence mapped-water alerts. Neither account addresses nor a separate location-history store are used for this check. Missing map coverage or an unavailable result does not mean land or safety. Map visibility is separate from opted-in alert delivery.</p>
      <h4>Information needed for services</h4><p>This is not an offline system: NWS and enabled supplemental providers receive the point needed for weather lookups. The configured NWS contact is included in its required identifying request header. NOAA receives the viewed area for radar and warning boundaries. OpenFreeMap supplies road tiles, labels, and styling; its requests reveal the viewed map area and network metadata, but do not include household names, profiles, or alert records. OpenFreeMap's policy describes anonymized access logs, limited error/security IP logs, and possible CDN processing. The browser map renderer is served from your own Home Assistant, not a code CDN. <a href="https://openfreemap.org/privacy/" target="_blank" rel="noopener noreferrer">Read OpenFreeMap's privacy policy</a>. Opening an official discussion requests its public product page.</p>
      <h4>Phone notifications</h4><p>Selected alert text and notification actions are sent to the phone targets you configure through Home Assistant Companion delivery. Depending on your setup, Home Assistant's push infrastructure and Apple or Google push services participate. Tests target the selected device, not everyone. Automatic and critical delivery require explicit choices.</p>
      <h4>Local records</h4><p>Incident, delivery, and acknowledgement records are stored locally in Home Assistant for restart continuity. An acknowledgement means the recipient tapped a button—not that they are safe. We do not create a separate personal-location history; Home Assistant or the Companion app may already maintain their own records.</p>
      <h4>Optional error forwarding</h4><p>If you enable MQTT error forwarding, only allowlisted diagnostic summaries are sent to the MQTT broker/topic you configured: software versions, time, component, and a fixed failure category. Raw log text, tracebacks, IPs, coordinates, credentials, and personal identifiers are omitted. They are not automatically sent to a developer endpoint. Home Assistant's normal local logging and backups remain under your control.</p>
      <h4>Optional maintainer reports</h4><p>${REPORTING_DISCLOSURE}</p><p>An administrator reviews the exact destination and example fields before enabling it. Changing the destination requires new consent. Turning reporting off cancels queued work but cannot recall a report already received. The local reporting history shows the exact sanitized fields and whether the receiver accepted them.</p>
      <h4>Separate outage contributions</h4><p>${OUTAGE_REPORTING_NOTICE}</p>
      <h4>Your controls</h4><p>Use User settings or revisit onboarding to change delivery, location display, and enrolled targets. This overview currently requires an administrator account; it does not create new access permissions.</p>
      <h4>Reporting history</h4><p>Administrators can review the exact prepared error and outage reports, their destination and delivery results in the local reporting history for 30 days. That history covers project reports, not every connection made by Home Assistant or its other integrations.</p>`;
    if (!dialog.open) dialog.showModal();
  }

  _friendlyTime(value) {const date = new Date(value);return value && Number.isFinite(date.getTime()) ? date.toLocaleString([], {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}) : "not yet checked";}

  _sourceCheck(key, label) { return `<label class="check"><input type="checkbox" data-source="${key}" ${this._config.sources[key] ? "checked" : ""}>${label}</label>`; }
  _newProfile() { return {profile_id: newProfileId(), name:"", person_entity:"", notify_entity:"", legacy_notify_service:"", mobile_platform:"auto", show_location_on_map:"inherit", enabled:true, receive_personal_location_alerts:true, receive_designated_home_alerts_while_away:false, automatic_official_warning_notifications:false, critical_notifications_enabled:false, hazard_families:this._config.hazard_families.map(x=>x.value), alert_events:recommendedAlertEvents(this._config.alert_choices || []), daily_briefing_enabled:false, daily_briefing_location:"designated_home"}; }
  _options(items, selected) { return `<option value="">Choose…</option>` + items.map(x=>`<option value="${this._escape(x.value)}" ${x.value===selected?"selected":""}>${this._escape(x.label)}</option>`).join(""); }
  _renderProfiles() {
    const root = this.shadowRoot.querySelector("#profiles");
    root.innerHTML = this._config.profiles.map((p,i)=>`<section class="profile" data-index="${i}"><div class="grid">
      <label>Name<input data-field="name" value="${this._escape(p.name)}"></label>
      <label>Person<select data-field="person_entity">${this._options(this._config.people,p.person_entity)}</select></label>
      <label>Companion notification target<select data-field="notify_entity">${this._options(this._config.notify_targets,p.notify_entity)}</select></label>
      <label>Phone type<select data-field="mobile_platform"><option value="auto" ${(p.mobile_platform||"auto")==="auto"?"selected":""}>Detect automatically</option><option value="android" ${p.mobile_platform==="android"?"selected":""}>Android</option><option value="ios" ${p.mobile_platform==="ios"?"selected":""}>iPhone</option></select></label></div>
      <label>Advanced Companion notification action<select data-field="legacy_notify_service">${this._options(this._config.legacy_targets,p.legacy_notify_service)}</select><small>Enables Weather Alert channels, sound treatment, icons, replacement, and automatic clearing.</small></label>
      ${this._check("enabled","Profile enabled",p.enabled)}${this._check("receive_personal_location_alerts","Alerts near this person",p.receive_personal_location_alerts)}${this._check("receive_designated_home_alerts_while_away","Home alerts while away",p.receive_designated_home_alerts_while_away)}
      <label>Location on weather map<select data-field="show_location_on_map"><option value="inherit" ${(p.show_location_on_map||"inherit")==="inherit"?"selected":""}>Follow Home Assistant entity visibility</option><option value="show" ${p.show_location_on_map==="show"?"selected":""}>Explicitly show available location here</option><option value="hide" ${p.show_location_on_map==="hide"?"selected":""}>Hide location here (keep opted-in moving alerts)</option></select></label>
      ${this._check("daily_briefing_enabled","Daily briefing",p.daily_briefing_enabled)}
      <label>Daily briefing location<select data-field="daily_briefing_location"><option value="designated_home" ${p.daily_briefing_location==="designated_home"?"selected":""}>Designated home</option><option value="person" ${p.daily_briefing_location==="person"?"selected":""}>This person's current location</option><option value="both" ${p.daily_briefing_location==="both"?"selected":""}>Designated home and current location</option></select></label>
      ${this._check("automatic_official_warning_notifications","Automatic relevant official hazard notifications",p.automatic_official_warning_notifications)}<p>DND bypass: ${p.critical_notifications_enabled?"on":"off"}. Use Edit alert and DND choices to review or change the bypass list.</p>
      <p>${Array.isArray(p.alert_events)?`${p.alert_events.length} individual alert choices selected.`:"Existing alert preferences preserved. Review each alert individually when you are ready."}</p><button data-alert-choices="${i}" ${(this._config.alert_choices || []).length?"":"disabled"}>Edit alert and DND choices</button>
      <button class="danger" data-remove="${i}">Remove profile</button></section>`).join("") || "<p>No one is enrolled.</p>";
    root.querySelectorAll("input[data-field],select[data-field]").forEach(el=>el.onchange=e=>this._change(e));
    root.querySelectorAll("button[data-alert-choices]").forEach(el=>el.onclick=()=>this._openAlertChoices(Number(el.dataset.alertChoices)));
    root.querySelectorAll("button[data-remove]").forEach(el=>el.onclick=e=>{this._profilesDirty=true;this._config.profiles.splice(Number(e.target.dataset.remove),1);this._renderProfiles();this._renderMobileSetup();});
  }
  _openAlertChoices(index) {
    const profile=this._config.profiles[index], choices=this._config.alert_choices || [];
    if (!profile || !choices.length) return;
    const owner=this._hass.states?.[profile.person_entity]?.attributes?.user_id;
    this._alertEditor.open(profile,this._config.alert_pages || [],choices,{notice:owner!==this._config.actor?.id,dndCatalog:this._config.dnd_catalog,dndSetup:this._config.dnd_setup?.[profile.profile_id],applyLabel:'Apply to unsaved profile',apply:async draft=>{
      const latest=this._config.profiles.find(item=>item.profile_id===profile.profile_id);
      if(!latest)throw new Error('This profile was removed. Reopen settings.');
      latest.alert_events=draft.alert_events;
      latest.hazard_families=[...new Set(choices.filter(item=>draft.alert_events.includes(item.value)).map(item=>item.family))];
      latest.life_safety_events=(latest.life_safety_events || []).filter(event=>!draft.reviewed_event_ids.includes(event));
      latest.marine_warning_mode=draft.marine_warning_mode;
      latest.marine_nearby_enabled=draft.marine_nearby_enabled;latest.marine_nearby_miles=draft.marine_nearby_miles;
      if(draft.dnd_confirmed){latest.critical_notifications_enabled=draft.dnd_bypass;latest.dnd_rule_ids=draft.dnd_rule_ids;latest.outage_dnd_enabled=draft.outage_dnd_enabled;}
      this._profilesDirty=true;this._renderProfiles();
    }});
  }
  _renderMobileSetup(){
    const root=this.shadowRoot.querySelector("#mobile-setup");
    const requested=new URLSearchParams(window.location.search).get("mobile_setup");
    const ios=this._config.profiles.filter(p=>p.mobile_platform==="ios");
    const android=this._config.profiles.filter(p=>p.mobile_platform==="android");
    const unknown=this._config.profiles.filter(p=>(p.mobile_platform||"auto")==="auto");
    root.innerHTML=(unknown.length?`<ha-alert alert-type="warning">Choose Android or iPhone for ${unknown.map(p=>this._escape(p.name||"an unnamed profile")).join(", ")} before completing spoken-alert setup.</ha-alert>`:"")+
      (ios.map(p=>`<section class="mobile-setup" data-setup-profile="${this._escape(p.profile_id)}"><h3>${this._escape(p.name)} — iPhone</h3>
        ${requested===p.profile_id?`<ha-alert alert-type="info">You opened the setup link on this device. Complete the steps below, then run the test.</ha-alert>`:""}
        <p>Save profile changes before sending setup or a test. This setup panel currently requires a Home Assistant administrator account.</p><ol class="steps"><li>In iPhone Settings, open Home Assistant's Notifications and enable notifications, sounds, and Critical Alerts.</li><li>For optional speech, open <strong>Settings → Siri</strong> (or <strong>Apple Intelligence & Siri</strong>) → <strong>Announce Notifications</strong>. On some versions this is under Notifications.</li><li>If <strong>Home Assistant</strong> is listed, turn on announcements for it. If it is not listed, speech is not verified on this device; keep tone-only alerts.</li><li>To hear speech from the phone itself, open <strong>Settings → Accessibility → Siri</strong> and turn on <strong>Announce Notifications on Speaker</strong>, if available. Otherwise announcements may be limited to supported headphones or CarPlay.</li><li>Run the TEST ONLY alert with the phone locked and outside a call. Confirm tone and optional speech separately before relying on either.</li></ol><small>The Settings button is best effort. If it does not open, follow the steps manually. Delivery alone does not verify Siri speech, and identical Android/iPhone timing is not guaranteed.</small>
        <div class="actions"><button data-ios-handoff="${this._escape(p.profile_id)}">Send setup to this iPhone</button><button data-open-settings>Open iPhone Settings</button><button class="primary" data-ios-test="${this._escape(p.profile_id)}">Send spoken-alert test</button><button data-copy-link="${this._escape(p.profile_id)}">Copy setup link</button></div><p class="setup-result" data-result="${this._escape(p.profile_id)}"></p>
      </section>`).join("")||"")+
      android.map(p=>`<section class="mobile-setup"><h3>${this._escape(p.name)} — Android</h3><p>Use the guided popup to save and test this phone in one flow.</p><button data-android-wizard="${this._escape(p.profile_id)}" class="primary">Continue Android onboarding</button><details><summary>Android sound instructions</summary>${ANDROID_SOUND_STEPS}</details></section>`).join("");
    root.querySelectorAll("button[data-android-wizard]").forEach(el=>el.onclick=()=>this._startAndroidSetup(el.dataset.androidWizard));
    root.querySelectorAll("button[data-android-action]").forEach(el=>el.onclick=()=>this._sendAndroidSetup(el.dataset.androidProfile,el.dataset.androidAction));
    root.querySelectorAll("button[data-ios-handoff]").forEach(el=>el.onclick=e=>this._sendIosHandoff(e.target.dataset.iosHandoff));
    root.querySelectorAll("button[data-ios-test]").forEach(el=>el.onclick=e=>this._sendIosTest(e.target.dataset.iosTest));
    root.querySelectorAll("button[data-open-settings]").forEach(el=>el.onclick=()=>{window.location.href="app-settings:";});
    root.querySelectorAll("button[data-copy-link]").forEach(el=>el.onclick=e=>this._copySetupLink(e.target.dataset.copyLink));
  }
  _setupResult(profileId,text){const el=this.shadowRoot.querySelector(`[data-result="${CSS.escape(profileId)}"]`);if(el)el.textContent=text;}
  async _sendAndroidSetup(profileId,action){this._setupResult(profileId,"Sending…");try{await this._hass.callWS({type:"weather_intelligence/mobile_setup/android",profile_id:profileId,action});this._setupResult(profileId,action==="test"?"TEST ONLY sent to this phone. Did you hear the tone followed by speech?":"Setup link sent to this phone.");}catch(error){this._setupResult(profileId,"Could not send: "+(error.message||"save the profile and check its phone target"));}}
  async _sendIosHandoff(profileId){this._setupResult(profileId,"Sending setup link…");try{await this._hass.callWS({type:"weather_intelligence/mobile_setup/send_ios_handoff",profile_id:profileId});this._setupResult(profileId,"Setup notification sent to this iPhone.");}catch(error){this._setupResult(profileId,"Could not send setup: "+(error.message||"check the Companion target"));}}
  async _sendIosTest(profileId){this._setupResult(profileId,"Sending one TEST ONLY alert…");try{await this._hass.callWS({type:"weather_intelligence/mobile_setup/test_ios_speech",profile_id:profileId});this._setupResult(profileId,"Test sent once. Confirm that you heard both the critical tone and Siri announcement.");}catch(error){this._setupResult(profileId,"Could not send test: "+(error.message||"check iPhone permissions"));}}
  async _copySetupLink(profileId){const link=`${window.location.origin}/weather-intelligence?mobile_setup=${encodeURIComponent(profileId)}`;try{await navigator.clipboard.writeText(link);this._setupResult(profileId,"Setup link copied. Open it in the Home Assistant app on the selected phone.");}catch(_error){this._setupResult(profileId,link);}}
  _check(key,label,on){return `<label class="check"><input type="checkbox" data-field="${key}" ${on?"checked":""}>${label}</label>`}
  _familyCheck(f,selected,index){return `<label class="check"><input type="checkbox" data-family="${f.value}" data-profile="${index}" ${selected.includes(f.value)?"checked":""}>${f.label}</label>`}
  _change(event){const section=event.target.closest("section");const p=this._config.profiles[Number(section.dataset.index)];const key=event.target.dataset.field;const old=p[key];const value=event.target.type==="checkbox"?event.target.checked:event.target.value;if(value&& !old && key==="automatic_official_warning_notifications"&&!confirm("Enable real automatic hazard notifications for this person?")){event.target.checked=false;return}if(value&& !old && key==="critical_notifications_enabled"&&!confirm("Critical notifications may bypass silent settings and make sound. Enable them?")){event.target.checked=false;return}this._profilesDirty=true;p[key]=value;this._renderMobileSetup();}
  _family(event){const p=this._config.profiles[Number(event.target.dataset.profile)];const key=event.target.dataset.family;const values=new Set(p.hazard_families||[]);event.target.checked?values.add(key):values.delete(key);p.hazard_families=[...values];}
  async _save(){const result=this.shadowRoot.querySelector("#result");result.textContent="Saving…";const sources={};this.shadowRoot.querySelectorAll("[data-source]").forEach(x=>sources[x.dataset.source]=x.checked);sources.airnow_api_key=this.shadowRoot.querySelector("#airnow-key").value;const developer_logging={mqtt_error_logging_enabled:this.shadowRoot.querySelector("#mqtt-error-logging").checked,mqtt_error_topic:this.shadowRoot.querySelector("#mqtt-error-topic").value};try{await this._hass.callWS({type:"weather_intelligence/config/update",config:{profiles:this._config.profiles,daily_briefing_time:this.shadowRoot.querySelector("#briefing-time").value,sources,developer_logging}});this._profilesDirty=false;this._renderMobileSetup();result.textContent="Saved.";await this._refreshDashboard();}catch(error){result.textContent="Could not save: "+(error.message||"invalid settings")}}
  _escape(value){return String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));}
}
// Existing tabs can import a new resource URL before the page is refreshed.
if (!customElements.get("weather-intelligence-panel")) {
  customElements.define("weather-intelligence-panel", WeatherIntelligencePanel);
}
