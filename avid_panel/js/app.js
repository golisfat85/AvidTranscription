/**
 * Avid Transcription Panel — JavaScript
 * Communicates with the local Python server (http://localhost:8765).
 */

const SERVER   = "http://localhost:8765";
const POLL_MS  = 800;
const SETTINGS_KEY = "avid_transcription_settings";

// Model download sizes (approx MB, shown as hint)
const MODEL_SIZES = {
  "tiny": "~75 MB", "base": "~145 MB", "small": "~465 MB",
  "medium": "~1.5 GB", "large-v3": "~3.1 GB",
};

// ── State ──────────────────────────────────────────────────────────────────

let currentJobId = null;
let pollTimer    = null;
let lastResult   = null;
let serverReady  = false;

// ── DOM ────────────────────────────────────────────────────────────────────

const $  = id => document.getElementById(id);
const indicator    = $("server-indicator");
const serverLabel  = $("server-label");
const offlineBanner= $("offline-banner");
const ffmpegBanner = $("ffmpeg-banner");
const dropZone     = $("drop-zone");
const mediaPath    = $("media-path");
const btnBrowse    = $("btn-browse");
const btnTranscribe= $("btn-transcribe");
const progressWrap = $("progress-wrap");
const progressFill = $("progress-fill");
const progressMsg  = $("progress-msg");
const resultsWrap  = $("results-wrap");
const resultMeta   = $("result-meta");
const preview      = $("preview");
const btnReveal    = $("btn-reveal");
const btnCopySrt   = $("btn-copy-srt");
const btnNew       = $("btn-new");
const modelSelect  = $("model");
const modelNote    = $("model-note");
const toast        = $("toast");

// ── Settings persistence ────────────────────────────────────────────────────

function saveSettings() {
  const s = {
    model:      modelSelect.value,
    language:   $("language").value,
    task:       $("task").value,
    audioTrack: $("audio-track").value,
    fps:        $("fps").value,
    fmtSrt:     $("fmt-srt").checked,
    fmtVtt:     $("fmt-vtt").checked,
    fmtCsv:     $("fmt-csv").checked,
    fmtMarkers: $("fmt-markers").checked,
  };
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)); } catch (_) {}
}

function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "null");
    if (!s) return;
    if (s.model)      modelSelect.value          = s.model;
    if (s.language)   $("language").value         = s.language;
    if (s.task)       $("task").value             = s.task;
    if (s.audioTrack) $("audio-track").value      = s.audioTrack;
    if (s.fps)        $("fps").value              = s.fps;
    if (s.fmtSrt     !== undefined) $("fmt-srt").checked     = s.fmtSrt;
    if (s.fmtVtt     !== undefined) $("fmt-vtt").checked     = s.fmtVtt;
    if (s.fmtCsv     !== undefined) $("fmt-csv").checked     = s.fmtCsv;
    if (s.fmtMarkers !== undefined) $("fmt-markers").checked = s.fmtMarkers;
  } catch (_) {}
}

// Save whenever a setting changes
["model","language","task","audio-track","fps","fmt-srt","fmt-vtt","fmt-csv","fmt-markers"]
  .forEach(id => $( id).addEventListener("change", saveSettings));

// ── Model size hint ─────────────────────────────────────────────────────────

function updateModelNote() {
  const size = MODEL_SIZES[modelSelect.value] || "";
  modelNote.textContent = `First use downloads the model (${size})`;
}
modelSelect.addEventListener("change", updateModelNote);

// ── Server health ───────────────────────────────────────────────────────────

async function checkServer() {
  try {
    const res = await fetch(`${SERVER}/api/health`, { signal: AbortSignal.timeout(2500) });
    if (res.ok) {
      const data = await res.json();
      setServerStatus(true);
      ffmpegBanner.hidden = data.ffmpeg !== false;
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
  offlineBanner.hidden = ok;
  btnTranscribe.disabled = !ok || !mediaPath.value.trim();
}

setInterval(checkServer, 5000);
checkServer();

// ── Drag and drop ───────────────────────────────────────────────────────────

dropZone.addEventListener("dragover", e => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (!file) return;
  // Chromium exposes the real FS path via the non-standard .path property
  const path = file.path || null;
  if (path && path.startsWith("/")) {
    setPath(path);
  } else {
    showToast("Could not read file path — type it in manually", "error");
  }
});

// ── Browse button ───────────────────────────────────────────────────────────

btnBrowse.addEventListener("click", async () => {
  btnBrowse.disabled = true;
  btnBrowse.textContent = "Opening…";
  try {
    const res  = await fetch(`${SERVER}/api/pick-file`, { signal: AbortSignal.timeout(120000) });
    const data = await res.json();
    if (data.path) setPath(data.path);
    else if (!data.cancelled) showToast("Could not open file picker", "error");
  } catch (e) {
    showToast("File picker unavailable", "error");
  } finally {
    btnBrowse.disabled = false;
    btnBrowse.textContent = "Browse…";
  }
});

function setPath(p) {
  mediaPath.value = p;
  btnTranscribe.disabled = !serverReady;
}

mediaPath.addEventListener("input", () => {
  btnTranscribe.disabled = !serverReady || !mediaPath.value.trim();
});

// ── Transcribe ──────────────────────────────────────────────────────────────

btnTranscribe.addEventListener("click", async () => {
  const path = mediaPath.value.trim();
  if (!path) { showToast("Enter a media file path", "error"); return; }

  const formats = [];
  if ($("fmt-srt").checked)     formats.push("srt");
  if ($("fmt-vtt").checked)     formats.push("vtt");
  if ($("fmt-csv").checked)     formats.push("csv");
  if ($("fmt-markers").checked) formats.push("avid_markers");
  if (!formats.length) { showToast("Select at least one output format", "error"); return; }

  saveSettings();

  const body = {
    media_path:    path,
    whisper_model: modelSelect.value,
    language:      $("language").value || null,
    task:          $("task").value,
    output_formats:formats,
    audio_track:   parseInt($("audio-track").value, 10),
    fps:           parseFloat($("fps").value),
  };

  try {
    const res = await fetch(`${SERVER}/api/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(err.detail || "Server error", "error");
      return;
    }
    const data = await res.json();
    currentJobId = data.job_id;
    setUIState("running");
    startPolling();
  } catch (e) {
    showToast("Could not reach server: " + e.message, "error");
  }
});

// ── Polling ─────────────────────────────────────────────────────────────────

function startPolling() { stopPolling(); pollTimer = setInterval(poll, POLL_MS); }
function stopPolling()  { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

async function poll() {
  if (!currentJobId) { stopPolling(); return; }
  try {
    const res  = await fetch(`${SERVER}/api/status/${currentJobId}`);
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
  progressFill.style.width = `${Math.round((frac || 0) * 100)}%`;
  progressMsg.textContent  = msg || "";
}

// ── Done ─────────────────────────────────────────────────────────────────────

function onDone(result) {
  setUIState("done");
  preview.textContent = result.srt_preview || "(no transcript)";

  const mins = result.duration ? (result.duration / 60).toFixed(1) : "?";
  const secs = result.elapsed  ? result.elapsed.toFixed(1)          : "?";
  resultMeta.textContent =
    `${result.segment_count} segments · ${result.language} · ${mins} min · processed in ${secs}s`;

  showToast("Transcription complete!", "success");
}

// ── Actions ──────────────────────────────────────────────────────────────────

btnReveal.addEventListener("click", async () => {
  if (!currentJobId) return;
  try {
    await fetch(`${SERVER}/api/reveal/${currentJobId}`);
    showToast("Opened output folder in Finder");
  } catch (_) {
    showToast("Could not open folder", "error");
  }
});

btnCopySrt.addEventListener("click", () => {
  if (!lastResult?.srt_preview) return;
  navigator.clipboard.writeText(lastResult.srt_preview)
    .then(() => showToast("SRT copied to clipboard", "success"))
    .catch(() => showToast("Could not copy", "error"));
});

btnNew.addEventListener("click", () => {
  currentJobId = null;
  lastResult   = null;
  mediaPath.value = "";
  setUIState("idle");
  updateProgress(0, "");
  preview.textContent = "";
  resultMeta.textContent = "";
});

// ── UI state machine ─────────────────────────────────────────────────────────

function setUIState(state) {
  const running = state === "running";
  const done    = state === "done";

  btnTranscribe.disabled    = running || !serverReady;
  btnTranscribe.textContent = running ? "Transcribing…" : "Transcribe";

  progressWrap.hidden = !(running || done);
  resultsWrap.hidden  = !done;
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let toastTimer = null;
function showToast(msg, type = "") {
  toast.textContent = msg;
  toast.className   = "show" + (type ? " " + type : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = ""; }, 3500);
}

// ── Init ──────────────────────────────────────────────────────────────────────

loadSettings();
updateModelNote();
