"""Independent constant-frame-rate video capture; never an agent observation input."""

import math
from pathlib import Path
import shutil
import subprocess
import threading
import time


class VideoRecorder:
    def __init__(self, window, config, directory):
        self.window, self.config, self.directory = window, config, Path(directory)
        self.fps = config["fps"]
        if self.fps < 30:
            raise ValueError("Task recording must be at least 30 FPS")
        configured = Path(config["ffmpeg"])
        self.ffmpeg = str(configured) if configured.is_file() else shutil.which("ffmpeg")
        if not self.ffmpeg:
            raise FileNotFoundError("FFmpeg missing; run tools/bootstrap.py or set recording.ffmpeg")
        self.stop_event, self.ready = threading.Event(), threading.Event()
        self.error = None
        self.process = self.thread = None
        self.started_at = self.finished_at = None
        self.frames = self.new_frames = self.duplicate_frames = 0
        self.focus_lost_frames = 0
        self.video_path = self.directory / "video.mp4"
        self.partial_path = self.directory / "video.partial.mp4"
        self.log = None

    def start(self):
        # The capture object is created and used only by its owning thread.
        self.thread = threading.Thread(target=self._record, name="recording-30fps", daemon=True)
        self.thread.start()
        if not self.ready.wait(10):
            self.stop()
            raise RuntimeError("No game frame available for recording after ten seconds")
        if self.error:
            raise RuntimeError(self.error)
        return self

    def _record(self):
        camera = None
        try:
            import dxcam
            region = self.window.region()
            monitor_x, monitor_y = self.config.get("monitor_origin_xy", [0, 0])
            crop = (region[0] - monitor_x, region[1] - monitor_y,
                    region[2] - monitor_x, region[3] - monitor_y)
            capture_width, capture_height = crop[2] - crop[0], crop[3] - crop[1]
            if crop[0] < 0 or crop[1] < 0:
                raise RuntimeError("Game is outside the configured capture output; set monitor_origin_xy")
            camera = dxcam.create(device_idx=self.config["device_index"],
                                  output_idx=self.config["output_index"], output_color="BGRA")
            command = [self.ffmpeg, "-hide_banner", "-loglevel", "warning", "-n",
                       "-f", "rawvideo", "-pixel_format", "bgra",
                       "-video_size", f"{capture_width}x{capture_height}",
                       "-framerate", str(self.fps), "-i", "pipe:0", "-an",
                       "-vf", f"scale={self.config['width']}:{self.config['height']}:force_original_aspect_ratio=decrease,pad={self.config['width']}:{self.config['height']}:(ow-iw)/2:(oh-ih)/2",
                       "-c:v", self.config["encoder"], "-preset", self.config["preset"],
                       "-crf", str(self.config["crf"]), "-pix_fmt", "yuv420p",
                       "-r", str(self.fps), "-fps_mode", "cfr", "-movflags", "+faststart",
                       str(self.partial_path)]
            self.log = (self.directory / "ffmpeg.log").open("wb")
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                            stderr=self.log, creationflags=subprocess.CREATE_NO_WINDOW)
            last_frame = None
            initial_deadline = time.monotonic() + 8
            while not self.stop_event.is_set():
                now = time.monotonic()
                if not self.window.foreground():
                    # Do not record a different application if the user switches away.
                    self.focus_lost_frames += 1
                    frame = None
                else:
                    if self.window.region() != region:
                        raise RuntimeError("Game window moved or resized during recording")
                    # DXcam may already cache the first frame while creating
                    # the duplicator. A static menu must still yield a frame.
                    frame = camera.grab(region=crop, new_frame_only=last_frame is not None)
                if frame is not None:
                    last_frame = frame.tobytes()
                    self.new_frames += 1
                elif last_frame is not None:
                    self.duplicate_frames += 1
                if last_frame is None:
                    if now >= initial_deadline:
                        raise RuntimeError("No foreground game frames were captured")
                    self.stop_event.wait(0.01)
                    continue
                if self.started_at is None:
                    self.started_at = time.monotonic()
                    self.ready.set()
                due = max(1, math.floor((time.monotonic() - self.started_at) * self.fps) + 1)
                backlog = due - self.frames
                if backlog > self.fps * self.config["max_backlog_seconds"]:
                    raise RuntimeError("Encoder cannot maintain the recording rate")
                while self.frames < due:
                    self.process.stdin.write(last_frame)
                    self.frames += 1
                deadline = self.started_at + self.frames / self.fps
                self.stop_event.wait(max(0, deadline - time.monotonic()))
            self.finished_at = time.monotonic()
            # Keep MP4 duration aligned with wall time, including a final partial slot.
            if last_frame is not None and self.started_at is not None:
                final_count = math.ceil((self.finished_at - self.started_at) * self.fps)
                if final_count - self.frames <= self.fps * self.config["max_backlog_seconds"]:
                    while self.frames < final_count:
                        self.process.stdin.write(last_frame)
                        self.frames += 1
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
        finally:
            self.finished_at = self.finished_at or time.monotonic()
            if camera is not None:
                try:
                    camera.release()
                except Exception as error:
                    self.error = self.error or f"Capture cleanup failed: {type(error).__name__}"
            if self.process is not None:
                try:
                    if self.process.stdin:
                        self.process.stdin.close()
                    returncode = self.process.wait(timeout=15)
                    if returncode:
                        self.error = self.error or f"FFmpeg exited with code {returncode}; see ffmpeg.log"
                except (OSError, subprocess.TimeoutExpired) as error:
                    self.process.kill()
                    self.process.wait()
                    self.error = self.error or f"Video finalization failed: {type(error).__name__}"
            if self.log:
                self.log.close()
            if not self.error and self.frames and self.partial_path.is_file():
                self.partial_path.replace(self.video_path)
            self.ready.set()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=20)
            if self.thread.is_alive():
                if self.process and self.process.poll() is None:
                    self.process.kill()
                self.thread.join(timeout=3)
                self.error = self.error or "Recording thread did not stop within the deadline"
        return {
            "path": str(self.video_path) if self.video_path.is_file() else None,
            "partial_path": str(self.partial_path) if self.partial_path.is_file() else None,
            "fps": self.fps, "width": self.config["width"], "height": self.config["height"],
            "encoded_frames": self.frames, "new_capture_frames": self.new_frames,
            "duplicate_capture_ticks": self.duplicate_frames, "focus_lost_ticks": self.focus_lost_frames,
            "video_duration_seconds": self.frames / self.fps,
            "wall_duration_seconds": (self.finished_at - self.started_at) if self.started_at else 0,
            "audio": False, "error": self.error,
        }
