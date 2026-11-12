"""The hourly popup: walks through every unlogged hour of today and books it in Orbit."""

import os
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from . import orbit
from .core import (
    Entry,
    Task,
    WorkHours,
    entry_ending_at,
    load_skipped,
    load_work_hours,
    parse_entries,
    parse_tasks,
    pending_slots,
    recent_task_ids,
    save_skipped,
)

# TL_UURTJES_DRY_RUN=1 prints the writes instead of sending them to Orbit.
DRY_RUN = os.environ.get("TL_UURTJES_DRY_RUN") == "1"


def now() -> datetime:
    """The current time; TL_UURTJES_NOW="2026-11-12 13:05" fakes it for testing."""
    fake = os.environ.get("TL_UURTJES_NOW")
    return datetime.fromisoformat(fake) if fake else datetime.now()


def fetch_entries(date_from, date_to) -> list[Entry]:
    text = orbit.call("ListTimeEntries", {"dateFrom": f"{date_from:%Y-%m-%d}", "dateTo": f"{date_to:%Y-%m-%d}"})
    return parse_entries(text)


def book_hour(slot: datetime, task: Task, description: str, entries: list[Entry]) -> None:
    """Extends the previous entry when it's the same work, otherwise creates a new one."""
    prev = entry_ending_at(slot, entries)
    if prev and prev.task_id == task.id and not prev.locked and description in ("", prev.description):
        name, args = "UpdateTimeEntry", {"entryId": prev.id, "durationMinutes": prev.minutes + 60}
    else:
        name, args = "CreateTimeEntry", {"taskId": task.id, "date": f"{slot:%Y-%m-%d %H:%M}", "durationMinutes": 60}
        if description:
            args["description"] = description
    if DRY_RUN:
        print(f"[dry run] {name} {args}", flush=True)
        entries.append(Entry(f"DRY{slot:%H%M}", slot, 60, task.id, description, False))
        return
    orbit.call(name, args)


class Popup:
    def __init__(self, root: tk.Tk, tasks: list[Task], entries: list[Entry], hours: WorkHours):
        self.root = root
        self.entries = entries
        self.hours = hours
        self.skipped = load_skipped()
        self.slots = pending_slots(now(), entries, self.skipped, hours)
        self.done = 0

        recent = recent_task_ids(entries)
        rank = {tid: i for i, tid in enumerate(recent)}
        self.tasks = sorted(tasks, key=lambda t: rank.get(t.id, len(rank)))
        self.recent = set(recent[:5])
        self.visible: list[Task] = []

        self._build()
        self._show_slot()

    # --- layout -------------------------------------------------------------

    def _build(self) -> None:
        root = self.root
        root.title("Teamleader uurtjes")
        root.attributes("-type", "dialog")  # i3 floats dialogs
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("TkDefaultFont", 15, "bold"))
        style.configure("Sub.TLabel", foreground="#666")
        style.configure("Error.TLabel", foreground="#c0392b")
        style.configure("Accent.TButton", font=("TkDefaultFont", 10, "bold"))

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)

        self.title = ttk.Label(frame, style="Title.TLabel")
        self.title.pack(anchor="w")
        self.subtitle = ttk.Label(frame, style="Sub.TLabel")
        self.subtitle.pack(anchor="w", pady=(0, 10))

        ttk.Label(frame, text="Search task").pack(anchor="w")
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self._filter())
        self.search = ttk.Entry(frame, textvariable=self.query)
        self.search.pack(fill="x", pady=(2, 6))

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(
            list_frame, height=14, width=78, activestyle="none", exportselection=False,
            selectbackground="#2d6cdf", selectforeground="white", relief="flat", highlightthickness=1,
        )
        scroll = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda _: self._log())

        ttk.Label(frame, text="Description (optional)").pack(anchor="w", pady=(10, 0))
        self.description = tk.StringVar()
        self.desc_entry = ttk.Entry(frame, textvariable=self.description)
        self.desc_entry.pack(fill="x", pady=(2, 10))

        self.status = ttk.Label(frame, style="Error.TLabel", wraplength=560)
        self.status.pack(anchor="w")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        self.later_btn = ttk.Button(buttons, text="Later (Esc)", command=root.destroy)
        self.later_btn.pack(side="left")
        self.skip_btn = ttk.Button(buttons, text="Didn't work", command=self._skip)
        self.skip_btn.pack(side="left", padx=6)
        self.log_btn = ttk.Button(buttons, text="Log hour (Enter)", style="Accent.TButton", command=self._log)
        self.log_btn.pack(side="right")
        self.all_btn = ttk.Button(buttons, command=lambda: self._log(all_remaining=True))
        self.all_btn.pack(side="right", padx=6)

        for widget in (self.search, self.desc_entry, self.listbox):
            widget.bind("<Return>", lambda _: self._log())
            widget.bind("<Control-Return>", lambda _: self._log(all_remaining=True))
        for widget in (self.search, self.desc_entry):
            widget.bind("<Down>", lambda _: self._move(1))
            widget.bind("<Up>", lambda _: self._move(-1))
        root.bind("<Escape>", lambda _: root.destroy())

        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        root.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")

    # --- task list ----------------------------------------------------------

    def _filter(self, keep: str | None = None) -> None:
        keep = keep or (self.selected().id if self.selected() else None)
        words = self.query.get().lower().split()
        self.visible = [t for t in self.tasks if all(w in t.label.lower() for w in words)]
        self.listbox.delete(0, "end")
        for t in self.visible:
            mark = "★ " if t.id in self.recent else "   "
            self.listbox.insert("end", f"{mark}{t.label}    ({t.remaining} left)")
        ids = [t.id for t in self.visible]
        self._select(ids.index(keep) if keep in ids else 0)

    def _select(self, index: int) -> None:
        if not self.visible:
            return
        index = max(0, min(index, len(self.visible) - 1))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)

    def _move(self, delta: int) -> str:
        current = self.listbox.curselection()
        self._select((current[0] if current else 0) + delta)
        return "break"

    def selected(self) -> Task | None:
        current = self.listbox.curselection()
        return self.visible[current[0]] if current and current[0] < len(self.visible) else None

    # --- flow ---------------------------------------------------------------

    def _show_slot(self) -> None:
        if not self.slots:
            # New hours may have ended while this window was open.
            self.slots = pending_slots(now(), self.entries, self.skipped, self.hours)
            if not self.slots:
                self.root.destroy()
                return
        slot = self.slots[0]
        total = self.done + len(self.slots)
        self.title.configure(text=f"What did you work on {slot:%H:%M} – {slot + timedelta(hours=1):%H:%M}?")
        self.subtitle.configure(
            text=f"{slot:%A %d %B}  ·  hour {self.done + 1} of {total}" + ("  ·  DRY RUN" if DRY_RUN else "")
        )
        remaining = len(self.slots)
        self.all_btn.configure(text=f"Log all {remaining} remaining (Ctrl+Enter)")
        self.all_btn.state(["!disabled"] if remaining > 1 else ["disabled"])

        prev = entry_ending_at(slot, self.entries)
        self.query.set("")
        self._filter(keep=prev.task_id if prev else None)
        self.description.set(prev.description if prev else "")
        self.status.configure(text="")
        self.root.deiconify()
        self.root.lift()
        self.search.focus_force()

    def _busy(self, busy: bool, message: str = "") -> None:
        for b in (self.log_btn, self.all_btn, self.skip_btn, self.later_btn):
            b.state(["disabled"] if busy else ["!disabled"])
        if not busy and len(self.slots) <= 1:
            self.all_btn.state(["disabled"])
        self.status.configure(text=message, style="Sub.TLabel" if busy else "Error.TLabel")

    def _skip(self) -> None:
        self.skipped.add(self.slots.pop(0))
        save_skipped(self.skipped)
        self.done += 1
        self._show_slot()

    def _log(self, all_remaining: bool = False) -> None:
        task = self.selected()
        if task is None or "disabled" in self.log_btn.state():
            return
        slots = list(self.slots) if all_remaining else [self.slots[0]]
        description = self.description.get().strip()
        today = slots[0].date()
        self._busy(True, f"Saving {len(slots)} hour(s) on {task.name}…")

        booked: list[datetime] = []

        def work():
            for slot in slots:
                book_hour(slot, task, description, self.entries)
                if not DRY_RUN:
                    fresh = fetch_entries(today, today)
                    self.entries[:] = [e for e in self.entries if e.start.date() != today] + fresh
                booked.append(slot)

        self._in_background(work, booked)

    def _in_background(self, fn, booked: list[datetime]) -> None:
        """Runs the Orbit writes off the UI thread; Tk is only touched from poll()."""
        errors: list[Exception] = []

        def target():
            try:
                fn()
            except Exception as e:  # shown in the window, the user can retry or skip
                errors.append(e)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()

        def poll():
            if thread.is_alive():
                self.root.after(100, poll)
                return
            for slot in booked:
                self.slots.remove(slot)
                self.done += 1
            self._busy(False)
            if errors:
                self.status.configure(text=f"Orbit said: {errors[0]}")
            else:
                self._show_slot()

        self.root.after(100, poll)


def run(scheduled: bool = False) -> None:
    """scheduled=True (the hourly systemd timer) stays quiet outside your working hours."""
    hours = load_work_hours()
    if scheduled and not hours.is_reminder_time(now()):
        return
    today = now().date()
    try:
        tasks_text = orbit.call("ListMyTasks")
        entries = fetch_entries(today - timedelta(days=14), today)
    except Exception as e:
        root = tk.Tk(className="tl-uurtjes")
        root.withdraw()
        messagebox.showerror("Teamleader uurtjes", f"Could not reach Teamleader Orbit:\n\n{e}")
        return

    if not pending_slots(now(), entries, load_skipped(), hours):
        return

    root = tk.Tk(className="tl-uurtjes")
    Popup(root, parse_tasks(tasks_text), entries, hours)
    root.mainloop()
