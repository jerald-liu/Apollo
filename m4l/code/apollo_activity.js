/**
 * Apollo Activity Meters — jsui script for Max4Live
 *
 * Dual vertical bars showing input (left, green) and output (right, purple)
 * MIDI activity with exponential decay.
 *
 * Messages:
 *   input_hit   — trigger input activity pulse
 *   output_hit  — trigger output activity pulse
 */

mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

var inputLevel = 0.0;
var outputLevel = 0.0;
var decay = 0.92;       // per-frame decay
var hitEnergy = 0.4;    // energy added per note hit
var maxLevel = 1.0;

var animTask = null;
var animating = false;

var colors = {
    bg:         [0.15, 0.15, 0.15],
    barBg:      [0.22, 0.22, 0.22],
    input:      [0.3, 0.78, 0.45],    // green
    inputGlow:  [0.3, 0.78, 0.45],
    output:     [0.6, 0.35, 0.85],    // purple
    outputGlow: [0.6, 0.35, 0.85],
    text:       [0.55, 0.55, 0.55],
};

function paint() {
    var w = mgraphics.size[0];
    var h = mgraphics.size[1];

    // Background
    mgraphics.set_source_rgba(colors.bg[0], colors.bg[1], colors.bg[2], 1.0);
    mgraphics.rectangle(0, 0, w, h);
    mgraphics.fill();

    var padding = 3;
    var labelHeight = 12;
    var barWidth = Math.floor((w - padding * 3) / 2);
    var barHeight = h - labelHeight - padding * 2;
    var barY = padding;

    // Input bar
    drawBar(padding, barY, barWidth, barHeight, inputLevel, colors.input);

    // Output bar
    drawBar(padding * 2 + barWidth, barY, barWidth, barHeight, outputLevel, colors.output);

    // Labels
    mgraphics.set_source_rgba(colors.text[0], colors.text[1], colors.text[2], 1.0);
    mgraphics.select_font_face("Arial");
    mgraphics.set_font_size(7);

    var inLabel = "IN";
    var te = mgraphics.text_measure(inLabel);
    mgraphics.move_to(padding + barWidth / 2 - te[0] / 2, h - 2);
    mgraphics.show_text(inLabel);

    var outLabel = "OUT";
    te = mgraphics.text_measure(outLabel);
    mgraphics.move_to(padding * 2 + barWidth + barWidth / 2 - te[0] / 2, h - 2);
    mgraphics.show_text(outLabel);
}

function drawBar(x, y, w, h, level, color) {
    // Bar background
    mgraphics.set_source_rgba(colors.barBg[0], colors.barBg[1], colors.barBg[2], 1.0);
    mgraphics.rectangle(x, y, w, h);
    mgraphics.fill();

    // Filled portion (bottom to top)
    var fillHeight = Math.max(0, Math.min(h, h * level));
    if (fillHeight > 1) {
        var fillY = y + h - fillHeight;

        // Gradient effect: brighter at top of fill
        mgraphics.set_source_rgba(color[0], color[1], color[2], 0.6);
        mgraphics.rectangle(x, fillY, w, fillHeight);
        mgraphics.fill();

        // Bright top edge
        var edgeHeight = Math.min(3, fillHeight);
        mgraphics.set_source_rgba(color[0], color[1], color[2], 0.95);
        mgraphics.rectangle(x, fillY, w, edgeHeight);
        mgraphics.fill();
    }
}

function input_hit() {
    inputLevel = Math.min(maxLevel, inputLevel + hitEnergy);
    ensureAnimating();
}

function output_hit() {
    outputLevel = Math.min(maxLevel, outputLevel + hitEnergy);
    ensureAnimating();
}

function ensureAnimating() {
    if (!animating) {
        animating = true;
        animTask = new Task(animate);
        animTask.interval = 33; // ~30fps
        animTask.repeat();
    }
}

function animate() {
    inputLevel *= decay;
    outputLevel *= decay;

    if (inputLevel < 0.005) inputLevel = 0;
    if (outputLevel < 0.005) outputLevel = 0;

    if (inputLevel === 0 && outputLevel === 0) {
        animating = false;
        if (animTask) {
            animTask.cancel();
            animTask = null;
        }
    }

    mgraphics.redraw();
}

function bang() {
    mgraphics.redraw();
}
