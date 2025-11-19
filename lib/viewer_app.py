"""Viewer application for stack worklog data."""

import contextlib
import dataclasses
import datetime as dt
import json

import customtkinter as tk
from lib.ctx import build_context
from lib.data import VIEWER_CONFIG
from lib.focus_manager import FocusManager
from lib.log_builder import build_log_entries
from lib.types import DataContext, LogEntry, TabConfig
from lib.utils import day_key, name_to_color

BAR_CHART_HEIGHT = 200
ENTRY_DUR_BAR_LEN = 100


class ViewerApp:
    """Viewer application for stack worklog data."""

    start_entry: tk.CTkEntry
    end_entry: tk.CTkEntry
    tab_view: tk.CTkTabview
    log_scroll: tk.CTkScrollableFrame
    chart_canvas: tk.CTkCanvas
    chart_frame: tk.CTkFrame
    tab_keys: list[str]
    left_panel: tk.CTkFrame
    focus_manager: FocusManager
    win_width: int = 0
    win_height: int = 0

    def __init__(self):
        """Initialize the viewer application."""
        self.focus_manager = FocusManager()
        self.focus_manager.capture_front_app()

        self.app = tk.CTk()
        self.app.title('Stack Worklog Viewer')

        self.start_date = dt.date.today()
        self.end_date = dt.date.today()

        self.ctx: DataContext | None = None
        self.log_entries: list[LogEntry] = []

        self.tabs: list[TabConfig] = self._load_tabs()
        if not self.tabs:
            self.tabs = [TabConfig(name='Default', selected_tags=[])]
            self._save_tabs()
        self.tab_keys = [t.name for t in self.tabs]

        self.current_tab_name: str = self.tabs[0].name

        # per-tab checkboxes
        self.tag_checkboxes_by_tab: dict[str, dict[str, tk.CTkCheckBox]] = {}
        self.rename_entry: tk.CTkEntry | None = None
        self.tab_keys: list[str] = []

        self.focus_manager.wait()

        self._build_ui()
        self._reload_data()

        self.win_width = self.app.winfo_width()
        self.win_height = self.app.winfo_height()

    # --- config persistence ---

    def _on_resized(self, _event: object) -> None:
        new_width = self.app.winfo_width()
        new_height = self.app.winfo_height()
        if new_width != self.win_width or new_height != self.win_height:
            self.win_width = new_width
            self.win_height = new_height
            self._render_chart()

    def _load_tabs(self) -> list[TabConfig]:
        if not VIEWER_CONFIG.exists():
            return []
        try:
            data = json.loads(VIEWER_CONFIG.read_text(encoding='utf-8'))
            return [TabConfig(**item) for item in data]
        except Exception:
            return []

    def _save_tabs(self) -> None:
        data = [dataclasses.asdict(t) for t in self.tabs]
        VIEWER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        VIEWER_CONFIG.touch(exist_ok=True)
        _ = VIEWER_CONFIG.write_text(json.dumps(data, indent=2), encoding='utf-8')

    def _get_tab(self, name: str) -> TabConfig:
        for t in self.tabs:
            if t.name == name:
                return t
        # Fallback - should not normally happen
        t = TabConfig(name=name, selected_tags=[])
        self.tabs.append(t)
        return t

    # --- UI construction ---

    def _build_ui(self):
        # Top date controls
        top_frame = tk.CTkFrame(master=self.app)
        top_frame.pack(side='top', fill='x', padx=10, pady=5)

        tk.CTkLabel(top_frame, text='Start (YYYY-MM-DD):').pack(side='left')
        self.start_entry = tk.CTkEntry(top_frame, width=100)
        self.start_entry.pack(side='left', padx=5)
        self.start_entry.insert(0, str(self.start_date))

        tk.CTkLabel(top_frame, text='End:').pack(side='left')
        self.end_entry = tk.CTkEntry(top_frame, width=100)
        self.end_entry.pack(side='left', padx=5)
        self.end_entry.insert(0, str(self.end_date))

        self.start_entry.bind('<Return>', lambda _e: self._on_date_change())
        self.end_entry.bind('<Return>', lambda _e: self._on_date_change())

        today_btn = tk.CTkButton(top_frame, text='Today', command=self._set_today)
        today_btn.pack(side='left', padx=5)

        yday_btn = tk.CTkButton(top_frame, text='Yesterday', command=self._set_yesterday)
        yday_btn.pack(side='left', padx=5)

        week_btn = tk.CTkButton(top_frame, text='Last 7 days', command=self._set_last_7d)
        week_btn.pack(side='left', padx=5)

        last_week_btn = tk.CTkButton(top_frame, text='Last week', command=self._set_last_week)
        last_week_btn.pack(side='left', padx=5)

        this_week_btn = tk.CTkButton(top_frame, text='This week', command=self._set_this_week)
        this_week_btn.pack(side='left', padx=5)

        # Main split: left (tabs/tags), right (log)
        main_frame = tk.CTkFrame(master=self.app)
        main_frame.pack(fill='both', expand=True, padx=10, pady=5)

        # Left panel: buttons + optional rename entry + tabs
        self.left_panel = tk.CTkFrame(master=main_frame)
        self.left_panel.pack(side='left', fill='y', padx=5, pady=5)

        button_frame = tk.CTkFrame(master=self.left_panel)
        button_frame.pack(side='top', fill='x', pady=(0, 5))
        _ = button_frame.grid_columnconfigure(0, weight=1)

        # Buttons horizontally: + / R / X
        tab_add_btn = tk.CTkButton(button_frame, text='+', width=40, command=self._add_tab)
        tab_add_btn.grid(row=0, column=0, sticky='ew', padx=2)
        tab_rename_btn = tk.CTkButton(
            button_frame, text='R', width=40, command=self._rename_current_tab
        )
        tab_rename_btn.grid(row=0, column=1, padx=2)
        tab_close_btn = tk.CTkButton(
            button_frame, text='X', width=40, command=self._close_current_tab
        )
        tab_close_btn.grid(row=0, column=2, sticky='e', padx=2)

        # Rename entry (created lazily in _rename_current_tab)
        self.rename_entry = None

        # Tab view below buttons
        self.tab_view = tk.CTkTabview(
            master=self.left_panel,
            width=220,
            command=self._on_tab_change,
        )
        self.tab_view.pack(side='top', fill='both', expand=True, padx=0, pady=(0, 0))

        # Log area on the right
        right_frame = tk.CTkFrame(master=main_frame)
        right_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)

        self.log_scroll = tk.CTkScrollableFrame(master=right_frame)
        self.log_scroll.pack(fill='both', expand=True)

        # Chart at bottom
        self.chart_frame = tk.CTkFrame(master=self.app, height=BAR_CHART_HEIGHT + 10)
        self.chart_frame.pack(fill='x', padx=10, pady=5)
        _ = self.chart_frame.pack_propagate(False)
        self.chart_canvas = tk.CTkCanvas(self.chart_frame, height=BAR_CHART_HEIGHT)
        self.chart_canvas.pack(fill='x', expand=True)

        self._rebuild_tabs()

        self.app.protocol('WM_DELETE_WINDOW', self._on_exit)
        _ = self.app.bind('<Escape>', lambda _e: self._on_exit())
        _ = self.app.bind('<Configure>', self._on_resized)

    # --- date handling ---

    def _set_today(self):
        today = dt.date.today()
        self.start_date = today
        self.end_date = today
        self.start_entry.delete(0, 'end')
        self.start_entry.insert(0, str(today))
        self.end_entry.delete(0, 'end')
        self.end_entry.insert(0, str(today))
        self._reload_data()

    def _set_yesterday(self):
        y = dt.date.today() - dt.timedelta(days=1)
        self.start_date = y
        self.end_date = y
        self.start_entry.delete(0, 'end')
        self.start_entry.insert(0, str(y))
        self.end_entry.delete(0, 'end')
        self.end_entry.insert(0, str(y))
        self._reload_data()

    def _set_last_7d(self):
        end = dt.date.today()
        start = end - dt.timedelta(days=7)
        self.start_date = start
        self.end_date = end
        self.start_entry.delete(0, 'end')
        self.start_entry.insert(0, str(start))
        self.end_entry.delete(0, 'end')
        self.end_entry.insert(0, str(end))
        self._reload_data()

    def _set_last_week(self):
        """Set date range to the preceeding week Mon-Sun."""
        today = dt.date.today()
        last_monday = today - dt.timedelta(days=today.weekday() + 7)
        last_sunday = last_monday + dt.timedelta(days=6)
        self.start_date = last_monday
        self.end_date = last_sunday
        self.start_entry.delete(0, 'end')
        self.start_entry.insert(0, str(last_monday))
        self.end_entry.delete(0, 'end')
        self.end_entry.insert(0, str(last_sunday))
        self._reload_data()

    def _set_this_week(self):
        """Set date range to the current week Mon-Sun."""
        today = dt.date.today()
        this_monday = today - dt.timedelta(days=today.weekday())
        this_sunday = this_monday + dt.timedelta(days=6)
        self.start_date = this_monday
        self.end_date = this_sunday
        self.start_entry.delete(0, 'end')
        self.start_entry.insert(0, str(this_monday))
        self.end_entry.delete(0, 'end')
        self.end_entry.insert(0, str(this_sunday))
        self._reload_data()

    def _on_date_change(self):
        try:
            start = dt.date.fromisoformat(self.start_entry.get().strip())
            end = dt.date.fromisoformat(self.end_entry.get().strip())
        except ValueError:
            return
        if start > end:
            return
        self.start_date = start
        self.end_date = end
        self._reload_data()

    # --- tabs & tags ---

    def _rebuild_tabs(self):
        for name in list(self.tab_keys):
            with contextlib.suppress(ValueError):
                self.tab_view.delete(name)

        for t in self.tabs:
            _ = self.tab_view.add(t.name)

        self.tab_keys = [t.name for t in self.tabs]

        if self.tabs:
            if self.current_tab_name not in self.tab_keys:
                self.current_tab_name = self.tabs[0].name
            self.tab_view.set(self.current_tab_name)

    def _on_tab_change(self):
        self.current_tab_name = self.tab_view.get()
        self._render_log()

    def _unique_tab_name(self) -> str:
        idx = 1
        while True:
            name = f'Tab {idx}'
            if all(t.name != name for t in self.tabs):
                return name
            idx += 1

    def _add_tab(self):
        name = self._unique_tab_name()
        self.tabs.append(TabConfig(name=name, selected_tags=[]))
        self.current_tab_name = name
        self._rebuild_tabs()
        self._save_tabs()
        self._reload_data()

    def _rename_current_tab(self):
        if self.rename_entry is not None:
            # Already renaming; focus existing entry
            self.rename_entry.focus_set()
            return

        current_name = self.tab_view.get()
        if not current_name:
            return

        # Inline rename entry under the buttons, above tabs
        entry = tk.CTkEntry(self.left_panel)
        entry.insert(0, current_name)
        entry.pack(side='top', fill='x', padx=5, pady=(0, 5))
        self.rename_entry = entry

        def commit():
            new_name = entry.get().strip()
            if new_name:
                for t in self.tabs:
                    if t.name == current_name:
                        t.name = new_name
                        break
                self.current_tab_name = new_name
                self._save_tabs()
                self._rebuild_tabs()
                self._reload_data()
            entry.destroy()
            self.rename_entry = None

        def cancel():
            entry.destroy()
            self.rename_entry = None

        entry.bind('<Return>', lambda _e: commit())
        entry.bind('<Escape>', lambda _e: cancel())
        entry.focus_set()

    def _close_current_tab(self):
        if len(self.tabs) <= 1:
            return  # keep at least one
        current_name = self.tab_view.get()
        self.tabs = [t for t in self.tabs if t.name != current_name]
        self.current_tab_name = self.tabs[0].name
        self._save_tabs()
        self._rebuild_tabs()
        self._reload_data()

    def _on_tag_toggle(self, tag: str):
        tab_cfg = self._get_tab(self.current_tab_name)
        cb = self.tag_checkboxes_by_tab.get(self.current_tab_name, {}).get(tag)
        if cb is None:
            return
        if cb.get():
            if tag not in tab_cfg.selected_tags:
                tab_cfg.selected_tags.append(tag)
        else:
            tab_cfg.selected_tags = [t for t in tab_cfg.selected_tags if t != tag]
        self._save_tabs()
        self._render_log()

    # --- data / rendering ---

    def _reload_data(self):
        self.ctx = build_context(self.start_date, self.end_date)
        self.log_entries = build_log_entries(self.ctx)

        # Build list of all tags
        all_tags: set[str] = set()
        for s in self.ctx.stacks.values():
            if s.tag:
                all_tags.add(s.tag)

        # Rebuild tag checkboxes per tab
        self.tag_checkboxes_by_tab = {}

        for tab_name, tab_cfg in ((t.name, t) for t in self.tabs):
            tab = self.tab_view.tab(tab_name)

            # Clear tab FIRST
            for child in list(tab.winfo_children()):
                child.destroy()

            tk.CTkLabel(tab, text='Tags:').pack(anchor='w', padx=5, pady=2)

            tab_frame = tk.CTkScrollableFrame(master=tab)
            tab_frame.pack(fill='both', expand=True)

            checkboxes: dict[str, tk.CTkCheckBox] = {}
            for tag in sorted(all_tags):
                cb = tk.CTkCheckBox(
                    tab_frame,
                    text=tag,
                    command=lambda t=tag: self._on_tag_toggle(t),
                )
                cb.pack(anchor='w', padx=10)
                if tag in tab_cfg.selected_tags:
                    cb.select()
                else:
                    cb.deselect()
                checkboxes[tag] = cb

            self.tag_checkboxes_by_tab[tab_name] = checkboxes

        self._render_log()
        self._render_chart()

    def _render_log(self):
        for child in list(self.log_scroll.winfo_children()):
            child.destroy()

        if self.ctx is None:
            return

        active_tab = self._get_tab(self.current_tab_name)
        selected_tags = set(active_tab.selected_tags or [])
        # If no tags selected, show everything
        filter_active = bool(selected_tags)

        entry_time_max = max(
            [e.duration.total_seconds() for e in self.log_entries if e.duration], default=0
        )

        for entry in self.log_entries:
            # Filter by tag
            if filter_active and entry.tag not in selected_tags:
                continue

            row = tk.CTkFrame(self.log_scroll)
            row.pack(fill='x', padx=5, pady=2)

            # Tag color box
            color = name_to_color(entry.tag) if entry.tag else '#888888'
            color_box = tk.CTkLabel(row, text=entry.tag or '-', width=80)
            color_box.pack(side='left', padx=5)
            color_box.configure(
                fg_color=color,
                text_color='white',
                corner_radius=6,
                padx=4,
                pady=2,
            )

            # Timestamp + message
            ts_str = entry.ts.strftime('%Y-%m-%d %H:%M:%S')
            msg = f'{ts_str}  {entry.message}'
            if entry.stack_name:
                msg = f'[{entry.stack_name}] {msg}'

            msg_label = tk.CTkLabel(row, text=msg, anchor='w')
            msg_label.pack(side='left', fill='x', expand=True)

            # Duration (right-justified)
            dur_str = ''
            if entry.duration is not None:
                total_seconds = int(entry.duration.total_seconds())
                hours = total_seconds // 3600
                mins = (total_seconds % 3600) // 60
                secs = total_seconds % 60
                dur_str = f'{hours:02d}:{mins:02d}:{secs:02d}'
                dur_pct = (
                    (entry.duration.total_seconds() / entry_time_max) * 100 if entry_time_max else 0
                )
                bar_len = int((dur_pct / 100) * ENTRY_DUR_BAR_LEN)
                dur_bar_canvas = tk.CTkCanvas(
                    row, width=ENTRY_DUR_BAR_LEN, height=10, highlightthickness=0, bd=0
                )
                dur_bar_canvas.pack(side='right', padx=5, pady=2)
                _ = dur_bar_canvas.create_rectangle(
                    0,
                    0,
                    bar_len,
                    10,
                    fill='blue',
                    outline='blue',
                )

            dur_label = tk.CTkLabel(row, text=dur_str, width=80, anchor='e')
            dur_label.pack(side='right', padx=5)

    def _render_chart(self):
        self.chart_canvas.delete('all')
        if not self.log_entries:
            return

        # Aggregate per day
        created_per_day: dict[dt.date, int] = {}
        finished_per_day: dict[dt.date, int] = {}
        switches_per_day: dict[dt.date, int] = {}

        for e in self.log_entries:
            d = day_key(e.ts)
            if e.is_creation:
                created_per_day[d] = created_per_day.get(d, 0) + 1
            if e.is_finish:
                finished_per_day[d] = finished_per_day.get(d, 0) + 1
            if e.is_context_switch:
                switches_per_day[d] = switches_per_day.get(d, 0) + 1

        all_days = sorted(set(created_per_day) | set(finished_per_day) | set(switches_per_day))
        if not all_days:
            return

        width = int(self.chart_canvas.winfo_width() or 400)

        margin = 20
        usable_width = width - 2 * margin
        usable_height = BAR_CHART_HEIGHT - 2 * margin
        mid_y = margin + usable_height // 2

        # Compute net per day
        nets: list[int] = []
        for d in all_days:
            c = created_per_day.get(d, 0)
            f = finished_per_day.get(d, 0)
            net = f - c  # positive if more finished than created
            nets.append(net)

        pos_max = max((n for n in nets if n > 0), default=0)
        neg_min = min((n for n in nets if n < 0), default=0)
        scale_up = pos_max or 1
        scale_down = -neg_min or 1

        max_switch = max(switches_per_day.values(), default=0) or 1

        bar_width = max(10, usable_width // (len(all_days) * 3))

        # Zero line
        _ = self.chart_canvas.create_line(margin, mid_y, width - margin, mid_y, fill='gray')

        for i, d in enumerate(all_days):
            x_center = margin + (i * 3 + 1) * bar_width

            c = created_per_day.get(d, 0)
            f = finished_per_day.get(d, 0)
            net = f - c
            switches = switches_per_day.get(d, 0)

            # Creation/finish net bar (above/below zero line)
            if net >= 0:
                bar_height = int((net / scale_up) * (usable_height / 2)) if scale_up else 0
                x0 = x_center - bar_width // 2
                x1 = x_center + bar_width // 2
                y0 = mid_y - bar_height
                y1 = mid_y
            else:
                bar_height = int((-net / scale_down) * (usable_height / 2)) if scale_down else 0
                x0 = x_center - bar_width // 2
                x1 = x_center + bar_width // 2
                y0 = mid_y
                y1 = mid_y + bar_height

            color = 'green' if net > 0 else 'red' if net < 0 else 'gray'
            _ = self.chart_canvas.create_rectangle(x0, y0, x1, y1, fill=color)

            # Switches bar - positive-only, above zero line
            s_height = int((switches / max_switch) * (usable_height / 2)) if max_switch else 0
            sx0 = x_center + bar_width // 2 + 2
            sx1 = sx0 + bar_width
            sy0 = mid_y - s_height
            sy1 = mid_y
            _ = self.chart_canvas.create_rectangle(sx0, sy0, sx1, sy1, fill='blue')

            # Day labels under bars
            day_str = d.strftime('%m-%d')
            _ = self.chart_canvas.create_text(
                x_center,
                BAR_CHART_HEIGHT - margin // 2,
                text=day_str,
                anchor='n',
            )

    # --- exit ---

    def _on_exit(self):
        self._save_tabs()
        self.focus_manager.restore_front_app()
        self.app.quit()

    def run(self):
        """Run the viewer application."""
        _ = self.app.eval('tk::PlaceWindow . center')
        self.app.state('zoomed')
        self.app.mainloop()
