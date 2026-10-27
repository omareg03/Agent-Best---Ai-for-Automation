# Caption Style Guide

Captions are burned as ASS with karaoke word timing (`\k`) so the active word fills
progressively in the accent colour. The SRT sidecar uses the same cues for platforms
that prefer soft subs.

## Enforced by `scripts/video_pipeline/captions.py`

| Rule | Value | Rationale |
|---|---|---|
| Max characters per line | 42 | Two-line max at 16:9 without shrinking type |
| Max words per cue | 7 | Reading speed at ~150 wpm narration |
| Max cue duration | 4.5 s | Beyond this, viewers stop tracking the highlight |
| Min cue duration | 0.25 s | Below this, cues flicker |
| Safe margin | 6 % of height | Keeps clear of Shorts/Reels UI |
| Font | DejaVu Sans (or brand TTF) | Licence-clean, ships with most Linux distros |
| Outline | 2 px at 720p, scaled | Readable over any footage |
| Fade | 120 ms in / out | Prevents hard pops |
| Alignment | Bottom centre, `\an2` | Standard broadcast position |

## Text hygiene

- Captions are derived from the narration script, never from ASR output alone —
  ASR turns "eleven" into "11" and breaks karaoke timing on numbers.
- ASS reserves `{` `}` and `\`; the renderer escapes them so a script containing
  code or maths cannot corrupt the subtitle file.
- No emoji in burned captions: libass may fall back to a missing glyph.

## Accessibility

The SRT sidecar is the accessibility artefact. Always ship it even when captions are
burned in — burned text is invisible to screen readers and to search.
