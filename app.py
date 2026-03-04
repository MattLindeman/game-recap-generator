"""
app.py
------
Step 4: Streamlit UI — game selection, style picker, live recap generation.

Run:
    streamlit run app.py

Requires:
    pip install streamlit anthropic requests

Environment:
    ANTHROPIC_API_KEY  — or enter it in the sidebar at runtime
"""

import os
import time
import json
import threading
from typing import Optional

import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title  = "Game Recap Generator",
    page_icon   = "🏟️",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)


# ── Custom CSS — dark editorial sports aesthetic ──────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=Barlow:wght@300;400;500&display=swap');

  /* ── Root vars ── */
  :root {
    --bg:        #0d0f12;
    --surface:   #161a20;
    --surface2:  #1e242d;
    --border:    #2a3040;
    --accent:    #f0a500;
    --accent2:   #e05c2a;
    --text:      #e8eaed;
    --muted:     #6b7585;
    --win:       #2ecc71;
    --loss:      #e74c3c;
  }

  /* ── Global ── */
  html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Barlow', sans-serif;
  }
  [data-testid="stSidebar"] {
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border);
  }

  /* ── Headers ── */
  h1, h2, h3 { font-family: 'Barlow Condensed', sans-serif !important; letter-spacing: 0.02em; }

  /* ── Scoreboard cards ── */
  .game-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }
  .game-card:hover        { border-color: var(--accent); background: var(--surface2); }
  .game-card.selected     { border-color: var(--accent); background: var(--surface2); box-shadow: 0 0 0 2px rgba(240,165,0,0.25); }
  .game-card .teams       { font-family: 'Barlow Condensed', sans-serif; font-size: 1.15rem; font-weight: 700; }
  .game-card .score       { font-family: 'Barlow Condensed', sans-serif; font-size: 1.5rem; font-weight: 800; color: var(--accent); }
  .game-card .meta        { font-size: 0.78rem; color: var(--muted); margin-top: 4px; }
  .game-card .status-live { color: var(--win); font-weight: 600; font-size: 0.78rem; }
  .game-card .status-fin  { color: var(--muted); font-size: 0.78rem; }

  /* ── Style pills ── */
  .style-pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-right: 6px;
  }
  .pill-beat       { background: rgba(240,165,0,0.15);  color: var(--accent);  border: 1px solid var(--accent); }
  .pill-analytics  { background: rgba(65,145,255,0.15); color: #4191ff;        border: 1px solid #4191ff; }
  .pill-fan        { background: rgba(224,92,42,0.15);  color: var(--accent2); border: 1px solid var(--accent2); }

  /* ── Recap output ── */
  .recap-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 28px 32px;
    line-height: 1.75;
    font-size: 1.05rem;
    white-space: pre-wrap;
  }

  /* ── Stat bar ── */
  .stat-bar {
    display: flex;
    gap: 24px;
    padding: 10px 16px;
    background: var(--surface2);
    border-radius: 6px;
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 12px;
  }
  .stat-bar span { color: var(--text); font-weight: 600; }

  /* ── Section label ── */
  .section-label {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 10px;
  }

  /* ── Headline ── */
  .game-headline {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    line-height: 1.1;
    margin-bottom: 4px;
    color: var(--text);
  }
  .game-subline {
    font-size: 0.85rem;
    color: var(--muted);
    margin-bottom: 20px;
  }

  /* ── Streamlit widget overrides ── */
  .stButton > button {
    background: var(--accent) !important;
    color: #0d0f12 !important;
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 0.5rem 1.5rem !important;
    text-transform: uppercase !important;
  }
  .stButton > button:hover { background: #ffc233 !important; }

  div[data-testid="stRadio"] label { color: var(--text) !important; font-size: 0.9rem; }
  div[data-testid="stSelectbox"] > div { background: var(--surface2) !important; border-color: var(--border) !important; }
  div[data-testid="stTextInput"] input { background: var(--surface2) !important; border-color: var(--border) !important; color: var(--text) !important; }
  div[data-testid="stTabs"] button { font-family: 'Barlow Condensed', sans-serif !important; font-size: 1rem !important; letter-spacing: 0.04em; }
  .stSpinner > div { border-top-color: var(--accent) !important; }

  /* ── Divider ── */
  hr { border-color: var(--border) !important; }

  /* ── Toast / info box ── */
  .stAlert { background: var(--surface2) !important; border-color: var(--border) !important; }
</style>
""", unsafe_allow_html=True)


# ── Lazy imports (after page config) ─────────────────────────────────────────
from espn_fetcher    import ESPNFetcher
from espn_parser     import ESPNParser, GameRecap
from recap_generator import RecapGenerator, STYLE_PROMPTS


# ── Constants ─────────────────────────────────────────────────────────────────

LEAGUES = {
    "🏀  NBA":  "nba",
    "🏈  NFL":  "nfl",
    "⚾  MLB":  "mlb",
    "🏒  NHL":  "nhl",
}

STYLE_META = {
    "beat_reporter": {
        "label":       "Beat Reporter",
        "pill_class":  "pill-beat",
        "icon":        "📰",
        "description": "Traditional newspaper-style game story. Authoritative, structured, journalistic.",
    },
    "analytics": {
        "label":       "Analytics",
        "pill_class":  "pill-analytics",
        "icon":        "📊",
        "description": "Data-driven efficiency analysis. What the numbers actually mean.",
    },
    "fan_friendly": {
        "label":       "Fan Friendly",
        "pill_class":  "pill-fan",
        "icon":        "🔥",
        "description": "Conversational and energetic. Like texting a friend who missed the game.",
    },
}


# ── Session state initialisation ──────────────────────────────────────────────

def init_state():
    defaults = {
        "games":          [],
        "selected_game":  None,
        "recap":          None,          # parsed GameRecap object
        "results":        {},            # {style: RecapResult}
        "active_style":   "beat_reporter",
        "league":         "nba",
        "fetcher":        None,
        "loading_games":  False,
        "error":          None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_api_key() -> Optional[str]:
    return (
        st.session_state.get("api_key_input")
        or os.environ.get("ANTHROPIC_API_KEY")
    )

def get_fetcher(league: str) -> ESPNFetcher:
    """Cache the fetcher per league in session state."""
    key = f"fetcher_{league}"
    if key not in st.session_state:
        st.session_state[key] = ESPNFetcher(league=league)
    return st.session_state[key]

def status_badge(status: str) -> str:
    if "progress" in status.lower() or "live" in status.lower():
        return f'<span class="status-live">● LIVE</span>'
    return f'<span class="status-fin">{status}</span>'


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<p style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.5rem;font-weight:800;color:#f0a500;letter-spacing:0.05em;">🏟️ RECAP GEN</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.78rem;color:#6b7585;margin-top:-12px;">Powered by ESPN + Claude</p>', unsafe_allow_html=True)
    st.divider()

    # API key
    st.markdown('<div class="section-label">Anthropic API Key</div>', unsafe_allow_html=True)
    api_key_display = get_api_key()
    if api_key_display:
        masked = api_key_display[:8] + "••••••••" + api_key_display[-4:] if len(api_key_display) > 12 else "••••••••"
        st.markdown(f'<p style="font-size:0.8rem;color:#2ecc71;">✓ Key loaded ({masked})</p>', unsafe_allow_html=True)
    else:
        st.text_input(
            "API Key",
            type="password",
            key="api_key_input",
            placeholder="sk-ant-...",
            label_visibility="collapsed",
        )

    st.divider()

    # League picker
    st.markdown('<div class="section-label">League</div>', unsafe_allow_html=True)
    league_display = st.radio(
        "League",
        list(LEAGUES.keys()),
        label_visibility="collapsed",
        key="league_radio",
    )
    selected_league = LEAGUES[league_display]

    # Reset game selection when league changes
    if selected_league != st.session_state.league:
        st.session_state.league          = selected_league
        st.session_state.games           = []
        st.session_state.selected_game   = None
        st.session_state.recap           = None
        st.session_state.results         = {}

    st.divider()

    # Load games button
    if st.button("Load Recent Games", use_container_width=True):
        with st.spinner("Fetching scoreboard..."):
            try:
                fetcher = get_fetcher(selected_league)
                st.session_state.games        = fetcher.get_recent_games(limit=12)
                st.session_state.selected_game = None
                st.session_state.recap         = None
                st.session_state.results       = {}
                st.session_state.error         = None
            except Exception as e:
                st.session_state.error = str(e)

    st.divider()

    # Style picker
    st.markdown('<div class="section-label">Recap Style</div>', unsafe_allow_html=True)
    style_choice = st.radio(
        "Style",
        list(STYLE_META.keys()),
        format_func=lambda s: f"{STYLE_META[s]['icon']}  {STYLE_META[s]['label']}",
        label_visibility="collapsed",
        key="style_radio",
    )
    st.session_state.active_style = style_choice

    meta = STYLE_META[style_choice]
    st.markdown(
        f'<p style="font-size:0.78rem;color:#6b7585;margin-top:2px;">{meta["description"]}</p>',
        unsafe_allow_html=True,
    )

    st.divider()

    # Generate all styles toggle
    generate_all = st.checkbox("Generate all 3 styles at once", value=False, key="gen_all")


# ── Main content ──────────────────────────────────────────────────────────────

# App title
st.markdown(
    '<h1 style="font-family:\'Barlow Condensed\',sans-serif;font-size:3rem;'
    'font-weight:800;letter-spacing:0.03em;margin-bottom:0;">GAME RECAP GENERATOR</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#6b7585;font-size:0.9rem;margin-top:0;margin-bottom:24px;">'
    'Select a league → load games → pick a game → generate a narrative recap with Claude</p>',
    unsafe_allow_html=True,
)

# Error banner
if st.session_state.error:
    st.error(f"⚠️ {st.session_state.error}")

# ── Recap result renderer ─────────────────────────────────────────────────────

def _render_recap_result(result, style: str):
    """Render a single RecapResult with the text box and stat bar."""
    # Open the styled wrapper, render markdown content separately (so Streamlit
    # processes ## headers, **bold**, etc.), then close the wrapper.
    st.markdown('<div class="recap-box">', unsafe_allow_html=True)
    st.markdown(result.text)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="stat-bar">'
        f'<div>Tokens in: <span>{result.input_tokens}</span></div>'
        f'<div>Tokens out: <span>{result.output_tokens}</span></div>'
        f'<div>Latency: <span>{result.latency_ms}ms</span></div>'
        f'<div>Model: <span>claude-sonnet-4-6</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.download_button(
        label     = "⬇ Download recap (.txt)",
        data      = result.text,
        file_name = f"recap_{style}_{int(time.time())}.txt",
        mime      = "text/plain",
        key       = f"dl_{style}_{result.latency_ms}",
    )


# ── Two-column layout: game list (left) | recap (right) ──────────────────────
col_games, col_recap = st.columns([1, 1.6], gap="large")

# ── Left: game list ───────────────────────────────────────────────────────────
with col_games:
    st.markdown('<div class="section-label">Recent Games</div>', unsafe_allow_html=True)

    games = st.session_state.games

    if not games:
        st.markdown(
            '<div style="color:#6b7585;font-size:0.9rem;padding:20px 0;">'
            '← Select a league and click <strong>Load Recent Games</strong> to begin.</div>',
            unsafe_allow_html=True,
        )
    else:
        for game in games:
            gid       = game["game_id"]
            is_sel    = st.session_state.selected_game == gid
            card_cls  = "game-card selected" if is_sel else "game-card"

            # Render card as HTML (display only) + Streamlit button for click
            st.markdown(f"""
            <div class="{card_cls}">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <div class="teams">{game['away_team']}</div>
                <div class="score">{game['away_score']}</div>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <div class="teams">{game['home_team']}</div>
                <div class="score">{game['home_score']}</div>
              </div>
              <div class="meta">
                {status_badge(game['status'])} &nbsp;·&nbsp; {game['date'][:10]}
                &nbsp;·&nbsp; {game.get('venue','—')}
              </div>
            </div>
            """, unsafe_allow_html=True)

            btn_label = "✓ Selected" if is_sel else "Select"
            if st.button(btn_label, key=f"sel_{gid}", use_container_width=True):
                if st.session_state.selected_game != gid:
                    st.session_state.selected_game = gid
                    st.session_state.recap          = None
                    st.session_state.results        = {}
                    # Fetch and parse immediately on selection
                    with st.spinner("Fetching game data..."):
                        try:
                            fetcher = get_fetcher(selected_league)
                            raw     = fetcher.get_game_summary(gid)
                            st.session_state.recap = ESPNParser(selected_league).parse(raw)
                            st.session_state.error = None
                        except Exception as e:
                            st.session_state.error = str(e)
                    st.rerun()


# ── Right: recap panel ────────────────────────────────────────────────────────
with col_recap:

    recap: Optional[GameRecap] = st.session_state.recap

    if recap is None:
        st.markdown(
            '<div style="color:#6b7585;font-size:0.9rem;padding:20px 0;">'
            '← Select a game from the list to load its data, then generate a recap.</div>',
            unsafe_allow_html=True,
        )
    else:
        # Game headline
        winner = recap.winner()
        loser  = recap.loser()
        ot_tag = " (OT)" if recap.went_to_ot else ""
        close_tag = " · 🔥 Close game" if recap.was_close else ""

        st.markdown(
            f'<div class="game-headline">{winner.name} def. {loser.name}{ot_tag}</div>'
            f'<div class="game-subline">'
            f'{recap.sport} · {recap.date} · {recap.venue}{close_tag}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Quick stat leaders (collapsible)
        with st.expander("📋 Stat leaders & key moments", expanded=False):
            if recap.stat_leaders:
                st.markdown("**Top Performers**")
                for line in recap.stat_leaders:
                    st.markdown(f"- {line}")
            if recap.key_moments:
                st.markdown("**Key Moments**")
                for m in recap.key_moments:
                    st.markdown(f"- {m}")

        st.divider()

        # Style tabs or single generate
        active_style = st.session_state.active_style
        results      = st.session_state.results
        gen_all      = st.session_state.get("gen_all", False)

        # Generate button
        api_key = get_api_key()
        if not api_key:
            st.warning("⚠️ Enter your Anthropic API key in the sidebar to generate recaps.")
        else:
            styles_to_gen = list(STYLE_META.keys()) if gen_all else [active_style]
            btn_label     = "Generate All 3 Styles" if gen_all else f"Generate {STYLE_META[active_style]['icon']} {STYLE_META[active_style]['label']} Recap"

            if st.button(btn_label, key="generate_btn"):
                gen = RecapGenerator(api_key=api_key)

                if gen_all:
                    # Progress bar across all 3 styles
                    progress = st.progress(0, text="Generating recaps…")
                    for i, style in enumerate(styles_to_gen):
                        progress.progress((i) / len(styles_to_gen), text=f"Generating {STYLE_META[style]['label']}…")
                        try:
                            result = gen.generate(recap, style=style)
                            st.session_state.results[style] = result
                        except Exception as e:
                            st.session_state.error = str(e)
                            break
                    progress.progress(1.0, text="Done!")
                    time.sleep(0.4)
                    progress.empty()
                else:
                    with st.spinner(f"Claude is writing the {STYLE_META[active_style]['label']} recap…"):
                        try:
                            result = gen.generate(recap, style=active_style)
                            st.session_state.results[active_style] = result
                            st.session_state.error = None
                        except Exception as e:
                            st.session_state.error = str(e)
                st.rerun()

        # ── Display results ───────────────────────────────────────────────────
        if results:
            st.markdown("")  # spacer

            if gen_all and len(results) > 1:
                # Tabs for all styles
                tab_labels = [
                    f"{STYLE_META[s]['icon']} {STYLE_META[s]['label']}"
                    for s in STYLE_META if s in results
                ]
                tabs = st.tabs(tab_labels)
                for tab, style in zip(tabs, [s for s in STYLE_META if s in results]):
                    with tab:
                        _render_recap_result(results[style], style)
            else:
                # Single style view — show whichever styles have been generated
                for style in STYLE_META:
                    if style in results:
                        _meta  = STYLE_META[style]
                        st.markdown(
                            f'<span class="style-pill {_meta["pill_class"]}">'
                            f'{_meta["icon"]} {_meta["label"]}</span>',
                            unsafe_allow_html=True,
                        )
                        _render_recap_result(results[style], style)
                        st.markdown("")


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    '<p style="text-align:center;color:#3a4455;font-size:0.78rem;">'
    'Data: ESPN public API &nbsp;·&nbsp; Generation: Anthropic Claude &nbsp;·&nbsp; '
    'Built with Streamlit &nbsp;·&nbsp; Portfolio project</p>',
    unsafe_allow_html=True,
)
