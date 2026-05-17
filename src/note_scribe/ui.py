from __future__ import annotations

import ctypes
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .audio import AudioDevice, AudioError, AudioSegment, ContinuousSystemAudioRecorder, list_loopback_devices
from .files import delete_file_if_exists
from .notes import build_chat_prompt, generate_note, write_note
from .profiles import list_builtin_profiles, load_profile
from .transcribe import transcribe_local


@dataclass(frozen=True)
class SegmentJob:
    segment_number: int
    audio_path: Path
    duration_seconds: float
    title: str
    profile_id: str
    workspace: Path
    local_model: str
    language: str | None
    local_transcribe: bool
    create_note: bool
    keep_audio: bool


@dataclass(frozen=True)
class ArtifactResult:
    segment_number: int
    transcript_path: Path | None
    prompt_path: Path
    note_path: Path | None
    audio_path: Path
    deleted_audio: bool


class NoteScribeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Note Scribe")
        icon_path = _resource_path("assets/note_scribe.ico")
        if icon_path.exists():
            self.iconbitmap(str(icon_path))
        self.geometry("1280x880")
        self.minsize(1120, 780)
        self.configure(bg="#f5f7f2")

        self.devices: list[AudioDevice] = []
        self.recorder: ContinuousSystemAudioRecorder | None = None
        self.started_at: float | None = None
        self.last_segment_at: float | None = None
        self.session_id: str | None = None
        self.session_workspace: Path | None = None
        self.segment_number = 1
        self.processing_count = 0
        self.stopping = False
        self.segment_lock = threading.Lock()
        self.process_lock = threading.Lock()
        self.ui_events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.current_prompt_path: Path | None = None
        self.current_note_path: Path | None = None

        self.title_var = tk.StringVar(value="筆記")
        self.profile_var = tk.StringVar(value="general-notes")
        self.device_var = tk.StringVar()
        self.workspace_var = tk.StringVar(value=str(_default_workspace()))
        self.local_transcribe_var = tk.BooleanVar(value=True)
        self.create_note_var = tk.BooleanVar(value=True)
        self.keep_audio_var = tk.BooleanVar(value=False)
        self.auto_segment_var = tk.BooleanVar(value=False)
        self.auto_segment_seconds_var = tk.StringVar(value="30")
        self.local_model_var = tk.StringVar(value="base")
        self.language_var = tk.StringVar(value="auto")
        self.status_var = tk.StringVar(value="就緒")
        self.elapsed_var = tk.StringVar(value="00:00")

        self._configure_style()
        self._build()
        self._load_profiles()
        self._load_devices()
        self.after(0, self._show_comfortable_startup_size)
        self._tick()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background="#f5f7f2")
        style.configure("Panel.TFrame", background="#ffffff", borderwidth=1, relief=tk.SOLID)
        style.configure("Inline.TFrame", background="#ffffff")
        style.configure("Title.TLabel", background="#f5f7f2", foreground="#18231f", font=("Segoe UI Semibold", 27))
        style.configure("Subtitle.TLabel", background="#f5f7f2", foreground="#5c6962", font=("Segoe UI", 10))
        style.configure("Label.TLabel", background="#ffffff", foreground="#203028", font=("Segoe UI Semibold", 10))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#69766f")
        style.configure("Timer.TLabel", background="#ffffff", foreground="#0f766e", font=("Consolas", 28, "bold"))
        style.configure("Status.TLabel", background="#ffffff", foreground="#25332d", wraplength=190)
        style.configure("TEntry", fieldbackground="#fbfcfa", foreground="#17211c", borderwidth=1, padding=8)
        style.configure("TCombobox", fieldbackground="#fbfcfa", foreground="#17211c", arrowsize=14, padding=6)
        style.configure("TCheckbutton", background="#ffffff", foreground="#25332d")
        style.map("TCheckbutton", background=[("active", "#ffffff")], foreground=[("active", "#0f766e")])
        style.configure("Accent.TButton", background="#0f766e", foreground="#ffffff", padding=(18, 10), font=("Segoe UI Semibold", 10), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#0d9488"), ("disabled", "#a7c3bd")])
        style.configure("Primary.TButton", background="#2563eb", foreground="#ffffff", padding=(18, 10), font=("Segoe UI Semibold", 10), borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#b7c6e8")])
        style.configure("Danger.TButton", background="#ef705b", foreground="#ffffff", padding=(18, 10), font=("Segoe UI Semibold", 10), borderwidth=0)
        style.map("Danger.TButton", background=[("active", "#f48a76"), ("disabled", "#e8b6ad")])
        style.configure("Ghost.TButton", background="#e7ede8", foreground="#223129", padding=(14, 9), borderwidth=0)
        style.map("Ghost.TButton", background=[("active", "#dbe5de"), ("disabled", "#edf1ed")], foreground=[("disabled", "#8b948f")])

    def _build(self) -> None:
        shell = ttk.Frame(self, style="App.TFrame", padding=22)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        header = ttk.Frame(shell, style="App.TFrame")
        header.grid(row=0, column=0, sticky=tk.EW, pady=(0, 18))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Note Scribe", style="Title.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(header, text="電腦聲音 -> 持續錄音 -> 分段本機轉錄 -> Markdown 筆記", style="Subtitle.TLabel").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Button(header, text="開啟資料夾", style="Ghost.TButton", command=self._open_workspace).grid(row=0, column=1, rowspan=2, sticky=tk.E)

        board = ttk.Frame(shell, style="Panel.TFrame", padding=18)
        board.grid(row=1, column=0, sticky=tk.EW)
        board.columnconfigure(1, weight=1)
        board.columnconfigure(3, weight=1)

        self._label(board, "標題", 0, 0)
        ttk.Entry(board, textvariable=self.title_var).grid(row=0, column=1, columnspan=3, sticky=tk.EW, padx=(10, 0), pady=7)

        self._label(board, "筆記模板", 1, 0)
        self.profile_combo = ttk.Combobox(board, textvariable=self.profile_var, state="readonly")
        self.profile_combo.grid(row=1, column=1, sticky=tk.EW, padx=(10, 14), pady=7)
        self._label(board, "模型", 1, 2)
        self.model_combo = ttk.Combobox(board, textvariable=self.local_model_var, values=["tiny", "base", "small", "medium"], width=12, state="readonly")
        self.model_combo.grid(row=1, column=3, sticky=tk.EW, padx=(10, 0), pady=7)

        self._label(board, "音效來源", 2, 0)
        self.device_combo = ttk.Combobox(board, textvariable=self.device_var, state="readonly")
        self.device_combo.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=(10, 14), pady=7)
        ttk.Button(board, text="重新整理", style="Ghost.TButton", command=self._load_devices).grid(row=2, column=3, sticky=tk.EW, pady=7)

        self._label(board, "工作資料夾", 3, 0)
        ttk.Entry(board, textvariable=self.workspace_var).grid(row=3, column=1, sticky=tk.EW, padx=(10, 14), pady=7)
        self._label(board, "語言提示", 3, 2)
        self.language_combo = ttk.Combobox(board, textvariable=self.language_var, values=["auto", "en", "zh", "ja"], width=12, state="readonly")
        self.language_combo.grid(row=3, column=3, sticky=tk.EW, padx=(10, 0), pady=7)

        toggles = ttk.Frame(board, style="Inline.TFrame")
        toggles.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(12, 2))
        ttk.Checkbutton(toggles, text="本機轉錄", variable=self.local_transcribe_var).pack(side=tk.LEFT)
        ttk.Checkbutton(toggles, text="產生 Markdown 草稿", variable=self.create_note_var).pack(side=tk.LEFT, padx=(22, 0))
        ttk.Checkbutton(toggles, text="保留 WAV", variable=self.keep_audio_var).pack(side=tk.LEFT, padx=(22, 0))
        ttk.Checkbutton(toggles, text="自動每", variable=self.auto_segment_var).pack(side=tk.LEFT, padx=(22, 4))
        ttk.Entry(toggles, textvariable=self.auto_segment_seconds_var, width=5).pack(side=tk.LEFT)
        ttk.Label(toggles, text="秒轉錄", style="Muted.TLabel").pack(side=tk.LEFT, padx=(4, 0))

        main = ttk.Frame(shell, style="App.TFrame")
        main.grid(row=2, column=0, sticky=tk.NSEW, pady=(18, 0))
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        side = ttk.Frame(main, style="Panel.TFrame", padding=18)
        side.grid(row=0, column=0, sticky=tk.NS, padx=(0, 18))
        ttk.Label(side, textvariable=self.elapsed_var, style="Timer.TLabel").pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(side, textvariable=self.status_var, style="Status.TLabel").pack(anchor=tk.W, fill=tk.X, pady=(0, 18))
        self.start_button = ttk.Button(side, text="開始錄音", style="Accent.TButton", command=self._start_recording)
        self.start_button.pack(fill=tk.X, pady=5)
        self.segment_button = ttk.Button(side, text="轉錄目前片段", style="Primary.TButton", command=self._transcribe_current_segment, state=tk.DISABLED)
        self.segment_button.pack(fill=tk.X, pady=5)
        self.stop_button = ttk.Button(side, text="停止錄音", style="Danger.TButton", command=self._stop_recording, state=tk.DISABLED)
        self.stop_button.pack(fill=tk.X, pady=5)
        ttk.Separator(side).pack(fill=tk.X, pady=16)
        self.open_note_button = ttk.Button(side, text="開啟筆記", style="Ghost.TButton", command=self._open_note, state=tk.DISABLED)
        self.open_note_button.pack(fill=tk.X, pady=5)
        self.open_prompt_button = ttk.Button(side, text="開啟 Prompt", style="Ghost.TButton", command=self._open_prompt, state=tk.DISABLED)
        self.open_prompt_button.pack(fill=tk.X, pady=5)
        self.copy_prompt_button = ttk.Button(side, text="複製 Prompt", style="Ghost.TButton", command=self._copy_prompt, state=tk.DISABLED)
        self.copy_prompt_button.pack(fill=tk.X, pady=5)
        ttk.Button(side, text="開啟資料夾", style="Ghost.TButton", command=self._open_workspace).pack(fill=tk.X, pady=5)

        log_panel = ttk.Frame(main, style="Panel.TFrame", padding=14)
        log_panel.grid(row=0, column=1, sticky=tk.NSEW)
        log_panel.rowconfigure(1, weight=1)
        log_panel.columnconfigure(0, weight=1)
        ttk.Label(log_panel, text="執行紀錄", style="Label.TLabel").grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        self.output = tk.Text(
            log_panel,
            height=16,
            wrap=tk.WORD,
            bg="#fbfdfb",
            fg="#223129",
            insertbackground="#0f766e",
            relief=tk.FLAT,
            padx=14,
            pady=14,
            font=("Consolas", 10),
        )
        self.output.grid(row=1, column=0, sticky=tk.NSEW)
        self.output.insert(tk.END, "就緒。開始播放課程後按「開始錄音」，途中可多次按「轉錄目前片段」。\n")
        self.output.configure(state=tk.DISABLED)

    def _label(self, parent: ttk.Frame, text: str, row: int, column: int) -> None:
        ttk.Label(parent, text=text, style="Label.TLabel").grid(row=row, column=column, sticky=tk.W, pady=7)

    def _load_profiles(self) -> None:
        profiles = list_builtin_profiles()
        self.profile_combo.configure(values=profiles)
        if profiles and self.profile_var.get() not in profiles:
            self.profile_var.set(profiles[0])

    def _load_devices(self) -> None:
        try:
            self.devices = list_loopback_devices()
        except AudioError as exc:
            self.status_var.set(str(exc))
            self.devices = []
            return

        labels = [self._device_label(device) for device in self.devices]
        self.device_combo.configure(values=labels)
        default = next((self._device_label(device) for device in self.devices if device.is_default), labels[0] if labels else "")
        self.device_var.set(default)
        self.status_var.set("就緒")

    def _start_recording(self) -> None:
        if self.recorder and self.recorder.is_recording:
            return

        device = self._selected_device()
        if not device:
            messagebox.showerror("Note Scribe", "尚未選擇音效來源。")
            return

        title = self.title_var.get().strip() or "筆記"
        workspace = Path(self.workspace_var.get().strip() or "workspace")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        self.session_id = f"{stamp}-{_slug(title)}"
        self.session_workspace = workspace
        self.segment_number = 1
        self.processing_count = 0
        self.stopping = False
        self.started_at = time.monotonic()
        self.last_segment_at = self.started_at
        self.current_prompt_path = None
        self.current_note_path = None

        try:
            self.recorder = ContinuousSystemAudioRecorder(device_index=device.index)
            self.recorder.start()
        except AudioError as exc:
            self.recorder = None
            self.started_at = None
            self.last_segment_at = None
            self.status_var.set(f"錄音失敗：{exc}")
            self._append(f"錄音失敗：{exc}\n")
            return

        self.start_button.configure(state=tk.DISABLED)
        self.segment_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL)
        self.open_prompt_button.configure(state=tk.DISABLED)
        self.open_note_button.configure(state=tk.DISABLED)
        self.copy_prompt_button.configure(state=tk.DISABLED)
        self.status_var.set("錄音中，可以隨時轉錄目前片段。")
        self._append(f"開始錄音：{self.session_id}\n")

    def _transcribe_current_segment(self) -> None:
        self._flush_current_segment("manual")

    def _flush_current_segment(self, reason: str) -> bool:
        if not self.recorder or not self.session_id or not self.session_workspace:
            return False

        try:
            with self.segment_lock:
                number = self.segment_number
                self.segment_number += 1
            suffix = "final" if reason == "final" else f"part-{number:03d}"
            audio_path = self.session_workspace / "notes" / f"{self.session_id}-{suffix}.wav"
            segment = self.recorder.flush_segment(audio_path)
        except AudioError as exc:
            self.status_var.set(f"切片失敗：{exc}")
            self._append(f"切片失敗：{exc}\n")
            return False

        self.last_segment_at = time.monotonic()
        if not segment:
            self._append("目前還沒有足夠音訊可轉錄。\n")
            return False

        job = self._build_segment_job(number, segment)
        self.processing_count += 1
        self.status_var.set(f"片段 {number:03d} 已送出轉錄，錄音仍在繼續。" if reason != "final" else f"最後片段已送出轉錄。")
        self._append(f"片段 {number:03d} 切出：{segment.path}（約 {segment.duration_seconds:.1f} 秒）\n")
        threading.Thread(target=self._process_segment_worker, args=(job,), daemon=True).start()
        return True

    def _build_segment_job(self, number: int, segment: AudioSegment) -> SegmentJob:
        title = self.title_var.get().strip() or "筆記"
        workspace = self.session_workspace or Path(self.workspace_var.get().strip() or "workspace")
        return SegmentJob(
            segment_number=number,
            audio_path=segment.path,
            duration_seconds=segment.duration_seconds,
            title=title,
            profile_id=self.profile_var.get(),
            workspace=workspace,
            local_model=self.local_model_var.get() or "base",
            language=self._language_hint(),
            local_transcribe=self.local_transcribe_var.get(),
            create_note=self.create_note_var.get(),
            keep_audio=self.keep_audio_var.get(),
        )

    def _stop_recording(self) -> None:
        if not self.recorder:
            return
        self.stopping = True
        self.segment_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("正在停止錄音...")
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self) -> None:
        try:
            if self.recorder:
                self.recorder.stop()
        except AudioError as exc:
            self.ui_events.put(("stop_error", exc))
            return
        self.ui_events.put(("stop_success", None))

    def _finish_stop_success(self) -> None:
        self.started_at = None
        flushed = self._flush_current_segment("final")
        self.recorder = None
        self.stopping = False
        self.start_button.configure(state=tk.NORMAL)
        self.status_var.set("錄音已停止，片段仍會在背景完成處理。" if flushed or self.processing_count else "錄音已停止。")
        self._append("錄音已停止。\n")

    def _finish_stop_error(self, exc: Exception) -> None:
        self.started_at = None
        self.recorder = None
        self.stopping = False
        self.start_button.configure(state=tk.NORMAL)
        self.status_var.set(f"停止錄音失敗：{exc}")
        self._append(f"停止錄音失敗：{exc}\n")

    def _process_segment_worker(self, job: SegmentJob) -> None:
        try:
            with self.process_lock:
                result = self._create_artifacts(job)
        except Exception as exc:
            self.ui_events.put(("segment_error", (job, exc)))
            return
        self.ui_events.put(("segment_success", result))

    def _finish_segment_success(self, result: ArtifactResult) -> None:
        self.processing_count = max(0, self.processing_count - 1)
        self.current_prompt_path = result.prompt_path
        self.current_note_path = result.note_path
        self.open_prompt_button.configure(state=tk.NORMAL)
        self.copy_prompt_button.configure(state=tk.NORMAL)
        if result.note_path:
            self.open_note_button.configure(state=tk.NORMAL)

        if result.deleted_audio:
            self._append(f"片段 {result.segment_number:03d} 轉錄完成，已刪除暫存 WAV。\n")
        else:
            self._append(f"片段 {result.segment_number:03d} 音檔已保留：{result.audio_path}\n")
        if result.transcript_path:
            self._append(f"片段 {result.segment_number:03d} 逐字稿：{result.transcript_path}\n")
        if result.note_path:
            self._append(f"片段 {result.segment_number:03d} Markdown 草稿：{result.note_path}\n")
        self._append(f"片段 {result.segment_number:03d} Prompt：{result.prompt_path}\n")

        if self.recorder and self.recorder.is_recording:
            self.status_var.set(
                f"錄音中，背景處理剩餘 {self.processing_count} 段。"
                if self.processing_count
                else "錄音中，可以繼續轉錄片段。"
            )
        elif self.processing_count:
            self.status_var.set(f"錄音已停止，背景處理剩餘 {self.processing_count} 段。")
        else:
            self.status_var.set("完成：所有片段都已處理。")

    def _finish_segment_error(self, job: SegmentJob, exc: Exception) -> None:
        self.processing_count = max(0, self.processing_count - 1)
        self.status_var.set(f"片段 {job.segment_number:03d} 處理失敗：{exc}")
        self._append(f"片段 {job.segment_number:03d} 處理失敗：{exc}\n")

    def _create_artifacts(self, job: SegmentJob) -> ArtifactResult:
        title = job.title
        profile = load_profile(job.profile_id)
        output_dir = job.workspace / "notes"
        prompt_path = output_dir / f"{job.audio_path.stem}.prompt.md"
        transcript_path: Path | None = None
        note_path: Path | None = None
        deleted_audio = False

        if job.local_transcribe:
            transcript = transcribe_local(
                job.audio_path,
                profile=profile,
                model=job.local_model,
                language=job.language,
            )
            transcript_path = output_dir / f"{job.audio_path.stem}.transcript.txt"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text(transcript.rstrip() + "\n", encoding="utf-8")
            prompt = build_chat_prompt(profile=profile, title=title, transcript=transcript)
            if job.create_note:
                note = generate_note(transcript, profile=profile, title=title, source=str(transcript_path))
                note_path = output_dir / f"{job.audio_path.stem}.md"
                write_note(note, note_path)
            if not job.keep_audio:
                deleted_audio = delete_file_if_exists(job.audio_path)
        else:
            prompt = build_chat_prompt(profile=profile, title=title, audio_path=str(job.audio_path))

        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
        return ArtifactResult(
            segment_number=job.segment_number,
            transcript_path=transcript_path,
            prompt_path=prompt_path,
            note_path=note_path,
            audio_path=job.audio_path,
            deleted_audio=deleted_audio,
        )

    def _language_hint(self) -> str | None:
        value = self.language_var.get().strip()
        return None if value == "auto" else value

    def _selected_device(self) -> AudioDevice | None:
        selected = self.device_var.get()
        for device in self.devices:
            if selected == self._device_label(device):
                return device
        return self.devices[0] if self.devices else None

    def _device_label(self, device: AudioDevice) -> str:
        marker = "* " if device.is_default else ""
        return f"{marker}{device.index}: {device.name}"

    def _open_prompt(self) -> None:
        if self.current_prompt_path and self.current_prompt_path.exists():
            os.startfile(self.current_prompt_path)

    def _open_note(self) -> None:
        if self.current_note_path and self.current_note_path.exists():
            os.startfile(self.current_note_path)

    def _copy_prompt(self) -> None:
        if not self.current_prompt_path or not self.current_prompt_path.exists():
            return
        self.clipboard_clear()
        self.clipboard_append(self.current_prompt_path.read_text(encoding="utf-8"))
        self.status_var.set("Prompt 已複製到剪貼簿。")

    def _open_workspace(self) -> None:
        workspace = Path(self.workspace_var.get().strip() or "workspace")
        workspace.mkdir(parents=True, exist_ok=True)
        os.startfile(workspace)

    def _append(self, message: str) -> None:
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, message)
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _tick(self) -> None:
        self._drain_ui_events()
        if self.started_at is not None:
            elapsed = int(time.monotonic() - self.started_at)
            minutes, seconds = divmod(elapsed, 60)
            self.elapsed_var.set(f"{minutes:02d}:{seconds:02d}")

            if self.auto_segment_var.get() and self.recorder and self.recorder.is_recording and not self.stopping:
                interval = self._auto_segment_seconds()
                last = self.last_segment_at or self.started_at
                if time.monotonic() - last >= interval:
                    self._flush_current_segment("auto")
        self.after(500, self._tick)

    def _auto_segment_seconds(self) -> int:
        try:
            seconds = int(self.auto_segment_seconds_var.get())
        except ValueError:
            return 30
        return max(10, min(seconds, 3600))

    def _drain_ui_events(self) -> None:
        while True:
            try:
                event, payload = self.ui_events.get_nowait()
            except queue.Empty:
                return

            if event == "stop_success":
                self._finish_stop_success()
            elif event == "stop_error" and isinstance(payload, Exception):
                self._finish_stop_error(payload)
            elif event == "segment_success" and isinstance(payload, ArtifactResult):
                self._finish_segment_success(payload)
            elif event == "segment_error" and isinstance(payload, tuple):
                job, exc = payload
                if isinstance(job, SegmentJob) and isinstance(exc, Exception):
                    self._finish_segment_error(job, exc)

    def _show_comfortable_startup_size(self) -> None:
        if sys.platform.startswith("win"):
            try:
                self.state("zoomed")
                return
            except tk.TclError:
                pass

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(max(1280, int(screen_width * 0.85)), screen_width - 80)
        height = min(max(880, int(screen_height * 0.85)), screen_height - 80)
        x = max((screen_width - width) // 2, 0)
        y = max((screen_height - height) // 2, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")


def main() -> None:
    _enable_dpi_awareness()
    app = NoteScribeApp()
    app.mainloop()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "study-note"


def _default_workspace() -> Path:
    if getattr(sys, "frozen", False):
        return Path.home() / "Documents" / "NoteScribe"
    return Path("workspace")


def _resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if getattr(sys, "frozen", False):
        return base / relative_path
    return Path(__file__).resolve().parents[2] / relative_path


def _enable_dpi_awareness() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


if __name__ == "__main__":
    main()
