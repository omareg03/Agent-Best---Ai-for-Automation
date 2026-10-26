# Style Anchor — the tokens every frame inherits

The `style_anchor` field on a storyboard is prepended to every keyframe and video prompt.
It is the cheapest consistency mechanism in the whole pipeline: one string, applied
everywhere, reviewable in git.

## What belongs in it (and nothing else)

| Slot | Example | Why |
|---|---|---|
| Medium | `shot on 35mm film`, `digital cinema`, `hand-painted 2D` | Locks texture |
| Grade | `teal-and-amber grade`, `desaturated cool palette` | Locks colour |
| Lighting | `natural window light`, `overcast diffusion`, `single practical lamp` | Locks contrast |
| Optics | `50mm, shallow depth of field`, `24mm wide, deep focus` | Locks perspective |
| Era | `late-1990s coastal town`, `near-future industrial` | Locks production design |
| Grain/detail | `fine grain`, `clean digital`, `visible brush strokes` | Locks micro-detail |

## What must NOT be in it

- Subject descriptions → those live in `character_sheet_prompt` and per-scene `visual_prompt`.
- Anything that changes per shot (time of day, camera move) → those are per-scene fields.
- Negations → put them in `negative_prompt`. Mixing "no text" into a style anchor often
  makes image models *draw* text.

## Example (copy, then edit)

```
cinematic, shot on 35mm film, teal-and-amber grade, natural overcast light,
shallow depth of field, fine grain, muted coastal palette
```

## Why this matters more than prompt cleverness

Consistency across 40 shots comes from the *reference sheet* + *this anchor* + *frame
chaining*, not from writing 40 variations of a paragraph. If a shot drifts, fix the
anchor (one place) rather than the shot (forty places).
