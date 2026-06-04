/**
 * app.js — Apollo local app: corpus audition, ingest, training, settings.
 *
 * Corpus page:
 *   - Wires .play-call buttons to fetch /midi/<nnn>/call.mid note JSON and
 *     play through ApolloSynth.playSequence.
 *   - Wires #add-pair-btn to POST /ingest via multipart FormData.
 *
 * Training page:
 *   - Wires #train-btn to POST /train; starts ~1s polling of /status.
 *   - drawLossCurve: canvas 2D loss-over-epochs chart (train solid, held dashed).
 *   - Wires #auto-retrain checkbox and #save-settings to POST /settings.
 *
 * Guards all DOM wiring with element-existence checks so this file loads safely
 * on every page.
 *
 * AudioContext is lazy-initialized on first user gesture (browser autoplay policy).
 *
 * Dependencies (loaded before this file via block scripts):
 *   spec_constants.js  → ALGORITHMS, LFO_TARGETS
 *   synth.js           → window.ApolloSynth.playSequence (corpus page only)
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Shared lazy AudioContext — created on first user gesture.
  // ---------------------------------------------------------------------------

  var ctx = null;

  function getCtx() {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  // ---------------------------------------------------------------------------
  // Error display helper (mirrors grade.js showError pattern).
  // ---------------------------------------------------------------------------

  /**
   * Show an error message in a .error div.
   * Finds an existing .error element or creates one appended to <main>.
   */
  function showError(msg) {
    var el = document.querySelector('.error-global');
    if (!el) {
      el = document.createElement('div');
      el.className = 'error error-global';
      var main = document.querySelector('main');
      if (main) {
        main.appendChild(el);
      } else {
        document.body.appendChild(el);
      }
    }
    el.textContent = msg;
  }

  // ---------------------------------------------------------------------------
  // Training: loss-over-epochs canvas curve (PATTERNS.md Pattern 7)
  // ---------------------------------------------------------------------------

  /**
   * Draw train_loss (solid #6D28D9) and held_loss (dashed #15803D) lines.
   * history: [{epoch, train_loss, held_loss}, ...]
   */
  function drawLossCurve(canvas, history) {
    var ctx2 = canvas.getContext('2d');
    var W = canvas.width, H = canvas.height;
    ctx2.clearRect(0, 0, W, H);
    if (history.length < 2) return;
    var maxLoss = Math.max.apply(null, history.map(function (d) { return d.train_loss || 0; }));
    var toX = function (i) { return (i / (history.length - 1)) * W; };
    var toY = function (v) { return H - (v / (maxLoss || 1)) * H * 0.9; };

    // train_loss — solid purple
    ctx2.beginPath();
    ctx2.strokeStyle = '#6D28D9';
    ctx2.setLineDash([]);
    history.forEach(function (d, i) {
      var x = toX(i), y = toY(d.train_loss);
      if (i === 0) { ctx2.moveTo(x, y); } else { ctx2.lineTo(x, y); }
    });
    ctx2.stroke();

    // held_loss — dashed green (filter null entries)
    var heldPoints = history.filter(function (d) { return d.held_loss != null; });
    if (heldPoints.length >= 2) {
      ctx2.beginPath();
      ctx2.strokeStyle = '#15803D';
      ctx2.setLineDash([4, 4]);
      heldPoints.forEach(function (d, i) {
        var origIdx = history.indexOf(d);
        var x = toX(origIdx), y = toY(d.held_loss);
        if (i === 0) { ctx2.moveTo(x, y); } else { ctx2.lineTo(x, y); }
      });
      ctx2.stroke();
      ctx2.setLineDash([]);
    }
  }

  // ---------------------------------------------------------------------------
  // Training: polling loop (~1s) + UI updates
  // ---------------------------------------------------------------------------

  var pollInterval = null;

  function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(async function () {
      try {
        var d = await fetch('/status').then(function (r) { return r.json(); });
        updateTrainingUI(d);
        if (d.status === 'complete' || d.status === 'error') {
          clearInterval(pollInterval);
          pollInterval = null;
        }
      } catch (e) {
        // Network error — keep polling, don't crash.
      }
    }, 1000);
  }

  function updateTrainingUI(d) {
    var progressDiv = document.getElementById('training-progress');
    var statusEl = document.getElementById('train-status');
    var fillEl = document.getElementById('progress-fill');
    var chartEl = document.getElementById('loss-chart');
    if (!progressDiv) return;

    // Reveal progress section.
    progressDiv.classList.remove('hidden');

    // Status text (UI-SPEC copywriting).
    if (statusEl) {
      if (d.status === 'running') {
        statusEl.textContent = 'Training locally… epoch ' + d.epoch + '/' + (d.total_epochs || 1);
      } else if (d.status === 'complete') {
        statusEl.textContent = 'Training complete — ready to generate';
      } else if (d.status === 'error') {
        statusEl.textContent = 'Training error — check the console for details';
      } else {
        statusEl.textContent = '';
      }
    }

    // Progress bar fill.
    if (fillEl) {
      var pct = d.total_epochs ? (100 * d.epoch / d.total_epochs) : 0;
      fillEl.style.width = pct + '%';
    }

    // Loss curve.
    if (chartEl && d.loss_history) {
      drawLossCurve(chartEl, d.loss_history);
    }
  }

  // ---------------------------------------------------------------------------
  // Corpus: wire .play-call buttons
  // ---------------------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', function () {
    var playBtns = document.querySelectorAll('.play-call');

    playBtns.forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var nnn = btn.dataset.nnn;
        var patchEl = document.getElementById('patch-' + nnn);
        var patch = patchEl ? JSON.parse(patchEl.textContent) : null;
        if (!patch) {
          showError('Pair ' + nnn + ' has an invalid patch');
          return;
        }
        try {
          var notes = await fetch('/midi/' + nnn + '/call.mid').then(function (r) {
            return r.json();
          });
          if (!Array.isArray(notes)) {
            showError(notes.error || 'Could not load notes for pair ' + nnn);
            return;
          }
          window.ApolloSynth.playSequence(getCtx(), patch, notes);
        } catch (e) {
          showError('Network error loading pair ' + nnn);
        }
      });
    });

    // -------------------------------------------------------------------------
    // Corpus: ingest FormData handler — POST /ingest
    // -------------------------------------------------------------------------

    var addPairBtn = document.getElementById('add-pair-btn');
    if (addPairBtn) {
      addPairBtn.addEventListener('click', async function () {
        var midInput = document.getElementById('call-mid-input');
        var fmInput = document.getElementById('call-fm-input');
        var respInput = document.getElementById('response-mid-input');
        var midF = midInput && midInput.files[0];
        var fmF = fmInput && fmInput.files[0];
        var respF = respInput && respInput.files[0];
        if (!midF || !fmF) {
          showError('Select both a call.mid and a call_fm.json');
          return;
        }
        var fd = new FormData();
        fd.append('call_mid', midF);
        fd.append('call_fm', fmF);
        if (respF) fd.append('response_mid', respF);
        try {
          var data = await fetch('/ingest', {method: 'POST', body: fd}).then(function (r) { return r.json(); });
          if (!data.ok) {
            showError(data.error || 'Ingest failed');
            return;
          }
          window.location.href = '/corpus';
        } catch (e) {
          showError('Network error during upload');
        }
      });
    }

    // -------------------------------------------------------------------------
    // Training page: train button + polling resume
    // -------------------------------------------------------------------------

    var trainBtn = document.getElementById('train-btn');
    if (trainBtn) {
      // Resume polling if a training run is in progress when the page loads.
      fetch('/status').then(function (r) { return r.json(); }).then(function (d) {
        updateTrainingUI(d);
        if (d.status === 'running') {
          startPolling();
        }
      }).catch(function () {});

      trainBtn.addEventListener('click', async function () {
        try {
          var data = await fetch('/train', {method: 'POST'}).then(function (r) { return r.json(); });
          if (!data.ok) {
            showError(data.error || 'Could not start training');
            return;
          }
          startPolling();
        } catch (e) {
          showError('Network error starting training');
        }
      });
    }

    // -------------------------------------------------------------------------
    // Training page: auto-retrain checkbox → POST /settings
    // -------------------------------------------------------------------------

    var autoRetrainCb = document.getElementById('auto-retrain');
    if (autoRetrainCb) {
      autoRetrainCb.addEventListener('change', async function () {
        try {
          await fetch('/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({auto_retrain: autoRetrainCb.checked}),
          });
        } catch (e) {
          showError('Could not save auto-retrain setting');
        }
      });
    }

    // -------------------------------------------------------------------------
    // Training page: save-settings button → POST /settings (responses_dir)
    // -------------------------------------------------------------------------

    var saveSettingsBtn = document.getElementById('save-settings');
    if (saveSettingsBtn) {
      saveSettingsBtn.addEventListener('click', async function () {
        var dirInput = document.getElementById('responses-dir');
        var savedEl = document.getElementById('settings-saved');
        try {
          var data = await fetch('/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({responses_dir: dirInput ? dirInput.value : ''}),
          }).then(function (r) { return r.json(); });
          if (data.ok && savedEl) {
            savedEl.classList.remove('hidden');
            setTimeout(function () { savedEl.classList.add('hidden'); }, 2000);
          } else {
            showError('Could not save settings');
          }
        } catch (e) {
          showError('Network error saving settings');
        }
      });
    }

  });

}());
