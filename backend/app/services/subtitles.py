from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.services.clip_extraction import ClipWord


@dataclass(frozen=True)
class CaptionStyle:
    preset: str
    font_size: int
    text_color: str
    highlight_color: str
    vertical_position: str


def ass_escape(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r\n", r"\N")
        .replace("\n", r"\N")
        .replace("\r", r"\N")
    )


def _ass_color(value: str) -> str:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Caption colors must use #RRGGBB format.")
    red, green, blue = value[1:3], value[3:5], value[5:7]
    return f"&H00{blue}{green}{red}".upper()


def choose_font(text: str, *, latin_font: str, complex_font: str) -> str:
    if re.search(r"[\u0590-\u08ff\u0900-\u097f\u0a00-\u0a7f]", text):
        return complex_font.strip() or "Nirmala UI"
    return latin_font.strip() or "Arial"


def _ass_time(milliseconds: int) -> str:
    centiseconds = max(0, round(milliseconds / 10))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _groups(words: list[ClipWord], size: int = 6) -> list[list[ClipWord]]:
    groups: list[list[ClipWord]] = []
    current: list[ClipWord] = []
    for word in words:
        if current and (len(current) >= size or word.start_ms - current[-1].end_ms > 700):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups


def build_ass_document(
    words: list[ClipWord],
    *,
    width: int,
    height: int,
    style: CaptionStyle,
    latin_font: str,
    complex_font: str,
) -> str:
    if style.preset == "none" or not words:
        return ""
    all_text = " ".join(word.word for word in words)
    font = choose_font(all_text, latin_font=latin_font, complex_font=complex_font)
    primary = _ass_color(style.text_color)
    highlight = _ass_color(style.highlight_color)
    alignment = {"bottom": 2, "center": 5, "top": 8}.get(style.vertical_position)
    if alignment is None:
        raise ValueError("Unsupported caption vertical position.")
    margin_v = max(48, round(height * 0.09))
    bold = -1 if style.preset in {"bold", "karaoke"} else 0
    outline = 4 if style.preset in {"bold", "karaoke"} else 2
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font},{style.font_size},{primary},{highlight},&HCC000000,&H66000000,{bold},0,0,0,100,100,0,0,1,{outline},1,{alignment},60,60,{margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events: list[str] = []
    for group in _groups(words):
        start_ms, end_ms = group[0].start_ms, group[-1].end_ms
        if style.preset == "karaoke":
            text = " ".join(
                rf"{{\k{max(1, round((word.end_ms - word.start_ms) / 10))}}}{ass_escape(word.word)}"
                for word in group
            )
        elif style.preset == "bold":
            keyword = max(group, key=lambda word: len(word.word))
            text = " ".join(
                (rf"{{\c{highlight}}}{ass_escape(word.word)}{{\c{primary}}}" if word is keyword else ass_escape(word.word))
                for word in group
            )
        else:
            text = " ".join(ass_escape(word.word) for word in group)
        events.append(
            f"Dialogue: 0,{_ass_time(start_ms)},{_ass_time(end_ms)},Default,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + "\n"


def write_ass_file(path: Path, document: str) -> None:
    path.write_text(document, encoding="utf-8-sig")
