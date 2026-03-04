"""
espn_fetcher.py
---------------
Step 1: Fetch raw game data from ESPN's public (unofficial) API.

Usage:
    python espn_fetcher.py                        # shows recent NBA games
    python espn_fetcher.py --sport nfl            # recent NFL games
    python espn_fetcher.py --game_id 401671793    # full summary for one game
"""

import requests
import json
import argparse
from datetime import datetime
from typing import Optional


# ESPN's public API base — no auth required
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

SUPPORTED_LEAGUES = {
    "nba":  ("basketball", "nba"),
    "nfl":  ("football",   "nfl"),
    "mlb":  ("baseball",   "mlb"),
    "nhl":  ("hockey",     "nhl"),
}


class ESPNFetcher:
    """
    Thin wrapper around ESPN's public API endpoints.
    Handles requests, basic error handling, and raw JSON storage.
    """

    def __init__(self, league: str = "nba"):
        if league not in SUPPORTED_LEAGUES:
            raise ValueError(f"League must be one of: {list(SUPPORTED_LEAGUES.keys())}")

        self.league = league
        sport, league_slug = SUPPORTED_LEAGUES[league]
        self.base_url = f"{ESPN_BASE}/{sport}/{league_slug}"
        self.session = requests.Session()
        self.session.headers.update({
            # Mimicking a browser slightly reduces the chance of being rate-limited
            "User-Agent": "Mozilla/5.0 (compatible; sports-recap-generator/1.0)"
        })

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        """Central request method with basic error handling."""
        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Request timed out: {url}")
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"HTTP {resp.status_code} from ESPN API: {e}")
        except requests.exceptions.JSONDecodeError:
            raise RuntimeError("ESPN returned non-JSON response — endpoint may have changed")

    def get_recent_games(self, limit: int = 10) -> list[dict]:
        """
        Fetch recent (or live) games from the scoreboard endpoint.
        Returns a simplified list — game_id, teams, score, status.

        Use this to discover game_ids for get_game_summary().
        """
        url = f"{self.base_url}/scoreboard"
        data = self._get(url)

        games = []
        for event in data.get("events", [])[:limit]:
            competition = event["competitions"][0]
            competitors  = competition["competitors"]

            # ESPN always puts home/away in the competitors list
            home = next(c for c in competitors if c["homeAway"] == "home")
            away = next(c for c in competitors if c["homeAway"] == "away")

            games.append({
                "game_id":    event["id"],
                "date":       event["date"],
                "status":     event["status"]["type"]["description"],  # e.g. "Final", "In Progress"
                "home_team":  home["team"]["displayName"],
                "home_score": home.get("score", "—"),
                "away_team":  away["team"]["displayName"],
                "away_score": away.get("score", "—"),
                "venue":      competition.get("venue", {}).get("fullName", "Unknown"),
            })

        return games

    def get_game_summary(self, game_id: str) -> dict:
        """
        Fetch the full summary payload for a single completed game.
        This is the raw JSON you'll parse in Step 2.

        Key top-level sections:
            header    — teams, final score, game metadata
            boxscore  — team/player stats
            leaders   — stat leaders per team
            plays     — full play-by-play
            standings — standings context
        """
        url = f"{self.base_url}/summary"
        return self._get(url, params={"event": game_id})

    def save_raw(self, data: dict, filepath: str) -> None:
        """Save a raw API response to disk. Useful for offline dev/testing."""
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved raw JSON → {filepath}")

    def load_raw(self, filepath: str) -> dict:
        """Load a previously saved raw JSON file."""
        with open(filepath) as f:
            return json.load(f)


# ── Quick inspection helpers ──────────────────────────────────────────────────

def print_recent_games(games: list[dict]) -> None:
    print(f"\n{'ID':<12} {'Status':<14} {'Matchup':<45} {'Score'}")
    print("─" * 80)
    for g in games:
        matchup = f"{g['away_team']} @ {g['home_team']}"
        score   = f"{g['away_score']} - {g['home_score']}"
        date    = datetime.fromisoformat(g["date"].replace("Z", "+00:00")).strftime("%b %d")
        print(f"{g['game_id']:<12} {g['status']:<14} {matchup:<45} {score}  ({date})")
    print()


def print_summary_structure(summary: dict) -> None:
    """Print the top-level keys and their sizes so you can plan your parser."""
    print("\nGame summary top-level structure:")
    print("─" * 40)
    for key, val in summary.items():
        if isinstance(val, dict):
            print(f"  {key}: dict  ({len(val)} keys)")
        elif isinstance(val, list):
            print(f"  {key}: list  ({len(val)} items)")
        else:
            print(f"  {key}: {type(val).__name__}")
    print()


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ESPN API fetcher — Step 1")
    parser.add_argument("--sport",   default="nba",  choices=SUPPORTED_LEAGUES.keys())
    parser.add_argument("--game_id", default=None,   help="Fetch full summary for this game ID")
    parser.add_argument("--save",    default=None,   help="Save raw JSON to this filepath")
    args = parser.parse_args()

    fetcher = ESPNFetcher(league=args.sport)

    if args.game_id:
        print(f"\nFetching full summary for game {args.game_id}...")
        summary = fetcher.get_game_summary(args.game_id)
        print_summary_structure(summary)

        if args.save:
            fetcher.save_raw(summary, args.save)
        else:
            print("Tip: re-run with --save game.json to persist this for Step 2 parsing.\n")

    else:
        print(f"\nFetching recent {args.sport.upper()} games...")
        games = fetcher.get_recent_games()
        print_recent_games(games)
        print("→ Copy a game_id and re-run with --game_id <id> to fetch the full summary.\n")


if __name__ == "__main__":
    main()
