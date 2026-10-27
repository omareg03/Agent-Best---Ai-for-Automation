Generate ONE still frame, not a montage: the {which} keyframe of scene "{scene_id}".

SHOT
{visual_prompt}

FRAME INTENT ({which})
{frame_prompt}

CAMERA
{camera_motion}

STYLE
{style_anchor}

CHARACTER LOCK
{character_sheet}. Reproduce the attached reference character exactly: same face,
same hair, same wardrobe, same age, same proportions. Only pose, framing and lighting
may change.

COMPOSITION RULES FOR A {which} FRAME
- Single continuous photographic moment; no panel borders, no collage, no text overlays.
- Cinematic aspect ratio with room for burned-in captions in the lower third.
- Depth must be readable: distinct foreground, subject plane and background.
- If this is a START frame: establish the composition the motion will move away from.
- If this is an END frame: resolve to a composition the next shot can cut from cleanly;
  keep the subject visible and the frame bright (a dark or empty final frame breaks chaining).

AVOID
{negative_prompt}. Also avoid: multiple heads, duplicate subjects, warped hands,
inconsistent wardrobe, readable text, UI elements, borders.
