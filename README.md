# ⏰ alarm — Python CLI Alarm Clock

A lightweight, persistent alarm clock that runs entirely in your terminal.

```
$ python3 alarm.py add 07:30 --label "Wake up"
✓ Alarm #1 set — Wake up at 07:30  (fires in 6h 45m)

$ python3 alarm.py list
╭──────┬──────────────┬─────────┬─────────────────┬────────────────────────╮
│ ID   │ Label        │ Time    │ Repeat          │ Next fire              │
├──────┼──────────────┼─────────┼─────────────────┼────────────────────────┤
│ 1    │ Wake up      │ 07:30   │ once            │ 2026-06-24 07:30       │
│      │              │         │                 │ in 6h 45m              │
╰──────┴──────────────┴─────────┴─────────────────┴────────────────────────╯
```

---

## Engineering Process (AI-directed)

> This section documents the design and implementation decisions made **before** writing code — the thinking the task asked for.

### Step 1 — Requirement Scoping (with AI)

The brief said "alarm clock CLI" with no further spec. Before coding, I used AI to turn that open brief into a bounded set of decisions:

**Questions I asked:**
- What's the minimum viable alarm clock? (set time, list, ring)
- Should alarms persist across terminal sessions? Yes — an alarm that vanishes when you close the shell is useless.
- Should `watch` mode be blocking or should alarms ring in the background? Blocking watch is simpler and testable; background daemon adds OS complexity. → **watch mode, blocking**.
- What's the right time format? 24h is unambiguous. But 12h is common. → Support both.
- Snooze — worth including? Yes, it's the defining real-world alarm feature. Without it the tool feels incomplete.

**Decided scope (MVP):**
| Feature | Decision |
|---|---|
| Persistence | JSON file in `~/.alarm_clock_data.json` |
| Commands | `add`, `list`, `delete`, `toggle`, `snooze`, `watch` |
| Time input | HH:MM (24h) **and** H:MMam/pm |
| Repeat | Optional `--repeat Mon Wed Fri` flag |
| Sound | Terminal bell (`\a`) — no external audio dependency |
| UI | `rich` for coloured, tabular output |

**Deliberately excluded:** GUI, database, audio files, daemon/background process, timezone support. Each was excluded for a clear reason: complexity vs. value given the 30-minute constraint.

---

### Step 2 — Design Decisions

**Why JSON over SQLite?**
An alarm clock stores ~5–20 records. SQLite adds a dependency and migration surface for no benefit. JSON is human-readable, trivially debuggable, and `json.load` / `json.dump` are stdlib.

**Why `rich` and not plain `print`?**
The output IS the UI. `rich` gives tables, colour, and live refresh with zero non-stdlib deps. It's the only third-party library used.

**Why `dataclass` over dict?**
Alarms have a stable schema. Dataclasses give type hints, `asdict()` for free serialisation, and make it impossible to silently misname a field.

**The `_next_fire()` function — the core logic:**
This is where I spent the most design thought. An alarm has three states:
1. Snoozed → fire at `snooze_until`
2. One-shot → fire today if not yet passed, else tomorrow
3. Recurring → find the nearest matching weekday ≥ now

Getting this right means the `list` command shows accurate countdowns and `watch` rings at the right moment. I validated this logic manually by setting alarms in the past and future and checking what `list` reported.

**`watch` mode — threading design:**
- Main thread: `rich.Live` loop, re-renders every second (display only)
- Daemon thread: checks alarms every 15 seconds, rings when `|now - next_fire| < 30s`

The 15-second poll is a deliberate tradeoff: precise enough for a clock (alarms fire within ±15s of the set time), but not burning CPU with a tight loop.

---

### Step 3 — What I'd add with more time

- **Background daemon** with `launchd`/`systemd` so alarms fire without an open terminal
- **Named alarm profiles** (morning routine, work schedule)
- **`edit` command** to change an alarm's time without delete + re-add
- **`next` command** — just prints the next alarm firing, for scripting
- **Timezone flag** (`--tz America/New_York`)

---

## Installation

```bash
pip install rich
```

No other dependencies. Python 3.10+ required.

---

## Usage

```bash
# Add a one-shot alarm
python3 alarm.py add 07:30
python3 alarm.py add 07:30 --label "Wake up"

# Add a recurring alarm
python3 alarm.py add 09:00 --label "Standup" --repeat Mon Tue Wed Thu Fri

# 12-hour format works too
python3 alarm.py add 9:00am --label "Morning coffee"
python3 alarm.py add 6:30pm --label "Evening walk"

# List all alarms (shows next fire time + ETA)
python3 alarm.py list

# Toggle on/off without deleting
python3 alarm.py toggle 1

# Snooze (default 5 min)
python3 alarm.py snooze 1
python3 alarm.py snooze 1 --minutes 10

# Delete
python3 alarm.py delete 2

# Live countdown — rings when alarm fires
python3 alarm.py watch
```

### Watch mode

`watch` shows a live clock and countdown to the next alarm. When an alarm fires, it plays a terminal bell (`\a`) and prints a visual alert. Press `Ctrl+C` to exit.

---

## File structure

```
alarm-clock/
├── alarm.py       # entire application, single file
└── README.md
```

Data is stored at `~/.alarm_clock_data.json` (auto-created).

---

## Design philosophy

> Do one thing well. An alarm clock should set alarms reliably, show you what's coming, and ring on time. Everything else is scope creep.

The single-file structure is intentional: this is a CLI tool, not a framework. The entry point, data model, business logic, and commands all fit in one readable file with no internal module boundaries to navigate.