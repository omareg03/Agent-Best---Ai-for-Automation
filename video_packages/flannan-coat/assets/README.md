# Asset intake convention

Place one generated/reference keyframe per storyboard block at `frames/frame_01.png` through `frame_12.png`. Place optional generated video at `clips/block_01_<block-suffix>.mp4` through `block_12_<block-suffix>.mp4`. The intake tool can synthesize a Ken Burns fallback clip from each available frame. Do not commit empty/fake media; `.gitkeep` only preserves the folders.

Run `python scripts/ingest_assets.py <package-dir>` after adding files. PNG/MP4 assets are covered by Git LFS patterns in the repository `.gitattributes`.
