/**
 * Apollo Timbre Meters — jsui script for Max4Live
 *
 * Displays three horizontal bars for brightness, attack, and richness
 * with smooth decay animation.
 *
 * Messages:
 *   timbre <brightness> <attack> <richness> <warmth> <flux>  — update values (0-1)
 */

mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

// Current display values (smoothed)
var brightness = 0.0;
var attack = 0.0;
var richness = 0.0;

// Target values (from model output)
var targetBrightness = 0.0;
var targetAttack = 0.0;
var targetRichness = 0.0;

// Smoothing factor (0 = no smoothing, 1 = frozen)
var smoothing = 0.85;

// Animation
var animTask = null;
var animating = false;

// Colors [r, g, b]
var colors = {
    brightness: [0.95, 0.82, 0.25],   // warm yellow
    attack:     [0.92, 0.45, 0.18],    // orange-red
    richness:   [0.25, 0.72, 0.85],    // blue-cyan
    bg:         [0.15, 0.15, 0.15],    // dark bg
    barBg:      [0.22, 0.22, 0.22],    // bar background
    text:       [0.65, 0.65, 0.65],    // label text
    valText:    [0.8, 0.8, 0.8],       // value text
};

var labels = ["B", "A", "R"];
var barColors = [colors.brightness, colors.attack, colors.richness];

function paint() {
    var w = mgraphics.size[0];
    var h = mgraphics.size[1];
    var values = [brightness, attack, richness];

    // Background
    mgraphics.set_source_rgba(colors.bg[0], colors.bg[1], colors.bg[2], 1.0);
    mgraphics.rectangle(0, 0, w, h);
    mgraphics.fill();

    var barCount = 3;
    var padding = 4;
    var labelWidth = 14;
    var valueWidth = 28;
    var barHeight = Math.floor((h - padding * (barCount + 1)) / barCount);
    var barX = labelWidth + padding;
    var barWidth = w - barX - valueWidth - padding * 2;

    for (var i = 0; i < barCount; i++) {
        var y = padding + i * (barHeight + padding);
        var val = Math.max(0, Math.min(1, values[i]));
        var col = barColors[i];

        // Label
        mgraphics.set_source_rgba(colors.text[0], colors.text[1], colors.text[2], 1.0);
        mgraphics.select_font_face("Arial");
        mgraphics.set_font_size(9);
        mgraphics.move_to(padding, y + barHeight * 0.72);
        mgraphics.show_text(labels[i]);

        // Bar background
        mgraphics.set_source_rgba(colors.barBg[0], colors.barBg[1], colors.barBg[2], 1.0);
        roundRect(barX, y, barWidth, barHeight, 2);
        mgraphics.fill();

        // Filled bar
        if (val > 0.005) {
            var fillWidth = Math.max(2, barWidth * val);
            mgraphics.set_source_rgba(col[0], col[1], col[2], 0.85);
            roundRect(barX, y, fillWidth, barHeight, 2);
            mgraphics.fill();

            // Bright edge highlight
            mgraphics.set_source_rgba(col[0], col[1], col[2], 0.4);
            mgraphics.rectangle(barX + fillWidth - 2, y, 2, barHeight);
            mgraphics.fill();
        }

        // Value text
        var valStr = Math.round(val * 100).toString();
        mgraphics.set_source_rgba(colors.valText[0], colors.valText[1], colors.valText[2], 1.0);
        mgraphics.set_font_size(8);
        var te = mgraphics.text_measure(valStr);
        mgraphics.move_to(barX + barWidth + padding, y + barHeight * 0.72);
        mgraphics.show_text(valStr);
    }
}

function roundRect(x, y, w, h, r) {
    mgraphics.move_to(x + r, y);
    mgraphics.line_to(x + w - r, y);
    mgraphics.arc(x + w - r, y + r, r, -Math.PI / 2, 0);
    mgraphics.line_to(x + w, y + h - r);
    mgraphics.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
    mgraphics.line_to(x + r, y + h);
    mgraphics.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
    mgraphics.line_to(x, y + r);
    mgraphics.arc(x + r, y + r, r, Math.PI, -Math.PI / 2);
    mgraphics.close_path();
}

function timbre() {
    var args = arrayfromargs(arguments);
    if (args.length >= 3) {
        targetBrightness = args[0];
        targetAttack = args[1];
        targetRichness = args[2];
    }
    if (!animating) {
        startAnimation();
    }
}

function startAnimation() {
    animating = true;
    if (animTask) {
        animTask.cancel();
    }
    animTask = new Task(animate);
    animTask.interval = 33; // ~30fps
    animTask.repeat();
}

function animate() {
    brightness = brightness * smoothing + targetBrightness * (1 - smoothing);
    attack = attack * smoothing + targetAttack * (1 - smoothing);
    richness = richness * smoothing + targetRichness * (1 - smoothing);

    // Stop animating when close enough to targets
    var diff = Math.abs(brightness - targetBrightness)
             + Math.abs(attack - targetAttack)
             + Math.abs(richness - targetRichness);

    if (diff < 0.003) {
        brightness = targetBrightness;
        attack = targetAttack;
        richness = targetRichness;
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
