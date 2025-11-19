"""Data context building from storage files."""

import datetime as dt

from lib.data import STORAGE, STORAGE_DONE, STORAGE_USAGE, TZLOCAL
from lib.types import Creatable, DataContext, Event, Stack, StackDict, Task, UsageEntry
from lib.utils import iter_jsonl_reverse, load_json_array, parse_iso


def from_ctx[T: Creatable](ctx: dict[str, T], name: str, typ: type[T]) -> T:
    """Helper to load a typed object from a dict."""
    ret = ctx.get(name)
    if ret:
        return ret
    return typ.create('UNDEFINED')


def ctx_add_stacks(
    events: list[Event],
    stacks: dict[str, Stack],
    tasks: dict[str, Task],
    task_parent: dict[str, str | None],
    stack_by_task: dict[str, str],
) -> None:
    """Add stacks and tasks from storage to the event list."""

    def register_stack(s: Stack):
        stacks[s.id] = s
        for t in s.children:
            register_task(s.id, t, parent=None)

    def register_task(stack_id: str, t: Task, parent: Task | None):
        tasks[t.id] = t
        stack_by_task[t.id] = stack_id
        task_parent[t.id] = parent.id if parent else None
        for child in t.children:
            register_task(stack_id, child, t)

    # Current (unfinished) stacks
    for s_dict in load_json_array(STORAGE, StackDict):
        s = Stack.from_dict(s_dict)
        register_stack(s)

    # Finished stacks from JSONL
    if STORAGE_DONE.exists():
        seen_stack_ids: set[str] = set(stacks)
        for raw in iter_jsonl_reverse(STORAGE_DONE):
            s_id = raw.get('id')
            if not s_id or s_id in seen_stack_ids:
                continue
            s = Stack.from_dict(raw)
            register_stack(s)
            seen_stack_ids.add(s_id)

    for s in stacks.values():
        ts_created = parse_iso(s.created_at)
        events.append(Event(ts=ts_created, type='stack_created', stack_id=s.id))

        if s.finished_at:
            ts_finished = parse_iso(s.finished_at)
            events.append(Event(ts=ts_finished, type='stack_finished', stack_id=s.id))

        for t in s.iter_tasks():
            events.append(
                Event(
                    ts=parse_iso(t.created_at),
                    type='task_created',
                    stack_id=s.id,
                    task_id=t.id,
                )
            )
            if t.finished_at:
                events.append(
                    Event(
                        ts=parse_iso(t.finished_at),
                        type='task_finished',
                        stack_id=s.id,
                        task_id=t.id,
                    )
                )


def ctx_add_usage(events: list[Event], stack_by_task: dict[str, str]) -> None:
    """Add usage events from usage.json to the event list."""
    if STORAGE_USAGE.exists():
        for raw in iter_jsonl_reverse(STORAGE_USAGE):
            try:
                u = UsageEntry.from_dict(raw)
            except Exception:  # noqa: S112
                continue
            ts = parse_iso(u.timestamp)
            events.append(
                Event(
                    ts=ts,
                    type='track_start'
                    if u.action == 'start'
                    else 'track_finish'
                    if u.action == 'finish'
                    else 'switch',
                    task_id=u.target,
                    stack_id=stack_by_task.get(u.target) if u.target else None,
                )
            )


def build_context(start_date: dt.date, end_date: dt.date) -> DataContext:
    """Build data context from storage files within the given date range."""
    stacks: dict[str, Stack] = {}
    tasks: dict[str, Task] = {}
    task_parent: dict[str, str | None] = {}
    stack_by_task: dict[str, str] = {}
    events: list[Event] = []

    ctx_add_stacks(events, stacks, tasks, task_parent, stack_by_task)
    ctx_add_usage(events, stack_by_task)

    # Filter to date range (by day) - timestamps are local
    start_dt = dt.datetime.combine(start_date, dt.time.min, TZLOCAL)
    end_dt = dt.datetime.combine(end_date, dt.time.max, TZLOCAL)
    events = [e for e in events if start_dt <= e.ts <= end_dt]

    # Sort chronologically
    events.sort(key=lambda e: e.ts)

    return DataContext(
        stacks=stacks,
        tasks=tasks,
        task_parent=task_parent,
        stack_by_task=stack_by_task,
        events=events,
    )
