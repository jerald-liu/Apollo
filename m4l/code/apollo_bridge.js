/**
 * Apollo Bridge — Node for Max script
 *
 * Handles OSC communication between Max4Live and the Python inference server,
 * plus lifecycle management of the Python subprocess.
 *
 * Messages from Max patcher:
 *   engine_start          — spawn Python inference server
 *   engine_stop           — kill Python process
 *   note <p> <v> <dt> <dur> <ped>  — forward note to engine
 *   pedal <val>           — forward pedal change
 *   config <temp> <topk> <density> <timbreInf>  — update generation params
 *   transport <playing> <tempo> <num> <den>  — send transport state
 *   model_load <name>     — request model switch
 *   timbre_offset <b> <a> <r>  — set timbral offsets
 *   bypass <0|1>          — toggle bypass
 *
 * Messages to Max patcher:
 *   gen_note <p> <v> <dt_ms> <dur_ms> <ped>  — generated note
 *   gen_cc <cc_num> <cc_val>                   — timbral CC
 *   gen_timbre <b> <a> <r> <w> <f>            — raw timbre for display
 *   status <state> <latency_ms>               — engine status
 *   connection <0|1|2>                         — 0=off, 1=connected, 2=slow
 *   error <message>                            — error report
 */

const Max = require("max-api");
const { spawn } = require("child_process");
const dgram = require("dgram");
const path = require("path");

// --- Configuration ---
const ENGINE_PORT = 7401; // We send to this port (Python listens here)
const LISTEN_PORT = 7400; // We listen on this port (Python sends here)
const PING_INTERVAL_MS = 2000;
const PING_TIMEOUT_MS = 500;
const SLOW_THRESHOLD_MS = 2000;

// --- State ---
let pythonProcess = null;
let udpClient = null;
let udpServer = null;
let pingTimer = null;
let lastPongTime = 0;
let connected = false;
let pendingPingTime = 0;

// Resolve project root (m4l/code/ -> project root)
const projectRoot = path.resolve(__dirname, "..", "..");

// --- UDP / OSC helpers ---
// Minimal OSC encoding (we avoid npm dependencies in Node for Max)

function encodeOSCString(str) {
  const buf = Buffer.from(str + "\0", "ascii");
  const pad = 4 - (buf.length % 4);
  return pad < 4 ? Buffer.concat([buf, Buffer.alloc(pad)]) : buf;
}

function encodeOSCInt(val) {
  const buf = Buffer.alloc(4);
  buf.writeInt32BE(val, 0);
  return buf;
}

function encodeOSCFloat(val) {
  const buf = Buffer.alloc(4);
  buf.writeFloatBE(val, 0);
  return buf;
}

function buildOSCMessage(address, args) {
  let typetag = ",";
  const argBuffers = [];

  for (const arg of args) {
    if (typeof arg === "number") {
      if (Number.isInteger(arg)) {
        typetag += "i";
        argBuffers.push(encodeOSCInt(arg));
      } else {
        typetag += "f";
        argBuffers.push(encodeOSCFloat(arg));
      }
    } else if (typeof arg === "string") {
      typetag += "s";
      argBuffers.push(encodeOSCString(arg));
    }
  }

  return Buffer.concat([
    encodeOSCString(address),
    encodeOSCString(typetag),
    ...argBuffers,
  ]);
}

function readOSCString(buf, offset) {
  let end = offset;
  while (end < buf.length && buf[end] !== 0) end++;
  const str = buf.toString("ascii", offset, end);
  end++; // skip null
  const padded = end + ((4 - (end % 4)) % 4);
  return [str, padded];
}

function parseOSCMessage(buf) {
  let offset = 0;
  let address;
  [address, offset] = readOSCString(buf, offset);

  let typetag;
  [typetag, offset] = readOSCString(buf, offset);
  typetag = typetag.slice(1); // remove leading comma

  const args = [];
  for (const t of typetag) {
    if (t === "i") {
      args.push(buf.readInt32BE(offset));
      offset += 4;
    } else if (t === "f") {
      args.push(buf.readFloatBE(offset));
      offset += 4;
    } else if (t === "s") {
      let str;
      [str, offset] = readOSCString(buf, offset);
      args.push(str);
    }
  }

  return { address, args };
}

function sendOSC(address, args) {
  if (!udpClient) return;
  const msg = buildOSCMessage(address, args);
  udpClient.send(msg, 0, msg.length, ENGINE_PORT, "127.0.0.1");
}

// --- UDP Server (receive from Python) ---

function startUDPServer() {
  if (udpServer) return;

  udpServer = dgram.createSocket("udp4");

  udpServer.on("message", (msg) => {
    try {
      const { address, args } = parseOSCMessage(msg);
      handleEngineMessage(address, args);
    } catch (e) {
      Max.post(`[Apollo] OSC parse error: ${e.message}`);
    }
  });

  udpServer.on("error", (err) => {
    Max.post(`[Apollo] UDP server error: ${err.message}`);
    Max.outlet("error", `Port ${LISTEN_PORT} in use`);
    Max.outlet("connection", 0);
  });

  udpServer.bind(LISTEN_PORT, () => {
    Max.post(`[Apollo] Listening on UDP port ${LISTEN_PORT}`);
  });

  udpClient = dgram.createSocket("udp4");
}

function stopUDPServer() {
  if (udpServer) {
    udpServer.close();
    udpServer = null;
  }
  if (udpClient) {
    udpClient.close();
    udpClient = null;
  }
}

// --- Handle messages from Python engine ---

function handleEngineMessage(address, args) {
  switch (address) {
    case "/apollo/gen/note":
      // [pitch, velocity, deltaTimeMs, durationMs, pedal]
      Max.outlet("gen_note", ...args);
      break;

    case "/apollo/gen/cc":
      // [ccNumber, value]
      Max.outlet("gen_cc", ...args);
      break;

    case "/apollo/gen/timbre":
      // [brightness, attack, richness, warmth, flux]
      Max.outlet("gen_timbre", ...args);
      break;

    case "/apollo/status":
      // [state, latencyMs]
      Max.outlet("status", ...args);
      break;

    case "/apollo/pong":
      lastPongTime = Date.now();
      const rtt = lastPongTime - pendingPingTime;
      if (rtt < SLOW_THRESHOLD_MS) {
        if (!connected) {
          connected = true;
          Max.post("[Apollo] Connected to engine");
        }
        Max.outlet("connection", 1);
        Max.outlet("latency", rtt / 2);
      } else {
        Max.outlet("connection", 2); // slow
        Max.outlet("latency", rtt / 2);
      }
      break;

    case "/apollo/error":
      Max.outlet("error", args[0] || "Unknown error");
      break;
  }
}

// --- Ping / heartbeat ---

function startPing() {
  stopPing();
  pingTimer = setInterval(() => {
    pendingPingTime = Date.now();
    sendOSC("/apollo/ping", []);

    // Check for timeout
    setTimeout(() => {
      if (Date.now() - lastPongTime > PING_INTERVAL_MS + PING_TIMEOUT_MS) {
        if (connected) {
          connected = false;
          Max.post("[Apollo] Connection lost");
        }
        Max.outlet("connection", 0);
      }
    }, PING_TIMEOUT_MS);
  }, PING_INTERVAL_MS);
}

function stopPing() {
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

// --- Python subprocess management ---

function startEngine() {
  if (pythonProcess) {
    Max.post("[Apollo] Engine already running");
    return;
  }

  startUDPServer();

  const pythonPath = path.join(projectRoot, "venv", "bin", "python3");
  const scriptPath = path.join(projectRoot, "src", "inference_server.py");
  const configPath = path.join(projectRoot, "configs", "inference.yaml");

  Max.post(`[Apollo] Starting engine: ${pythonPath} ${scriptPath}`);

  pythonProcess = spawn(pythonPath, [scriptPath, "--config", configPath], {
    cwd: projectRoot,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });

  pythonProcess.stdout.on("data", (data) => {
    const lines = data.toString().trim().split("\n");
    for (const line of lines) {
      Max.post(`[Apollo Engine] ${line}`);
    }
  });

  pythonProcess.stderr.on("data", (data) => {
    const lines = data.toString().trim().split("\n");
    for (const line of lines) {
      Max.post(`[Apollo Engine ERR] ${line}`);
      // Report first error line to M4L device
      if (line.includes("Error") || line.includes("error")) {
        Max.outlet("error", line.slice(0, 120));
      }
    }
  });

  pythonProcess.on("close", (code) => {
    Max.post(`[Apollo] Engine process exited with code ${code}`);
    pythonProcess = null;
    connected = false;
    stopPing();
    Max.outlet("connection", 0);
  });

  pythonProcess.on("error", (err) => {
    Max.post(`[Apollo] Failed to start engine: ${err.message}`);
    Max.outlet("error", `Failed to start: ${err.message}`);
    Max.outlet("connection", 0);
    pythonProcess = null;
  });

  // Start pinging after a brief delay to let Python start up
  setTimeout(() => startPing(), 1500);
}

function stopEngine() {
  stopPing();
  if (pythonProcess) {
    Max.post("[Apollo] Stopping engine...");
    pythonProcess.kill("SIGTERM");
    // Force kill after 3 seconds if it hasn't exited
    setTimeout(() => {
      if (pythonProcess) {
        pythonProcess.kill("SIGKILL");
        pythonProcess = null;
      }
    }, 3000);
  }
  connected = false;
  Max.outlet("connection", 0);
}

// --- Max message handlers ---

Max.addHandler("engine_start", () => startEngine());
Max.addHandler("engine_stop", () => stopEngine());

Max.addHandler("note", (pitch, velocity, deltaTime, duration, pedal) => {
  sendOSC("/apollo/note", [
    Math.round(pitch),
    velocity,
    deltaTime,
    duration,
    Math.round(pedal),
  ]);
});

Max.addHandler("pedal", (value) => {
  sendOSC("/apollo/pedal", [Math.round(value)]);
});

Max.addHandler("config", (temperature, topK, density, timbreInfluence) => {
  sendOSC("/apollo/config", [temperature, Math.round(topK), density, timbreInfluence]);
});

Max.addHandler("transport", (playing, tempo, num, den) => {
  sendOSC("/apollo/transport", [Math.round(playing), tempo, Math.round(num), Math.round(den)]);
});

Max.addHandler("model_load", (name) => {
  sendOSC("/apollo/model/load", [name]);
});

Max.addHandler("timbre_offset", (brightness, attack, richness) => {
  sendOSC("/apollo/timbre/offset", [brightness, attack, richness]);
});

Max.addHandler("bypass", (state) => {
  sendOSC("/apollo/bypass", [Math.round(state)]);
});

Max.addHandler("cc_map", (brightness_cc, attack_cc, richness_cc) => {
  sendOSC("/apollo/cc_map", [
    Math.round(brightness_cc),
    Math.round(attack_cc),
    Math.round(richness_cc),
  ]);
});

Max.addHandler("velocity_scale", (scale) => {
  sendOSC("/apollo/velocity_scale", [scale]);
});

// Cleanup on script unload
Max.addHandler("bang", () => {
  Max.post("[Apollo] Bridge ready");
});

// Ensure cleanup on exit
process.on("exit", () => {
  stopEngine();
  stopUDPServer();
});

Max.post("[Apollo] Bridge script loaded");
