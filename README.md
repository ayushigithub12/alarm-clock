# ⏰ alarm — Python CLI Alarm Clock

A lightweight, persistent alarm clock that runs entirely in your terminal.

```
$ python alarm.py add 07:30 --label "Wake up"
✓ Alarm #1 set — Wake up at 07:30  (fires in 6h 45m)

$ python alarm.py list
╭──────┬──────────────┬─────────┬─────────────────────┬──────────────────────┬───────────╮
│ ID   │ Label        │ Time    │ Repeat              │ Next fire            │ Status    │
├──────┼──────────────┼─────────┼─────────────────────┼──────────────────────┼───────────┤
│ 1    │ Wake up      │ 07:30   │ once                │ 2026-06-24 07:30     │ on        │
│      │              │         │                     │ in 6h 45m            │           │
╰──────┴──────────────┴─────────┴─────────────────────┴──────────────────────┴───────────╯

$ python alarm.py watch
⏰  Watch mode started — Ctrl+C to exit

  🕐  07:29:45  Wed 24 Jun 2026

  ⏰  [1] Wake up  07:30  → 15s

============================================================
  🔔  ALARM RINGING!  🔔
  [1] Wake up  --  07:30
============================================================
```

---

## Engineering Process (AI-directed)

> This section documents the design and implementation decisions made **before** writing code — the thinking the task asked for.

### Step 1 — Requirement Scoping (with AI)

The brief said "alarm clock CLI" with no further spec. Before coding, I used AI to turn that open brief into a bounded set of decisions.

**Questions I asked:**
- What's the minimum viable alarm clock?
- Should alarms persist across terminal sessions? Yes — an alarm that vanishes when you close the shell is useless.
- Should `watch` mode be blocking or background? Blocking is simpler and testable. → **watch mode, blocking**.
- What's the right time format? 24h is unambiguous, but 12h is common. → Support both.
- Snooze — worth including? Yes, it's the defining real-world alarm feature. Without it the tool feels incomplete.

**Decided scope (MVP):**

| Feature | Decision |
|---|---|
| Persistence | JSON file at `~/.alarm_clock_data.json` |
| Commands | `add`, `list`, `delete`, `toggle`, `snooze`, `watch` |
| Time input | HH:MM (24h) **and** H:MMam/pm |
| Repeat | Optional `--repeat Mon Wed Fri` flag |
| Sound | Terminal bell (`\a`) — no external audio dependency |
| UI | `rich` for coloured, tabular output |

**Deliberately excluded:** GUI, database, audio files, background daemon, timezone support. Each excluded for a clear reason — complexity vs. value given the time constraint.

---

### Step 2 — Design Decisions

**Why JSON over SQLite?**
An alarm clock stores ~5–20 records. SQLite adds a dependency and migration surface for no benefit. JSON is human-readable, trivially debuggable, and `json.load` / `json.dump` are stdlib.

**Why `rich` and not plain `print`?**
The output IS the UI. `rich` gives tables, colour, and formatted output. It's the only third-party library used.

**Why `dataclass` over dict?**
Alarms have a stable schema. Dataclasses give type hints, `asdict()` for free serialisation, and make it impossible to silently misname a field.

**The `_next_fire()` function — the core logic:**
An alarm has three states:
1. Snoozed → fire at `snooze_until`
2. One-shot → fire today if not yet passed, else tomorrow
3. Recurring → find the nearest matching weekday ≥ now

A 1-minute grace window ensures alarms set for "this minute" still fire rather than being pushed to tomorrow.

**`watch` mode — threading design:**
- Main thread: renders a live clock every second (display only)
- Daemon thread: polls every 5 seconds, fires when `0 ≤ (now - next_fire) < 90s`
- A `ringing` event flag pauses the display while the alarm rings so they don't conflict

The 5-second poll is a deliberate tradeoff: precise enough (alarms fire within ±5s), not burning CPU in a tight loop.

---

### Step 3 — What I'd add with more time

- **Background daemon** with `launchd`/`systemd` so alarms fire without an open terminal
- **`edit` command** to change an alarm's time without delete + re-add
- **Timezone support** (`--tz America/New_York`)
- **`next` command** — prints just the next alarm firing, useful for scripting

---

## Installation

```bash
pip install -r requirements.txt
```

Python 3.10+ required.

---

## Usage

```bash
# Add a one-shot alarm
python alarm.py add 07:30
python alarm.py add 07:30 --label "Wake up"

# Add a recurring alarm
python alarm.py add 09:00 --label "Standup" --repeat Mon Tue Wed Thu Fri

# 12-hour format works too
python alarm.py add 9:00am --label "Morning coffee"
python alarm.py add 6:30pm --label "Evening walk"

# List all alarms (shows next fire time + ETA)
python alarm.py list

# Toggle on/off without deleting
python alarm.py toggle 1

# Snooze (default 5 min)
python alarm.py snooze 1
python alarm.py snooze 1 --minutes 10

# Delete
python alarm.py delete 2

# Live countdown — rings when alarm fires
python alarm.py watch
```

---

## File structure

```
alarm-clock/
├── alarm.py          # entire application, single file
├── requirements.txt
└── README.md
```

Data is stored at `~/.alarm_clock_data.json` (auto-created, git-ignored).

---

## Design philosophy

> Do one thing well. An alarm clock should set alarms reliably, show you what's coming, and ring on time. Everything else is scope creep.

Single-file structure is intentional: this is a CLI tool, not a framework. Entry point, data model, business logic, and commands all fit in one readable file.
