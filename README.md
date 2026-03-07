# fitness-video-summary

An OpenClaw skill for turning YouTube fitness videos into structured, readable summary pages.

It is designed for workout tutorials, technique breakdowns, training theory videos, and long-form fitness content. Instead of dumping raw notes, it tries to preserve the original structure of the video and generate a clean HTML report with clickable timestamps and representative screenshots.

## What it does

- Detects **YouTube Chapters** and uses them as the preferred structure when available
- Falls back to automatic sectioning when no chapters exist
- Uses subtitles and Gemini to generate a structured Chinese summary
- Extracts multiple candidate frames for each section instead of blindly taking the first frame
- Produces a **single-file HTML report** with embedded images and clickable links back to the source video
- Can optionally send the generated file through macOS Mail

## Good fit for

This skill works especially well for:

- fitness tutorials
- exercise breakdowns
- mobility / stretching / warm-up videos
- technique correction videos
- training theory, recovery, and programming content
- long YouTube videos that are worth reviewing later in a structured format

## Repository structure

- `SKILL.md` — OpenClaw skill definition and workflow guidance
- `scripts/summarize_fitness_video.py` — main script for downloading, parsing, summarizing, and generating HTML
- `scripts/extract_best_frame.py` — simple multi-frame sampling helper
- `scripts/extract_smart_frame.py` — OCR-assisted frame selection helper
- `scripts/extract_vision_frame.py` — vision-model-based frame selection helper

## How it works

1. Fetch video metadata and detect YouTube Chapters with `yt-dlp`
2. Download the video and subtitles locally
3. Prefer Gemini-based structured analysis
4. Fall back to local subtitle parsing if model analysis fails
5. Sample multiple candidate screenshots for each section
6. Generate a self-contained HTML file with embedded images
7. Save the result to the desktop
8. Optionally send the output via macOS Mail

## Requirements

Recommended environment:

- macOS
- Python 3.11+
- `yt-dlp`
- `ffmpeg`
- `tesseract`
- `google-genai`

Install example:

```bash
brew install yt-dlp ffmpeg tesseract
pip3 install --break-system-packages google-genai
```

## Environment variables

### Required

Gemini is used for the main structured summary flow:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

### Optional

If you want to use the vision-based frame selection helper, configure your own compatible API endpoint and key:

```bash
export VISION_API_KEY="your-api-key"
export VISION_API_BASE="https://your-vision-api.example.com"
```

If you want the generated HTML to be emailed automatically through macOS Mail, also set:

```bash
export SUMMARY_EMAIL_TO="your-email@example.com"
```

Notes:

- `VISION_API_BASE` should point to a service compatible with the request format used in `scripts/extract_vision_frame.py`
- If `VISION_API_KEY` is not set, the vision frame helper will fail and you should fall back to the other screenshot strategies
- If `SUMMARY_EMAIL_TO` is not set, the script will simply skip the email step
- This repository does **not** include any real API credentials or built-in recipient address

## Usage

Run the main script directly:

```bash
python3 scripts/summarize_fitness_video.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

By default, the output is saved to:

```bash
~/Desktop/[视频标题]_训练总结.html
```

## Design principles

- Respect the creator’s original structure instead of forcing every video into the same template
- Prefer YouTube Chapters when they exist
- Download locally before analysis instead of sending the raw YouTube URL directly to the model
- Sample multiple screenshots per section instead of relying on a single timestamp frame
- Generate a portable HTML output that still works after temporary files are gone

## Sensitive information cleanup

Before publishing this repository, one hardcoded API key was removed from:

- `scripts/extract_vision_frame.py`

That logic now reads configuration from user-supplied environment variables instead:

- `VISION_API_KEY`
- `VISION_API_BASE`

This keeps the repository safe to publish while still allowing users to plug in their own API provider.

## Limitations

- `send_email()` currently depends on macOS Mail + AppleScript and only runs when `SUMMARY_EMAIL_TO` is configured
- Automatic subtitles may contain transcription errors
- If Gemini quota is exhausted, fallback mode may produce lower-quality results
- Screenshot quality still depends on video clarity, pacing, subtitle overlays, and the chosen frame selection strategy

## License

No license has been added yet. If you plan to share or reuse this publicly, adding an MIT license would be a sensible default.
