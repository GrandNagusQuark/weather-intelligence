export function renderAdminActionNotice(notice, escape) {
  if (!notice) return '';
  return `<aside role="status" aria-label="Account notice" style="margin:16px auto;padding:16px;max-width:640px;border:1px solid var(--divider-color);border-radius:12px"><strong>${escape(notice.title)}</strong><p>${escape(notice.message)}</p></aside>`;
}
