import {MARINE_BETA_NOTICE,isMarinePage} from './marine-beta.js?v=2';

export function profileAlertEvents(profile,choices) {
  if (Array.isArray(profile.alert_events)) return [...profile.alert_events];
  const families=profile.hazard_families || [];
  return choices.filter(choice=>!families.length || families.includes(choice.family)).map(choice=>choice.value);
}

export function tierEvents(page,tier='warning') {
  const item=tier==='warning'?page:page[tier];
  return item ? [...(item.event_ids || [item.id])] : [];
}

export function tierState(page,tier,selected) {
  const events=tierEvents(page,tier),count=events.filter(event=>selected.has(event)).length;
  return count===0?'off':count===events.length?'on':'mixed';
}

export function toggleProfileTier(page,tier,selected,reviewed) {
  if (tier==='watch' && page.watch_automatic) return;
  const include=tierState(page,tier,selected)!=='on';
  const events=tierEvents(page,tier);
  if (tier==='warning' && page.watch_automatic) events.push(...tierEvents(page,'watch'));
  for(const event of events){include?selected.add(event):selected.delete(event);reviewed.add(event);}
}

export function renderProfileAlertGrid(pages,selected,escape,filter='') {
  const matches=pages.filter(page=>(page.group_label || page.title).toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  return ['official','weather_intelligence'].map(section=>{
    const items=matches.filter(page=>page.section===section);
    if(!items.length)return '';
    return `<section><h3>${section==='official'?'Official alerts':'Weather Intelligence alerts'}</h3>${items.some(isMarinePage)?MARINE_BETA_NOTICE:''}${section==='weather_intelligence'?'<p>These notifications are specific to Weather Intelligence, not official warnings.</p>':''}<div class="hazard-grid">${items.map(page=>{
      return `<button type="button" data-hazard="${escape(page.id)}" aria-haspopup="dialog"><strong>${escape(page.group_label || page.title)}</strong></button>`;
    }).join('')}</div></section>`;
  }).join('') || '<p>No hazards match that name.</p>';
}
