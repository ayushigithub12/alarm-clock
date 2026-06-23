#!/usr/bin/env python3
"""
alarm.py - A Python CLI Alarm Clock
Author: Ayushi Sharma
"""

import time
import sys
import argparse
import threading
import json
import os
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich import box

console = Console()
ALARMS_FILE = os.path.expanduser("~/.alarm_clock_data.json")


@dataclass
class Alarm:
    id: int
    label: str
    time_str: str        # "HH:MM" 24h format
    repeat: list = field(default_factory=list)  # [] = once, ["Mon","Tue",...] = recurring
    enabled: bool = True
    snooze_until: Optional[str] = None  # ISO datetime string when snoozed


class AlarmClock:
    def __init__(self):
        self.alarms: list[Alarm] = []
        self._next_id = 1
        self._ring_event = threading.Event()
        self._ringing_alarm: Optional[Alarm] = None
        self.load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def load(self):
        if os.path.exists(ALARMS_FILE):
            try:
                with open(ALARMS_FILE) as f:
                    data = json.load(f)
                self.alarms = [Alarm(**a) for a in data.get("alarms", [])]
                self._next_id = data.get("next_id", 1)
            except Exception:
                self.alarms = []

    def save(self):
        with open(ALARMS_FILE, "w") as f:
            json.dump({
                "alarms": [asdict(a) for a in self.alarms],
                "next_id": self._next_id
            }, f, indent=2)

    # ── Core logic ────────────────────────────────────────────────────────────

    def _parse_time(self, time_str: str) -> tuple[int, int]:
        """Accept HH:MM (24h) or H:MMam/pm."""
        time_str = time_str.strip()
        try:
            if "am" in time_str.lower() or "pm" in time_str.lower():
                dt = datetime.strptime(time_str.upper(), "%I:%M%p")
            else:
                dt = datetime.strptime(time_str, "%H:%M")
            return dt.hour, dt.minute
        except ValueError:
            raise ValueError(f"Cannot parse time '{time_str}'. Use HH:MM (24h) or H:MMam/H:MMpm")

    def _next_fire(self, alarm: Alarm) -> Optional[datetime]:
        """Calculate the next datetime this alarm should fire."""
        if not alarm.enabled:
            return None

        now = datetime.now().replace(second=0, microsecond=0)

        # Snoozed?
        if alarm.snooze_until:
            snooze_dt = datetime.fromisoformat(alarm.snooze_until)
            if snooze_dt > now:
                return snooze_dt

        h, m = self._parse_time(alarm.time_str)

        if not alarm.repeat:
            # One-shot: fire today if not yet passed, else tomorrow
            candidate = now.replace(hour=h, minute=m)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

        # Recurring: find the nearest matching weekday
        day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        target_days = sorted(day_map[d] for d in alarm.repeat)
        for offset in range(8):
            candidate = now + timedelta(days=offset)
            candidate = candidate.replace(hour=h, minute=m)
            if candidate <= now:
                continue
            if candidate.weekday() in target_days:
                return candidate
        return None

    def _seconds_until(self, alarm: Alarm) -> Optional[float]:
        nf = self._next_fire(alarm)
        if nf is None:
            return None
        return (nf - datetime.now()).total_seconds()

    # ── Commands ──────────────────────────────────────────────────────────────

    def add(self, time_str: str, label: str = "Alarm", repeat: list = None):
        h, m = self._parse_time(time_str)   # validates
        normalized = f"{h:02d}:{m:02d}"
        alarm = Alarm(
            id=self._next_id,
            label=label,
            time_str=normalized,
            repeat=repeat or []
        )
        self.alarms.append(alarm)
        self._next_id += 1
        self.save()
        nf = self._next_fire(alarm)
        eta = self._fmt_eta(self._seconds_until(alarm))
        console.print(f"[green]✓ Alarm #{alarm.id} set[/green] — [bold]{alarm.label}[/bold] at [cyan]{normalized}[/cyan]  (fires in {eta})")

    def list_alarms(self):
        if not self.alarms:
            console.print("[dim]No alarms set. Use [bold]alarm add HH:MM[/bold] to add one.[/dim]")
            return

        table = Table(box=box.ROUNDED, header_style="bold cyan", show_lines=True)
        table.add_column("ID", style="dim", width=4)
        table.add_column("Label", min_width=14)
        table.add_column("Time", width=7)
        table.add_column("Repeat", width=22)
        table.add_column("Next fire", width=20)
        table.add_column("Status", width=9)

        for a in self.alarms:
            repeat_str = ", ".join(a.repeat) if a.repeat else "once"
            nf = self._next_fire(a)
            nf_str = nf.strftime("%Y-%m-%d %H:%M") if nf else "—"
            eta_str = self._fmt_eta(self._seconds_until(a)) if nf else "—"
            status = "[green]on[/green]" if a.enabled else "[red]off[/red]"
            table.add_row(str(a.id), a.label, a.time_str, repeat_str,
                          f"{nf_str}\n[dim]in {eta_str}[/dim]", status)

        console.print(table)

    def delete(self, alarm_id: int):
        alarm = self._get(alarm_id)
        self.alarms.remove(alarm)
        self.save()
        console.print(f"[red]✗ Alarm #{alarm_id} deleted.[/red]")

    def toggle(self, alarm_id: int):
        alarm = self._get(alarm_id)
        alarm.enabled = not alarm.enabled
        self.save()
        state = "enabled" if alarm.enabled else "disabled"
        console.print(f"Alarm #{alarm_id} [bold]{state}[/bold].")

    def snooze(self, alarm_id: int, minutes: int = 5):
        alarm = self._get(alarm_id)
        snooze_until = datetime.now() + timedelta(minutes=minutes)
        alarm.snooze_until = snooze_until.isoformat()
        self.save()
        console.print(f"[yellow]💤 Alarm #{alarm_id} snoozed for {minutes} min — rings at {snooze_until.strftime('%H:%M')}[/yellow]")

    # ── Watch mode (live countdown) ───────────────────────────────────────────

    def watch(self):
        """Live countdown + ring when alarm fires."""
        console.print(Panel("[bold cyan]Alarm Clock — Watch Mode[/bold cyan]\nPress [bold]Ctrl+C[/bold] to exit.", expand=False))

        def render():
            now = datetime.now()
            text = Text()
            text.append(f"  🕐  {now.strftime('%H:%M:%S')}  ", style="bold white")
            text.append(f"{now.strftime('%a %d %b %Y')}\n\n", style="dim")

            active = [a for a in self.alarms if a.enabled]
            if not active:
                text.append("  No active alarms.\n", style="dim")
            for a in active:
                secs = self._seconds_until(a)
                eta = self._fmt_eta(secs) if secs is not None else "—"
                text.append(f"  ⏰  [{a.id}] {a.label}  ", style="cyan")
                text.append(f"{a.time_str}  ", style="bold")
                text.append(f"→ {eta}\n", style="dim")
            return Panel(text, title="[bold]alarm[/bold]", border_style="cyan")

        def check_ring():
            while True:
                now = datetime.now().replace(second=0, microsecond=0)
                for a in self.alarms:
                    if not a.enabled:
                        continue
                    nf = self._next_fire(a)
                    if nf and abs((nf - now).total_seconds()) < 30:
                        # Check we haven't already rung this minute
                        self._ring_alarm(a)
                        # For one-shot alarms, disable after firing
                        if not a.repeat and not a.snooze_until:
                            a.enabled = False
                            self.save()
                time.sleep(15)

        ring_thread = threading.Thread(target=check_ring, daemon=True)
        ring_thread.start()

        try:
            with Live(render(), refresh_per_second=1, screen=False) as live:
                while True:
                    live.update(render())
                    time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[dim]Exited watch mode.[/dim]")

    def _ring_alarm(self, alarm: Alarm):
        """Ring the alarm — terminal bell + visual alert."""
        # Clear snooze
        alarm.snooze_until = None
        self.save()

        # Visual alert
        for _ in range(3):
            console.print(f"\a[bold red blink]🔔  ALARM! [{alarm.id}] {alarm.label}  —  {alarm.time_str}  🔔[/bold red blink]")
            sys.stdout.write("\a")   # terminal bell
            sys.stdout.flush()
            time.sleep(0.6)

        console.print("[dim]Press Enter to dismiss, or run: alarm snooze <id>[/dim]")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get(self, alarm_id: int) -> Alarm:
        for a in self.alarms:
            if a.id == alarm_id:
                return a
        raise ValueError(f"Alarm #{alarm_id} not found.")

    @staticmethod
    def _fmt_eta(seconds: Optional[float]) -> str:
        if seconds is None:
            return "—"
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    clock = AlarmClock()

    parser = argparse.ArgumentParser(
        prog="alarm",
        description="🕐  Python CLI Alarm Clock",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  alarm add 07:30                          # one-shot alarm at 07:30
  alarm add 07:30 --label "Wake up"        # with a label
  alarm add 07:30 --repeat Mon Wed Fri     # every Mon/Wed/Fri
  alarm add 9:00am --label "Standup"       # 12h format
  alarm list                               # show all alarms
  alarm delete 2                           # delete alarm #2
  alarm toggle 1                           # enable / disable alarm #1
  alarm snooze 1                           # snooze alarm #1 for 5 min
  alarm snooze 1 --minutes 10              # snooze for 10 min
  alarm watch                              # live countdown + auto-ring
        """
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Add a new alarm")
    p_add.add_argument("time", help="Alarm time: HH:MM (24h) or H:MMam/H:MMpm")
    p_add.add_argument("--label", "-l", default="Alarm", help="Name for this alarm")
    p_add.add_argument("--repeat", "-r", nargs="+",
                       choices=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
                       help="Repeat on these days")

    # list
    sub.add_parser("list", help="List all alarms")

    # delete
    p_del = sub.add_parser("delete", help="Delete an alarm by ID")
    p_del.add_argument("id", type=int)

    # toggle
    p_tog = sub.add_parser("toggle", help="Enable / disable an alarm")
    p_tog.add_argument("id", type=int)

    # snooze
    p_snz = sub.add_parser("snooze", help="Snooze an alarm")
    p_snz.add_argument("id", type=int)
    p_snz.add_argument("--minutes", "-m", type=int, default=5)

    # watch
    sub.add_parser("watch", help="Live countdown — rings when alarm fires")

    args = parser.parse_args()

    try:
        if args.command == "add":
            clock.add(args.time, label=args.label, repeat=args.repeat)
        elif args.command == "list":
            clock.list_alarms()
        elif args.command == "delete":
            clock.delete(args.id)
        elif args.command == "toggle":
            clock.toggle(args.id)
        elif args.command == "snooze":
            clock.snooze(args.id, args.minutes)
        elif args.command == "watch":
            clock.watch()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()