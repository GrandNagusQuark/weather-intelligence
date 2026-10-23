// Android-only guided setup. Drafts are isolated; saving never sends a test.
import "./android-sound-guide.js?v=4";
export function cloneSetup(value) { return JSON.parse(JSON.stringify(value)); }

export function setupSteps(mode) {
  return ["mode", "person", "phone", "delivery", ...(mode === "full" ? ["alerts", "details"] : []), "review", "sound", "finish"];
}

export function setupError(profile) {
  if (!profile.name?.trim() || !/^person\.[a-z0-9_]+$/.test(profile.person_entity || "")) return "Choose a person and enter a name.";
  if (!/^notify\.mobile_app_[a-z0-9_]+$/.test(profile.legacy_notify_service || "") || profile.notify_entity) return "Choose one phone-specific Home Assistant Companion action.";
  if (profile.mobile_platform !== "android") return "Confirm that this is an Android phone.";
  if (profile.critical_notifications_enabled && !profile.automatic_official_warning_notifications) return "Critical alerts need automatic alerts enabled.";
  return "";
}

export const ANDROID_SOUND_STEPS = `<ol class="steps"><li>Allow Home Assistant notifications on this phone.</li><li>Weather Siren uses Companion’s <strong>alarm_stream</strong> category for critical sound. Saving or opening setup does not send a notification. If the category is missing, explicitly create it below when it is safe to make sound.</li><li>Open <strong>Settings → Apps → Home Assistant → Notifications → Notification categories → alarm_stream → Sound</strong>. Tap the category name, not its switch. Select Alert if set to Silent, then choose your tone.</li><li>On Samsung, if Notification categories is missing, turn on <strong>Settings → Notifications → Advanced settings → Manage notification categories for each app</strong>.</li><li>For your selected critical alerts to sound during DND, allow <strong>Alarms</strong> in the phone’s Do Not Disturb settings. Do not allow the whole Home Assistant app. Ordinary alerts, briefings, and setup links use separate normal channels. Alarm audio is not a guaranteed override of every phone mode; test tone and speech with DND on.</li><li><strong>Optional but recommended:</strong> enable <strong>Show as pop-up</strong> for the alarm category and <strong>Lock screen → Show content</strong>. This also lets others viewing the screen read warnings. Vibrate is optional. A popup is not a guarantee of fully expanded text or a full-screen alert. Leave app-wide popup-style settings unchanged.</li></ol><details><summary>Illustrated Samsung walkthrough — older category labels</summary><android-sound-guide></android-sound-guide></details>`;

export class AndroidOnboarding {
  constructor(dialog, {snapshot, newProfile, save, send, escape}) {
    this.dialog=dialog; this.snapshot=cloneSetup(snapshot); this.newProfile=newProfile;
    this.save=save; this.send=send; this.escape=escape; this.mode="quick"; this.step="mode";
    this.draft=null; this.expected=null; this.busy=false; this.saved=false; this.message="";
    dialog.oncancel=event=>{if(this.busy){event.preventDefault();return;} this.close();};
  }
  open(profileId) {
    this.permissionsOnly=false;
    const profile=this.snapshot.profiles.find(p=>p.profile_id===profileId && p.mobile_platform!=="ios");
    if(profile){this.selectProfile(profile.profile_id);this.step="mode";}
    this.render();this.dialog.showModal();
  }
  openPermissions(profileId) {
    const profile=this.snapshot.profiles.find(p=>p.profile_id===profileId && p.mobile_platform==='android');
    if(!profile)throw new Error('Reopen setup and choose an enrolled Android device.');
    this.selectProfile(profileId);this.permissionsOnly=true;this.mode='quick';
    this.saved=true;this.step='sound';
    this.message='Review the saved phone settings below. Opening this screen does not save changes or send a notification.';
    this.render();this.dialog.showModal();
  }
  close() {if(this.busy)return;this.dialog.close();}
  selectProfile(id) {
    const profile=this.snapshot.profiles.find(p=>p.profile_id===id && p.mobile_platform!=="ios");
    this.expected=profile?cloneSetup(profile):null;
    this.draft=cloneSetup(profile || this.newProfile());
    this.draft.mobile_platform="android";
    this.draft.android_confirmed=profile?.mobile_platform==="android";
    this.saved=false;this.message="";this.choiceIndex=0;
  }
  choices() {return this.snapshot.alert_choices || [];}
  selected() {
    if(Array.isArray(this.draft.alert_events))return new Set(this.draft.alert_events);
    const families=this.draft.hazard_families || [];
    return new Set(this.choices().filter(c=>!families.length || families.includes(c.family)).map(c=>c.value));
  }
  setSelected(selected) {
    this.draft.alert_events=[...selected];
    this.draft.hazard_families=[...new Set(this.choices().filter(c=>selected.has(c.value)).map(c=>c.family))];
  }
  go(delta) {
    if(this.busy)return;
    if(delta>0){
      if(this.step==="person" && (!this.draft?.name.trim() || !this.draft.person_entity)){this.message="Choose a person and enter a name.";this.render();return;}
      if(this.step==="phone" && setupError({...this.draft,critical_notifications_enabled:false})){this.message=setupError({...this.draft,critical_notifications_enabled:false});this.render();return;}
    }
    const steps=setupSteps(this.mode);this.step=steps[steps.indexOf(this.step)+delta] || this.step;this.message="";this.render();
  }
  async saveDraft() {
    if(this.busy)return;
    const error=setupError(this.draft);if(error){this.message=error;this.render();return;}
    this.busy=true;this.message="Saving this person's setup…";this.render();
    try {
      const saved=await this.save(cloneSetup(this.draft),cloneSetup(this.expected));
      // A reused alarm channel may already be audible. Never notify on save.
      this.draft=cloneSetup(saved);this.expected=cloneSetup(saved);this.saved=true;this.step="sound";
      this.draft.android_confirmed=true;
      const index=this.snapshot.profiles.findIndex(p=>p.profile_id===saved.profile_id);
      index<0?this.snapshot.profiles.push(cloneSetup(saved)):this.snapshot.profiles.splice(index,1,cloneSetup(saved));
      this.message="Saved. No tone or speech test has been sent.";
    } catch(error){this.message=`Could not save: ${error.message || "Please try again."}`;}
    finally{this.busy=false;this.render();}
  }
  async sendAction(action) {
    if(this.busy || !this.saved || this.step!=="sound")return;
    this.busy=true;this.message="Sending to the saved phone…";this.render();
    try {
      await this.send(this.draft.profile_id,action,cloneSetup(this.expected));
      this.message=action==="test"?"TEST ONLY sent to this phone. Confirm the tone and speech on the phone; sending is not proof they were audible.":action==="prepare"?"Siren category notification sent. It may play the category’s saved sound. Choose alarm_stream in the phone’s notification settings.":"Setup link sent to this phone.";
    }catch(error){this.message=`Could not send: ${error.message || "Check the phone connection."}`;}
    finally{this.busy=false;this.render();}
  }
  field(key,label,type="checkbox") {
    const p=this.draft,e=this.escape;
    return type==="checkbox"?`<label class="check"><input data-setup-field="${key}" type="checkbox" ${p[key]?"checked":""}>${label}</label>`:`<label>${label}<input data-setup-field="${key}" value="${e(p[key])}"></label>`;
  }
  options(items,value) {return `<option value="">Choose…</option>`+items.map(p=>`<option value="${this.escape(p.value)}" ${p.value===value?"selected":""}>${this.escape(p.label)}</option>`).join("");}
  render() {
    const e=this.escape,p=this.draft,steps=setupSteps(this.mode),index=steps.indexOf(this.step);
    let content="",title="Set up Android weather alerts";
    if(this.step==="mode")content=`<p>How much control would you like?</p><div class="setup-modes"><button data-mode="quick" class="${this.mode==="quick"?"primary":""}" aria-pressed="${this.mode==="full"?"false":"true"}">Quick setup</button><button data-mode="full" class="${this.mode==="full"?"primary":""}" aria-pressed="${this.mode==="full"}">Full control</button></div><p>Quick setup uses recommended choices for new users. Existing alert preferences stay unchanged unless you choose otherwise. Both paths ask who to protect, which Android phone to use, and whether to enable real alerts.</p><p><small>Nothing is saved or sent until you explicitly choose it. Saving does not send a setup notification or a test. This panel requires a Home Assistant administrator account.</small></p><details><summary>Preview Android phone setup instructions</summary>${ANDROID_SOUND_STEPS}</details>`;
    if(this.step==="person") {
      if(!p)this.selectProfile("");
      const d=this.draft;
      content=`<label>Set up or revisit<select id="setup-existing"><option value="">New person</option>${this.snapshot.profiles.filter(p=>p.mobile_platform!=="ios").map(item=>`<option value="${e(item.profile_id)}" ${item.profile_id===d.profile_id?"selected":""}>${e(item.name)}</option>`).join("")}</select></label><label>Home Assistant person<select data-setup-field="person_entity">${this.options(this.snapshot.people,d.person_entity)}</select></label>${this.field("name","Display name","text")}<p><small>Choose an existing Home Assistant Person. Nobody is enrolled automatically. iPhone users keep their existing setup in User settings.</small></p>`;
    }
    if(this.step==="phone") content=`<h3>Choose ${e(p.name)}'s phone</h3><label>Android Companion phone<select data-setup-field="legacy_notify_service">${this.options(this.snapshot.legacy_targets,p.legacy_notify_service)}</select></label>${this.field("android_confirmed","This is an Android phone")}<p><small>Select one phone, not a notification group. This supports custom notification sound and alarm-stream speech. Choosing it replaces this person's previous target only when you save. Multiple devices per person will be added separately.</small></p>`;
    if(this.step==="delivery")content=`<p>Do you want real weather notifications on this phone?</p>${this.field("automatic_official_warning_notifications","Enable automatic weather alerts")}${this.field("critical_notifications_enabled","Enable urgent life-safety sound and speech")}<p><small>Urgent alerts can make sound despite silent settings, subject to phone permissions. They are for immediate life safety, not every advisory. Both options are off for new users until you choose them. A manual test does not require automatic alerts to be enabled.</small></p>`;
    if(this.step==="alerts") {
      const choices=this.choices(),selected=this.selected(),choice=choices[this.choiceIndex||0];
      content=`<p>${selected.size} individual types selected. You do not need to answer every question.</p><label>Review an alert<select id="setup-alert-jump">${choices.map((c,i)=>`<option value="${i}" ${i===(this.choiceIndex||0)?"selected":""}>${e(c.label)}</option>`).join("")}</select></label>${choice?`<h3>Do you want ${e(choice.label)}?</h3><p>${e(choice.description)}</p><div class="actions"><button data-answer="yes" aria-pressed="${selected.has(choice.value)}" class="${selected.has(choice.value)?"primary":""}">Yes</button><button data-answer="no" aria-pressed="${!selected.has(choice.value)}" class="${!selected.has(choice.value)?"primary":""}">No</button></div>`:""}<p><button id="setup-defaults">Use recommended defaults</button></p><p><small>Choices are individual, not enrollment bundles. Radar hail needs the MRMS source enabled. The shared map follows enabled household selections; an unreviewed legacy user keeps its existing broad coverage.</small></p>`;
    }
    if(this.step==="details")content=`${this.field("enabled","Profile enabled")}${this.field("receive_personal_location_alerts","Weather near this person's current location")}${this.field("receive_designated_home_alerts_while_away","Home alerts while away")}<label>Location on the map<select data-setup-field="show_location_on_map"><option value="inherit" ${p.show_location_on_map==="inherit"?"selected":""}>Follow Home Assistant entity visibility</option><option value="show" ${p.show_location_on_map==="show"?"selected":""}>Explicitly show available location</option><option value="hide" ${p.show_location_on_map==="hide"?"selected":""}>Hide marker; keep opted-in moving alerts</option></select></label>${this.field("daily_briefing_enabled","Daily briefing")}<label>Briefing location<select data-setup-field="daily_briefing_location">${[ ["designated_home","Home"],["person","Current location"],["both","Both"] ].map(([value,label])=>`<option value="${value}" ${p.daily_briefing_location===value?"selected":""}>${label}</option>`).join("")}</select></label>`;
    if(this.step==="review")content=`<h3>Review ${e(p.name)}'s setup</h3><dl><dt>Android phone</dt><dd>${e(this.snapshot.legacy_targets.find(t=>t.value===p.legacy_notify_service)?.label || p.legacy_notify_service)}</dd><dt>Automatic alerts</dt><dd>${p.automatic_official_warning_notifications?"On":"Off"}</dd><dt>Urgent sound and speech</dt><dd>${p.critical_notifications_enabled?"On":"Off"}</dd><dt>Alert choices</dt><dd>${Array.isArray(p.alert_events)?`${p.alert_events.length} selected`:"Existing preferences preserved"}</dd></dl><details><summary>Review selected alerts</summary><p>${this.choices().filter(c=>this.selected().has(c.value)).map(c=>e(c.label)).join(" · ") || "None selected"}</p></details>${this.mode==="quick"?`<p><button id="setup-customize">Customize before saving</button>${!Array.isArray(p.alert_events)?' <button id="setup-defaults">Use recommended defaults</button>':""}</p>`:""}<p>Your installation uses location supplied by Home Assistant, not independent tracking. Hiding a marker does not disable opted-in moving alerts; missing or stale location limits that coverage. Weather services receive required lookup points, and map providers receive viewed areas. Household locations are not sent to project developers.</p><p><small>Save updates only this person. Other users, source settings, and the daily briefing time are unchanged. Saving can activate real alerts if you opted in. It never sends a test automatically.</small></p>`;
    if(this.step==="sound")content=`<h3>Weather Siren — ${e(p.name)}</h3><p>The Android category is <strong>alarm_stream</strong>. It carries critical siren tone and alarm-stream speech; routine messages stay on their normal channels. Nothing is sent automatically.</p><details><summary>Android sound instructions and screenshots</summary>${ANDROID_SOUND_STEPS}</details><p>When it is safe to make sound, test the tone and speech with DND on. The phone must allow alarms; this does not allow all Home Assistant notifications.</p><div class="actions"><button id="setup-test">Send TEST ONLY tone and speech</button><button id="setup-handoff">Send setup link to this phone</button></div><details><summary>Siren category missing?</summary><p>Creating it may play its saved sound. It is not a silent test.</p><button id="setup-prepare">Create siren category (may play sound)</button></details>`;
    if(this.step==="finish")content=`<h3>Setup saved for ${e(p.name)}</h3><p>Your choices are saved. Only your own check on the phone can confirm the sound and speech work. You can revisit onboarding at any time.</p><p><small>Weather Intelligence supplements official warning channels. Do not rely on a single app or an untested phone configuration for life safety.</small></p>`;
    this.dialog.innerHTML=`<div class="heading"><h2 id="android-setup-heading">${title}</h2><button id="setup-close" ${this.busy?"disabled":""}>${this.saved?"Close":"Cancel"}</button></div><p class="setup-progress">Step ${index+1} of ${steps.length} · ${this.mode==="full"?"Full control":"Quick setup"}</p><div id="setup-page">${content}</div><p id="setup-status" role="status">${e(this.message)}</p><div class="actions setup-nav">${index>0?'<button id="setup-back">Back</button>':""}${this.step==="review"?'<button id="setup-save" class="primary">Save and continue to sound setup</button>':this.step==="finish"?'<button id="setup-done" class="primary">Done</button>':'<button id="setup-next" class="primary">Continue</button>'}</div>`;
    const root=this.dialog;
    if(this.permissionsOnly){
      root.querySelector('#android-setup-heading').textContent='Mobile alert permissions';
      root.querySelector('.setup-progress').textContent='Permissions and sound for the saved notification device';
      root.querySelector('.setup-nav').innerHTML='<button id="setup-done" class="primary">Done</button>';
    }
    root.querySelector("#setup-close").onclick=()=>this.close();
    root.querySelector("#setup-back")?.addEventListener("click",()=>{if(this.step==="sound")this.saved=false;this.go(-1);});
    root.querySelector("#setup-next")?.addEventListener("click",()=>{
      if(this.step==="phone" && !this.draft.android_confirmed){this.message="Confirm that the selected phone is Android.";this.render();return;}
      this.go(1);
    });
    root.querySelector("#setup-done")?.addEventListener("click",()=>this.close());
    root.querySelector("#setup-save")?.addEventListener("click",()=>this.saveDraft());
    root.querySelectorAll("[data-mode]").forEach(button=>button.onclick=()=>{this.mode=button.dataset.mode;this.render();});
    root.querySelector("#setup-existing")?.addEventListener("change",event=>{this.selectProfile(event.target.value);this.render();});
    root.querySelectorAll("[data-setup-field]").forEach(input=>input.onchange=()=>{
      const key=input.dataset.setupField;this.draft[key]=input.type==="checkbox"?input.checked:input.value;this.saved=false;
      if(key==="legacy_notify_service")this.draft.notify_entity="";
      if(key==="person_entity" && !this.draft.name){this.draft.name=this.snapshot.people.find(p=>p.value===input.value)?.label || "";this.render();}
      if(key==="automatic_official_warning_notifications" && !input.checked){this.draft.critical_notifications_enabled=false;this.render();}
      if(key==="critical_notifications_enabled" && input.checked && !this.draft.automatic_official_warning_notifications){this.draft.critical_notifications_enabled=false;this.message="Enable automatic alerts first, or leave urgent alerts off.";this.render();}
    });
    root.querySelector("#setup-alert-jump")?.addEventListener("change",event=>{this.choiceIndex=Number(event.target.value);this.render();});
    root.querySelectorAll("[data-answer]").forEach(button=>button.onclick=()=>{const selected=this.selected(),choice=this.choices()[this.choiceIndex||0];button.dataset.answer==="yes"?selected.add(choice.value):selected.delete(choice.value);this.setSelected(selected);this.choiceIndex=Math.min((this.choiceIndex||0)+1,this.choices().length-1);this.render();});
    root.querySelector("#setup-defaults")?.addEventListener("click",()=>{this.setSelected(new Set(this.choices().filter(c=>c.default).map(c=>c.value)));this.render();});
    root.querySelector("#setup-customize")?.addEventListener("click",()=>{this.mode="full";this.step="alerts";this.render();});
    root.querySelector("#setup-test")?.addEventListener("click",()=>this.sendAction("test"));
    root.querySelector("#setup-prepare")?.addEventListener("click",()=>this.sendAction("prepare"));
    root.querySelector("#setup-handoff")?.addEventListener("click",()=>this.sendAction("handoff"));
    if(this.busy)root.querySelectorAll("button,input,select").forEach(control=>control.disabled=true);
    root.scrollTop=0;
  }
}
