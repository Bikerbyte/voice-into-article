from __future__ import annotations

import re
import textwrap
from datetime import date
from pathlib import Path

from .profiles import NoteProfile


class NoteError(RuntimeError):
    pass


def apply_corrections(text: str, profile: NoteProfile) -> str:
    corrected = text
    for wrong, right in profile.corrections.items():
        corrected = re.sub(re.escape(wrong), right, corrected, flags=re.IGNORECASE)
    return corrected


def generate_note(
    transcript: str,
    profile: NoteProfile,
    title: str,
    source: str | None = None,
    llm: str = "none",
    model: str = "gpt-4o-mini",
) -> str:
    transcript = apply_corrections(transcript.strip(), profile)
    if not transcript:
        raise NoteError("Transcript is empty.")

    if llm == "openai":
        return _generate_note_openai(transcript, profile, title, source, model)
    if llm != "none":
        raise NoteError(f"Unknown note generator: {llm}")

    return _generate_note_local(transcript, profile, title, source)


def write_note(markdown: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return output_path


def build_chat_prompt(
    profile: NoteProfile,
    title: str,
    transcript: str | None = None,
    audio_path: str | None = None,
) -> str:
    if not transcript and not audio_path:
        raise NoteError("A transcript or audio path is required to build a chat prompt.")

    source_instruction = (
        "我會上傳一個音訊檔。請先把音訊轉成逐字稿，再根據內容整理成清楚的筆記。"
        if audio_path
        else "下面是音訊逐字稿。請只根據逐字稿整理成清楚的筆記。"
    )
    source_block = f"音訊檔路徑/檔名：{audio_path}" if audio_path else f"逐字稿：\n\n{transcript.strip()}"
    sections = profile.sections or ["重點摘要", "重要細節", "待辦事項", "需要確認", "原始逐字稿摘要"]

    return f"""你是我的筆記整理助手。

{source_instruction}

請遵守：
- 使用 {profile.language}。
- 本次整理模板是：{profile.name}。
- 只根據逐字稿整理，不要憑空補充事實。
- 如果有不確定的數字、限制、時程、負責人或外部資訊，放到「需要確認」。
- 不要逐字抄長段內容；請整理成容易閱讀和後續使用的筆記。
- 技術名詞、專有名詞、人名、產品名請盡量保留原文。
- 請輸出 Markdown，而且包含 YAML front matter。

文章標題：{title}
模板 ID：{profile.id}
Tags：{", ".join(profile.tags)}
Glossary：{", ".join(profile.glossary)}
建議章節：{", ".join(sections)}
整理提示：{", ".join(profile.question_patterns)}

請輸出以下結構：

---
title: "{title}"
date: "YYYY-MM-DD"
template: "{profile.name}"
profile: "{profile.id}"
tags: [{", ".join(profile.tags)}]
---

# {title}

{chr(10).join(f"## {section}" for section in sections)}

{source_block}
""".strip()


def default_post_path(title: str, profile: NoteProfile) -> Path:
    slug = _slug(title)
    return Path("workspace") / "notes" / f"{date.today().isoformat()}-{profile.id}-{slug}.md"


def _generate_note_local(
    transcript: str,
    profile: NoteProfile,
    title: str,
    source: str | None,
) -> str:
    sentences = _split_sentences(transcript)
    term_hits = _term_hits(sentences, profile.glossary)
    terms = list(term_hits.keys())
    representative = _representative_sentences(sentences, term_hits)

    lines: list[str] = [
        "---",
        f'title: "{title}"',
        f'date: "{date.today().isoformat()}"',
        f'template: "{profile.name}"',
        f'profile: "{profile.id}"',
        "tags: [" + ", ".join(profile.tags) + "]",
        "---",
        "",
        f"# {title}",
        "",
        f"> 模板：{profile.name}",
    ]
    if source:
        lines.append(f"> 來源：{source}")
    lines.extend(["", _summary_line(terms, representative), ""])

    lines.extend(_key_points(representative))
    lines.extend(_details(term_hits))
    lines.extend(_action_items(profile, terms))
    lines.extend(_followups(profile, terms))
    lines.extend(_transcript_block(transcript))
    return "\n".join(lines).rstrip() + "\n"


def _generate_note_openai(
    transcript: str,
    profile: NoteProfile,
    title: str,
    source: str | None,
    model: str,
) -> str:
    try:
        from openai import OpenAI, OpenAIError
    except ImportError as exc:
        raise NoteError("The openai package is required for --llm openai.") from exc

    prompt = f"""
You are generating clear Markdown notes from an audio transcript.

Rules:
- Write in {profile.language}.
- Use only the transcript as the source of factual claims.
- If a claim is unclear or needs confirmation, put it under "需要確認".
- Prefer concise bullets, tables, and action items when useful.
- Preserve technical terms, names, product names, and proper nouns exactly.
- Do not copy long transcript passages.
- Output Markdown only, including YAML front matter.

Title: {title}
Source: {source or "recorded system audio"}
Template id: {profile.id}
Tags: {", ".join(profile.tags)}
Glossary: {", ".join(profile.glossary)}
Hints: {", ".join(profile.question_patterns)}

Transcript:
{transcript}
"""
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You produce careful Markdown notes grounded in the provided transcript."},
                {"role": "user", "content": textwrap.dedent(prompt).strip()},
            ],
            temperature=0.2,
        )
    except OpenAIError as exc:
        raise NoteError("OpenAI note generation failed. Set OPENAI_API_KEY or run without `--llm openai`.") from exc
    content = response.choices[0].message.content
    if not content:
        raise NoteError("OpenAI returned an empty note.")
    return content.strip()


def _summary_line(terms: list[str], representative: list[str]) -> str:
    if terms:
        return f"本段主要提到：{', '.join(terms[:10])}。"
    if representative:
        return "本段已整理成初版筆記；建議再依實際用途補上結論、負責人或下一步。"
    return "本段逐字稿內容較少，請檢查錄音或轉錄品質。"


def _key_points(representative: list[str]) -> list[str]:
    lines = ["## 重點摘要", ""]
    if not representative:
        lines.append("- 尚未擷取到足夠明確的重點。")
    else:
        lines.extend(f"- {sentence}" for sentence in representative[:8])
    lines.append("")
    return lines


def _details(term_hits: dict[str, list[str]]) -> list[str]:
    terms = list(term_hits.keys())[:8]
    lines = ["## 重要細節", ""]
    if not terms:
        lines.append("- 尚未偵測到模板詞彙；可以補充模板 glossary 或檢查轉錄品質。")
        lines.append("")
        return lines

    lines.extend(["| 項目 | 逐字稿線索 | 備註 |", "|---|---|---|"])
    for term in terms:
        clue = _compact(term_hits[term][0])
        lines.append(f"| {term} | {clue} | 可依實際情境補充結論或負責人 |")
    lines.append("")
    return lines


def _action_items(profile: NoteProfile, terms: list[str]) -> list[str]:
    lines = ["## 待辦事項", ""]
    hints = profile.question_patterns[:4] or [
        "整理出需要追蹤的事項。",
        "標出負責人、期限與下一步。",
        "把需要補充資料的地方列出來。",
    ]
    lines.extend(f"- {hint}" for hint in hints)
    if terms:
        lines.append(f"- 本段可追蹤關鍵詞：{', '.join(terms[:10])}。")
    lines.append("")
    return lines


def _followups(profile: NoteProfile, terms: list[str]) -> list[str]:
    lines = ["## 需要確認", ""]
    lines.append("- 涉及數字、時程、負責人、費用、承諾或外部規範時，發布前請再次確認。")
    lines.append("- 如果轉錄中出現聽起來像專有名詞但不確定的片段，建議回到原音訊確認。")
    if not terms:
        lines.append("- 目前缺少明確關鍵詞，可視需要補充模板詞彙。")
    lines.append("")
    return lines


def _transcript_block(transcript: str) -> list[str]:
    return [
        "## 原始逐字稿",
        "",
        "<details>",
        "<summary>展開逐字稿</summary>",
        "",
        transcript,
        "",
        "</details>",
        "",
    ]


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?。！？])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def _term_hits(sentences: list[str], glossary: list[str]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for term in glossary:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        matches = [sentence for sentence in sentences if pattern.search(sentence)]
        if matches:
            hits[term] = matches[:3]
    return hits


def _representative_sentences(sentences: list[str], term_hits: dict[str, list[str]]) -> list[str]:
    selected: list[str] = []
    for matches in term_hits.values():
        for sentence in matches:
            if sentence not in selected:
                selected.append(sentence)
            if len(selected) >= 8:
                return selected
    return sentences[:8]


def _compact(text: str, limit: int = 140) -> str:
    text = text.replace("|", "\\|").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-") or "note"
