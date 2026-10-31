# Caption presets

Howlix burns ASS subtitles with FFmpeg/libass using only persisted transcript words. For a clip beginning at `clip_start`, each included timestamp is `word_start - clip_start` and `word_end - clip_start`, then clamped to the clip. Words outside the approved interval are excluded; no text or timing is invented.

## Presets

- **Minimal:** white modern text, subtle shadow, lower-third position.
- **Bold:** larger high-contrast text with the selected violet-style keyword highlight.
- **Karaoke:** readable word-by-word highlighting using ASS karaoke timing.
- **None:** captions are disabled and no subtitle filter is added.

Users can select font size, text and highlight colors, and top/middle/bottom position. Server validation bounds all values. ASS control characters and newlines are escaped before writing the temporary file.

## Fonts and scripts

```dotenv
CAPTION_FONTS_DIR=C:/Windows/Fonts
CAPTION_LATIN_FONT=Noto Sans
CAPTION_COMPLEX_FONT=Nirmala UI
```

Hindi, Punjabi/Gurmukhi, Arabic, and other complex-script text selects the complex font. The FFmpeg/libass build should include HarfBuzz/FriBidi shaping. Verify installed fonts with:

```powershell
Get-ChildItem C:\Windows\Fonts | Where-Object Name -Match "Noto|Nirmala|Arial"
```

If a configured font is missing, libass uses system fallback. Always inspect a rendered frame for glyph coverage; font-name detection cannot guarantee every character exists. Caption avoidance around moving faces is not implemented, so use top or middle placement when the lower third covers important content.
