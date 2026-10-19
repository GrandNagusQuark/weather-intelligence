// One notice for onboarding and post-setup marine preferences. Official alerts
// are not experimental; this notice describes Weather Intelligence's delivery/filtering.
export const MARINE_BETA_NOTICE = `<p class="marine-beta-note" role="note"><strong>Marine notifications — Early state</strong><br>Real-time delivery and location filtering are in an early state and require further testing. Water-map coverage and boating or bridge detection may be incomplete. This notice applies to Weather Intelligence—not the official alerts.</p>`;

const MARINE_EVENTS = new Set([
  'special marine warning', 'gale warning', 'gale watch', 'storm warning', 'storm watch',
  'hurricane force wind warning', 'hurricane force wind watch', 'hazardous seas warning',
  'hazardous seas watch', 'small craft advisory', 'brisk wind advisory', 'lake wind advisory',
  'low water advisory', 'heavy freezing spray warning', 'heavy freezing spray watch',
  'freezing spray advisory', 'beach hazards statement', 'coastal flood warning',
  'coastal flood advisory', 'coastal flood watch', 'coastal flood statement',
  'lakeshore flood warning', 'lakeshore flood advisory', 'lakeshore flood watch',
  'lakeshore flood statement', 'high surf warning', 'high surf advisory',
  'rip current statement', 'storm surge warning', 'storm surge watch',
  'tsunami warning', 'tsunami advisory', 'tsunami watch', 'marine weather statement',
]);

export function isMarinePage(page) {
  if (!page || page.kind === 'transition') return false;
  return [page, ...['advisory', 'watch', 'statement'].map(tier => page[tier])]
    .filter(Boolean).some(item => (item.event_ids || [item.id]).some(event => MARINE_EVENTS.has(event)));
}
