export function renderAdminActionNotice(notice, escape) {
  if (!notice) return '';
  return `<aside data-account-notice role="status" aria-label="Account notice" style="margin:16px auto;padding:16px;max-width:640px;border:1px solid var(--divider-color);border-radius:12px"><strong>${escape(notice.title)}</strong><p>${escape(notice.message)}</p><button data-dismiss-account-notice data-notice-id="${escape(notice.id)}">Dismiss</button><p data-notice-result role="status" hidden></p></aside>`;
}

export function bindAdminActionNotice(root,{send,dismissed=()=>{}}){
  const button=root.querySelector('[data-dismiss-account-notice]');
  if(!button)return;
  button.onclick=async()=>{
    if(button.disabled)return;
    const id=button.dataset.noticeId,box=button.closest('[data-account-notice]');
    button.disabled=true;
    try{
      await send(id);
      dismissed(id);
      box.remove(); // Keep the surrounding screen and unsaved form fields intact.
    }catch(error){
      button.disabled=false;
      const result=box.querySelector('[data-notice-result]');
      result.hidden=false;result.textContent=error.message||'Could not dismiss this notice. Please try again.';
    }
  };
}
