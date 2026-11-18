"""Isolated CUDA worker. No fake animation or fallback mouth movement."""
import base64
import copy
import io
import math
import queue
import sys
import threading
import traceback
from collections import deque

from .audio import HubertWindows, SAMPLES_PER_FRAME
from .expressions import DITTO_EMOTIONS
from .emotion_motion import restore_emotion, expression_controls, SentenceExpression
from .expression_timeline import cue_at


def run_worker(settings, commands, events, cancel=None):
    cancel = cancel or threading.Event()
    try:
        missing = settings.missing()
        if missing:
            raise RuntimeError("Missing Ditto assets: " + ", ".join(missing))
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("Ditto requires a working CUDA GPU for this deployment")
        torch.set_num_threads(2)
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
        import numpy as np
        from PIL import Image
        sys.path.insert(0, settings.ditto)
        import stream_pipeline_online as upstream

        # Replace the file writer only in this isolated process, before setup starts threads.
        class Sink:
            def __init__(self, *args, **kwargs):
                pass

            def __call__(self, rgb, **kwargs):
                emit_frame(rgb)

            def close(self):
                pass

        upstream.VideoWriterByImageIO = Sink
        class StreamingSDK(upstream.StreamSDK):
            def _warp_f3d_worker(self):
                warper = self.warp_f3d.warp_net
                decoder = self.decode_f3d.decoder
                if warper.model_type != "pytorch" or decoder.model_type != "pytorch":
                    return super()._warp_f3d_worker()
                batch_size = max(1, min(settings.batch_size, 8))
                ended = False
                while not self.stop_event.is_set() and not ended:
                    batch = []
                    while len(batch) < batch_size:
                        try:
                            item = self.warp_f3d_queue.get(timeout=0.01 if batch else 1)
                        except queue.Empty:
                            if batch:
                                break
                            if self.stop_event.is_set():
                                return
                            continue
                        if item is None:
                            ended = True
                            break
                        batch.append(item)
                    if batch:
                        if cancel.is_set():
                            continue
                        features = np.concatenate([self.source_info["f_s_lst"][item[0]] for item in batch])
                        source = np.concatenate([item[1] for item in batch])
                        driving = np.concatenate([item[2] for item in batch])
                        # Keep intermediate features on CUDA. Upstream copies these
                        # GPU -> CPU -> GPU separately for every frame.
                        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                            warped = warper.model(torch.from_numpy(features).cuda(),
                                                  torch.from_numpy(source).cuda(),
                                                  torch.from_numpy(driving).cuda())
                            rgb = decoder.model(warped).clamp(0, 1).mul(255).permute(0, 2, 3, 1)
                            rgb = rgb.float().cpu().numpy()
                        for item, picture in zip(batch, rgb):
                            self.decode_f3d_queue.put([item[0], picture])
                self.decode_f3d_queue.put(None)

            def _decode_f3d_worker(self):
                if self.warp_f3d.warp_net.model_type != "pytorch" or self.decode_f3d.decoder.model_type != "pytorch":
                    return super()._decode_f3d_worker()
                while not self.stop_event.is_set():
                    try:
                        item = self.decode_f3d_queue.get(timeout=1)
                    except queue.Empty:
                        continue
                    self.putback_queue.put(item)
                    if item is None:
                        return

            def _motion_stitch_worker(self):
                output_index = 0
                while not self.stop_event.is_set():
                    try:
                        item = self.motion_stitch_queue.get(timeout=1)
                    except queue.Empty:
                        continue
                    if item is None:
                        self.warp_f3d_queue.put(None)
                        break
                    # End padding is only for motion context. Do not spend GPU
                    # time rendering it after the real audio has finished.
                    with condition:
                        skip = finished and output_index >= math.ceil(len(audio) / 1280)
                    skip = skip or cancel.is_set() or output_index % settings.render_stride != 0
                    output_index += 1
                    if skip:
                        continue
                    frame_idx, motion, controls = item
                    source = self.source_info["x_s_info_lst"][frame_idx]
                    motion = restore_emotion(motion, self.motion_stitch.d0,
                                             neutral_reference, (output_index-1)/25, emotion)
                    controls = dict(controls)
                    # Use the matching audio window, not wall time or generation speed.
                    sample_start = (output_index-1)*1280
                    with condition:
                        samples = np.frombuffer(bytes(audio[sample_start:sample_start+2560]), dtype=np.int16).astype(np.float32)
                    energy = float(np.sqrt(np.mean(samples*samples))/6000) if len(samples) else 0
                    controls['delta_exp'] = (sentence_expression.sample((output_index-1)/25, energy)
                                             if sentence_expression else
                                             expression_controls(emotion, (output_index-1)/25, energy))
                    x_s, x_d = self.motion_stitch(source, motion, **controls)
                    self.warp_f3d_queue.put([frame_idx, x_s, x_d])

        neutral_reference = None
        sdk = StreamingSDK(settings.config, settings.data_root)
        original_defaults = copy.deepcopy(sdk.default_kwargs)
        registrar = sdk.avatar_registrar
        registered = {}

        def cached_register(source, **kwargs):
            if "source" not in registered:
                registered["source"] = registrar(source, **kwargs)
            return registered["source"]

        sdk.avatar_registrar = cached_register
        extract_features = sdk.wav2feat.wav2feat
        silent_features = {}

        def cached_silence(samples, *args, **kwargs):
            if np.any(samples):
                return extract_features(samples, *args, **kwargs)
            key = (len(samples), str(args), str(kwargs))
            if key not in silent_features:
                silent_features[key] = extract_features(samples, *args, **kwargs)
            return silent_features[key].copy()

        sdk.wav2feat.wav2feat = cached_silence
        condition = threading.Condition()
        audio = bytearray()
        finished = False
        frame_index = 0
        turn = None
        warming = True

        def emit_frame(rgb):
            nonlocal frame_index
            if cancel.is_set():
                return
            jpeg = None
            if not warming:
                picture = Image.fromarray(rgb)
                buffer = io.BytesIO()
                picture.save(buffer, format="JPEG", quality=85)
                jpeg = base64.b64encode(buffer.getvalue()).decode()
            for _ in range(settings.render_stride):
                start = frame_index * SAMPLES_PER_FRAME * 2
                stop = start + SAMPLES_PER_FRAME * 2
                with condition:
                    condition.wait_for(lambda: finished or cancel.is_set() or len(audio) >= stop, timeout=1)
                    while not finished and not cancel.is_set() and len(audio) < stop:
                        condition.wait(timeout=0.1)
                    if cancel.is_set():
                        return
                    if finished and start >= len(audio):
                        return
                    pcm = bytes(audio[start:stop]).ljust(SAMPLES_PER_FRAME * 2, b"\0")
                if not warming:
                    events.put({"type": "frame", "turn": turn, "index": frame_index,
                                "pts_ms": frame_index * 40, "jpeg": jpeg,
                                "emotion": cue_at(timeline, frame_index / 25)["emotion"] if timeline else emotion,
                                "pcm": base64.b64encode(pcm).decode()})
                frame_index += 1

        bootstrap = deque([("begin", "warmup"), ("audio", bytes(32000)), ("end",)])
        while True:
            try:
                command = bootstrap.popleft() if bootstrap else commands.get(timeout=0.1)
            except queue.Empty:
                if cancel.is_set():
                    cancel.clear()
                    events.put({"type": "ready"})
                continue
            kind = command[0]
            if kind == "begin":
                turn = command[1]
                emotion = command[2] if len(command) > 2 else "neutral"
                timeline = command[3] if len(command) > 3 else None
                sentence_expression = SentenceExpression(timeline) if timeline else None
                # A neutral neural base avoids carrying the first sentence mood
                # through all later sentences; timed controls supply the accents.
                if timeline:
                    emotion = "neutral"
                audio = bytearray()
                finished = False
                frame_index = 0
                windows = HubertWindows()
                sdk.default_kwargs = copy.deepcopy(original_defaults)
                sdk.setup(settings.image, "/tmp/ditto-unused", online_mode=True,
                          max_size=settings.max_size, emo=DITTO_EMOTIONS[emotion], ch_info=None,
                          delta_eye_arr=None, overall_ctrl_info={}, overlap_v2=70,
                          use_d_keys=("exp",),
                          sampling_timesteps=settings.sampling_steps)
                # Default stitching replaces all non-eye/non-lip expression points
                # with the source portrait, hiding much of the emotion condition.
                sdk.motion_stitch.fix_exp_a1 = np.ones((1, 63), dtype=np.float32)
                sdk.motion_stitch.fix_exp_a2 = np.zeros((1, 63), dtype=np.float32)
                sdk.motion_stitch.fix_exp_a3 = 0
                # Upstream online motion discards its first prediction except the
                # fused tail. Prime that discarded region with silence so output
                # frame zero corresponds to input audio zero, including short turns.
                prime = sdk.audio2motion.seq_frames - sdk.overlap_v2 - sdk.audio2motion.fuse_length
                if prime > 0:
                    zeros = sdk.wav2feat.wav2feat(np.zeros(prime * 640, np.float32), sr=16000)
                    sdk.audio2motion_queue.put(zeros)
                    sdk.cond_idx_start -= prime
                if not warming:
                    events.put({"type": "started", "turn": turn, "emotion": emotion})
            elif kind == "audio":
                if cancel.is_set():
                    continue
                with condition:
                    audio.extend(command[1])
                    condition.notify_all()
                for window in windows.feed(command[1]):
                    sdk.run_chunk(window)
                    if sdk.worker_exception:
                        raise sdk.worker_exception
            elif kind == "end":
                with condition:
                    finished = True
                    condition.notify_all()
                sdk.setup_Nd((len(audio) + 1279) // 1280)
                if not cancel.is_set():
                    for window in windows.finish(sdk.audio2motion.valid_clip_len + sdk.audio2motion.fuse_length):
                        sdk.run_chunk(window)
                sdk.close()
                expected = (len(audio) + 1279) // 1280
                if not cancel.is_set() and frame_index != expected:
                    raise RuntimeError(f"Ditto generated {frame_index} frames; expected {expected}")
                if cancel.is_set():
                    cancel.clear()
                    events.put({"type": "ready"})
                elif warming:
                    neutral_reference = copy.deepcopy(sdk.motion_stitch.d0)
                    warming = False
                    events.put({"type": "ready"})
                else:
                    events.put({"type": "done", "turn": turn, "frames": frame_index})
    except BaseException as exc:
        traceback.print_exc()
        events.put({"type": "error", "message": str(exc)})
        # Upstream can leave non-daemon threads blocked after an exception.
        # The supervisor terminates this process on receiving the error.
