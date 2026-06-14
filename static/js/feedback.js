function openFeedback() {
  document.getElementById('feedback-page').value = window.location.pathname;
  document.getElementById('feedback-modal').removeAttribute('hidden');
  document.getElementById('feedback-message').focus();
}

function closeFeedback() {
  const modal = document.getElementById('feedback-modal');
  modal.setAttribute('hidden', '');
  // Reset form for next open
  document.getElementById('feedback-form').reset();
  document.getElementById('feedback-form').removeAttribute('hidden');
  document.getElementById('feedback-success').setAttribute('hidden', '');
  document.getElementById('feedback-error').setAttribute('hidden', '');
  document.getElementById('feedback-submit').disabled = false;
  document.getElementById('feedback-submit').textContent = 'Send Feedback';
}

async function submitFeedback(e) {
  e.preventDefault();
  const form   = document.getElementById('feedback-form');
  const btn    = document.getElementById('feedback-submit');
  const errBox = document.getElementById('feedback-error');

  btn.disabled = true;
  btn.textContent = 'Sending…';
  errBox.setAttribute('hidden', '');

  const data = new FormData(form);

  try {
    const resp = await fetch('/feedback/submit', { method: 'POST', body: data });
    const json = await resp.json();

    if (json.ok) {
      form.setAttribute('hidden', '');
      document.getElementById('feedback-success').removeAttribute('hidden');
    } else {
      errBox.textContent = json.error || 'Something went wrong.';
      errBox.removeAttribute('hidden');
      btn.disabled = false;
      btn.textContent = 'Send Feedback';
    }
  } catch {
    errBox.textContent = 'Network error — please try again.';
    errBox.removeAttribute('hidden');
    btn.disabled = false;
    btn.textContent = 'Send Feedback';
  }
}

// Close modal on backdrop click
document.addEventListener('click', function (e) {
  const modal = document.getElementById('feedback-modal');
  if (e.target === modal) closeFeedback();
});

// Close on Escape
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') closeFeedback();
});
