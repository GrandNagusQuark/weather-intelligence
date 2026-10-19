const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
export const FEEDBACK_BAR=`<style>.wi-feedback-bar{display:flex;justify-content:flex-end;padding:12px 16px;box-sizing:border-box}.wi-feedback-bar button{min-height:44px;padding:10px 16px;border:1px solid var(--divider-color,#526476);border-radius:9px;background:var(--card-background-color,#17232e);color:var(--primary-text-color,#e7eef5);font:inherit;cursor:pointer}</style><div class="wi-feedback-bar"><button id="give-feedback">Give feedback</button></div>`;
export const FEEDBACK_NOTICE="Please don’t include personal information in your message.";
export const FEEDBACK_DETAILS='Feedback goes through Cloudflare to the project maintainer and is kept for 30 days, with a local sending history for the same period. Sending feedback does not enable automatic error or outage reporting. Included diagnostics are software versions and known phone platform, OS version and Companion app version. No account name, device name, device ID, installation ID, serial number, MAC address, location or IP address is added. Cloudflare processes the connection IP under its own policies. A random number identifies this submission only, so retries do not create duplicates. Review your message carefully because automated checks cannot catch all private details.';

export function mountFeedback(root,snapshot,prepare,send) {
  let draft={category:'bug',message:'',device_id:''};
  const style='<style>.wi-feedback{line-height:1.5;overflow-wrap:anywhere}.wi-feedback label{display:block;margin:16px 0}.wi-feedback textarea,.wi-feedback select{display:block;width:100%;box-sizing:border-box;padding:10px;color:inherit;background:var(--card-background-color,#17232e);border:1px solid var(--divider-color,#526476);border-radius:8px;font:inherit}.wi-feedback textarea{min-height:150px;resize:vertical}.wi-feedback pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:40vh;overflow:auto}.wi-feedback button{min-height:44px;padding:10px 14px;margin:6px 8px 6px 0;font:inherit}</style>';
  const form=()=>{
    root.innerHTML=`${style}<section class="wi-feedback"><p>${FEEDBACK_NOTICE}</p><p>This Home Assistant installation can send two feedback submissions in a rolling hour, shared by all accounts.</p><details><summary>Feedback privacy details</summary><p>${FEEDBACK_DETAILS}</p></details>
      <form id="feedback-form"><label>What would you like to share?<select id="feedback-category"><option value="bug">Report a problem</option><option value="idea">Suggest an idea</option><option value="other">Other feedback</option></select></label>
      <label>Related device<select id="feedback-device"><option value="">This Home Assistant installation</option>${snapshot.devices.map(device=>`<option value="${escapeHtml(device.id)}">${escapeHtml(device.name)}</option>`).join('')}</select></label>
      <label>Your feedback<textarea id="feedback-message" minlength="3" maxlength="1000" required placeholder="Describe what happened or what you would like to improve."></textarea></label>
      <p>Up to 1000 characters. Do not include private information or links. This is not an emergency or monitored support channel.</p>
      <button type="submit" id="feedback-review">Review before sending</button><p id="feedback-result" role="status"></p></form>
      <details><summary>Your recent feedback history</summary><p>Only your account’s submissions are shown here.</p><pre>${escapeHtml(JSON.stringify(snapshot.history?.entries||[],null,2))}</pre></details></section>`;
    root.querySelector('#feedback-category').value=draft.category;
    root.querySelector('#feedback-device').value=draft.device_id;
    root.querySelector('#feedback-message').value=draft.message;
    root.querySelector('#feedback-form').onsubmit=async event=>{
      event.preventDefault();
      draft={category:root.querySelector('#feedback-category').value,device_id:root.querySelector('#feedback-device').value,message:root.querySelector('#feedback-message').value};
      root.querySelector('#feedback-review').disabled=true;
      try {const reviewed=await prepare(draft);review(reviewed);}
      catch(error){root.querySelector('#feedback-result').textContent=error.message||'Could not prepare feedback.';root.querySelector('#feedback-review').disabled=false;}
    };
  };
  const review=reviewed=>{
    root.innerHTML=`${style}<section class="wi-feedback"><h3>Review your feedback</h3><p>These are the exact fields that will be sent to ${escapeHtml(reviewed.destination)}.</p><pre>${escapeHtml(JSON.stringify(reviewed.report,null,2))}</pre><p>${FEEDBACK_NOTICE}</p><details><summary>Feedback privacy details</summary><p>${FEEDBACK_DETAILS}</p></details>
      <button id="feedback-send">Send feedback</button><button id="feedback-edit">Back to edit</button><p id="feedback-result" role="status"></p></section>`;
    root.querySelector('#feedback-edit').onclick=form;
    root.querySelector('#feedback-send').onclick=async()=>{
      root.querySelector('#feedback-send').disabled=true;root.querySelector('#feedback-edit').disabled=true;
      try {
        const result=await send({feedback_id:reviewed.report.feedback_id,consent:true});
        if(result.accepted){root.innerHTML=`${style}<section class="wi-feedback"><h3>Feedback received</h3><p>Your feedback was saved in the maintainer’s User feedback inbox. Thank you.</p><p>A response is not guaranteed. No contact details were requested.</p></section>`;}
        else throw new Error('The receiver did not accept this submission. You can retry this same review.');
      }catch(error){root.querySelector('#feedback-result').textContent=error.message||'Delivery could not be confirmed. You can retry this same review.';root.querySelector('#feedback-send').disabled=false;root.querySelector('#feedback-edit').disabled=false;}
    };
  };
  form();
}
