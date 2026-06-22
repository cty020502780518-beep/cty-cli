#!/usr/bin/env python3
"""CTY-Cli — A minimalist Claude Code-style coding agent.

Usage:
  python main.py                          # Start interactive REPL
  python main.py --provider deepseek     # Use DeepSeek
  python main.py --model deepseek-v4-pro # Specific model
  python main.py --working-dir ~/project # Set working directory

Architecture:
  main.py → agent.py → providers/  (API)
                    → tools.py     (execution)
                    → context.py   (token mgmt)
                    → permissions.py (safety)
                    → trace.py     (logging)
                    → plan.py      (tasks)
                    → memory.py    (persistence)
                    → skills.py    (skill engine)
  ui.py → Terminal rendering

Requirements: pip install -r requirements.txt
Config: copy .env.example to .env and add your API keys
"""
import argparse
import os
import sys
from pathlib import Path

# Add project root to path (in case run from elsewhere)
sys.path.insert(0, str(Path(__file__).parent))

from config import Config, PROVIDER_PRESETS
from providers import create_provider
from ui import TerminalUI
from agent import Agent


def parse_args():
    p = argparse.ArgumentParser(
        description="CTY-Cli — A coding agent in your terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --provider deepseek --model deepseek-chat
  python main.py --working-dir ~/my-project
        """,
    )
    p.add_argument("--provider", default=None, help="LLM provider (deepseek, anthropic, openai)")
    p.add_argument("--model", default=None, help="Model name")
    p.add_argument("--working-dir", default=None, help="Working directory")
    p.add_argument("--version", action="store_true", help="Show version")
    return p.parse_args()


def main():
    args = parse_args()

    if args.version:
        print("CTY-Cli v0.1.0")
        return

    # Replace lone surrogates in all stdout output (DeepSeek reasoning_content)
    sys.stdout.reconfigure(errors="replace")

    # ── Config ───────────────────────────────────────────────────────
    config = Config()

    if args.provider:
        config.switch_provider(args.provider)
    if args.model:
        config.switch_model(args.model)
    if args.working_dir:
        os.chdir(Path(args.working_dir).expanduser())

    config.working_dir = Path.cwd()

    # ── Verify API key ───────────────────────────────────────────────
    try:
        api_key = config.get_api_key()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # ── Provider ─────────────────────────────────────────────────────
    base_url = config.provider.base_url
    provider = create_provider(
        name=config.provider_name,
        api_key=api_key,
        model=config.model,
        base_url=base_url,
    )

    # ── UI ───────────────────────────────────────────────────────────
    ui = TerminalUI()

    # ── Agent ────────────────────────────────────────────────────────
    agent = Agent(provider=provider, config=config, ui=ui)

    # ── Welcome ──────────────────────────────────────────────────────
    print("\033[2J\033[H")  # Clear screen
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  CTY-Cli v0.1.0                              ║")
    print(f"║  Provider: {config.provider_name:<35}║")
    print(f"║  Model:    {config.model:<35}║")
    print(f"║  CWD:      {str(config.working_dir):<35}║")
    print(f"╠══════════════════════════════════════════════╣")
    print(f"║  Type /help for commands, /exit to quit      ║")
    print(f"╚══════════════════════════════════════════════╝")
    print()

    ui.update_header(
        model=config.model,
        tokens="0 / 100k",
        cwd=str(config.working_dir),
    )

    # ── REPL ─────────────────────────────────────────────────────────
    while agent.running:
        try:
            user_input = ui.get_input()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        print()  # blank line before agent response
        agent.run(user_input)
        print()  # blank line after

        # Update header with fresh token count
        tokens = agent.context.stats_line(agent.messages)
        ui.update_header(
            model=config.model,
            tokens=tokens,
            cwd=str(config.working_dir),
        )

    # ── Cleanup ──────────────────────────────────────────────────────
    print(f"\n{agent.tracer.summary()}")


if __name__ == "__main__":
    main()
