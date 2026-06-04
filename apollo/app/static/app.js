/**
 * app.js — Apollo local app: corpus audition wiring.
 *
 * Wires .play-call buttons on the corpus page to:
 *   1. Fetch /midi/<nnn>/call.mid note JSON from the server.
 *   2. Play the notes through the browser FM synth (ApolloSynth.playSequence)
 *      using the pair's own call_fm.json patch (embedded in the page as JSON).
 *
 * Guards all DOM wiring with element-existence checks so this file loads safely
 * on every page (dashboard, training, generate — pages without .play-call buttons
 * will simply find no matching elements and do nothing).
 *
 * AudioContext is lazy-initialized on first user gesture (browser autoplay policy).
 *
 * Dependencies (loaded before this file via corpus.html {% block scripts %}):
 *   spec_constants.js  → ALGORITHMS, LFO_TARGETS
 *   synth.js           → window.ApolloSynth.playSequence
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
  // Corpus: wire .play-call buttons
  // ---------------------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', function () {
    var playBtns = document.querySelectorAll('.play-call');
    if (!playBtns.length) return; // Not on corpus page — nothing to wire.

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
  });

}());
