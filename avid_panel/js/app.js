/**
 * Avid Transcription Panel — JavaScript
 *
 * Communicates with the local Python server (localhost:8765).
 * Also integrates with Avid Media Composer's JS panel API when available,
 * falling back gracefully to manual file-path input when running outside Avid.
 */

const SERVER = "http://localhost:8765";
const POLL_MS = 800;

// ── State ──────────────────────────────────────────────────────────────────

let currentJobId = null;
let pollTimer = null;
let lastResult = null;
let serverReady = false;

// ── DOM refs ───────────────────────────────────────────────────────────────

const $  = id => document.getElementById(id);
const indicator   = $("server-indicator");
const serverLabel = $("server-label");
const mediaPath   = $("media-path");
const btnFromAvid = $("btn-from-avid");
const btnTranscribe = $("btn-transcribe");
const progressWrap  = $("progress-wrap");
const progressFill  = $("progress-fill");
const progressMsg   = $("progress-msg");
const previewWrap   = $("preview-wrap");
const preview       = $("preview");
const actionsWrap   = $("actions-wrap");
const btnImport     = $("btn-import-markers");
const btnCopySrt    = $("btn-copy-srt");
const btnNew        = $("btn-new");
const toast         = $("toast");

// ── Avid Media Composer JS API ─────────────────────────────────────────────

/**
 * Returns the file-system path of the currently selected clip in Avid's bin.
 * Works when the panel is running inside Media Composer; gracefully returns
 * null when running in a browser for development/testing.
 */
async function getAvidSelectedClipPath() {
  try {
    // Avid MC exposes window.avidmc (older) or window.avid.mc (newer builds)
    const mc = window.avidmc || (window.avid && window.avid.mc);
    if (!mc) return null;

    const clips = await mc.getSelectedClips();
    if (!clips || clips.length === 0) { showToast("No clip selected in bin", "error"); return null; }

    const clip = clips[0];
    // Resolve the linked media file path
    const path = clip.filePath || clip.mediaFilePath || clip.path || null;
    return path;
  } catch (e) {
    console.warn("Avid MC API unavailable:", e);
    return null;
  }
}

/**
 * Import marker data back into the currently open Avid sequence/bin.
 */
async function importMarkersIntoAvid(markersText) {
  try {
    const mc = window.avidmc || (window.avid && window.avid.mc);
    if (!mc) {
      showToast("Avid API not available – copy the marker file manually", "error");
      return false;
    }
    // Parse our tab-delimited markers into the MC marker format
    const lines = markersText.trim().split("\n").slice(1);  // skip header
    const markers = lines.map(line => {
      const [name, inTC, outTC, track, color, comment] = line.split("\t");
      return { name, inTC, outTC, track, color: color || "Red", comment };
    });
    await mc.importMarkers(markers);
    showToast("Markers imported into Avid", "success");
    return true;
  } catch (e) {
    console.warn("importMarkers failed:", e);
    showToast("Could not import markers: " + e.message, "error");
    return false;
  }
}

// ── Server health check ────────────────────────────────────────────────────

async function checkServer() {
  try {
    const res = await fetch(`${SERVER}/api/health`, { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      setServerStatus(true);
      return true;
    }
  } catch (_) {}
  setServerStatus(false);
  return false;
}

function setServerStatus(ok) {
  serverReady = ok;
  indicator.className = ok ? "connected" : "";
  serverLabel.textContent = ok ? "Server ready" : "Server offline";
  btnTranscribe.disabled = !ok || !mediaPath.value.trim();
}

// Poll server health every 5 s
setInterval(checkServer, 5000);
checkServer();

// ── Input events ───────────────────────────────────────────────────────────

mediaPath.addEventListener("input", () => {
  btnTranscribe.disabled = !serverReady || !mediaPath.value.trim();
});

btnFromAvid.addEventListener("click", async () => {
  const path = await getAvidSelectedClipPath();
  if (path) {
    mediaPath.value = path;
    btnTranscribe.disabled = !serverReady;
    showToast("Clip path loaded from bin");
  } else if (!path) {
    // Prompt the user if Avid API unavailable
    showToast("Select a clip in the Avid bin first", "error");
  }
});

// ── Transcribe ─────────────────────────────────────────────────────────────

btnTranscribe.addEventListener("click", async () => {
  const path = mediaPath.value.trim();
  if (!path) { showToast("Enter a media file path", "error"); return; }

  const formats = [];
  if ($("fmt-srt").checked)     formats.push("srt");
  if ($("fmt-vtt").checked)     formats.push("vtt");
  if ($("fmt-csv").checked)     formats.push("csv");
  if ($("fmt-markers").checked) formats.push("avid_markers");

  if (!formats.length) { showToast("Select at least one output format", "error"); return; }

  const body = {
    media_path:       path,
    whisper_model:    $("model").value,
    language:         $("language").value || null,
    task:             $("task").value,
    output_formats:   formats,
    audio_track:      parseInt($("audio-track").value, 10),
    fps:              parseFloat($("fps").value),
  };

  try {
    const res = await fetch(`${SERVER}/api/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Server error", "error");
      return;
    }
    const data = await res.json();
    currentJobId = data.job_id;
    startPolling();
    setUIState("running");
  } catch (e) {
    showToast("Could not reach server: " + e.message, "error");
  }
});

// ── Polling ────────────────────────────────────────────────────────────────

function startPolling() {
  stopPolling();
  pollTimer = setInterval(poll, POLL_MS);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function poll() {
  if (!currentJobId) { stopPolling(); return; }
  try {
    const res = await fetch(`${SERVER}/api/status/${currentJobId}`);
    if (!res.ok) return;
    const data = await res.json();

    updateProgress(data.progress, data.message);

    if (data.status === "done") {
      stopPolling();
      lastResult = data.result;
      onDone(data.result);
    } else if (data.status === "error") {
      stopPolling();
      setUIState("error");
      showToast(data.error || "Transcription failed", "error");
    }
  } catch (_) {}
}

function updateProgress(frac, msg) {
  progressFill.style.width = `${Math.round(frac * 100)}%`;
  progressMsg.textContent = msg || "";
}

// ── Done ───────────────────────────────────────────────────────────────────

function onDone(result) {
  setUIState("done");
  preview.textContent = result.srt_preview || "(no transcript)";
  showToast(
    `Done  ·  ${result.segment_count} segments  ·  ${result.language}  ·  ${result.elapsed?.toFixed(1)}s`,
    "success"
  );
}

// ── Post-job actions ───────────────────────────────────────────────────────

btnImport.addEventListener("click", async () => {
  if (!lastResult?.avid_markers) { showToast("No marker data", "error"); return; }
  await importMarkersIntoAvid(lastResult.avid_markers);
});

btnCopySrt.addEventListener("click", () => {
  if (!lastResult?.srt_preview) return;
  navigator.clipboard.writeText(lastResult.srt_preview).then(() => {
    showToast("SRT copied to clipboard", "success");
  });
});

btnNew.addEventListener("click", () => {
  currentJobId = null;
  lastResult = null;
  mediaPath.value = "";
  setUIState("idle");
  updateProgress(0, "");
  preview.textContent = "";
});

// ── UI state machine ───────────────────────────────────────────────────────

function setUIState(state) {
  // state: idle | running | done | error
  const running = state === "running";
  const done    = state === "done";

  btnTranscribe.disabled = running || !serverReady;
  btnTranscribe.textContent = running ? "Transcribing…" : "Transcribe";

  progressWrap.className = (running || done) ? "card visible" : "card";
  previewWrap.className  = done ? "card visible" : "card";
  actionsWrap.className  = done ? "visible" : "";
}

// ── Toast ──────────────────────────────────────────────────────────────────

let toastTimer = null;
function showToast(msg, type = "") {
  toast.textContent = msg;
  toast.className = "show" + (type ? " " + type : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = ""; }, 3500);
}
