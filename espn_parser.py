"""
espn_parser.py
--------------
Step 2: Parse raw ESPN summary JSON into a clean, structured GameRecap dataclass.

The raw ESPN payload is a deeply nested ~2000-line JSON. This module:
  1. Extracts only the fields that matter for recap generation
  2. Normalises inconsistencies across sports (NBA vs NFL vs MLB vs NHL)
  3. Returns typed dataclasses — no raw dicts leaking into Step 3/4

Usage:
    from espn_fetcher import ESPNFetcher
    from espn_parser  import ESPNParser

    fetcher = ESPNFetcher("nba")
    raw     = fetcher.get_game_summary("401671793")  # or load_raw("game.json")
    recap   = ESPNParser("nba").parse(raw)
    print(recap)                    # human-readable summary
    print(recap.to_prompt_dict())   # clean dict ready for LLM prompting
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing      import Optional
import json


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PlayerLine:
    """One player's stat line — fields vary by sport, unused ones stay None."""
    name:        str
    position:    Optional[str] = None

    # Basketball
    points:      Optional[int]   = None
    rebounds:    Optional[int]   = None
    assists:     Optional[int]   = None
    steals:      Optional[int]   = None
    blocks:      Optional[int]   = None
    fg:          Optional[str]   = None   # "9-18"
    three_pt:    Optional[str]   = None   # "3-7"
    minutes:     Optional[int]   = None

    # Football
    pass_yards:  Optional[int]   = None
    pass_tds:    Optional[int]   = None
    rush_yards:  Optional[int]   = None
    rush_tds:    Optional[int]   = None
    rec_yards:   Optional[int]   = None
    receptions:  Optional[int]   = None

    # Baseball
    hits:        Optional[int]   = None
    rbi:         Optional[int]   = None
    home_runs:   Optional[int]   = None
    era:         Optional[float] = None
    strikeouts:  Optional[int]   = None

    # Hockey
    goals:       Optional[int]   = None
    plus_minus:  Optional[int]   = None
    shots:       Optional[int]   = None
    saves:       Optional[int]   = None
    save_pct:    Optional[float] = None

    def to_prose_line(self) -> str:
        """Return a compact human-readable stat line, e.g. '28 pts, 9 reb, 7 ast'."""
        parts = []
        if self.points    is not None: parts.append(f"{self.points} pts")
        if self.rebounds  is not None: parts.append(f"{self.rebounds} reb")
        if self.assists   is not None: parts.append(f"{self.assists} ast")
        if self.pass_yards is not None:
            parts.append(f"{self.pass_yards} pass yds")
            if self.pass_tds: parts.append(f"{self.pass_tds} TD")
        if self.rush_yards is not None: parts.append(f"{self.rush_yards} rush yds")
        if self.rec_yards  is not None: parts.append(f"{self.rec_yards} rec yds")
        if self.hits       is not None: parts.append(f"{self.hits} H")
        if self.rbi        is not None: parts.append(f"{self.rbi} RBI")
        if self.home_runs              : parts.append(f"{self.home_runs} HR")
        if self.goals      is not None: parts.append(f"{self.goals} G")
        if self.saves      is not None: parts.append(f"{self.saves} saves")
        return ", ".join(parts) if parts else "—"


@dataclass
class TeamSummary:
    name:         str
    abbreviation: str
    score:        int
    is_winner:    bool
    color:        Optional[str] = None     # hex, useful for UI later

    # Key team-level stats (sport-specific)
    stats:        dict = field(default_factory=dict)   # {"FG%": "48.2", "3P%": "38.1", ...}
    top_players:  list[PlayerLine] = field(default_factory=list)


@dataclass
class GameRecap:
    """
    The clean, sport-agnostic structure passed to the LLM in Step 3.
    Everything the model needs — nothing it doesn't.
    """
    sport:          str
    game_id:        str
    date:           str          # "2024-03-15"
    venue:          str
    attendance:     Optional[int]

    home:           TeamSummary
    away:           TeamSummary

    # Narrative helpers
    headline:       str          # e.g. "Lakers defeat Celtics 118-112"
    margin:         int          # absolute point/run/goal difference
    was_close:      bool         # margin <= sport's "close game" threshold
    went_to_ot:     bool

    # Key moments — short strings, sport-specific
    key_moments:    list[str]    = field(default_factory=list)   # scoring runs, big plays
    stat_leaders:   list[str]    = field(default_factory=list)   # "LeBron James: 32 pts, 8 reb"

    def winner(self) -> TeamSummary:
        return self.home if self.home.is_winner else self.away

    def loser(self) -> TeamSummary:
        return self.away if self.home.is_winner else self.home

    def score_line(self) -> str:
        return f"{self.away.name} {self.away.score}, {self.home.name} {self.home.score}"

    def to_prompt_dict(self) -> dict:
        """
        Returns a serialisable dict sized for an LLM prompt (~600 tokens).
        Strips internal implementation fields the model doesn't need.
        """
        return {
            "sport":        self.sport,
            "date":         self.date,
            "venue":        self.venue,
            "headline":     self.headline,
            "score":        self.score_line(),
            "was_close":    self.was_close,
            "went_to_ot":   self.went_to_ot,
            "winner":       self.winner().name,
            "loser":        self.loser().name,
            "winner_stats": self.winner().stats,
            "loser_stats":  self.loser().stats,
            "top_players": [
                {"name": p.name, "team": self.winner().name, "line": p.to_prose_line()}
                for p in self.winner().top_players
            ] + [
                {"name": p.name, "team": self.loser().name, "line": p.to_prose_line()}
                for p in self.loser().top_players
            ],
            "key_moments":  self.key_moments,
            "stat_leaders": self.stat_leaders,
        }

    def __str__(self) -> str:
        lines = [
            f"\n{'═'*55}",
            f"  {self.headline}",
            f"  {self.date}  ·  {self.venue}",
            f"{'═'*55}",
            f"  {self.away.name:30s}  {self.away.score:>3}",
            f"  {self.home.name:30s}  {self.home.score:>3}",
            f"  {'(OT)' if self.went_to_ot else ''}",
            "",
            "  STAT LEADERS",
        ]
        for s in self.stat_leaders:
            lines.append(f"    • {s}")
        if self.key_moments:
            lines.append("\n  KEY MOMENTS")
            for m in self.key_moments:
                lines.append(f"    • {m}")
        lines.append(f"{'═'*55}\n")
        return "\n".join(lines)


# ── Sport-specific parsers ─────────────────────────────────────────────────────

class ESPNParser:
    """
    Dispatches to the correct sport parser based on the league string.
    Add new sports by subclassing _BaseSportParser.
    """

    # "Close game" thresholds — used to set was_close flag
    CLOSE_THRESHOLDS = {"nba": 8, "nfl": 7, "mlb": 2, "nhl": 1}

    def __init__(self, league: str):
        self.league    = league
        self.threshold = self.CLOSE_THRESHOLDS.get(league, 5)

    def parse(self, raw: dict) -> GameRecap:
        """Entry point — auto-dispatches to sport-specific sub-parser."""
        parsers = {
            "nba": self._parse_nba,
            "nfl": self._parse_nfl,
            "mlb": self._parse_mlb,
            "nhl": self._parse_nhl,
        }
        if self.league not in parsers:
            raise ValueError(f"No parser implemented for: {self.league}")
        return parsers[self.league](raw)

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _extract_header(self, raw: dict) -> tuple[dict, dict, dict]:
        """Returns (competition_dict, home_competitor, away_competitor)."""
        comp        = raw["header"]["competitions"][0]
        competitors = comp["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")
        return comp, home, away

    def _safe_int(self, val) -> Optional[int]:
        try:   return int(val)
        except: return None

    def _safe_float(self, val) -> Optional[float]:
        try:   return float(val)
        except: return None

    def _went_to_ot(self, raw: dict) -> bool:
        status_detail = (
            raw.get("header", {})
               .get("competitions", [{}])[0]
               .get("status", {})
               .get("type", {})
               .get("detail", "")
        )
        return "OT" in status_detail or "overtime" in status_detail.lower()

    def _venue_attendance(self, comp: dict) -> tuple[str, Optional[int]]:
        venue      = comp.get("venue", {}).get("fullName", "Unknown venue")
        attendance = self._safe_int(comp.get("attendance"))
        return venue, attendance

    def _stat_value(self, stats_list: list, name: str) -> Optional[str]:
        """Pull a named stat from ESPN's [{"name": ..., "displayValue": ...}] list."""
        for s in stats_list:
            if s.get("name") == name or s.get("abbreviation") == name:
                return s.get("displayValue")
        return None

    # ── NBA ───────────────────────────────────────────────────────────────────

    def _parse_nba(self, raw: dict) -> GameRecap:
        comp, home_c, away_c = self._extract_header(raw)
        venue, attendance    = self._venue_attendance(comp)

        home = self._build_nba_team(home_c, raw, is_home=True)
        away = self._build_nba_team(away_c, raw, is_home=False)

        margin  = abs(home.score - away.score)
        leaders = self._nba_leaders(raw)
        moments = self._nba_key_moments(raw)

        winner = home if home.is_winner else away
        loser  = away if home.is_winner else home

        return GameRecap(
            sport       = "NBA",
            game_id     = raw["header"]["id"],
            date        = comp["date"][:10],
            venue       = venue,
            attendance  = attendance,
            home        = home,
            away        = away,
            headline    = f"{winner.name} defeat {loser.name} {winner.score}–{loser.score}",
            margin      = margin,
            was_close   = margin <= self.threshold,
            went_to_ot  = self._went_to_ot(raw),
            key_moments = moments,
            stat_leaders= leaders,
        )

    def _build_nba_team(self, competitor: dict, raw: dict, is_home: bool) -> TeamSummary:
        team_id  = competitor["id"]
        team_obj = competitor["team"]
        score    = self._safe_int(competitor.get("score", 0)) or 0
        winner   = competitor.get("winner", False)

        # Team-level stats from boxscore
        team_stats = {}
        for team_entry in raw.get("boxscore", {}).get("teams", []):
            if team_entry.get("team", {}).get("id") == team_id:
                for s in team_entry.get("statistics", []):
                    team_stats[s.get("label", s.get("name", ""))] = s.get("displayValue", "")

        # Top players (sort by points, take top 3)
        players = self._nba_players(raw, team_id)

        return TeamSummary(
            name         = team_obj["displayName"],
            abbreviation = team_obj["abbreviation"],
            score        = score,
            is_winner    = winner,
            color        = team_obj.get("color"),
            stats        = team_stats,
            top_players  = players[:3],
        )

    def _nba_players(self, raw: dict, team_id: str) -> list[PlayerLine]:
        players = []
        for team_entry in raw.get("boxscore", {}).get("players", []):
            if team_entry.get("team", {}).get("id") != team_id:
                continue
            for stat_group in team_entry.get("statistics", []):
                labels = stat_group.get("labels", [])     # ["MIN","FG","3PT","FT","REB","AST","STL","BLK","PTS"]
                for athlete in stat_group.get("athletes", []):
                    if not athlete.get("active", True):
                        continue
                    stats = athlete.get("stats", [])
                    if len(stats) < len(labels):
                        continue

                    def g(label):
                        try: return stats[labels.index(label)]
                        except ValueError: return None

                    pts = self._safe_int(g("PTS"))
                    if pts is None:
                        continue

                    players.append(PlayerLine(
                        name     = athlete["athlete"]["displayName"],
                        position = athlete["athlete"].get("position", {}).get("abbreviation"),
                        points   = pts,
                        rebounds = self._safe_int(g("REB")),
                        assists  = self._safe_int(g("AST")),
                        steals   = self._safe_int(g("STL")),
                        blocks   = self._safe_int(g("BLK")),
                        fg       = g("FG"),
                        three_pt = g("3PT"),
                        minutes  = self._safe_int((g("MIN") or "0").split(":")[0]),
                    ))

        return sorted(players, key=lambda p: p.points or 0, reverse=True)

    def _nba_leaders(self, raw: dict) -> list[str]:
        lines = []
        for leader_group in raw.get("leaders", []):
            category = leader_group.get("displayName", "")
            leaders  = leader_group.get("leaders", [])
            if not leaders:
                continue
            top     = leaders[0]
            athlete = top.get("athlete", {})
            name    = athlete.get("displayName", "Unknown")
            value   = top.get("displayValue", "")
            team    = top.get("team", {}).get("abbreviation", "")
            lines.append(f"{name} ({team}): {value} {category}")
        return lines

    def _nba_key_moments(self, raw: dict) -> list[str]:
        """
        Extract notable plays: large scoring runs and clutch-time moments.
        We scan play-by-play for score swings rather than returning raw play text.
        """
        plays   = raw.get("plays", [])
        moments = []

        if not plays:
            return moments

        # Find largest lead changes and final-minute plays
        max_swing  = 0
        swing_text = ""

        for play in plays:
            score_text = play.get("scoreValue", 0)
            period     = play.get("period", {}).get("number", 0)
            clock      = play.get("clock", {}).get("displayValue", "")
            text       = play.get("text", "")

            # Flag big individual plays (3-pt plays, dunks in final minute)
            if score_text and int(score_text or 0) >= 3 and period >= 4 and clock:
                try:
                    mins = int(clock.split(":")[0])
                    if mins <= 2 and text:
                        moments.append(f"Q{period} ({clock}) — {text}")
                except:
                    pass

        # Cap at 5 moments to keep the prompt lean
        return moments[:5]

    # ── NFL ───────────────────────────────────────────────────────────────────

    def _parse_nfl(self, raw: dict) -> GameRecap:
        comp, home_c, away_c = self._extract_header(raw)
        venue, attendance    = self._venue_attendance(comp)

        home = self._build_nfl_team(home_c, raw)
        away = self._build_nfl_team(away_c, raw)

        margin  = abs(home.score - away.score)
        winner  = home if home.is_winner else away
        loser   = away if home.is_winner else home
        leaders = self._nfl_leaders(raw)

        return GameRecap(
            sport       = "NFL",
            game_id     = raw["header"]["id"],
            date        = comp["date"][:10],
            venue       = venue,
            attendance  = attendance,
            home        = home,
            away        = away,
            headline    = f"{winner.name} defeat {loser.name} {winner.score}–{loser.score}",
            margin      = margin,
            was_close   = margin <= self.threshold,
            went_to_ot  = self._went_to_ot(raw),
            key_moments = self._nfl_scoring_plays(raw),
            stat_leaders= leaders,
        )

    def _build_nfl_team(self, competitor: dict, raw: dict) -> TeamSummary:
        team_id  = competitor["id"]
        team_obj = competitor["team"]
        score    = self._safe_int(competitor.get("score", 0)) or 0
        winner   = competitor.get("winner", False)

        team_stats = {}
        for team_entry in raw.get("boxscore", {}).get("teams", []):
            if team_entry.get("team", {}).get("id") == team_id:
                for s in team_entry.get("statistics", []):
                    team_stats[s.get("label", "")] = s.get("displayValue", "")

        players = self._nfl_players(raw, team_id)

        return TeamSummary(
            name         = team_obj["displayName"],
            abbreviation = team_obj["abbreviation"],
            score        = score,
            is_winner    = winner,
            stats        = team_stats,
            top_players  = players[:3],
        )

    def _nfl_players(self, raw: dict, team_id: str) -> list[PlayerLine]:
        players = []
        for team_entry in raw.get("boxscore", {}).get("players", []):
            if team_entry.get("team", {}).get("id") != team_id:
                continue
            for stat_group in team_entry.get("statistics", []):
                category = stat_group.get("name", "")
                labels   = stat_group.get("labels", [])
                for athlete in stat_group.get("athletes", []):
                    stats  = athlete.get("stats", [])
                    name   = athlete.get("athlete", {}).get("displayName", "?")

                    def g(label):
                        try: return stats[labels.index(label)]
                        except ValueError: return None

                    p = PlayerLine(name=name)
                    if category == "passing":
                        p.pass_yards = self._safe_int(g("YDS"))
                        p.pass_tds   = self._safe_int(g("TD"))
                    elif category == "rushing":
                        p.rush_yards = self._safe_int(g("YDS"))
                        p.rush_tds   = self._safe_int(g("TD"))
                    elif category == "receiving":
                        p.rec_yards  = self._safe_int(g("YDS"))
                        p.receptions = self._safe_int(g("REC"))
                    else:
                        continue

                    players.append(p)

        return players

    def _nfl_scoring_plays(self, raw: dict) -> list[str]:
        scoring = raw.get("scoringPlays", [])
        moments = []
        for play in scoring:
            team  = play.get("team", {}).get("abbreviation", "")
            text  = play.get("text", "")
            score = f"({play.get('awayScore', '?')}–{play.get('homeScore', '?')})"
            if text:
                moments.append(f"{team}: {text} {score}")
        return moments[:8]

    def _nfl_leaders(self, raw: dict) -> list[str]:
        return self._nba_leaders(raw)   # same ESPN structure

    # ── MLB ───────────────────────────────────────────────────────────────────

    def _parse_mlb(self, raw: dict) -> GameRecap:
        comp, home_c, away_c = self._extract_header(raw)
        venue, attendance    = self._venue_attendance(comp)

        home = self._build_mlb_team(home_c, raw)
        away = self._build_mlb_team(away_c, raw)

        margin  = abs(home.score - away.score)
        winner  = home if home.is_winner else away
        loser   = away if home.is_winner else home

        return GameRecap(
            sport       = "MLB",
            game_id     = raw["header"]["id"],
            date        = comp["date"][:10],
            venue       = venue,
            attendance  = attendance,
            home        = home,
            away        = away,
            headline    = f"{winner.name} defeat {loser.name} {winner.score}–{loser.score}",
            margin      = margin,
            was_close   = margin <= self.threshold,
            went_to_ot  = "Extra" in raw.get("header", {}).get("competitions", [{}])[0]
                                         .get("status", {}).get("type", {}).get("detail", ""),
            key_moments = self._mlb_key_moments(raw),
            stat_leaders= self._nba_leaders(raw),
        )

    def _build_mlb_team(self, competitor: dict, raw: dict) -> TeamSummary:
        team_id  = competitor["id"]
        team_obj = competitor["team"]
        score    = self._safe_int(competitor.get("score", 0)) or 0
        winner   = competitor.get("winner", False)

        team_stats = {}
        for team_entry in raw.get("boxscore", {}).get("teams", []):
            if team_entry.get("team", {}).get("id") == team_id:
                for s in team_entry.get("statistics", []):
                    team_stats[s.get("label", "")] = s.get("displayValue", "")

        return TeamSummary(
            name         = team_obj["displayName"],
            abbreviation = team_obj["abbreviation"],
            score        = score,
            is_winner    = winner,
            stats        = team_stats,
            top_players  = [],   # MLB player parsing is a future extension
        )

    def _mlb_key_moments(self, raw: dict) -> list[str]:
        scoring = raw.get("scoringPlays", [])
        moments = []
        for play in scoring:
            text  = play.get("text", "")
            score = f"({play.get('awayScore', '?')}–{play.get('homeScore', '?')})"
            if text:
                moments.append(f"{text} {score}")
        return moments[:6]

    # ── NHL ───────────────────────────────────────────────────────────────────

    def _parse_nhl(self, raw: dict) -> GameRecap:
        comp, home_c, away_c = self._extract_header(raw)
        venue, attendance    = self._venue_attendance(comp)

        home = self._build_nhl_team(home_c, raw)
        away = self._build_nhl_team(away_c, raw)

        margin  = abs(home.score - away.score)
        winner  = home if home.is_winner else away
        loser   = away if home.is_winner else home

        return GameRecap(
            sport       = "NHL",
            game_id     = raw["header"]["id"],
            date        = comp["date"][:10],
            venue       = venue,
            attendance  = attendance,
            home        = home,
            away        = away,
            headline    = f"{winner.name} defeat {loser.name} {winner.score}–{loser.score}",
            margin      = margin,
            was_close   = margin <= self.threshold,
            went_to_ot  = self._went_to_ot(raw),
            key_moments = self._mlb_key_moments(raw),   # scoring plays work the same way
            stat_leaders= self._nba_leaders(raw),
        )

    def _build_nhl_team(self, competitor: dict, raw: dict) -> TeamSummary:
        team_id  = competitor["id"]
        team_obj = competitor["team"]
        score    = self._safe_int(competitor.get("score", 0)) or 0
        winner   = competitor.get("winner", False)

        team_stats = {}
        for team_entry in raw.get("boxscore", {}).get("teams", []):
            if team_entry.get("team", {}).get("id") == team_id:
                for s in team_entry.get("statistics", []):
                    team_stats[s.get("label", "")] = s.get("displayValue", "")

        return TeamSummary(
            name         = team_obj["displayName"],
            abbreviation = team_obj["abbreviation"],
            score        = score,
            is_winner    = winner,
            stats        = team_stats,
            top_players  = [],
        )


# ── CLI entrypoint ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ESPN parser — Step 2")
    parser.add_argument("filepath", help="Path to a raw JSON file saved in Step 1")
    parser.add_argument("--sport",  default="nba", choices=["nba", "nfl", "mlb", "nhl"])
    parser.add_argument("--prompt_dict", action="store_true",
                        help="Also print the to_prompt_dict() output (what the LLM will see)")
    args = parser.parse_args()

    with open(args.filepath) as f:
        raw = json.load(f)

    recap = ESPNParser(args.sport).parse(raw)
    print(recap)

    if args.prompt_dict:
        print("PROMPT DICT (LLM input):")
        print(json.dumps(recap.to_prompt_dict(), indent=2))


if __name__ == "__main__":
    main()
