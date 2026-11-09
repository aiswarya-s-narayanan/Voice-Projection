# How to make the motion clips

Use an AI **image-to-video** tool that supports a **start frame and an end frame**, such as Kling AI, Luma Dream Machine or Runway.

## Settings for every clip

| Setting | Value |
|---|---|
| Start frame | `start-frame-green.png` (in this folder) |
| End frame | `start-frame-green.png`, the **same** picture, so all clips join smoothly |
| Length | 5 seconds |
| Size | 9:16 portrait, 1080p if possible (720p is OK) |
| Camera | no movement |
| Save as | MP4 in this folder, with the file name from the table below |

**Add this text to the end of every prompt:**

```
Static camera, full body, plain green background. Realistic, natural, calm movement.
Her lips stay closed with a soft smile, she is not talking.
She ends in exactly the same pose as the start.
```

**Negative prompt**, if the tool has one:

```
talking, mouth moving, camera movement, zoom, background change, extra fingers, distorted hands
```

## The clips

| File name | Prompt (then add the text above) |
|---|---|
| `idle.mp4` | She stands relaxed and breathes naturally, with small natural movements of her head, shoulders and hands. She blinks. |
| `talk-1.mp4` | She is explaining something to the viewer with natural hand gestures. Both hands move gently in front of her body, then go back to the starting pose. |
| `talk-2.mp4` | She talks with her open-palm hand, making relaxed gestures as if describing something, with small head movements, then goes back to the starting pose. |
| `wave.mp4` | She waves hello to the viewer with her raised hand, friendly and happy, then goes back to the starting pose. |
| `show.mp4` | She presents something at her side with her open palm, turning slightly toward it, then goes back to the starting pose. |
| `nod.mp4` | She nods her head twice, agreeing, with a warm smile. |
| `bow.mp4` *(optional)* | She does a small, polite Japanese bow, then stands up straight again. |
| `think.mp4` *(optional)* | She brings one hand up near her chin, thinking, then goes back to the starting pose. |

## Check each clip before you keep it

- The background stays plain green.
- Her face stays the same person.
- Her **lips stay closed**. The module adds the talking mouth itself.
- The camera does not move or zoom.
- She ends in the starting pose.

If a clip fails one of these checks, generate it again.

**Tip:** make `idle.mp4` first and tell Claude, so it can test the whole pipeline before you make the rest.
