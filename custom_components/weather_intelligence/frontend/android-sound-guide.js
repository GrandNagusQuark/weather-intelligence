// Samsung screenshots supplied by the project owner. No network or phone actions.
export const ANDROID_GUIDE_STEPS = [
  {image:"step-1-notification.jpg",title:"Find the setup notification",text:"Swipe down to open notifications and find SETUP ONLY — Weather Siren. If there is no setup notification, open Settings → Apps → Home Assistant → Notifications, then continue at image 3.",marks:[[.04,.334,.92,.088]]},
  {image:"step-2-press-hold.jpg",title:"Open notification settings",text:"Press and hold the Weather Siren notification, then tap the gear icon on the right. Do not tap the crossed-out bell—it disables notifications.",marks:[[.846,.35,.088,.043]]},
  {image:"step-3-app-notifications.jpg",title:"Open Notification categories",text:"Keep Allow notifications and Sound and vibration enabled. Tap Notification categories at the bottom. Leave app-wide popup settings unchanged; they affect other Home Assistant notifications too.",marks:[[.026,.125,.94,.057],[.029,.211,.938,.054],[.026,.76,.94,.06]]},
  {image:"step-4-weather-siren.jpg",title:"Choose Weather Siren",text:"Tap the Weather Siren name, not its on/off switch, to open that category's settings.",marks:[[.028,.866,.79,.056]]},
  {image:"step-5-category-settings.jpg",title:"Choose sound and visibility",text:"Keep Allow notifications on. Select Alert, then tap Sound to choose your tone. Show as pop-up and Lock screen → Show content are optional but recommended. Vibrate is optional. Showing lock-screen content makes the warning readable without unlocking, but also visible to anyone who can see the screen. The sound shown in the example is not required.",marks:[[.026,.328,.94,.06],[.028,.419,.94,.061],[.028,.611,.94,.073]],optionalMarks:[[.028,.548,.94,.061],[.028,.752,.94,.082]]},
];

if (typeof customElements !== "undefined" && !customElements.get("android-sound-guide")) {
  class AndroidSoundGuide extends HTMLElement {
    constructor(){super();this.attachShadow({mode:"open"});this.index=0;}
    connectedCallback(){this.render();}
    render(){
      const step=ANDROID_GUIDE_STEPS[this.index];
      const channel_name = (this.getAttribute('channel-name') || 'Weather Siren').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
      const step_text = step.text.replaceAll('Weather Siren', channel_name);
      const step_title = step.title.replaceAll('Weather Siren', channel_name);
      const url=new URL(`./images/android-guide/${step.image}`,import.meta.url).href;
      this.shadowRoot.innerHTML=`<style>
        :host{display:block;margin:14px 0;color:var(--primary-text-color);font:inherit}
        h3{font-size:17px;margin:10px 0}p{line-height:1.5;margin:10px 0}small{color:var(--secondary-text-color)}
        .picture{position:relative;width:143px;max-width:100%;margin:12px auto}img{display:block;width:100%;height:auto;border-radius:10px;background:#101010}
        .mark{position:absolute;border:2px solid #72d9ff;border-radius:7px;box-sizing:border-box;pointer-events:none;animation:guide-pulse 1.6s ease-in-out 3}
        .mark.optional{border-color:#ffc56d;border-style:dashed}.key{display:block}.key b{color:#72d9ff}.key em{color:#ffc56d;font-style:normal}
        @keyframes guide-pulse{0%,100%{opacity:1}50%{opacity:.35}}@media(prefers-reduced-motion:reduce){.mark{animation:none}}
        nav{display:flex;align-items:center;gap:12px;justify-content:space-between;margin-top:12px}
        button{padding:10px 14px;border:0;border-radius:8px;cursor:pointer;color:var(--primary-text-color);background:var(--secondary-background-color);font:inherit}
        button:disabled{opacity:.5;cursor:default}a{color:var(--primary-color)}
        @media(max-width:400px){.picture{width:120px}}
      </style><small>Samsung Galaxy / One UI example. Other Android phones may use different menu names.</small>
      <section aria-live="polite"><h3>${this.index+1}. ${step_title}</h3><p>${this.hasAttribute('channel-name') && this.index === 0 ? step_text.replace('SETUP ONLY — ' + channel_name, 'SETUP ONLY — Weather Intelligence') : step_text}</p>
      <div class="picture"><img src="${url}" alt="Samsung screenshot: ${step.title}" width="591" height="1280" loading="lazy">${[...(step.marks||[]).map(mark=>[mark,false]),...(step.optionalMarks||[]).map(mark=>[mark,true])].map(([mark,optional])=>`<span class="mark ${optional?"optional":""}" aria-hidden="true" style="left:${mark[0]*100}%;top:${mark[1]*100}%;width:${mark[2]*100}%;height:${mark[3]*100}%"></span>`).join("")}</div>
      <small class="key"><b>Solid outlines:</b> setup controls.${step.optionalMarks?.length?" <em>Dashed outlines:</em> optional, recommended visibility.":""} Highlights pulse three times; reduced-motion settings use steady outlines.</small>
      <p><button id="replay">Replay highlights</button> <a href="${url}" target="_blank" rel="noopener">Open full-size screenshot</a></p></section>
      <nav aria-label="Android screenshot steps"><button id="previous" ${this.index===0?"disabled":""}>Previous image</button><span>${this.index+1} / ${ANDROID_GUIDE_STEPS.length}</span><button id="next" ${this.index===ANDROID_GUIDE_STEPS.length-1?"disabled":""}>Next image</button></nav>`;
      this.shadowRoot.querySelector("#previous").onclick=()=>{if(this.index>0){this.index--;this.render();}};
      this.shadowRoot.querySelector("#next").onclick=()=>{if(this.index<ANDROID_GUIDE_STEPS.length-1){this.index++;this.render();}};
      this.shadowRoot.querySelector("#replay").onclick=()=>this.render();
    }
  }
  customElements.define("android-sound-guide",AndroidSoundGuide);
}
