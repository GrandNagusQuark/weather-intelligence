// Custom panels must supply their own menu entry point on narrow screens.
// Use HA's normal sidebar event, not a separate navigation menu.
export const PANEL_NAVIGATION = `<style>
  .wi-navigation{display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10;height:56px;padding:0 12px;background:var(--app-header-background-color,var(--primary-background-color,#111));color:var(--app-header-text-color,var(--primary-text-color));border-bottom:1px solid var(--divider-color,#333)}
  .wi-navigation button{display:grid;place-items:center;flex-shrink:0;width:44px;height:44px;padding:10px;border:0;border-radius:50%;background:transparent;color:inherit;cursor:pointer}
  .wi-navigation button:focus-visible{outline:2px solid var(--primary-color,#67e8f9);outline-offset:2px}
  .wi-navigation svg{width:24px;height:24px;fill:currentColor}.wi-navigation span{font-size:18px;font-weight:500}
  @media(min-width:871px){:host(:not([narrow])) .wi-navigation{display:none}}
</style><header class="wi-navigation"><button id="wi-menu" aria-label="Open Home Assistant menu" title="Open Home Assistant menu"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/></svg></button><span>Weather Intelligence</span></header>`;

export function openHomeAssistantMenu(panel) {
  panel.dispatchEvent(new CustomEvent("hass-toggle-menu", {bubbles:true, composed:true, detail:{}}));
}

export function returnToWeatherIntelligence() {
  // HA's in-app router uses history + location-changed. A document navigation
  // can be intercepted as an external browser launch by Companion.
  if(window.location.pathname==="/weather-intelligence")return;
  window.history.replaceState(window.history.state,"","/weather-intelligence");
  window.dispatchEvent(new CustomEvent("location-changed",{bubbles:true,composed:true,detail:{replace:true}}));
}
