from __future__ import annotations

import re
import textwrap
from datetime import date
from pathlib import Path

from .profiles import ExamProfile


class NoteError(RuntimeError):
    pass


def apply_corrections(text: str, profile: ExamProfile) -> str:
    corrected = text
    for wrong, right in profile.corrections.items():
        corrected = re.sub(re.escape(wrong), right, corrected, flags=re.IGNORECASE)
    return corrected


def generate_note(
    transcript: str,
    profile: ExamProfile,
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
    profile: ExamProfile,
    title: str,
    transcript: str | None = None,
    audio_path: str | None = None,
) -> str:
    if not transcript and not audio_path:
        raise NoteError("A transcript or audio path is required to build a chat prompt.")

    source_instruction = (
        "我會上傳一個音訊檔。請先把音訊轉成逐字稿，再根據逐字稿整理備考筆記。"
        if audio_path
        else "下面是課程逐字稿。請只根據逐字稿整理備考筆記。"
    )
    source_block = f"音訊檔路徑/檔名：{audio_path}" if audio_path else f"逐字稿：\n\n{transcript.strip()}"
    sections = [
        "核心觀念",
        "考試會怎麼問",
        "易混淆選項",
        "情境題判斷規則",
        "記憶口訣",
        "需要查官方文件",
        "原始逐字稿摘要",
    ]

    return f"""你是我的備考筆記整理助手。

{source_instruction}

請遵守：
- 使用 {profile.language}。
- 這是通用「備考筆記」格式，本次 exam profile 是：{profile.name}。
- 只根據逐字稿整理，不要憑空補充事實。
- 如果某個限制、數字、價格、SLA、配額或服務行為不確定，放到「需要查官方文件」。
- 不要逐字抄長段課程內容；請整理成我的理解型筆記。
- 技術名詞請盡量保留原文。
- 請輸出 Markdown，而且包含 YAML front matter。
- 優先寫成考試導向：情境、限制條件、容易混淆的選項、判斷規則。

文章標題：{title}
Profile ID：{profile.id}
Tags：{", ".join(profile.tags)}
Glossary：{", ".join(profile.glossary)}
建議章節：{", ".join(sections)}
題型提示：{", ".join(profile.question_patterns)}

請輸出以下結構：

---
title: "{title}"
date: "YYYY-MM-DD"
exam: "{profile.name}"
profile: "{profile.id}"
tags: [{", ".join(profile.tags)}]
---

# {title}

## 核心觀念

## 考試會怎麼問

## 易混淆選項

## 情境題判斷規則

## 記憶口訣

## 需要查官方文件

## 原始逐字稿摘要

{source_block}
""".strip()


def default_post_path(title: str, profile: ExamProfile) -> Path:
    slug = _slug(title)
    return Path("workspace") / "notes" / f"{date.today().isoformat()}-{profile.id}-{slug}.md"


def _generate_note_local(
    transcript: str,
    profile: ExamProfile,
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
        f'exam: "{profile.name}"',
        f'profile: "{profile.id}"',
        "tags: [" + ", ".join(profile.tags) + "]",
        "---",
        "",
        f"# {title}",
        "",
        f"> Profile: {profile.name}",
    ]
    if source:
        lines.append(f"> Source: {source}")
    lines.extend(["", _summary_line(terms, representative), ""])

    lines.extend(_core_concepts(representative))
    lines.extend(_exam_questions(profile, terms))
    lines.extend(_confusing_options(term_hits))
    lines.extend(_scenario_rules(profile, terms))
    lines.extend(_memory_hooks(terms))
    lines.extend(_verification_items())
    lines.extend(_transcript_block(transcript))
    return "\n".join(lines).rstrip() + "\n"


def _generate_note_openai(
    transcript: str,
    profile: ExamProfile,
    title: str,
    source: str | None,
    model: str,
) -> str:
    try:
        from openai import OpenAI, OpenAIError
    except ImportError as exc:
        raise NoteError("The openai package is required for --llm openai.") from exc

    prompt = f"""
You are generating exam-prep study notes from a lecture transcript.

Rules:
- Write in {profile.language}.
- Use only the transcript as the source of factual claims.
- If a claim is unclear or likely needs official documentation, put it under "需要查官方文件".
- Prefer concise bullets, comparison tables, and scenario-based exam cues.
- Preserve technical terms exactly.
- Do not copy long transcript passages.
- Output Markdown only, including YAML front matter.

Title: {title}
Source: {source or "recorded system audio"}
Profile id: {profile.id}
Tags: {", ".join(profile.tags)}
Glossary: {", ".join(profile.glossary)}
Question patterns: {", ".join(profile.question_patterns)}

Transcript:
{transcript}
"""
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You produce careful exam-prep Markdown notes grounded in the provided transcript."},
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
        return "本段已整理成備考草稿；建議再用聊天工具潤稿與補強考試語氣。"
    return "本段逐字稿內容較少，請檢查錄音或轉錄品質。"


def _core_concepts(representative: list[str]) -> list[str]:
    lines = ["## 核心觀念", ""]
    if not representative:
        lines.append("- 尚未擷取到足夠明確的核心觀念。")
    else:
        lines.extend(f"- {sentence}" for sentence in representative[:8])
    lines.append("")
    return lines


def _exam_questions(profile: ExamProfile, terms: list[str]) -> list[str]:
    lines = ["## 考試會怎麼問", ""]
    if terms:
        lines.extend(f"- 題目可能會要求你判斷 `{term}` 的適用情境、限制條件或替代選項。" for term in terms[:8])
    else:
        lines.append("- 尚未偵測到 profile 詞彙，建議補充 glossary 或檢查轉錄品質。")
    for pattern in profile.question_patterns[:4]:
        lines.append(f"- 題型線索：{pattern}")
    lines.append("")
    return lines


def _confusing_options(term_hits: dict[str, list[str]]) -> list[str]:
    terms = list(term_hits.keys())[:8]
    lines = ["## 易混淆選項", ""]
    if len(terms) < 2:
        lines.append("- 目前擷取到的術語不足以形成比較表。")
        lines.append("")
        return lines

    lines.extend(["| 選項 | 逐字稿線索 | 複習焦點 |", "|---|---|---|"])
    for term in terms:
        clue = _compact(term_hits[term][0])
        lines.append(f"| {term} | {clue} | 比較使用時機、限制、成本與營運負擔 |")
    lines.append("")
    return lines


def _scenario_rules(profile: ExamProfile, terms: list[str]) -> list[str]:
    lines = ["## 情境題判斷規則", ""]
    rules = profile.question_patterns[:5] or [
        "先找題目限制條件，再排除不符合的選項。",
        "比較成本、可用性、安全性與營運負擔。",
        "遇到 managed service 或 serverless 選項時，注意題目是否要求最低管理負擔。",
    ]
    lines.extend(f"- {rule}" for rule in rules)
    if terms:
        lines.append(f"- 本段重點術語：{', '.join(terms[:10])}。")
    lines.append("")
    return lines


def _memory_hooks(terms: list[str]) -> list[str]:
    lines = ["## 記憶口訣", ""]
    if not terms:
        lines.append("- 先補足轉錄內容後，再建立記憶口訣。")
    else:
        for term in terms[:6]:
            lines.append(f"- `{term}`：用「題目限制 -> 適用情境 -> 反例」三步驟記。")
    lines.append("")
    return lines


def _verification_items() -> list[str]:
    return [
        "## 需要查官方文件",
        "",
        "- 涉及數字、限制、SLA、價格、配額、區域支援時，發布前請查官方文件。",
        "- 如果轉錄中出現聽起來像專有名詞但不確定的片段，先回原影片確認。",
        "- 本機草稿不會主動外部查證，適合當第一版筆記，不適合直接當最終事實來源。",
        "",
    ]


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
    return re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-") or "study-note"
