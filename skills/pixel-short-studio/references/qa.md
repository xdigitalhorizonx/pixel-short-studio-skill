# Pixel-short acceptance checks

## Visual review

- Open the source assets and every decisive preview at original logical resolution.
- Inspect the contact sheet from left to right as a sentence.
- Confirm the main character is visible in every intended beat.
- Confirm sheet rows and cell counts; direction-neutral sheets often contain only row zero.
- Check bottom-center feet alignment, center rotation, and shadow placement.
- Reject changes in character scale, outline, palette, or proportions across sequences.
- Confirm anticipation precedes action and reaction follows contact.
- Hold contact long enough to read without making the short feel frozen.
- Confirm effects reinforce silhouettes instead of covering faces or limbs.
- Check title/text at delivery size and ensure it remains bitmap-crisp.
- Review the encoded MP4, not only source PNGs.

## Technical review

- Duration is within the requested 15–30 second window.
- Frame count equals duration × fps within one frame.
- Video is H.264 with `yuv420p` for broad compatibility.
- Delivery dimensions are the logical canvas multiplied by an integer.
- Upscaling uses nearest-neighbor.
- Audio exists when the brief calls for it and does not clip.
- MP4 uses fast-start metadata.
- No missing referenced files or absolute author-machine paths remain in `short.json`.
- Rendering from a fresh copy reproduces the output.

## Delivery

Include:

- Final MP4.
- Timeline contact sheet.
- `short.json`.
- Shot chart and style contract.
- Source/attribution record.
- Exact render and validation commands.
- Any known IP or licensing limitation.

