"""UI."""

import customtkinter as tk
from lib.control_socket import ControlSocket
from lib.data import CONTROL_SOCKET
from lib.focus_manager_cocoa import FocusManagerCocoa
from lib.protocols.focus_manager import FocusManager
from lib.stack_manager import StackManager
from lib.types import Stack, StackView, Task
from lib.utils import name_to_color


class StackApp:
    """The main Stack application UI."""

    focus_manager: FocusManager
    _socket: ControlSocket
    _highlighted_view: StackView | None

    INDENT_WIDTH = 20

    def __init__(self) -> None:
        """Initialize the StackApp with the given StackManager."""
        self.manager = StackManager()
        self.manager.start()
        self.manager.ensure_default_stack()

        self._socket = ControlSocket(CONTROL_SOCKET)
        self._socket.register('toggle', self._toggle)
        self._socket.register('quit', self._quit)
        self._socket.start()

        self.app = tk.CTk()
        self.app.title('Stack Manager')
        self.app.withdraw()

        self.focus_manager = FocusManagerCocoa()
        self.focus_manager.start()
        self.focus_manager.capture_front_app()

        self.stack_views: list[StackView] = []
        self.selected_index = 0
        self.show_completed = False
        self.hide_scheduled = False

        self._highlighted_view = None

        self._build_stack_views()
        self._setup_bindings()

        self.show()

    # ----- Hide/unhide logic -----

    def _visible(self) -> bool:
        return bool(self.app.winfo_viewable())

    def _toggle(self) -> bool:
        print('Toggling app visibility')
        if self._visible():
            self.hide()
        else:
            self.show()
        return True

    def show(self) -> None:
        """Show the application window."""
        print('Showing app')
        self.focus_manager.capture_front_app()
        self.app.deiconify()
        self.app.lift()
        self.app.focus_force()
        if self.stack_views:
            self.stack_views[self.selected_index].entry_widget.focus_set()

    def hide(self) -> None:
        """Hide the application window."""
        print('Hiding app')
        self.app.withdraw()
        if self._highlighted_view is not None:
            self._rerender_stack_entries(self._highlighted_view)
            self._highlighted_view = None
        self.focus_manager.restore_front_app()
        self.hide_scheduled = False

    def _quit(self) -> bool:
        self.manager.save()
        self.app.quit()
        self.focus_manager.restore_front_app()
        return True

    def _schedule_hide(self, delay: int = 0) -> None:
        print('Scheduling hide...')
        if self.hide_scheduled:
            return
        self.hide_scheduled = True
        self.manager.save()
        _ = self.app.after(delay, self.hide)
        print('Scheduled hide in', delay, 'ms')

    # ----- UI construction -----

    def _build_stack_views(self) -> None:
        active_stacks = self.manager.active_stacks()
        for stack in active_stacks:
            self._create_stack_view(stack)

        if self.stack_views:
            self.selected_index = len(self.stack_views) - 1
            self._update_stack_selection()
        else:
            # Fallback (should not happen due to ensure_default_stack)
            placeholder = tk.CTkEntry(master=self.app)
            placeholder.pack()

    def _create_stack_view(self, stack: Stack) -> None:
        stack_frame = tk.CTkFrame(master=self.app, border_width=0)
        stack_frame.pack(pady=10, padx=10, fill='both', expand=True)

        header_frame = tk.CTkFrame(
            master=stack_frame, fg_color='transparent', bg_color='transparent'
        )
        header_frame.pack(pady=5, padx=5, fill='x')

        stack_label = tk.CTkLabel(
            master=header_frame,
            text=stack.name,
            font=('Arial', 14),
        )
        stack_label.pack(side='left')

        tag_label = tk.CTkLabel(
            master=header_frame,
            text='',
            font=('Arial', 12),
        )
        tag_label.pack(side='right')

        entries_frame = tk.CTkFrame(master=stack_frame)
        entries_frame.pack(pady=5, padx=10, fill='both', expand=True)

        entry_widget = tk.CTkEntry(master=entries_frame, width=200)
        entry_widget.pack(pady=5, padx=0, anchor='w')

        view = StackView(
            stack=stack,
            frame=stack_frame,
            header_frame=header_frame,
            label=stack_label,
            tag_label=tag_label,
            entries_frame=entries_frame,
            entry_widget=entry_widget,
        )
        view.base_fg_color = stack_frame.cget('fg_color')
        self.stack_views.append(view)

        self._update_tag_badge(view)
        self._rerender_stack_entries(view)

        stack_label.bind(
            '<Button-1>',
            lambda _event, sv=view: self._select_stack(self.stack_views.index(sv)),
        )

        entry_widget.bind(
            '<Return>',
            lambda _event, sv=view: self._on_enter(sv),
        )
        entry_widget.bind(
            '<Control-Return>',
            lambda _event, sv=view: self._on_enter(sv, with_hide=False),
        )
        entry_widget.bind(
            '<Left>',
            lambda _event, sv=view: self._finish_last_task_ui(sv),
        )
        entry_widget.bind(
            '<Control-Left>',
            lambda _event, sv=view: self._finish_last_task_ui(sv, with_hide=False),
        )

    def _setup_bindings(self) -> None:
        _ = self.app.bind('<Up>', lambda _event: self._on_up_key())
        _ = self.app.bind('<Down>', lambda _event: self._on_down_key())
        _ = self.app.bind('<Control-a>', self._toggle_show_completed)
        _ = self.app.bind('<Control-r>', self._start_rename_current_stack)
        _ = self.app.bind('<Control-t>', self._start_edit_tag)
        _ = self.app.bind('<Control-Up>', self._on_ctrl_up)
        _ = self.app.bind('<Control-Down>', self._on_ctrl_down)
        _ = self.app.bind('<Control-e>', lambda _event: self._end())
        _ = self.app.bind('<Escape>', lambda _event: self.hide())
        _ = self.app.bind('<Control-Escape>', lambda _event: self._quit())
        _ = self.app.protocol('WM_DELETE_WINDOW', self.manager.save)

    def _end(self) -> None:
        self.app.iconify()
        self.manager.end()
        self._schedule_hide(500)

    # ----- Selection handling -----

    def _update_stack_selection(self) -> None:
        if not self.stack_views:
            return

        for idx, view in enumerate(self.stack_views):
            if idx == self.selected_index:
                view.frame.configure(border_width=2)
                self._unfold_stack(view)
            else:
                view.frame.configure(border_width=0)
                self._fold_stack(view)

        self.stack_views[self.selected_index].stack.touch()
        self.stack_views[self.selected_index].entry_widget.focus_set()
        if task := self.stack_views[self.selected_index].stack.last_updated_task():
            task.touch()
            self.manager.make_dirty()

    def _select_stack(self, new_index: int) -> None:
        if not self.stack_views:
            return
        new_index = max(0, min(new_index, len(self.stack_views) - 1))
        self.selected_index = new_index
        self._update_stack_selection()

    # ----- Tag color / badge -----

    @staticmethod
    def _tag_color(name: str) -> str:
        """Deterministically derive a color from the tag name."""
        return name_to_color(name)

    def _update_tag_badge(self, view: StackView) -> None:
        tag = view.stack.tag
        if tag:
            color = self._tag_color(tag)
            view.tag_label.configure(
                text=tag,
                fg_color=color,
                text_color='white',
                corner_radius=10,
                padx=8,
                pady=2,
            )
        else:
            view.tag_label.configure(
                text='',
                fg_color='transparent',
            )

    # ----- Entry rendering -----

    def _rerender_stack_entries(
        self,
        view: StackView,
        with_entry: bool = True,
        highlight_task_id: str | None = None,
        highlight_color: str | None = None,
    ) -> None:
        """Rerender the task entries in the given StackView."""
        # Clear existing labels
        for label in view.entry_labels.values():
            label.destroy()
        view.entry_labels.clear()
        view.task_order.clear()

        # Recursive rendering of task tree
        def render_task(task: Task, depth: int) -> None:
            # If completed tasks are hidden, skip this label but still render children,
            # EXCEPT if this is the highlighted task (we always want to show that).
            if (
                not self.show_completed
                and task.finished_at is not None
                and (highlight_task_id is None or task.id != highlight_task_id)
            ):
                for child in task.children:
                    render_task(child, depth + 1)
                return

            lbl = tk.CTkLabel(
                master=view.entries_frame,
                text=task.text,
                font=('Arial', 12),
            )

            lbl.pack(
                pady=2,
                padx=5 + depth * self.INDENT_WIDTH,
                anchor='w',
            )

            # Text color for finished / temporary highlight (complete/create)
            if task.finished_at is not None:
                lbl.configure(text_color='gray')

            if highlight_task_id is not None and task.id == highlight_task_id and highlight_color:
                lbl.configure(text_color=highlight_color)

            view.entry_labels[task.id] = lbl
            view.task_order.append((task, depth))

            for child in task.children:
                render_task(child, depth + 1)

        for root_task in view.stack.children:
            render_task(root_task, depth=0)

        view.entry_widget.pack_forget()
        if with_entry:
            self._place_entry_widget(view)

    def _place_entry_widget(self, view: StackView) -> None:
        """Place the entry widget directly under the current anchor task (one row down).

        If there are no tasks yet, place at root level.
        """
        tasks = view.task_order
        stack = view.stack

        # No tasks: root-level entry at top
        if not tasks:
            stack.entry_parent_task_id = None
            view.entry_widget.pack(pady=5, padx=5, anchor='w')
            return

        parent_id = stack.entry_parent_task_id

        # Root-level anchor while tasks exist:
        # treat as "root" parent, but visually keep entry at the top.
        if parent_id is None:
            entry_indent = 5
            # Place before the first task widget if it exists
            first_task = tasks[0][0]
            first_widget = view.entry_labels.get(first_task.id)
            if first_widget is not None:
                view.entry_widget.pack(
                    pady=5,
                    padx=entry_indent,
                    anchor='w',
                    before=first_widget,
                )
            else:
                view.entry_widget.pack(pady=5, padx=entry_indent, anchor='w')
            return

        # Find anchor task index and depth in visible order
        parent_index = None
        parent_depth = 0
        for i, (t, d) in enumerate(tasks):
            if t.id == parent_id:
                parent_index = i
                parent_depth = d
                break

        # If the anchor task is not visible for some reason, snap to last visible task
        if parent_index is None:
            parent_index = len(tasks) - 1
            parent_task, parent_depth = tasks[parent_index]
            stack.entry_parent_task_id = parent_task.id

        child_depth = parent_depth + 1
        entry_indent = 5 + child_depth * self.INDENT_WIDTH

        # Place entry widget right after the anchor row, before the next row (if any)
        if parent_index + 1 < len(tasks):
            next_task = tasks[parent_index + 1][0]
            next_widget = view.entry_labels.get(next_task.id)
            if next_widget is not None:
                view.entry_widget.pack(
                    pady=5,
                    padx=entry_indent,
                    anchor='w',
                    before=next_widget,
                )
                return

        # Otherwise, pack at the end
        view.entry_widget.pack(pady=5, padx=entry_indent, anchor='w')

    # ----- Actions -----

    def _on_enter(self, view: StackView, with_hide: bool = True) -> None:
        text = view.entry_widget.get()
        if text.strip() == '':
            task = view.stack.focused_task()
            if self.manager and task and self.manager.last_switch_target != task.id:
                self.manager.switch(task.id)
            self.hide()
            return

        parent: Task | None = None
        parent_id = view.stack.entry_parent_task_id
        if parent_id is not None:
            parent = view.stack.find_task_by_id(parent_id)

        task = self.manager.add_task_to_stack(view.stack, text, parent=parent)

        # New tasks become the new current parent (stack-like behaviour)
        view.stack.entry_parent_task_id = task.id
        self.manager.save()

        view.entry_widget.delete(0, 'end')
        self._rerender_stack_entries(
            view,
            with_entry=not with_hide,
            highlight_task_id=task.id,
            highlight_color='green',
        )
        self._highlighted_view = view
        if with_hide:
            self._schedule_hide(500)

    def _finish_last_task_ui(self, view: StackView, with_hide: bool = True) -> None:
        task_id = view.stack.entry_parent_task_id
        if task_id is None:
            self.hide()
            return
        task = view.stack.find_task_by_id(task_id)
        if task is None or (task.children and any(c.finished_at is None for c in task.children)):
            return

        view.stack.mark_task_finished(task)
        self.manager.make_dirty()
        self.manager.save()

        self._rerender_stack_entries(
            view,
            with_entry=not with_hide,
            highlight_task_id=task.id,
            highlight_color='red',
        )
        self._highlighted_view = view

        if with_hide:
            self._schedule_hide(500)

    # ----- Folding -----

    @staticmethod
    def _fold_stack(view: StackView) -> None:
        if not view.folded:
            view.entries_frame.pack_forget()
            view.folded = True

    @staticmethod
    def _unfold_stack(view: StackView) -> None:
        if view.folded:
            view.entries_frame.pack(pady=5, padx=10, fill='both', expand=True)
            view.folded = False

    # ----- Renaming -----

    def _start_rename_current_stack(self, _event=None) -> str:
        if not self.stack_views:
            return 'break'

        view = self.stack_views[self.selected_index]

        if view.rename_entry is not None:
            return 'break'

        stack_label = view.label
        parent = stack_label.master

        rename_entry = tk.CTkEntry(master=parent, width=250)
        rename_entry.insert(0, view.stack.name)
        rename_entry.pack(pady=5, padx=5, anchor='w', before=stack_label)

        stack_label.pack_forget()
        view.rename_entry = rename_entry

        def finish_rename(_event=None) -> str:
            new_name = rename_entry.get().strip()

            stack_label.pack(pady=5, padx=5, anchor='w', before=rename_entry)

            rename_entry.destroy()
            view.rename_entry = None

            if new_name:
                self._rename_stack(view, new_name)

            view.entry_widget.focus_set()
            return 'break'

        def cancel_rename(_event=None) -> str:
            rename_entry.destroy()
            view.rename_entry = None

            stack_label.pack(pady=5, padx=5, anchor='w')
            view.entry_widget.focus_set()
            return 'break'

        rename_entry.bind('<Return>', finish_rename)
        rename_entry.bind('<Escape>', cancel_rename)

        rename_entry.focus_set()
        return 'break'

    def _rename_stack(self, view: StackView, new_name: str) -> None:
        view.stack.name = new_name
        view.stack.touch()
        view.label.configure(text=new_name)
        self.manager.make_dirty()
        self.manager.save()

    # ----- Tag editing -----

    def _start_edit_tag(self, _event=None) -> str:
        if not self.stack_views:
            return 'break'

        view = self.stack_views[self.selected_index]

        if view.tag_entry is not None:
            return 'break'

        tag_entry = tk.CTkEntry(master=view.header_frame, width=160, justify='right')
        current_tag = view.stack.tag or ''
        tag_entry.insert(0, current_tag)

        view.tag_label.pack_forget()
        tag_entry.pack(side='right')
        view.tag_entry = tag_entry

        def finish_tag(_event=None) -> str:
            new_tag = tag_entry.get().strip()
            tag_entry.destroy()
            view.tag_entry = None
            view.tag_label.pack(side='right')

            view.stack.tag = new_tag or None
            view.stack.touch()
            self.manager.make_dirty()
            self.manager.save()
            self._update_tag_badge(view)

            view.entry_widget.focus_set()
            return 'break'

        def cancel_tag(_event=None) -> str:
            tag_entry.destroy()
            view.tag_entry = None
            view.tag_label.pack(side='right')
            view.entry_widget.focus_set()
            return 'break'

        tag_entry.bind('<Return>', finish_tag)
        tag_entry.bind('<Escape>', cancel_tag)

        tag_entry.focus_set()
        return 'break'

    # ----- Global key handlers -----

    def _toggle_show_completed(self, _event=None) -> str:
        self.show_completed = not self.show_completed
        for view in self.stack_views:
            self._rerender_stack_entries(view)
        return 'break'

    def _on_up_key(self) -> None:
        self._select_stack(self.selected_index - 1)

    def _on_down_key(self) -> None:
        if not self.stack_views:
            return

        if self.selected_index == len(self.stack_views) - 1:
            idx = len(self.stack_views) + 1
            name = f'Stack {idx}'
            new_stack = self.manager.add_stack(name)
            self.manager.save()
            self._create_stack_view(new_stack)
            self._select_stack(len(self.stack_views) - 1)
        else:
            self._select_stack(self.selected_index + 1)

    def _on_ctrl_up(self, _event=None) -> str:
        self._move_entry_cursor(-1)
        return 'break'

    def _on_ctrl_down(self, _event=None) -> str:
        self._move_entry_cursor(1)
        return 'break'

    def _move_entry_cursor(self, direction: int) -> None:
        """Move the entry widget to the previous/next task within the current stack.

        Ctrl-Up: direction = -1
        Ctrl-Down: direction = +1

        Positions:
            -1     -> root level (entry_parent_task_id = None)
            0..n-1 -> tasks in view.task_order
        """
        if not self.stack_views:
            return

        view = self.stack_views[self.selected_index]
        tasks = view.task_order
        if not tasks:
            return

        stack = view.stack
        current_id = stack.entry_parent_task_id

        # Map current position to a linear index
        if current_id is None:
            # Root level
            pos = -1
        else:
            pos = -1
            for i, (task, _depth) in enumerate(tasks):
                if task.id == current_id:
                    pos = i
                    break
            # If current parent is not visible for some reason, snap to last task
            if pos == -1:
                pos = len(tasks) - 1

        new_pos = pos + direction

        # Clamp to valid range: [-1, len(tasks)-1]
        if new_pos < -1 or new_pos >= len(tasks):
            return

        # Map back from position to entry_parent_task_id
        if new_pos == -1:
            # Root level
            stack.entry_parent_task_id = None
        else:
            new_task = tasks[new_pos][0]
            stack.entry_parent_task_id = new_task.id

        self.manager.make_dirty()
        self.manager.save()
        self._rerender_stack_entries(view)

    # ----- Run loop -----

    def run(self) -> None:
        """Run the main application loop."""
        self.app.focus_force()
        if self.stack_views:
            self.stack_views[self.selected_index].entry_widget.focus_set()
        _ = self.app.eval('tk::PlaceWindow . center')
        self.app.minsize(self.app.winfo_width(), self.app.winfo_height())
        self.app.mainloop()
