"""Data types used in the application."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict

from lib.utils import now

if TYPE_CHECKING:
    import datetime as dt

    import customtkinter as tk


class Creatable(Protocol):
    """Protocol for creatable types."""

    @classmethod
    def create(cls, *args, **kwargs) -> Creatable:
        """Create a new instance of the type."""
        ...


class TaskDict(TypedDict):
    """Dictionary representation of a Task."""

    id: str
    created_at: str
    updated_at: str | None
    finished_at: str | None
    text: str
    children: list[TaskDict]


@dataclass
class Task(Creatable):
    """A task in the stack."""

    id: str
    created_at: str
    text: str
    updated_at: str | None = None
    finished_at: str | None = None
    children: list[Task] = field(default_factory=list)

    @classmethod
    def create(cls, text: str) -> Task:
        """Create a new Task with a unique ID and current timestamp."""
        nowts = now()
        return cls(
            id=str(uuid.uuid4()),
            created_at=nowts,
            updated_at=nowts,
            text=text,
        )

    @classmethod
    def from_dict(cls, data: TaskDict) -> Task:
        """Create a Task from a dictionary representation."""
        return cls(
            id=data['id'],
            created_at=data['created_at'],
            updated_at=data.get('updated_at'),
            text=data['text'],
            finished_at=data.get('finished_at'),
            children=[cls.from_dict(child) for child in data.get('children', [])],
        )

    def to_dict(self) -> TaskDict:
        """Convert the Task to a dictionary representation."""
        return {
            'id': self.id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'finished_at': self.finished_at,
            'text': self.text,
            'children': [child.to_dict() for child in self.children],
        }

    def finish(self, ts: str | None = None) -> None:
        """Mark the task as finished with the current timestamp."""
        self.finished_at = ts or now()
        self.touch(self.finished_at)

    def touch(self, ts: str | None = None) -> None:
        """Update the updated_at timestamp to now."""
        self.updated_at = ts or now()


UsageAction = Literal['start', 'finish', 'switch']


class UsageEntryDict(TypedDict):
    """Dictionary representation of a UsageEntry."""

    timestamp: str
    action: UsageAction
    target: str | None


@dataclass
class UsageEntry:
    """A usage entry for tracking start/finish actions."""

    timestamp: str
    action: UsageAction
    target: str | None = None

    def to_dict(self) -> UsageEntryDict:
        """Convert the UsageEntry to a dictionary representation."""
        return {
            'timestamp': self.timestamp,
            'action': self.action,
            'target': self.target,
        }

    @classmethod
    def create(cls, action: UsageAction, target: str | None = None) -> UsageEntry:
        """Create a new UsageEntry with the current timestamp."""
        return cls(
            timestamp=now(),
            action=action,
            target=target,
        )

    @classmethod
    def from_dict(cls, data: UsageEntryDict) -> UsageEntry:
        """Create a UsageEntry from a dictionary representation."""
        return cls(
            timestamp=data['timestamp'],
            action=data['action'],
            target=data.get('target'),
        )


class StackDict(TypedDict):
    """Dictionary representation of a Stack."""

    id: str
    name: str
    created_at: str
    last_updated_at: str | None
    finished_at: str | None
    tag: str | None
    children: list[TaskDict]
    entry_parent_task_id: str | None


@dataclass
class Stack(Creatable):
    """A stack of tasks."""

    id: str
    name: str
    created_at: str
    last_updated_at: str | None = None
    finished_at: str | None = None
    tag: str | None = None
    children: list[Task] = field(default_factory=list)
    # Task under which the entry widget is currently placed (by id)
    entry_parent_task_id: str | None = None

    @classmethod
    def create(cls, name: str) -> Stack:
        """Create a new Stack with a unique ID and current timestamp."""
        created = now()
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            created_at=created,
            last_updated_at=created,
        )

    @classmethod
    def from_dict(cls, data: StackDict) -> Stack:
        """Create a Stack from a dictionary representation."""
        return cls(
            id=data['id'],
            name=data['name'],
            created_at=data['created_at'],
            last_updated_at=data.get('last_updated_at'),
            finished_at=data.get('finished_at'),
            tag=data.get('tag'),
            children=[Task.from_dict(child) for child in data.get('children', [])],
            entry_parent_task_id=data.get('entry_parent_task_id'),
        )

    def to_dict(self) -> StackDict:
        """Convert the Stack to a dictionary representation."""
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at,
            'last_updated_at': self.last_updated_at,
            'finished_at': self.finished_at,
            'tag': self.tag,
            'children': [child.to_dict() for child in self.children],
            'entry_parent_task_id': self.entry_parent_task_id,
        }

    def touch(self, ts: str | None = None) -> None:
        """Update the last_updated_at timestamp to now."""
        self.last_updated_at = ts or now()

    def iter_tasks(self):
        """Pre-order traversal of all tasks in this stack."""

        def _iter(tasks: list[Task]):
            for t in tasks:
                yield t
                yield from _iter(t.children)

        yield from _iter(self.children)

    def find_task_by_id(self, task_id: str) -> Task | None:
        """Find a task by its ID in this stack."""
        for t in self.iter_tasks():
            if t.id == task_id:
                return t
        return None

    def add_task(self, text: str, parent: Task | None = None) -> Task:
        """Add a task as a child of the given parent, or root-level if parent is None."""
        task = Task.create(text)
        if parent is None:
            self.children.append(task)
        else:
            parent.children.append(task)
        self.touch()
        return task

    def unfinished_tasks(self) -> list[Task]:
        """Return a list of all unfinished tasks in this stack."""
        return [t for t in self.iter_tasks() if t.finished_at is None]

    def mark_task_finished(self, task: Task) -> None:
        """Mark the given task as finished, and update stack status if needed."""
        if task.finished_at is None:
            task.finish()
            self.touch()
        # Stack is finished when all top-level tasks are finished.
        if self.children and all(t.finished_at is not None for t in self.children):
            self.finished_at = now()

    def last_updated_task(self) -> Task | None:
        """Return the task that was most recently updated (created or finished)."""
        tasks = sorted(
            self.iter_tasks(),
            key=lambda t: t.updated_at or t.created_at,
            reverse=True,
        )
        return tasks[0] if tasks else None

    def focused_task(self) -> Task | None:
        """Return the currently focused task (the one under which the entry is placed)."""
        if self.entry_parent_task_id is None:
            return None
        return self.find_task_by_id(self.entry_parent_task_id)


AnyDataDict = TaskDict | StackDict | UsageEntryDict


@dataclass
class StackView:
    """UI representation of a Stack."""

    stack: Stack
    frame: tk.CTkFrame
    header_frame: tk.CTkFrame
    label: tk.CTkLabel
    tag_label: tk.CTkLabel
    entries_frame: tk.CTkFrame
    entry_widget: tk.CTkEntry
    entry_labels: dict[str, tk.CTkLabel] = field(default_factory=dict)
    folded: bool = False
    rename_entry: tk.CTkEntry | None = None
    tag_entry: tk.CTkEntry | None = None
    # Linear order of visible tasks in this stack: (task, depth)
    task_order: list[tuple[Task, int]] = field(default_factory=list)
    # Base frame color for resetting after highlight
    base_fg_color: object | None = None


EventType = Literal[
    'track_start',
    'track_finish',
    'task_created',
    'task_finished',
    'stack_created',
    'stack_finished',
    'switch',
]


@dataclass
class Event:
    """An event in the system."""

    ts: dt.datetime
    type: EventType
    stack_id: str | None = None
    task_id: str | None = None


@dataclass
class DataContext:
    """In-memory data context for stacks, tasks, and events."""

    stacks: dict[str, Stack]
    tasks: dict[str, Task]
    task_parent: dict[str, str | None]  # task_id -> parent_task_id
    stack_by_task: dict[str, str]  # task_id -> stack_id
    events: list[Event]


@dataclass
class LogEntry:
    """A log entry for usage tracking."""

    ts: dt.datetime
    message: str
    stack_id: str | None
    stack_name: str | None
    tag: str | None
    task_id: str | None
    duration: dt.timedelta | None
    is_context_switch: bool = False
    is_creation: bool = False
    is_finish: bool = False


@dataclass
class TabConfig:
    """Configuration for a tab in the UI."""

    name: str
    selected_tags: list[str]
