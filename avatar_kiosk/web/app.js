'use strict';
const $ = id => document.getElementById(id);
const canvas = $('avatar'), context = canvas.getContext('2d');
let socket, audio, source, sources = [], turn = null, packets = [], packetBytes = 0;
let pendingLength = null;
let ready = false, busy = false, connected = false, full = false, preparing = false;
let epoch = 0, startTime = 0, lastFrame = -1, decoding = false, lastImage;
let activeEmotion = 'neutral', activeEnergy = 0, lastJpeg = null;
let streamingStarted = false, allFramesDone = false;
let expectedFrames = 0, firstFrameAt = 0, startTimer = 0, timing = {};
const motionState = new AvatarMotion.MotionState();
const idleBlink = new AvatarMotion.IdleBlink();
const blinkRenderer = new AvatarMotion.BlinkRenderer();
let motionRenderer;
try { motionRenderer = new AvatarMotion.Renderer(); } catch { motionRenderer = new AvatarMotion.CanvasRenderer(); }
const idle = new Image();
idle.onload = () => { if (!turn) draw(idle); };
idle.src = '/portrait';
function draw(image) {
  lastImage = image;
}
// One continuous motion clock: pausing speech never snaps the hat or charm home.
function renderMotion(now) {
  if (lastImage) {
    const speaking = !!source && speakerTime() >= startTime;
    const motion = motionState.sample(now / 1000, speaking, activeEmotion, activeEnergy, preparing && !speaking);
    // Blink only on the original idle image; Ditto owns the eyes during speech.
    const blink = idleBlink.amount(now / 1000, !speaking && lastImage === idle);
    const portrait = blinkRenderer.render(lastImage, blink);
    let rendered;
    if (motionRenderer) {
      try { rendered = motionRenderer.render(portrait, full, motion); }
      catch { motionRenderer = new AvatarMotion.CanvasRenderer(); rendered = motionRenderer.render(portrait, full, motion); }
    }
    const width = lastImage.width, height = lastImage.height;
    const crop = full ? [0, 0, width, height] : [width * .24, 0, width * .5, height * .35];
    const outputHeight = Math.round(720 * crop[3] / crop[2]);
    if (canvas.width !== 720 || canvas.height !== outputHeight) { canvas.width = 720; canvas.height = outputHeight; }
    if (rendered) context.drawImage(rendered, 0, 0, canvas.width, canvas.height);
    else context.drawImage(lastImage, ...crop, 0, 0, canvas.width, canvas.height);
  }
  requestAnimationFrame(renderMotion);
}
requestAnimationFrame(renderMotion);
function setPreparing(value) {
  preparing = value;
  $('stage-status').dataset.thinking = String(value);
  $('portrait').setAttribute('aria-busy', String(value));
  if (value) $('mood').textContent = 'Thinking';
  else if (!source) $('mood').textContent = 'Ready to meet you';
}
function status(text) { $('status').textContent = text; }
function controls() {
  $('speak').disabled = !connected || !ready || busy || !!turn;
  $('stop').disabled = !connected || (!busy && !turn);
  $('connect').hidden = connected;
}
function reset() {
  setPreparing(false);
  epoch++;
  for (const s of sources) { s.onended = null; try { s.stop(); } catch {} }
  sources = []; source = null;
  turn = null; packets = []; packetBytes = 0; lastFrame = -1; decoding = false;
  pendingLength = null;
  activeEmotion = 'neutral'; activeEnergy = 0; lastJpeg = null;
  streamingStarted = false; allFramesDone = false;
  expectedFrames = 0; firstFrameAt = 0; startTimer = 0;
  $('mood').textContent = 'Ready to meet you';
  if (idle.complete && idle.naturalWidth) draw(idle);
}
async function post(path, data) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data || {})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Request failed');
  return result;
}
function fail(error) {
  reset(); ready = false; busy = false; status(error.message || String(error)); controls();
}
function pcmBytes(base64) {
  const raw = atob(base64), bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}
function speakerTime() {
  // Map to the output device clock where supported, excluding output latency.
  const stamp = audio.getOutputTimestamp?.();
  return stamp && stamp.contextTime > 0 ? stamp.contextTime + (performance.now() - stamp.performanceTime) / 1000
    : audio.currentTime - (audio.outputLatency || 0);
}
function animate(token) {
  if (token !== epoch || !source) return;
  const index = Math.min(packets.length - 1, Math.floor((speakerTime() - startTime) * 25));
  if (index >= 0) { if (preparing) setPreparing(false); activeEnergy = packets[index].energy || 0; activeEmotion = packets[index].emotion || 'neutral'; }
  if (index >= 0 && index !== lastFrame && !decoding) {
    lastFrame = index; decoding = true;
    const frame = packets[index];
    if (frame.jpeg === lastJpeg) {
      decoding = false; $('mood').textContent = frame.emotion || 'neutral';
      requestAnimationFrame(() => animate(token)); return;
    }
    const image = new Image();
    image.onload = () => {
      if (token !== epoch) return;
      decoding = false; lastJpeg = frame.jpeg; draw(image); $('mood').textContent = frame.emotion || 'neutral';
    };
    image.onerror = () => { if (token === epoch) decoding = false; };
    image.src = 'data:image/jpeg;base64,' + frame.jpeg;
  }
  requestAnimationFrame(() => animate(token));
}

// ---------------------------------------------------------------------------
// Streaming playback with calculated start and adaptive headroom:
// Start audio as soon as enough frames have buffered based on GPU render rate,
// preventing stuttering while keeping the initial delay as low as 2-5 seconds.
// ---------------------------------------------------------------------------
const MIN_START_FRAMES = 12;   // never start with less than 0.5 s buffered
const SAFETY_FRAMES = 12;      // extra 0.5 s cushion
const REBUFFER_FRAMES = 25;    // after running dry, wait for 1 s of new frames
const PLAY_RATE = 25;          // frames per second needed for playback
const MAX_PROTECT_SECONDS = 8; // cap start-rule look-ahead: only protect first 8 s of audio

function startRule() {
  const n = packets.length;
  if (allFramesDone) return n > 0;
  if (n < MIN_START_FRAMES) return false;
  if (!expectedFrames) return n >= 25;            // length unknown: old behaviour
  const seconds = (performance.now() - firstFrameAt) / 1000;
  if (seconds < 0.5) return false;                // too early to measure GPU speed
  const rate = Math.min((n - 1) / seconds, PLAY_RATE);
  // Cap: for long replies only protect the first MAX_PROTECT_SECONDS of audio.
  // Once playing, the GPU will keep up; the formula need not demand frames for the full reply.
  const protectedFrames = Math.min(expectedFrames, MAX_PROTECT_SECONDS * PLAY_RATE);
  const need = protectedFrames * (1 - rate / PLAY_RATE) + SAFETY_FRAMES;
  return n >= need;
}

function tryStreamingStart() {
  if (streamingStarted || !turn || !packets.length) return;
  if (!startRule()) {
    const token = epoch;
    if (!startTimer) startTimer = setTimeout(() => { startTimer = 0; if (token === epoch) tryStreamingStart(); }, 100);
    return;
  }
  streamingStarted = true;
  playStreaming().catch(error => { fail(error); socket.close(); });
}

async function playStreaming() {
  const token = epoch;
  await audio.resume();
  if (token !== epoch) return;
  if (audio.state !== 'running') throw new Error('Audio is paused. Click Connect again to enable sound.');
  // Decode energy for currently available frames.
  const decodeEnergy = (from) => {
    for (let i = from; i < packets.length; i++) {
      if (packets[i].energy !== undefined) continue;
      const bytes = pcmBytes(packets[i].pcm), view = new DataView(bytes.buffer);
      if (bytes.length !== 1280) throw new Error('Invalid audio packet');
      let squareSum = 0;
      for (let j = 0; j < 640; j++) { const v = view.getInt16(j * 2, true); squareSum += v * v; }
      packets[i].energy = Math.min(1, Math.sqrt(squareSum / 640) / 6000);
    }
  };
  decodeEnergy(0);
  // Build initial audio buffer from currently available frames.
  let currentLen = packets.length;
  let buffer = audio.createBuffer(1, currentLen * 640, 16000);
  let samples = buffer.getChannelData(0);
  for (let i = 0; i < currentLen; i++) {
    const bytes = pcmBytes(packets[i].pcm), view = new DataView(bytes.buffer);
    for (let j = 0; j < 640; j++) samples[i * 640 + j] = view.getInt16(j * 2, true) / 32768;
  }
  source = audio.createBufferSource(); source.buffer = buffer; source.connect(audio.destination);
  sources.push(source);
  const playingTurn = turn;
  let scheduledEnd = currentLen * 640 / 16000; // seconds of audio scheduled
  startTime = audio.currentTime + .06; source.start(startTime);
  status('Speaking'); animate(token);

  timing.audioStart = performance.now();
  const s = k => ((timing[k] - timing.click) / 1000).toFixed(2);
  console.log(`click→started ${s('started')}s | first frame ${s('firstFrame')}s | first sound ${s('audioStart')}s | frames buffered ${currentLen} of ${expectedFrames || '?'}`);
  window.avatarTiming = timing;

  // Poll for new frames and stitch continuation AudioBufferSources so playback
  // continues without gaps while the GPU is still rendering.
  const extendOrFinish = () => {
    if (token !== epoch) return;
    const now = audio.currentTime;
    const prevEnd = startTime + scheduledEnd;
    const running = prevEnd > now + .02;
    const pending = packets.length - currentLen;
    if (pending > 0 && (running || allFramesDone || pending >= REBUFFER_FRAMES)) {
      decodeEnergy(currentLen);
      const nextBuffer = audio.createBuffer(1, pending * 640, 16000);
      const nextSamples = nextBuffer.getChannelData(0);
      for (let i = 0; i < pending; i++) {
        const bytes = pcmBytes(packets[currentLen + i].pcm), view = new DataView(bytes.buffer);
        for (let j = 0; j < 640; j++) nextSamples[i * 640 + j] = view.getInt16(j * 2, true) / 32768;
      }
      const nextSource = audio.createBufferSource();
      nextSource.buffer = nextBuffer; nextSource.connect(audio.destination);
      sources.push(nextSource);
      if (running) {
        nextSource.start(prevEnd);
      } else {
        const resumeAt = now + .005;
        nextSource.start(resumeAt);
        startTime = resumeAt - scheduledEnd;   // keeps the face in step with the sound
        timing.stalls = (timing.stalls || 0) + 1;
        status('Speaking');
      }
      source = nextSource;
      scheduledEnd += pending * 640 / 16000;
      currentLen = packets.length;
    } else if (pending > 0 && !running) {
      status('Buffering…');   // audio ran dry: wait for more frames, then resume cleanly
    }
    if (allFramesDone && currentLen === packets.length) {
      const total = packets.length * 640 / 16000;
      const finish = () => {
        if (token !== epoch) return;
        if (speakerTime() < startTime + total) { setTimeout(finish, 25); return; }
        console.log('stalls:', timing.stalls || 0);
        reset(); busy = false; status('Finishing…'); controls();
        if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:'played',turn:playingTurn}));
      };
      finish();
      return;
    }
    setTimeout(extendOrFinish, 60);
  };
  setTimeout(extendOrFinish, 60);
}

$('connect').onclick = async () => {
  try {
    if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
    await audio.resume();
    if (socket && socket.readyState < WebSocket.CLOSING) return;
    status('Connecting…');
    socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/events`);
    socket.onmessage = event => {
      try {
        const message = JSON.parse(event.data);
        switch (message.type) {
          case 'status': connected = true; ready = message.state === 'ready'; status(message.error || (ready ? 'Ready · write a message below.' : 'Loading avatar…')); break;
          case 'ready': setPreparing(false); ready = true; busy = false; status('Ready · write a message below.'); break;
          case 'started': reset(); timing.started = performance.now(); turn = message.turn;
            if (pendingLength && pendingLength.turn === turn) { expectedFrames = pendingLength.frames; pendingLength = null; }
            ready = false; busy = true; setPreparing(true); status('Thinking · preparing your reply…'); break;
          case 'audio_length':
            if (message.turn === turn) { expectedFrames = message.frames; tryStreamingStart(); }
            else pendingLength = message;
            break;
          case 'frame':
            if (message.turn !== turn) break;
            if (message.index === 0) { firstFrameAt = performance.now(); timing.firstFrame = firstFrameAt; }
            // Render-stride packets repeat one picture for multiple audio frames.
            // Keep a single string reference instead of retaining decoded JSON copies.
            const previous = packets[packets.length - 1];
            if (previous && previous.jpeg === message.jpeg) {
              message.jpeg = previous.jpeg;
              packetBytes += message.pcm.length;
            } else packetBytes += message.jpeg.length + message.pcm.length;
            if (packets.length >= 2250 || packetBytes > 256 * 1024 * 1024) throw new Error('Reply exceeds browser buffer limit');
            if (message.index !== packets.length) throw new Error('A playback packet is missing. Please reconnect.');
            packets.push(message);
            if (!streamingStarted) status('Thinking · preparing your reply…');
            // Try to start streaming playback as soon as we have enough frames.
            tryStreamingStart();
            break;
          case 'done':
            if (message.turn === turn) {
              allFramesDone = true;
              // If streaming already started, extendOrFinish will handle completion.
              // Otherwise start playback now with whatever we have.
              tryStreamingStart();
            }
            break;
          case 'interrupted': reset(); status('Stopping…'); break;
          case 'error': throw new Error(message.message);
        }
        controls();
      } catch (error) { fail(error); socket.close(); }
    };
    socket.onclose = () => { connected = false; ready = false; busy = false; reset(); controls(); if (!$('status').textContent.includes('display')) status('Disconnected. Close any desktop display, then reconnect.'); };
    socket.onerror = () => status('Cannot connect. Check that the avatar service is running.');
  } catch (error) { fail(error); }
};
$('form').onsubmit = async event => {
  event.preventDefault();
  timing = { click: performance.now() };
  if ($('speak').disabled) return;
  busy = true; setPreparing(true); controls(); status('Thinking · preparing your reply…');
  try {
    await audio.resume();
    const result = await post('/speak-text', {text:$('text').value, emotion:$('emotion').value});
    if (result.cancelled) { setPreparing(false); busy = false; status('Stopped. Ready for another message.'); }
  } catch (error) { setPreparing(false); busy = false; status(error.message); }
  controls();
};
$('stop').onclick = async () => {
  reset(); ready = false; controls(); status('Stopping…');
  try {
    const result = await post('/interrupt');
    ready = result.state === 'ready';
    if (ready) status('Stopped. Ready for another message.');
  } catch (error) { status(error.message); }
  busy = false; controls();
};
$('text').oninput = () => { $('count').textContent = `${$('text').value.length} / 800`; };
$('text').oninput();
$('text').onkeydown = event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); $('form').requestSubmit(); } };
$('view').onclick = () => { full = !full; $('view').setAttribute('aria-pressed', String(full)); $('view').textContent = full ? 'Portrait view ↙' : 'Full character ↗'; if (lastImage) draw(lastImage); };
window.addEventListener('pagehide', () => { reset(); socket?.close(); });
