// Apollo grader — audio sequencing + keyboard shortcuts + submit (EVAL-02, UI-SPEC §Interaction Contract).
(function () {
  const nnn = document.body.dataset.nnn;
  if (!nnn) return;

  const audioCall = document.getElementById('audio-call');
  const audioResp = document.getElementById('audio-response');
  const playBtn = document.getElementById('play-sequence');
  const submitBtn = document.getElementById('submit');
  const submitHint = document.getElementById('submit-hint');
  const noteEl = document.getElementById('note');
  const revealLink = document.getElementById('reveal-link');
  const revealAside = document.getElementById('reveal-aside');

  const state = { fit: null, coherence: null, playing: false };

  // ---- Score buttons ----
  document.querySelectorAll('.segmented').forEach(group => {
    const dim = group.dataset.dim;
    group.querySelectorAll('.score-btn').forEach(btn => {
      btn.addEventListener('click', () => setScore(dim, parseInt(btn.dataset.value, 10)));
    });
  });

  function setScore(dim, value) {
    state[dim] = value;
    document.querySelectorAll(`.segmented[data-dim="${dim}"] .score-btn`).forEach(b => {
      b.classList.toggle('selected', parseInt(b.dataset.value, 10) === value);
    });
    updateSubmitEnabled();
  }

  function updateSubmitEnabled() {
    const ready = state.fit !== null && state.coherence !== null;
    submitBtn.disabled = !ready;
    submitHint.classList.toggle('hidden', ready);
  }

  // ---- Audio sequence ----
  function playSequence() {
    if (state.playing) { stopSequence(); return; }
    state.playing = true;
    playBtn.textContent = '⏸ Stop';
    audioCall.pause(); audioResp.pause();
    audioCall.currentTime = 0; audioResp.currentTime = 0;
    audioCall.play();
    audioCall.onended = () => { audioResp.currentTime = 0; audioResp.play(); };
    audioResp.onended = () => { state.playing = false; playBtn.textContent = '▶ Play call → response'; };
  }
  function stopSequence() {
    audioCall.pause(); audioResp.pause();
    state.playing = false;
    playBtn.textContent = '▶ Play call → response';
  }
  playBtn.addEventListener('click', playSequence);

  // ---- Submit ----
  submitBtn.addEventListener('click', submit);
  async function submit() {
    if (submitBtn.disabled) return;
    const payload = {
      pair_id: nnn,
      fit: state.fit,
      coherence: state.coherence,
      note: noteEl.value || '',
    };
    try {
      const r = await fetch('/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) {
        showError("Couldn't save that score. The server log will say why — most likely `eval/scores.jsonl` isn't writable. Your sliders are still set; hit Submit again after you fix it.");
        return;
      }
      if (data.next) {
        window.location.href = `/pair/${data.next}`;
      } else {
        window.location.href = '/';
      }
    } catch (e) {
      showError("Network error. Score not saved.");
    }
  }
  function showError(msg) {
    let el = document.querySelector('.error');
    if (!el) {
      el = document.createElement('div');
      el.className = 'error';
      submitBtn.parentNode.appendChild(el);
    }
    el.textContent = msg;
  }

  // ---- Reveal ----
  revealLink.addEventListener('click', async (e) => {
    e.preventDefault();
    const r = await fetch(`/reveal/${nnn}`);
    const data = await r.json();
    revealAside.textContent =
      `run_id: ${data.run_id}\n` +
      `checkpoint: ${data.checkpoint_path || '—'}\n` +
      `iteration: ${data.iteration === null ? '—' : data.iteration}`;
    revealAside.classList.remove('hidden');
  });

  // ---- Keyboard shortcuts ----
  document.addEventListener('keydown', (e) => {
    if (e.target === noteEl) {
      if (e.key === 'Escape') noteEl.blur();
      return;
    }
    if (e.key === ' ' || e.code === 'Space') { e.preventDefault(); playSequence(); return; }
    if (e.key === 'r') { stopSequence(); playSequence(); return; }
    if (e.key === 'n') { e.preventDefault(); noteEl.focus(); return; }
    if (e.key === 'Enter') { submit(); return; }
    // Use e.code (physical key), not e.key — Shift+1 on macOS turns e.key into "!"
    // and the previous /^[1-5]$/.test(e.key) check would never match.
    const m = /^Digit([1-5])$/.exec(e.code);
    if (m) {
      const v = parseInt(m[1], 10);
      if (e.shiftKey) setScore('coherence', v);
      else            setScore('fit',       v);
    }
  });

  // ---- Pre-populate from prior score (resumability) ----
  (async () => {
    try {
      const r = await fetch(`/score/${nnn}`);
      const data = await r.json();
      if (data.fit !== null)       setScore('fit', data.fit);
      if (data.coherence !== null) setScore('coherence', data.coherence);
      if (data.note)               noteEl.value = data.note;
    } catch (e) { /* fresh pair, no prior record */ }
  })();
})();
