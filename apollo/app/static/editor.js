/**
 * editor.js — Apollo FM patch editor.
 *
 * Builds a spec-locked patch editor (D-18/D-19/D-20):
 *   - Algorithm selector (from ALGORITHMS)
 *   - Per-operator controls: ratio / level / attack / decay / sustain / release
 *   - Master gain control
 *   - Collapsible LFO section (optional; D-19): rate / depth / wave / target
 * All input min/max/step come from BOUNDS (spec_constants.js).
 * Live preview via window.ApolloSynth.playSequence on every control change (debounced).
 * Emits call_fm.json via readPatch(); validates via validatePatch() + checkBounds().
 *
 * Dependencies (must be loaded before this file):
 *   spec_constants.js   → SPEC_VERSION, N_OPERATORS, ALGORITHMS, BOUNDS, LFO_WAVES,
 *                          LFO_TARGETS, checkBounds
 *   synth.js            → window.ApolloSynth.playSequence
 *   app.js              → getCtx(), showError()
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Internal state — set by buildEditor, read by readPatch / validatePatch
  // ---------------------------------------------------------------------------

  var _container = null;
  var _debounceTimer = null;
  var DEBOUNCE_MS = 150;

  // Fields per operator (display label → BOUNDS key)
  var OP_FIELDS = [
    { key: 'ratio',   label: 'Ratio',   step: 0.01 },
    { key: 'level',   label: 'Level',   step: 0.01 },
    { key: 'attack',  label: 'Attack',  step: 0.001 },
    { key: 'decay',   label: 'Decay',   step: 0.001 },
    { key: 'sustain', label: 'Sustain', step: 0.01 },
    { key: 'release', label: 'Release', step: 0.001 },
  ];

  // ---------------------------------------------------------------------------
  // buildEditor(container)
  // ---------------------------------------------------------------------------

  /**
   * Render the patch editor into `container`.
   * Populates algorithm select from ALGORITHMS; 3 op-panel blocks with per-field
   * range+number inputs; a master gain input; and a collapsible LFO section.
   */
  function buildEditor(container) {
    _container = container;
    container.innerHTML = '';

    // --- Algorithm row
    var algRow = document.createElement('div');
    algRow.className = 'editor-row editor-algorithm-row';

    var algLabel = document.createElement('label');
    algLabel.textContent = 'Algorithm';
    algLabel.htmlFor = 'ed-algorithm';

    var algSelect = document.createElement('select');
    algSelect.id = 'ed-algorithm';
    algSelect.name = 'algorithm';
    Object.entries(ALGORITHMS).forEach(function (kv) {
      var opt = document.createElement('option');
      opt.value = kv[1];
      opt.textContent = kv[0];
      algSelect.appendChild(opt);
    });
    algRow.appendChild(algLabel);
    algRow.appendChild(algSelect);
    container.appendChild(algRow);

    // --- Gain row
    var gainRow = document.createElement('div');
    gainRow.className = 'editor-row';
    var gainLabel = document.createElement('label');
    gainLabel.textContent = 'Master Gain';
    gainLabel.htmlFor = 'ed-gain';
    var gainInput = _makeNumberInput('ed-gain', 'gain', 0.7);
    gainRow.appendChild(gainLabel);
    gainRow.appendChild(gainInput);
    container.appendChild(gainRow);

    // --- Operator panels
    for (var i = 0; i < N_OPERATORS; i++) {
      var panel = document.createElement('div');
      panel.className = 'op-panel';

      var panelTitle = document.createElement('div');
      panelTitle.className = 'op-panel-title';
      panelTitle.textContent = 'Operator ' + (i + 1);
      panel.appendChild(panelTitle);

      var fieldsDiv = document.createElement('div');
      fieldsDiv.className = 'op-fields';

      OP_FIELDS.forEach(function (f) {
        var row = document.createElement('div');
        row.className = 'op-field-row';

        var lbl = document.createElement('label');
        lbl.textContent = f.label;
        var inputId = 'ed-op' + i + '-' + f.key;
        lbl.htmlFor = inputId;

        var inp = _makeNumberInput(inputId, f.key, _defaultOpValue(f.key));
        inp.dataset.opIndex = i;
        inp.dataset.fieldKey = f.key;

        row.appendChild(lbl);
        row.appendChild(inp);
        fieldsDiv.appendChild(row);
      });

      panel.appendChild(fieldsDiv);
      container.appendChild(panel);
    }

    // --- LFO section (collapsible)
    var lfoDetails = document.createElement('details');
    lfoDetails.className = 'lfo-section';

    var lfoSummary = document.createElement('summary');
    lfoSummary.textContent = 'LFO (optional)';
    lfoDetails.appendChild(lfoSummary);

    var lfoInner = document.createElement('div');
    lfoInner.className = 'lfo-inner';

    // Enable checkbox
    var cbRow = document.createElement('div');
    cbRow.className = 'editor-row';
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = 'ed-lfo-enable';
    var cbLabel = document.createElement('label');
    cbLabel.htmlFor = 'ed-lfo-enable';
    cbLabel.textContent = 'Enable LFO';
    cbRow.appendChild(cb);
    cbRow.appendChild(cbLabel);
    lfoInner.appendChild(cbRow);

    // Rate
    lfoInner.appendChild(_makeLfoFieldRow('Rate (Hz)', 'ed-lfo-rate', 'lfo_rate', 1.0));
    // Depth
    lfoInner.appendChild(_makeLfoFieldRow('Depth', 'ed-lfo-depth', 'lfo_depth', 0.3));

    // Wave select
    var waveRow = document.createElement('div');
    waveRow.className = 'editor-row';
    var waveLabel = document.createElement('label');
    waveLabel.textContent = 'Wave';
    waveLabel.htmlFor = 'ed-lfo-wave';
    var waveSelect = document.createElement('select');
    waveSelect.id = 'ed-lfo-wave';
    Object.entries(LFO_WAVES).forEach(function (kv) {
      var opt = document.createElement('option');
      opt.value = kv[1];
      opt.textContent = kv[0];
      waveSelect.appendChild(opt);
    });
    waveRow.appendChild(waveLabel);
    waveRow.appendChild(waveSelect);
    lfoInner.appendChild(waveRow);

    // Target select
    var targetRow = document.createElement('div');
    targetRow.className = 'editor-row';
    var targetLabel = document.createElement('label');
    targetLabel.textContent = 'Target';
    targetLabel.htmlFor = 'ed-lfo-target';
    var targetSelect = document.createElement('select');
    targetSelect.id = 'ed-lfo-target';
    Object.entries(LFO_TARGETS).forEach(function (kv) {
      var opt = document.createElement('option');
      opt.value = kv[1];
      opt.textContent = kv[0];
      targetSelect.appendChild(opt);
    });
    targetRow.appendChild(targetLabel);
    targetRow.appendChild(targetSelect);
    lfoInner.appendChild(targetRow);

    lfoDetails.appendChild(lfoInner);
    container.appendChild(lfoDetails);

    // --- Wire change events for live preview
    container.addEventListener('input', _onControlChange);
    container.addEventListener('change', _onControlChange);
  }

  // ---------------------------------------------------------------------------
  // readPatch() → call_fm.json object
  // ---------------------------------------------------------------------------

  /**
   * Collect current editor state into a call_fm.json-compatible object.
   * LFO key is OMITTED entirely when the enable checkbox is unchecked (absent
   * lfo key = v1.0-identical render; must not include a null/empty lfo object).
   */
  function readPatch() {
    if (!_container) return null;

    var patch = {
      spec_version: SPEC_VERSION,
      algorithm: Number(document.getElementById('ed-algorithm').value),
      gain: Number(document.getElementById('ed-gain').value),
      operators: [],
    };

    for (var i = 0; i < N_OPERATORS; i++) {
      var op = {};
      OP_FIELDS.forEach(function (f) {
        op[f.key] = Number(document.getElementById('ed-op' + i + '-' + f.key).value);
      });
      patch.operators.push(op);
    }

    // LFO: include only when enabled (absent = v1.0-identical render).
    var lfoEnable = document.getElementById('ed-lfo-enable');
    if (lfoEnable && lfoEnable.checked) {
      patch.lfo = {
        rate:   Number(document.getElementById('ed-lfo-rate').value),
        depth:  Number(document.getElementById('ed-lfo-depth').value),
        wave:   Number(document.getElementById('ed-lfo-wave').value),
        target: Number(document.getElementById('ed-lfo-target').value),
      };
    }
    // If lfoEnable is unchecked, patch.lfo is NOT set — key is absent entirely.

    return patch;
  }

  // ---------------------------------------------------------------------------
  // validatePatch(patch) → {ok, errors[]}
  // ---------------------------------------------------------------------------

  /**
   * Client-side validation (mirrors server-side load_manifest, T-05-13 dual
   * validation). Checks all operator fields + gain via checkBounds(value, field),
   * and validates lfo fields if present.
   */
  function validatePatch(patch) {
    var errors = [];
    if (!patch) {
      errors.push('No patch data');
      return { ok: false, errors: errors };
    }

    // Gain
    if (!checkBounds(patch.gain, 'gain')) {
      errors.push('gain ' + patch.gain + ' out of range ' + JSON.stringify(BOUNDS.gain));
    }

    // Operators
    var opKeys = ['ratio', 'level', 'attack', 'decay', 'sustain', 'release'];
    (patch.operators || []).forEach(function (op, i) {
      opKeys.forEach(function (k) {
        if (!checkBounds(op[k], k)) {
          errors.push('operator ' + i + ' ' + k + ' ' + op[k] + ' out of range');
        }
      });
    });

    // LFO (only if present)
    if (patch.lfo) {
      if (!checkBounds(patch.lfo.rate, 'lfo_rate')) {
        errors.push('lfo rate ' + patch.lfo.rate + ' out of range ' + JSON.stringify(BOUNDS.lfo_rate));
      }
      if (!checkBounds(patch.lfo.depth, 'lfo_depth')) {
        errors.push('lfo depth ' + patch.lfo.depth + ' out of range ' + JSON.stringify(BOUNDS.lfo_depth));
      }
      if (![0, 1, 2].includes(Number(patch.lfo.wave))) {
        errors.push('lfo wave ' + patch.lfo.wave + ' not in {0,1,2}');
      }
      if (![0, 1].includes(Number(patch.lfo.target))) {
        errors.push('lfo target ' + patch.lfo.target + ' not in {0,1}');
      }
    }

    return { ok: errors.length === 0, errors: errors };
  }

  // ---------------------------------------------------------------------------
  // previewNote()
  // ---------------------------------------------------------------------------

  /**
   * Play a short 2-note test sequence through the browser synth.
   * C4 (pitch 60) then E4 (pitch 64), each 0.4s, velocity 100.
   */
  function previewNote() {
    var patch = readPatch();
    if (!patch) return;
    var notes = [
      { pitch: 60, velocity: 100, start: 0.0,  duration: 0.4 },
      { pitch: 64, velocity: 100, start: 0.45, duration: 0.4 },
    ];
    try {
      window.ApolloSynth.playSequence(getCtx(), patch, notes);
    } catch (e) {
      // Preview failures are non-fatal — swallow.
    }
  }

  // ---------------------------------------------------------------------------
  // loadPreset(presetObj)
  // ---------------------------------------------------------------------------

  /**
   * Populate all editor inputs from a preset object (call_fm.json).
   * Sets the LFO enable checkbox + fields if the preset has an lfo key.
   */
  function loadPreset(preset) {
    if (!_container || !preset) return;

    // Algorithm
    var algEl = document.getElementById('ed-algorithm');
    if (algEl) algEl.value = preset.algorithm;

    // Gain
    var gainEl = document.getElementById('ed-gain');
    if (gainEl) gainEl.value = preset.gain;

    // Operators
    (preset.operators || []).forEach(function (op, i) {
      OP_FIELDS.forEach(function (f) {
        var el = document.getElementById('ed-op' + i + '-' + f.key);
        if (el) el.value = op[f.key];
      });
    });

    // LFO
    var lfoEnable = document.getElementById('ed-lfo-enable');
    if (lfoEnable) {
      if (preset.lfo) {
        lfoEnable.checked = true;
        var rateEl = document.getElementById('ed-lfo-rate');
        var depthEl = document.getElementById('ed-lfo-depth');
        var waveEl = document.getElementById('ed-lfo-wave');
        var targetEl = document.getElementById('ed-lfo-target');
        if (rateEl) rateEl.value = preset.lfo.rate;
        if (depthEl) depthEl.value = preset.lfo.depth;
        if (waveEl) waveEl.value = preset.lfo.wave;
        if (targetEl) targetEl.value = preset.lfo.target;
      } else {
        lfoEnable.checked = false;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // applyPresetByName(name)
  // ---------------------------------------------------------------------------

  /**
   * Fetch a bundled preset by name from /presets/<name> and load it.
   */
  function applyPresetByName(name) {
    return fetch('/presets/' + name)
      .then(function (r) { return r.json(); })
      .then(function (preset) { loadPreset(preset); })
      .catch(function (e) {
        if (typeof showError === 'function') showError('Could not load preset: ' + name);
      });
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  function _makeNumberInput(id, boundsKey, defaultVal) {
    var wrap = document.createElement('span');
    wrap.className = 'input-pair';

    var range = document.createElement('input');
    range.type = 'range';
    range.id = id + '-range';
    _applyBounds(range, boundsKey);
    range.value = defaultVal;

    var number = document.createElement('input');
    number.type = 'number';
    number.id = id;
    number.name = id;
    _applyBounds(number, boundsKey);
    number.value = defaultVal;

    // Keep range and number in sync
    range.addEventListener('input', function () { number.value = range.value; });
    number.addEventListener('input', function () { range.value = number.value; });

    wrap.appendChild(range);
    wrap.appendChild(number);
    return wrap;
  }

  function _makeLfoFieldRow(labelText, inputId, boundsKey, defaultVal) {
    var row = document.createElement('div');
    row.className = 'editor-row';
    var lbl = document.createElement('label');
    lbl.textContent = labelText;
    lbl.htmlFor = inputId;
    var inp = _makeNumberInput(inputId, boundsKey, defaultVal);
    row.appendChild(lbl);
    row.appendChild(inp);
    return row;
  }

  function _applyBounds(input, boundsKey) {
    var b = BOUNDS[boundsKey];
    if (!b) return;
    input.min = b[0];
    input.max = b[1];
    // Derive step from range magnitude for usable sliders
    var range = b[1] - b[0];
    input.step = range <= 1 ? 0.01 : (range <= 2 ? 0.001 : 0.01);
  }

  function _defaultOpValue(key) {
    var defaults = {
      ratio: 1.0, level: 0.5, attack: 0.01,
      decay: 0.1, sustain: 0.5, release: 0.1,
    };
    return defaults[key] !== undefined ? defaults[key] : 0.5;
  }

  function _onControlChange() {
    if (_debounceTimer) clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(function () {
      previewNote();
    }, DEBOUNCE_MS);
  }

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  window.ApolloEditor = {
    buildEditor:       buildEditor,
    readPatch:         readPatch,
    validatePatch:     validatePatch,
    previewNote:       previewNote,
    loadPreset:        loadPreset,
    applyPresetByName: applyPresetByName,
  };

}());
