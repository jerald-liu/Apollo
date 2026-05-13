/**
 * Apollo Status LED — jsui script for Max4Live
 *
 * Draws a connection status indicator:
 *   0 = red (disconnected)
 *   1 = green (connected)
 *   2 = amber (slow/high latency)
 *
 * Also displays latency in ms below the LED.
 *
 * Messages:
 *   connection <0|1|2>  — set connection state
 *   latency <ms>        — set latency display value
 */

// jsui setup
mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

var state = 0;       // 0=off, 1=connected, 2=slow
var latencyMs = 0;
var width = 60;
var height = 50;

// Colors [r, g, b, a]
var colors = {
  off:   [0.7, 0.15, 0.15, 1.0],    // red
  on:    [0.15, 0.75, 0.3, 1.0],     // green
  slow:  [0.9, 0.7, 0.1, 1.0],       // amber
  bg:    [0.2, 0.2, 0.2, 1.0],       // dark background
  text:  [0.75, 0.75, 0.75, 1.0],    // light gray text
};

var labels = ["OFF", "OK", "SLOW"];

function paint() {
  var w = mgraphics.size[0];
  var h = mgraphics.size[1];

  // Background
  mgraphics.set_source_rgba(colors.bg);
  mgraphics.rectangle(0, 0, w, h);
  mgraphics.fill();

  // LED circle
  var cx = w / 2;
  var cy = h * 0.35;
  var radius = Math.min(w, h) * 0.18;

  var color = state === 1 ? colors.on : state === 2 ? colors.slow : colors.off;

  // Glow effect (larger circle, lower alpha)
  mgraphics.set_source_rgba(color[0], color[1], color[2], 0.25);
  mgraphics.arc(cx, cy, radius * 1.6, 0, Math.PI * 2);
  mgraphics.fill();

  // Main LED
  mgraphics.set_source_rgba(color);
  mgraphics.arc(cx, cy, radius, 0, Math.PI * 2);
  mgraphics.fill();

  // Highlight on LED
  mgraphics.set_source_rgba(1, 1, 1, 0.3);
  mgraphics.arc(cx - radius * 0.25, cy - radius * 0.25, radius * 0.4, 0, Math.PI * 2);
  mgraphics.fill();

  // Status label
  mgraphics.set_source_rgba(colors.text);
  mgraphics.select_font_face("Arial");
  mgraphics.set_font_size(9);
  var label = labels[state] || "OFF";
  var te = mgraphics.text_measure(label);
  mgraphics.move_to(cx - te[0] / 2, h * 0.65);
  mgraphics.show_text(label);

  // Latency text
  if (state > 0) {
    var latText = latencyMs.toFixed(1) + "ms";
    mgraphics.set_font_size(8);
    te = mgraphics.text_measure(latText);
    mgraphics.move_to(cx - te[0] / 2, h * 0.85);
    mgraphics.show_text(latText);
  }
}

function connection(val) {
  state = Math.max(0, Math.min(2, Math.round(val)));
  mgraphics.redraw();
}

function latency(val) {
  latencyMs = val;
  mgraphics.redraw();
}

// Force initial draw
function bang() {
  mgraphics.redraw();
}
