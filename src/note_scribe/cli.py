from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audio import AudioError, list_loopback_devices, record_system_audio
from .files import delete_file_if_exists
from .notes import NoteError, build_chat_prompt, default_post_path, generate_note, write_note
from .profiles import list_builtin_profiles, load_profile
from .transcribe import TranscriptionError, transcribe_local, transcribe_openai


def main(argv: list[str] | None = None) -> int:
    _configure_console_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except (AudioError, NoteError, TranscriptionError, ValueError) as exc:
        print(f"error: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="note-scribe",
        description="Generate Markdown notes from system audio.",
    )
    sub = parser.add_subparsers(required=True)

    profiles = sub.add_parser("profiles", help="List built-in note templates.")
    profiles.set_defaults(func=cmd_profiles)

    devices = sub.add_parser("devices", help="List Windows speaker loopback recording devices.")
    devices.set_defaults(func=cmd_devices)

    record = sub.add_parser("record", help="Record Windows system audio to a WAV file.")
    record.add_argument("--minutes", type=float, default=5)
    record.add_argument("--seconds", type=float)
    record.add_argument("--out", type=Path, default=Path("workspace/notes/session.wav"))
    record.add_argument("--device-index", type=int)
    record.set_defaults(func=cmd_record)

    transcribe = sub.add_parser("transcribe", help="Transcribe an audio file.")
    transcribe.add_argument("audio", type=Path)
    transcribe.add_argument("--out", type=Path)
    transcribe.add_argument("--profile", default="general-notes")
    transcribe.add_argument("--provider", choices=["local", "openai"], default="local")
    transcribe.add_argument("--model", help="Use `base`/`small` for local or an OpenAI transcription model.")
    transcribe.add_argument("--device", default="cpu", help="Local transcription device: cpu or cuda.")
    transcribe.add_argument("--compute-type", default="int8", help="Local faster-whisper compute type.")
    transcribe.add_argument("--language", help="Optional audio language hint, for example `en` or `zh`.")
    transcribe.add_argument("--delete-audio", action="store_true", help="Delete the input audio after a successful transcription.")
    transcribe.set_defaults(func=cmd_transcribe)

    note = sub.add_parser("note", help="Generate a Markdown study note from a transcript.")
    note.add_argument("transcript", type=Path)
    note.add_argument("--profile", default="general-notes")
    note.add_argument("--title", default="Study Note")
    note.add_argument("--out", type=Path)
    note.add_argument("--llm", choices=["none", "openai"], default="none")
    note.add_argument("--model", default="gpt-4o-mini")
    note.set_defaults(func=cmd_note)

    prompt = sub.add_parser("prompt", help="Build a pasteable chat prompt without using an API key.")
    prompt.add_argument("--transcript", type=Path)
    prompt.add_argument("--audio", type=Path)
    prompt.add_argument("--profile", default="general-notes")
    prompt.add_argument("--title", default="Study Note")
    prompt.add_argument("--out", type=Path)
    prompt.set_defaults(func=cmd_prompt)

    ui = sub.add_parser("ui", help="Open the desktop start/stop recording UI.")
    ui.set_defaults(func=cmd_ui)

    run = sub.add_parser("run", help="Record, transcribe, and generate a note.")
    run.add_argument("--minutes", type=float, default=5)
    run.add_argument("--seconds", type=float)
    run.add_argument("--profile", default="general-notes")
    run.add_argument("--title", default="Study Note")
    run.add_argument("--workspace", type=Path, default=Path("workspace"))
    run.add_argument("--device-index", type=int)
    run.add_argument("--transcribe-provider", choices=["local", "openai"], default="local")
    run.add_argument("--transcribe-model", default="gpt-4o-mini-transcribe")
    run.add_argument("--transcribe-device", default="cpu")
    run.add_argument("--transcribe-compute-type", default="int8")
    run.add_argument("--transcribe-language", help="Optional audio language hint, for example `en` or `zh`.")
    run.add_argument("--keep-audio", action="store_true", help="Keep the temporary WAV recording after transcription.")
    run.add_argument("--note-llm", choices=["none", "openai"], default="none")
    run.add_argument("--note-model", default="gpt-4o-mini")
    run.set_defaults(func=cmd_run)

    demo = sub.add_parser("demo", help="Create a sample transcript and note without recording or API calls.")
    demo.add_argument("--profile", default="general-notes")
    demo.add_argument("--workspace", type=Path, default=Path("workspace"))
    demo.set_defaults(func=cmd_demo)

    return parser


def cmd_profiles(_args: argparse.Namespace) -> int:
    for profile in list_builtin_profiles():
        print(profile)
    return 0


def cmd_devices(_args: argparse.Namespace) -> int:
    devices = list_loopback_devices()
    if not devices:
        print("No loopback devices found.")
        return 1

    for device in devices:
        marker = "*" if device.is_default else " "
        print(
            f"{marker} index={device.index} channels={device.channels} "
            f"rate={device.sample_rate} name={device.name}"
        )
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    seconds = args.seconds if args.seconds is not None else args.minutes * 60
    path = record_system_audio(args.out, seconds=seconds, device_index=args.device_index)
    print(path)
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    if args.provider == "openai":
        text = transcribe_openai(
            args.audio,
            profile=profile,
            model=args.model or "gpt-4o-mini-transcribe",
        )
    else:
        text = transcribe_local(
            args.audio,
            profile=profile,
            model=args.model or "base",
            device=args.device,
            compute_type=args.compute_type,
            language=args.language,
        )
    out = args.out or Path("workspace/notes") / f"{args.audio.stem}.transcript.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text.rstrip() + "\n", encoding="utf-8")
    print(out)
    if args.delete_audio:
        delete_file_if_exists(args.audio)
        print(f"deleted audio: {args.audio}")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    transcript = args.transcript.read_text(encoding="utf-8")
    markdown = generate_note(
        transcript,
        profile=profile,
        title=args.title,
        source=str(args.transcript),
        llm=args.llm,
        model=args.model,
    )
    out = args.out or default_post_path(args.title, profile)
    write_note(markdown, out)
    print(out)
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    if bool(args.transcript) == bool(args.audio):
        raise NoteError("Use exactly one of --transcript or --audio.")

    profile = load_profile(args.profile)
    transcript = args.transcript.read_text(encoding="utf-8") if args.transcript else None
    prompt = build_chat_prompt(
        profile=profile,
        title=args.title,
        transcript=transcript,
        audio_path=str(args.audio) if args.audio else None,
    )
    out = args.out or Path("workspace/notes") / f"{_slug(args.title)}.prompt.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt.rstrip() + "\n", encoding="utf-8")
    print(out)
    return 0


def cmd_ui(_args: argparse.Namespace) -> int:
    from .ui import main as ui_main

    ui_main()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    seconds = args.seconds if args.seconds is not None else args.minutes * 60
    base = _slug(args.title)
    output_dir = args.workspace / "notes"
    recordings = output_dir / f"{base}.wav"
    transcripts = output_dir / f"{base}.transcript.txt"
    post = output_dir / f"{base}.md"

    print("Recording system audio...")
    record_system_audio(recordings, seconds=seconds, device_index=args.device_index)

    print("Transcribing...")
    if args.transcribe_provider == "openai":
        transcript = transcribe_openai(recordings, profile=profile, model=args.transcribe_model)
    else:
        local_model = args.transcribe_model
        if local_model == "gpt-4o-mini-transcribe":
            local_model = "base"
        transcript = transcribe_local(
            recordings,
            profile=profile,
            model=local_model,
            device=args.transcribe_device,
            compute_type=args.transcribe_compute_type,
            language=args.transcribe_language,
        )
    transcripts.parent.mkdir(parents=True, exist_ok=True)
    transcripts.write_text(transcript.rstrip() + "\n", encoding="utf-8")

    print("Generating note...")
    markdown = generate_note(
        transcript,
        profile=profile,
        title=args.title,
        source=str(transcripts),
        llm=args.note_llm,
        model=args.note_model,
    )
    write_note(markdown, post)

    if not args.keep_audio:
        delete_file_if_exists(recordings)
        print(f"deleted audio: {recordings}")

    print(post)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    transcript_path = args.workspace / "notes" / f"demo-{profile.id}.transcript.txt"
    note_path = args.workspace / "notes" / f"demo-{profile.id}.md"
    sample = (
        "Today we reviewed the project timeline and confirmed two decisions. "
        "The first action item is to update the onboarding document before Friday. "
        "The second follow-up is to check whether the dashboard numbers match the weekly report. "
        "There is one open issue about handoff timing, so the owner should confirm the deadline."
    )
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(sample + "\n", encoding="utf-8")
    markdown = generate_note(
        sample,
        profile=profile,
        title=f"{profile.name} Demo",
        source=str(transcript_path),
    )
    write_note(markdown, note_path)
    print(transcript_path)
    print(note_path)
    return 0


def _slug(value: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "session"


def _configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
