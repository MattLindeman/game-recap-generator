# 🏟️ Game Recap Generator

A full-stack sports writing tool that fetches live and recent game data from the ESPN API and uses **Claude (Anthropic)** to generate narrative recaps in three distinct editorial voices — all inside a Streamlit UI.

Built as a portfolio project demonstrating API integration, data parsing, LLM prompt engineering, and interactive app design.

---

## Demo

![App screenshot placeholder — replace with a screen recording or screenshot]

**Three recap styles, one game:**

> **Beat Reporter** — *"The Oklahoma City Thunder dispatched the Memphis Grizzlies 118–99 on Tuesday, a wire-to-wire statement performance anchored by Shai Gilgeous-Alexander's 34-point, 8-assist masterclass..."*

> **Analytics** — *"Oklahoma City's +19 margin understates their dominance. A 48.6% effective field goal rate against a Memphis defence that held opponents to 44.1% on the season signals the Thunder have turned a corner offensively..."*

> **Fan Friendly** — *"The Thunder didn't just win — they sent a message 🔥 SGA was absolutely COOKING from the jump and Memphis had no answer all night..."*

---

## Features

- **Live scoreboard** — fetch recent or in-progress games across NBA, NFL, MLB, and NHL
- **Clean data parsing** — typed `GameRecap` dataclass extracts only what matters from ESPN's large nested payloads
- **Three prompt-engineered styles** — beat reporter, analytics-focused, fan-friendly
- **Extensible style system** — register custom styles at runtime with `add_custom_style()`
- **Token + latency telemetry** — every recap shows input tokens, output tokens, and API latency
- **Download** — export any recap as a `.txt` file
- **Generate all 3** — parallel-style progress bar generates all styles in one click

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    app.py (Streamlit)                │
│  Sidebar: league picker, API key, style selector     │
│  Main: game cards → stat preview → recap output      │
└──────────────┬──────────────────────────────────────┘
               │ calls
┌──────────────▼──────────────────────────────────────┐
│              recap_generator.py                      │
│  RecapGenerator — prompt construction, API call,     │
│  RecapResult dataclass (text, tokens, latency)       │
└──────────────┬──────────────────────────────────────┘
               │ uses
┌──────────────▼──────────────────────────────────────┐
│              espn_parser.py                          │
│  ESPNParser — sport-specific parsing logic           │
│  GameRecap, TeamSummary, PlayerLine dataclasses      │
│  to_prompt_dict() → lean ~600-token LLM payload      │
└──────────────┬──────────────────────────────────────┘
               │ uses
┌──────────────▼──────────────────────────────────────┐
│              espn_fetcher.py                         │
│  ESPNFetcher — scoreboard + game summary endpoints   │
│  save_raw() / load_raw() for offline development     │
└──────────────┬──────────────────────────────────────┘
               │ HTTP
      ESPN public API (no auth required)
```

### Key design decisions

| Decision | Rationale |
|---|---|
| `GameRecap` dataclass as the layer boundary | Parser and generator are fully decoupled — swap out ESPN for another data source without touching the LLM layer |
| `to_prompt_dict()` instead of raw JSON | Controls exactly what the model sees; prevents ESPN's ~2000-line payload from bloating the context window |
| `(system, user_template)` prompt pairs | System prompt handles persona/constraints; user template handles data injection. Separating them reduces prompt variance |
| Streamlit session state as data cache | Parsed recaps and generated text persist across re-renders — switching styles never re-fetches |
| `save_raw()` / `load_raw()` in fetcher | Offline development workflow: save one real response, iterate on parser/prompts without hitting the API |

---

## Project Structure

```
game-recap-generator/
│
├── app.py                  # Streamlit UI (Step 4)
├── recap_generator.py      # LLM layer — Anthropic API (Step 3)
├── espn_parser.py          # Data parsing — GameRecap dataclasses (Step 2)
├── espn_fetcher.py         # ESPN API client (Step 1)
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/game-recap-generator.git
cd game-recap-generator

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and add your Anthropic API key
```

Or export it directly:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

### 3. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## CLI Usage

Each module is independently runnable — useful for development and debugging.

```bash
# Step 1 — browse recent games and get a game ID
python espn_fetcher.py --sport nba
python espn_fetcher.py --sport nba --game_id 401671793 --save raw_game.json

# Step 2 — parse a saved game file and inspect the output
python espn_parser.py raw_game.json --sport nba
python espn_parser.py raw_game.json --sport nba --prompt_dict   # show LLM input

# Step 3 — generate a recap from the CLI
python recap_generator.py --file raw_game.json --sport nba --style beat_reporter
python recap_generator.py --file raw_game.json --sport nba --all_styles --save recaps.json
```

---

## Extending

### Add a custom recap style

```python
from recap_generator import RecapGenerator

gen = RecapGenerator()
gen.add_custom_style(
    name="radio",
    system="You are a radio play-by-play announcer filing a post-game report. "
           "Write in a punchy, spoken-word style designed to be read aloud.",
    user_template="Here is the game data:\n{game_json}\n\n"
                  "Write a 3-paragraph radio-style recap."
)
result = gen.generate(recap, style="radio")
```

### Add a new sport

1. Add the sport/league pair to `SUPPORTED_LEAGUES` in `espn_fetcher.py`
2. Add a `_parse_<sport>()` method and team builder to `ESPNParser` in `espn_parser.py`
3. Add a close-game threshold to `CLOSE_THRESHOLDS`
4. Add the league to `LEAGUES` in `app.py`

### Parallelise multi-style generation

The `generate_all_styles()` method makes sequential API calls. For a production deployment, replace it with the async pattern sketched in `recap_generator.py`:

```python
import asyncio
from anthropic import AsyncAnthropic

async def generate_all_async(recap, api_key):
    client = AsyncAnthropic(api_key=api_key)
    tasks  = {style: _generate_one_async(client, recap, style) for style in STYLE_PROMPTS}
    return {style: await task for style, task in tasks.items()}
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com) |

---

## Dependencies

| Package | Purpose |
|---|---|
| `anthropic` | Claude API client |
| `streamlit` | Web UI framework |
| `requests` | ESPN API HTTP calls |

See `requirements.txt` for pinned versions.

---

## Notes on the ESPN API

ESPN does not publish an official public API. This project uses the same undocumented endpoints that power ESPN's own web and mobile apps. They require no authentication and have been stable for several years, but:

- Field names occasionally differ between sports (e.g. `score` vs `points`)
- Schema changes happen without notice — the `print_summary_structure()` helper in `espn_fetcher.py` is useful for debugging
- Be respectful with request frequency — `~1 req/sec` is a safe ceiling when looping

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

## Author

Built by [Your Name](https://github.com/YOUR_USERNAME) · [LinkedIn](https://linkedin.com/in/YOUR_PROFILE)

*Statistics / Data Science background · Sports analytics · Python*
