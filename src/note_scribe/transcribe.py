from __future__ import annotations

from pathlib import Path

from .profiles import NoteProfile


class TranscriptionError(RuntimeError):
    pass


def transcribe_openai(
    audio_path: Path,
    profile: NoteProfile | None = None,
    model: str = "gpt-4o-mini-transcribe",
) -> str:
    try:
        from openai import OpenAI, OpenAIError
    except ImportError as exc:
        raise TranscriptionError(
            "The openai package is required. Install dependencies with: python -m pip install -e ."
        ) from exc

    if not audio_path.exists():
        raise TranscriptionError(f"Audio file does not exist: {audio_path}")

    prompt = None
    if profile and profile.glossary:
        terms = ", ".join(profile.glossary[:80])
        prompt = f"Audio transcript. Preserve these terms exactly when spoken: {terms}."

    try:
        client = OpenAI()
        with audio_path.open("rb") as audio_file:
            result = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                response_format="text",
                prompt=prompt,
            )
    except OpenAIError as exc:
        raise TranscriptionError(
            "OpenAI transcription failed. Set OPENAI_API_KEY, check your account access, "
            "or generate notes from an existing transcript."
        ) from exc

    if isinstance(result, str):
        return result.strip()

    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text.strip()

    return str(result).strip()


def transcribe_local(
    audio_path: Path,
    profile: NoteProfile | None = None,
    model: str = "base",
    device: str = "cpu",
    compute_type: str = "int8",
    language: str | None = None,
) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper is required for local transcription. "
            "Install dependencies with: python -m pip install -e ."
        ) from exc

    if not audio_path.exists():
        raise TranscriptionError(f"Audio file does not exist: {audio_path}")

    try:
        whisper = WhisperModel(model, device=device, compute_type=compute_type)
        segments, info = whisper.transcribe(
            str(audio_path),
            beam_size=5,
            vad_filter=True,
            language=language,
            initial_prompt=_initial_prompt(profile),
        )
        lines = [
            f"[{_format_timestamp(segment.start)} -> {_format_timestamp(segment.end)}] {segment.text.strip()}"
            for segment in segments
            if segment.text.strip()
        ]
    except Exception as exc:
        raise TranscriptionError(f"Local transcription failed: {exc}") from exc

    if not lines:
        language = getattr(info, "language", "unknown")
        raise TranscriptionError(f"Local transcription produced no text. Detected language: {language}.")

    return "\n".join(lines).strip()


def _initial_prompt(profile: NoteProfile | None) -> str | None:
    if not profile or not profile.glossary:
        return None
    terms = ", ".join(profile.glossary[:80])
    return f"Audio transcript. Preserve these terms exactly: {terms}."


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
