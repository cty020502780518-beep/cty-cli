# Demo Guide

This document describes how to record and showcase CTY-Cli's features for GitHub and interview purposes.

## Planned Screenshots

Place screenshots in `docs/images/` using the following filenames:

| File | Content | How to Capture |
|------|---------|---------------|
| `startup.png` | Welcome screen after `python main.py` | Run `cty-cli` with an API key configured, screenshot the welcome banner |
| `help.png` | Output of `/help` command | Type `/help` in the REPL |
| `tool-use.png` | Agent using read_file + edit_file | Ask: "read main.py and change the version to 0.2.0" |
| `permission.png` | Permission prompt for write/exec | Ask: "create a file called test.txt" — the permission dialog appears |
| `memory-demo.png` | Memory add + recall workflow | `/memory add "I prefer Java ACM format for algorithm problems"` then `/memory list` |
| `trace.png` | Trace output after a complex request | Ask the agent to do a multi-step task, then type `/trace` |
| `plan.png` | Plan with multiple tasks | Ask: "Create a plan for implementing a login feature" |
| `multi-provider.png` | Switching providers with `/provider` | `/providers` to list, `/provider anthropic` to switch |

## Planned Videos

Place videos in `docs/videos/`:

| File | Content | Suggested Length |
|------|---------|-----------------|
| `demo.mp4` | Full workflow: startup, tool use, memory recall, plan execution | 3-5 minutes |

### Demo Script

1. **Start** (0:00-0:10): Run `python main.py` — show the welcome banner
2. **Simple chat** (0:10-0:30): Ask "What can you do?" — agent responds with capabilities
3. **Tool use** (0:30-1:30): Ask "Read the README.md and tell me what providers are supported"
   - Agent calls `read_file` tool (auto-allowed)
   - Shows formatted output
4. **Permission check** (1:30-2:00): Ask "Create a file called hello.py with a Hello World function"
   - Agent calls `write_file` tool
   - Permission prompt appears
   - User approves
5. **Memory** (2:00-2:45): 
   - `/memory add "I prefer Java ACM format for algorithm problems"`
   - Exit and restart
   - Ask "What format do I use for algorithm problems?"
   - Agent auto-recalls the memory
6. **Plan** (2:45-3:30): Ask "Create a plan to build a REST API with 3 endpoints"
   - Agent creates plan steps via `plan_create`
   - `/plan` to view
7. **Trace** (3:30-4:00): `/trace` to show the execution trace

## Recording Tools

- **Windows**: OBS Studio, ShareX (free), or Xbox Game Bar (Win+G)
- **macOS**: QuickTime Player → File → New Screen Recording
- **Linux**: OBS Studio, SimpleScreenRecorder, or `ffmpeg -f x11grab`

## GIF Creation

For README GIFs (under 10 seconds each):
```bash
# Convert video segment to GIF
ffmpeg -i demo.mp4 -ss 00:00:05 -t 8 -vf "fps=10,scale=800:-1" startup.gif
```

Or use [ScreenToGif](https://www.screentogif.com/) (Windows, free).
