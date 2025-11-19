"""Manage stacks of tasks with loading, saving, and usage logging."""

import json
from collections.abc import Sequence
from pathlib import Path

from lib.data import STORAGE, STORAGE_DONE, STORAGE_USAGE
from lib.types import AnyDataDict, Stack, Task, UsageAction, UsageEntry
from lib.utils import read_last_line


class StackManager:
    """Manage loading, saving, and manipulating stacks."""

    stacks: list[Stack]
    last_switch_target: str | None

    def __init__(
        self,
        storage_path: Path = STORAGE,
        storage_done_path: Path = STORAGE_DONE,
        usage_path: Path = STORAGE_USAGE,
    ) -> None:
        """Initialize the StackManager and load stacks from storage."""
        self.storage_path = storage_path
        self.storage_done_path = storage_done_path
        self.storage_usage_path = usage_path
        self.stacks: list[Stack] = []
        self.last_switch_target = None
        self._dirty = False
        self._load()

    @staticmethod
    def _sort_tasks_recursive(tasks: list[Task]) -> None:
        tasks.sort(key=lambda t: t.created_at)
        for t in tasks:
            StackManager._sort_tasks_recursive(t.children)

    def _load(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            _ = self.storage_path.write_text('[]', encoding='utf-8')

        with self.storage_path.open('r', encoding='utf-8') as f:
            raw = json.load(f)

        self.stacks = [Stack.from_dict(item) for item in raw]

        # Sort once on load for stable ordering
        for stack in self.stacks:
            StackManager._sort_tasks_recursive(stack.children)
        self.stacks.sort(key=lambda s: s.last_updated_at or s.created_at)

        # Initialize entry_parent_task_id for stacks that don't have it yet
        for stack in self.stacks:
            if stack.entry_parent_task_id is None:
                last_task = stack.last_updated_task()
                if last_task is not None:
                    stack.entry_parent_task_id = last_task.id

        self._dirty = False

    def switch(self, target: str) -> None:
        """Record a switch action in the usage log."""
        self._record_event('switch', target=target)
        self.last_switch_target = target

    def _record_event(self, event: UsageAction, target: str | None = None) -> None:
        with self.storage_usage_path.open('a', encoding='utf-8') as f:
            entry = UsageEntry.create(event, target=target)
            _ = f.write(json.dumps(entry.to_dict()) + '\n')

    def start(self) -> None:
        """Record a start action in the usage log."""
        self.storage_usage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_usage_path.touch(exist_ok=True)
        last_line = read_last_line(self.storage_usage_path)
        if not last_line:
            self._record_event('start')
            return
        entry = UsageEntry.from_dict(json.loads(last_line))
        if entry.action == 'finish':
            self._record_event('start')

    def end(self) -> None:
        """Record a finish action in the usage log."""
        self._record_event('finish')

    def make_dirty(self) -> None:
        """Mark the manager as dirty, indicating that changes need to be saved."""
        self._dirty = True

    def ensure_default_stack(self) -> None:
        """Ensure there is at least one active stack."""
        if not self.stacks or all(stack.finished_at is not None for stack in self.stacks):
            _ = self.add_stack('Default Stack')
            self.save()

    def add_stack(self, name: str) -> Stack:
        """Add a new stack with the given name."""
        stack = Stack.create(name)
        self.stacks.append(stack)
        self._dirty = True
        return stack

    def active_stacks(self) -> list[Stack]:
        """Return a list of active (unfinished) stacks."""
        return [s for s in self.stacks if s.finished_at is None]

    def _save_path(self, path: Path, data: Sequence[AnyDataDict], as_jsonl: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if as_jsonl:
            with path.open('a', encoding='utf-8') as f:
                for item in data:
                    _ = f.write(json.dumps(item) + '\n')
        else:
            tmp_path = path.with_suffix('.tmp')
            with tmp_path.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            _ = tmp_path.replace(path)

    def save(self) -> None:
        """Save stacks to storage if dirty."""
        if not self._dirty:
            return

        # keep stacks sorted by last_updated_at / created_at
        self.stacks.sort(key=lambda s: s.last_updated_at or s.created_at)
        for stack in self.stacks:
            StackManager._sort_tasks_recursive(stack.children)

        unfinished = [s for s in self.stacks if s.finished_at is None]
        data = [stack.to_dict() for stack in unfinished]
        data_done = [stack.to_dict() for stack in self.stacks if stack.finished_at is not None]

        self._save_path(self.storage_path, data)
        # Append finished stacks to done storage as JSONL to avoid rewriting the whole file
        self._save_path(self.storage_done_path, data_done, as_jsonl=True)

        self._dirty = False
        self.stacks = unfinished

    def add_task_to_stack(self, stack: Stack, text: str, parent: Task | None = None) -> Task:
        """Add a task to the given stack under the specified parent."""
        task = stack.add_task(text, parent)
        self._dirty = True
        return task
