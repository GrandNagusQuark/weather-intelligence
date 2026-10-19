// Both entry points use the same server supplied product and source directory.
import {SUPPORT_BUTTON} from './support-link.js?v=1';
const escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;')
  .replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');

function sourceLink(name,url) {
  let allowed=false;
  try {const parsed=new URL(url);allowed=parsed.protocol==='https:'&&!parsed.username&&!parsed.password;} catch {}
  return allowed?`<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(name)}</a>`:escapeHtml(name);
}

export const ABOUT_STYLE=`
  .wi-about{font:inherit;line-height:1.5;overflow-wrap:anywhere;text-align:start}
  .wi-about h3{font-size:17px;margin:18px 0 8px}.wi-about p{margin:10px 0}
  .wi-about details{margin:16px 0}.wi-about summary{cursor:pointer;font-weight:600;min-height:44px;display:list-item;align-content:center}
  .wi-about ul{padding-inline-start:22px}.wi-about li{margin:12px 0}.wi-about small{display:block;color:var(--secondary-text-color,#a5b5c7)}
  .wi-about a{color:var(--primary-color,#67e8f9);text-decoration:underline;text-underline-offset:3px}
  .wi-about a:focus-visible,.wi-about summary:focus-visible{outline:2px solid var(--primary-color,#67e8f9);outline-offset:3px}
  .wi-about .wi-support{display:inline-flex;margin:8px 0;max-width:100%}.wi-support img{display:block;max-width:100%;height:auto}
`;

export function renderSources(about,{expanded=false}={}) {
  if(!about?.groups)return '<p>The source directory is unavailable. Try reopening this screen.</p>';
  return `<div class="wi-about"><p>${escapeHtml(about.source_note)}</p>${about.groups.map(group=>
    `<details ${expanded?'open':''}><summary>${escapeHtml(group.name)}</summary><ul>${group.sources.map(source=>
      `<li>${sourceLink(source.name,source.url)}<small>${escapeHtml(source.status)}</small><span>${escapeHtml(source.purpose)}</span>${source.credits?.length?`<small>${source.credits.map(credit=>sourceLink(credit.name,credit.url)).join(' · ')}</small>`:''}</li>`
    ).join('')}</ul></details>`).join('')}</div>`;
}

export function renderAbout(about) {
  if(!about)return '<p>About information is unavailable. Try reopening this screen.</p>';
  return `<style>${ABOUT_STYLE}</style><article class="wi-about">
    <p><strong>${escapeHtml(about.name)}</strong><br>Version ${escapeHtml(about.version)} · ${escapeHtml(about.stage)}</p>
    <p>${escapeHtml(about.summary)}</p>
    <h3>Purpose and limitations</h3>${about.limitations.map(text=>`<p>${escapeHtml(text)}</p>`).join('')}
    <details><summary>Sources and credits</summary>${renderSources(about)}</details>
    <details><summary>Privacy</summary><p>${escapeHtml(about.privacy)}</p></details>
    <details><summary>Development and testing</summary><p>${escapeHtml(about.development)}</p><p>${escapeHtml(about.testing)}</p></details>
    <details><summary>License</summary><p>${sourceLink(about.license.name,about.license.url)}</p><p>${escapeHtml(about.license.note)}</p></details>
    <details><summary>Support</summary><p>${escapeHtml(about.support)}</p></details>
    <h3>Support development</h3><p>If you’d like to help with development and testing, you can buy me a coffee. Support is optional and does not change the alerts you receive.</p>
    ${SUPPORT_BUTTON}<small>Opens Buy Me a Coffee in a new tab.</small>
  </article>`;
}
