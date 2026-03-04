"""
recap_generator.py
------------------
Step 3: Generate narrative game recaps using the Anthropic API.

Three built-in styles:
  • beat_reporter   — traditional newspaper game story
  • analytics       — data-driven, efficiency and advanced stats focus
  • fan_friendly    — conversational, emoji-accented, emotional

Usage:
    # As a module
    from espn_fetcher     import ESPNFetcher
    from espn_parser      import ESPNParser
    from recap_generator  import RecapGenerator

    raw    = ESPNFetcher("nba").get_game_summary("401671793")
    recap  = ESPNParser("nba").parse(raw)
    gen    = RecapGenerator()
    result = gen.generate(recap, style="beat_reporter")
    print(result.text)

    # From the CLI
    python recap_generator.py --file raw_game.json --sport nba --style analytics
    python recap_generator.py --file raw_game.json --sport nba --all_styles
"""

import os
import json
import time
import argparse
from dataclasses import dataclass
from typing      import Optional

import anthropic

from espn_parser import GameRecap


# ── Model config ──────────────────────────────────────────────────────────────

MODEL        = "claude-sonnet-4-6"   # fast + capable; swap to claude-opus-4-6 for richer prose
MAX_TOKENS   = 1024                  # ~600-800 words — right length for a recap


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class RecapResult:
    style:         str
    text:          str
    input_tokens:  int
    output_tokens: int
    latency_ms:    int

    def __str__(self) -> str:
        return (
            f"\n{'═'*60}\n"
            f"  Style: {self.style.upper()}\n"
            f"  Tokens: {self.input_tokens} in / {self.output_tokens} out  "
            f"  Latency: {self.latency_ms}ms\n"
            f"{'─'*60}\n"
            f"{self.text}\n"
            f"{'═'*60}\n"
        )


# ── Prompt library ────────────────────────────────────────────────────────────

# Each style is a (system_prompt, user_template) pair.
# The user template receives a single .format(game_json=...) call.
#
# Design principles:
#   1. System prompt establishes the persona and hard constraints
#   2. User message delivers the data + specific structural instructions
#   3. Explicit length guidance prevents runaway output
#   4. "Do not invent" instruction is critical — LLMs will fabricate quotes

STYLE_PROMPTS: dict[str, tuple[str, str]] = {

    "beat_reporter": (
        # ── System ──────────────────────────────────────────────────────────
        """You are a veteran sports beat reporter for a major metropolitan newspaper.
Your game recaps are authoritative, well-structured, and read like polished journalism.

Rules you never break:
- Lead with the most important story (score, key performer, or decisive moment)
- Attribute statistics precisely: "shot 58% from the field", not "shot well"
- Write in past tense, third person
- No invented quotes — if you'd normally include a quote, write "[Coach name] said after the game" as a placeholder
- Length: 4–5 tight paragraphs, ~350–450 words
- No emoji, no bullet points, no headers — pure prose""",

        # ── User ────────────────────────────────────────────────────────────
        """Write a beat reporter game recap for the following game.

Game data (JSON):
{game_json}

Structure your recap as:
1. Lede paragraph — score, winner, defining story of the game
2. Key performer paragraph — best player(s) and their stat lines
3. How the game was won — key runs, momentum shifts, or decisive sequences
4. Supporting cast / team stats that explain the margin
5. Context closer — standings implications or what to watch next (keep brief)"""
    ),

    "analytics": (
        # ── System ──────────────────────────────────────────────────────────
        """You are a sports analytics writer in the style of The Athletic's data desk.
You translate box score numbers into genuine insight — not just recitation.

Rules you never break:
- Always ask "what does this number mean?" before writing it
- Highlight efficiency metrics (shooting percentages, turnovers, pace) over raw counting stats
- Use comparative language: "well above their season average", "a defensive performance that limited..."
- If the data suggests a narrative (team dominated a specific area), make that the spine of the piece
- Length: 4–5 paragraphs, ~350–450 words
- No emoji; headers are acceptable if they add clarity""",

        # ── User ────────────────────────────────────────────────────────────
        """Write an analytics-focused game recap for the following game.

Game data (JSON):
{game_json}

Structure your recap as:
1. Thesis — the one or two statistical storylines that decided this game
2. Offensive efficiency breakdown — what the numbers say about how each team scored
3. Defensive / turnover analysis — where the losing team broke down
4. Individual standout — the player whose efficiency metrics stood out most
5. Takeaway — what this game reveals about each team's tendencies or trajectory"""
    ),

    "fan_friendly": (
        # ── System ──────────────────────────────────────────────────────────
        """You are a sports writer for a fan-first digital outlet — think Bleacher Report meets a
passionate fan podcast. Your recaps are energetic, accessible, and fun to read.

Rules you never break:
- Write like you're texting a friend who missed the game
- Use some emoji (but not one per sentence — be selective)
- Celebrate the winner genuinely; acknowledge the loser fairly
- Translate jargon — if you mention "net rating" explain it in a clause
- Length: 3–4 paragraphs, ~250–350 words — snappy, not exhaustive
- Avoid clichés like "gave 110%" or "left it all on the floor" """,

        # ── User ────────────────────────────────────────────────────────────
        """Write a fan-friendly game recap for the following game.

Game data (JSON):
{game_json}

Structure:
1. Hook — open with the most exciting / dramatic element of the game
2. Star power — who carried their team and why fans should care
3. The turning point — that one stretch or play that flipped the game
4. What it means — quick take on where both teams go from here"""
    ),
}


# ── Generator ─────────────────────────────────────────────────────────────────

class RecapGenerator:
    """
    Wraps the Anthropic client and handles prompt construction,
    API calls, and result packaging.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = MODEL):
        """
        api_key defaults to the ANTHROPIC_API_KEY environment variable.
        The SDK raises AuthenticationError on first call if it's missing.
        """
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.model = model

    def generate(self, recap: GameRecap, style: str = "beat_reporter") -> RecapResult:
        """
        Generate a single recap in the requested style.

        Args:
            recap:  A parsed GameRecap from espn_parser.py
            style:  One of "beat_reporter", "analytics", "fan_friendly"

        Returns:
            RecapResult with text, token counts, and latency
        """
        if style not in STYLE_PROMPTS:
            raise ValueError(
                f"Unknown style '{style}'. "
                f"Available: {list(STYLE_PROMPTS.keys())}"
            )

        system_prompt, user_template = STYLE_PROMPTS[style]

        # Build the user message — inject the structured game data
        game_data   = json.dumps(recap.to_prompt_dict(), indent=2)
        user_prompt = user_template.format(game_json=game_data)

        t0 = time.monotonic()

        response = self.client.messages.create(
            model      = self.model,
            max_tokens = MAX_TOKENS,
            system     = system_prompt,
            messages   = [{"role": "user", "content": user_prompt}],
        )

        latency_ms = int((time.monotonic() - t0) * 1000)

        return RecapResult(
            style         = style,
            text          = response.content[0].text,
            input_tokens  = response.usage.input_tokens,
            output_tokens = response.usage.output_tokens,
            latency_ms    = latency_ms,
        )

    def generate_all_styles(self, recap: GameRecap) -> dict[str, RecapResult]:
        """
        Generate recaps in all three styles.
        Returns a dict keyed by style name.

        Note: makes 3 sequential API calls. For a production app you'd
        parallelise these with asyncio — see the docstring below.
        """
        results = {}
        for style in STYLE_PROMPTS:
            print(f"  Generating {style}...", end=" ", flush=True)
            result     = self.generate(recap, style)
            results[style] = result
            print(f"✓  ({result.latency_ms}ms, {result.output_tokens} tokens)")

        return results

    def add_custom_style(self, name: str, system: str, user_template: str) -> None:
        """
        Register a custom style at runtime.
        user_template must contain a {game_json} placeholder.

        Example:
            gen.add_custom_style(
                name="kids",
                system="Explain the game to a 10-year-old sports fan.",
                user_template="Here is the game: {game_json}\\n\\nWrite a fun, simple recap."
            )
        """
        if "{game_json}" not in user_template:
            raise ValueError("user_template must contain the {game_json} placeholder")
        STYLE_PROMPTS[name] = (system, user_template)

    def save_results(
        self,
        results: dict[str, RecapResult],
        filepath: str,
        recap: Optional[GameRecap] = None,
    ) -> None:
        """Save all generated recaps to a JSON file."""
        output = {
            "game_headline": recap.headline if recap else "unknown",
            "game_date":     recap.date     if recap else "unknown",
            "recaps": {
                style: {
                    "text":          r.text,
                    "input_tokens":  r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "latency_ms":    r.latency_ms,
                }
                for style, r in results.items()
            }
        }
        with open(filepath, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nSaved recaps → {filepath}")


# ── Async alternative (for Step 4 / Streamlit) ────────────────────────────────
#
# When you move to Streamlit, you'll want to parallelise the 3 API calls
# so all styles generate simultaneously. Here's the pattern:
#
#   import asyncio
#   from anthropic import AsyncAnthropic
#
#   async def generate_all_async(recap: GameRecap) -> dict[str, RecapResult]:
#       client = AsyncAnthropic()
#       tasks  = {
#           style: asyncio.create_task(_generate_one(client, recap, style))
#           for style in STYLE_PROMPTS
#       }
#       return {style: await task for style, task in tasks.items()}
#
# This cuts total latency from ~sum(latencies) to ~max(latency).


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Recap generator — Step 3")
    parser.add_argument("--file",       required=True, help="Path to raw ESPN JSON (from Step 1 --save)")
    parser.add_argument("--sport",      default="nba", choices=["nba", "nfl", "mlb", "nhl"])
    parser.add_argument("--style",      default="beat_reporter",
                        choices=list(STYLE_PROMPTS.keys()),
                        help="Recap style (ignored if --all_styles)")
    parser.add_argument("--all_styles", action="store_true", help="Generate all three styles")
    parser.add_argument("--save",       default=None, help="Save output to this JSON filepath")
    args = parser.parse_args()

    # ── Load and parse ────────────────────────────────────────────────────────
    from espn_parser import ESPNParser
    with open(args.file) as f:
        raw = json.load(f)

    print(f"\nParsing {args.sport.upper()} game...")
    recap = ESPNParser(args.sport).parse(raw)
    print(recap)

    # ── Generate ─────────────────────────────────────────────────────────────
    gen = RecapGenerator()

    if args.all_styles:
        print("\nGenerating all styles:")
        results = gen.generate_all_styles(recap)
        for result in results.values():
            print(result)
        if args.save:
            gen.save_results(results, args.save, recap)
    else:
        print(f"\nGenerating {args.style} recap...")
        result = gen.generate(recap, style=args.style)
        print(result)
        if args.save:
            gen.save_results({args.style: result}, args.save, recap)


if __name__ == "__main__":
    main()
