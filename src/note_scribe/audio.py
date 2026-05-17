from __future__ import annotations

import time
import wave
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread


class AudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    channels: int
    sample_rate: int
    is_default: bool = False


@dataclass(frozen=True)
class AudioSegment:
    path: Path
    duration_seconds: float
    byte_count: int


def _load_pyaudio():
    try:
        import pyaudiowpatch as pyaudio
    except ImportError as exc:
        raise AudioError(
            "pyaudiowpatch is required for Windows system-audio recording. "
            "Install dependencies with: python -m pip install -e ."
        ) from exc
    return pyaudio


def list_loopback_devices() -> list[AudioDevice]:
    pyaudio = _load_pyaudio()
    devices: list[AudioDevice] = []

    with pyaudio.PyAudio() as pa:
        default_index = _default_loopback_device(pa, pyaudio).get("index")
        for raw in pa.get_loopback_device_info_generator():
            devices.append(
                AudioDevice(
                    index=int(raw["index"]),
                    name=str(raw["name"]),
                    channels=int(raw.get("maxInputChannels") or raw.get("maxOutputChannels") or 2),
                    sample_rate=int(raw.get("defaultSampleRate") or 48000),
                    is_default=int(raw["index"]) == int(default_index),
                )
            )

    return devices


def record_system_audio(
    output_path: Path,
    seconds: float,
    device_index: int | None = None,
    chunk_size: int = 1024,
) -> Path:
    if seconds <= 0:
        raise AudioError("Recording duration must be greater than zero.")

    pyaudio = _load_pyaudio()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pyaudio.PyAudio() as pa:
        device = (
            pa.get_device_info_by_index(device_index)
            if device_index is not None
            else _default_loopback_device(pa, pyaudio)
        )

        channels = int(device.get("maxInputChannels") or 2)
        rate = int(device.get("defaultSampleRate") or 48000)
        sample_format = pyaudio.paInt16
        sample_width = pa.get_sample_size(sample_format)

        frames: list[bytes] = []
        started = time.monotonic()
        with pa.open(
            format=sample_format,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=int(device["index"]),
            frames_per_buffer=chunk_size,
        ) as stream:
            while time.monotonic() - started < seconds:
                frames.append(stream.read(chunk_size, exception_on_overflow=False))

    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(rate)
        wav.writeframes(b"".join(frames))

    return output_path


def record_system_audio_until_stopped(
    output_path: Path,
    stop_event: Event,
    device_index: int | None = None,
    chunk_size: int = 1024,
) -> Path:
    recorder = ContinuousSystemAudioRecorder(device_index=device_index, chunk_size=chunk_size)
    recorder.start()
    try:
        while not stop_event.is_set():
            time.sleep(0.05)
    finally:
        recorder.stop()

    segment = recorder.flush_segment(output_path)
    if not segment:
        raise AudioError("Recording stopped before any audio frames were captured.")
    return segment.path


class ContinuousSystemAudioRecorder:
    """Keep capturing system audio while allowing completed chunks to be flushed."""

    def __init__(self, device_index: int | None = None, chunk_size: int = 1024) -> None:
        self.device_index = device_index
        self.chunk_size = chunk_size
        self.error: BaseException | None = None

        self._frames: list[bytes] = []
        self._lock = Lock()
        self._ready_event = Event()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._channels: int | None = None
        self._rate: int | None = None
        self._sample_width: int | None = None

    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def start(self, timeout_seconds: float = 5) -> None:
        if self._thread and self._thread.is_alive():
            raise AudioError("Recording is already running.")

        self.error = None
        self._frames = []
        self._ready_event.clear()
        self._stop_event.clear()
        self._thread = Thread(target=self._capture_worker, daemon=True)
        self._thread.start()

        if not self._ready_event.wait(timeout_seconds):
            self._stop_event.set()
            raise AudioError("Timed out while opening the audio recording device.")
        self._raise_if_failed()

    def stop(self, timeout_seconds: float = 10) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout_seconds)
            if self._thread.is_alive():
                raise AudioError("Timed out while stopping the audio recording device.")
        self._raise_if_failed()

    def flush_segment(self, output_path: Path) -> AudioSegment | None:
        self._raise_if_failed()
        if not self._ready_event.is_set():
            raise AudioError("Recording device is not ready yet.")

        with self._lock:
            frames = self._frames
            self._frames = []

        if not frames:
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = b"".join(frames)
        channels = self._channels or 2
        rate = self._rate or 48000
        sample_width = self._sample_width or 2

        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(sample_width)
            wav.setframerate(rate)
            wav.writeframes(data)

        bytes_per_second = max(channels * sample_width * rate, 1)
        return AudioSegment(
            path=output_path,
            duration_seconds=len(data) / bytes_per_second,
            byte_count=len(data),
        )

    def _capture_worker(self) -> None:
        try:
            pyaudio = _load_pyaudio()
            with pyaudio.PyAudio() as pa:
                device = (
                    pa.get_device_info_by_index(self.device_index)
                    if self.device_index is not None
                    else _default_loopback_device(pa, pyaudio)
                )

                channels = int(device.get("maxInputChannels") or 2)
                rate = int(device.get("defaultSampleRate") or 48000)
                sample_format = pyaudio.paInt16
                sample_width = pa.get_sample_size(sample_format)

                self._channels = channels
                self._rate = rate
                self._sample_width = sample_width
                self._ready_event.set()

                def callback(in_data, frame_count, time_info, status):
                    if in_data:
                        with self._lock:
                            self._frames.append(in_data)
                    if self._stop_event.is_set():
                        return (None, pyaudio.paComplete)
                    return (None, pyaudio.paContinue)

                with pa.open(
                    format=sample_format,
                    channels=channels,
                    rate=rate,
                    input=True,
                    input_device_index=int(device["index"]),
                    frames_per_buffer=self.chunk_size,
                    stream_callback=callback,
                    start=False,
                ) as stream:
                    stream.start_stream()
                    while stream.is_active() and not self._stop_event.is_set():
                        time.sleep(0.05)
                    if stream.is_active():
                        stream.stop_stream()
        except BaseException as exc:
            self.error = exc
            self._ready_event.set()

    def _raise_if_failed(self) -> None:
        if self.error:
            raise AudioError(f"System-audio recording failed: {self.error}") from self.error


def _default_loopback_device(pa, pyaudio) -> dict:
    try:
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError as exc:
        raise AudioError("WASAPI is not available. System-audio recording requires Windows.") from exc

    default_output = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if default_output.get("isLoopbackDevice"):
        return default_output

    default_name = str(default_output.get("name", "")).split("[")[0].strip()
    for loopback in pa.get_loopback_device_info_generator():
        loopback_name = str(loopback.get("name", ""))
        if default_name and default_name in loopback_name:
            return loopback

    try:
        return next(pa.get_loopback_device_info_generator())
    except StopIteration as exc:
        raise AudioError("No WASAPI loopback recording device was found.") from exc
