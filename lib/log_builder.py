"""Build log entries from data context events."""

import datetime as dt

from lib.ctx import from_ctx
from lib.types import DataContext, LogEntry, Task


def build_log_entries(ctx: DataContext) -> list[LogEntry]:
    """Build log entries from data context events."""
    log: list[LogEntry] = []

    tracking_on = False
    current_task: str | None = None
    current_start: dt.datetime | None = None

    def end_segment(until: dt.datetime):
        nonlocal current_start, current_task
        if not tracking_on or current_start is None:
            current_start = until
            return
        if current_task is None:
            current_start = until
            return

        duration = until - current_start

        # Attach duration to the last log entry for this task without duration
        for entry in reversed(log):
            if entry.task_id == current_task and entry.duration is None:
                entry.duration = duration
                break

        current_start = until

    for ev in ctx.events:
        if ev.type == 'track_start':
            if tracking_on:
                continue
            tracking_on = True
            current_start = ev.ts
            log.append(
                LogEntry(
                    ts=ev.ts,
                    message='Tracking started',
                    stack_id=None,
                    stack_name=None,
                    tag=None,
                    task_id=None,
                    duration=None,
                    is_creation=False,
                    is_finish=False,
                )
            )

        elif ev.type == 'track_finish':
            if not tracking_on:
                continue
            end_segment(ev.ts)
            tracking_on = False
            log.append(
                LogEntry(
                    ts=ev.ts,
                    message='Tracking stopped',
                    stack_id=None,
                    stack_name=None,
                    tag=None,
                    task_id=None,
                    duration=None,
                    is_finish=True,
                )
            )
            current_task = None
            current_start = None

        elif ev.type == 'switch':
            # context switch to a specific task
            new_task = ev.task_id
            if not tracking_on:
                # record switch but don't create segment
                new_task_text = (
                    from_ctx(ctx.tasks, new_task, Task).text if new_task in ctx.tasks else new_task
                )
                stack = ctx.stacks.get(ev.stack_id) if ev.stack_id else None
                log.append(
                    LogEntry(
                        ts=ev.ts,
                        message=f'Switched focus to {new_task_text}',
                        stack_id=ev.stack_id,
                        stack_name=stack.name if stack else None,
                        tag=stack.tag if stack else None,
                        task_id=new_task,
                        duration=None,
                        is_context_switch=True,
                    )
                )
                current_task = new_task
                continue

            if new_task == current_task:
                continue

            end_segment(ev.ts)
            old_task = current_task
            current_task = new_task
            current_start = ev.ts

            s = ctx.stacks.get(ev.stack_id) if ev.stack_id else None
            msg = 'Context switch'
            if old_task and new_task:
                t_old = ctx.tasks.get(old_task)
                t_new = ctx.tasks.get(new_task)
                text_old = t_old.text if t_old else old_task
                text_new = t_new.text if t_new else new_task
                msg = f'Switch: {text_old} → {text_new}'

            log.append(
                LogEntry(
                    ts=ev.ts,
                    message=msg,
                    stack_id=ev.stack_id,
                    stack_name=s.name if s else None,
                    tag=s.tag if s else None,
                    task_id=new_task,
                    duration=None,
                    is_context_switch=True,
                )
            )

        elif ev.type == 'task_created':
            # treat as focus switch to new task (stack semantics)
            stack = ctx.stacks.get(ev.stack_id) if ev.stack_id else None
            t = ctx.tasks.get(ev.task_id) if ev.task_id else None
            if tracking_on:
                end_segment(ev.ts)
                current_task = ev.task_id
                current_start = ev.ts
            msg = f'Started task: {t.text if t else ev.task_id}'
            log.append(
                LogEntry(
                    ts=ev.ts,
                    message=msg,
                    stack_id=ev.stack_id,
                    stack_name=stack.name if stack else None,
                    tag=stack.tag if stack else None,
                    task_id=ev.task_id,
                    duration=None,
                    is_creation=True,
                )
            )

        elif ev.type == 'task_finished':
            # close current segment, then focus returns to parent
            t = ctx.tasks.get(ev.task_id) if ev.task_id else None
            stack_id = ev.stack_id
            stack = ctx.stacks.get(stack_id) if stack_id else None

            if tracking_on and current_task == ev.task_id:
                end_segment(ev.ts)
                # move focus up to parent
                parent_id = ctx.task_parent.get(ev.task_id) if ev.task_id else None
                current_task = parent_id
                current_start = ev.ts if parent_id else None

                if parent_id:
                    p = ctx.tasks.get(parent_id)
                    task_text = t.text if t else ev.task_id
                    parent_text = p.text if p else parent_id
                    msg = f'Finished {task_text}, continue {parent_text}'
                    # time from here will belong to the parent task
                    log.append(
                        LogEntry(
                            ts=ev.ts,
                            message=msg,
                            stack_id=stack_id,
                            stack_name=stack.name if stack else None,
                            tag=stack.tag if stack else None,
                            task_id=parent_id,
                            duration=None,
                            is_finish=True,
                        )
                    )
                else:
                    msg = f'Finished {t.text if t else ev.task_id}, no active parent'
                    log.append(
                        LogEntry(
                            ts=ev.ts,
                            message=msg,
                            stack_id=stack_id,
                            stack_name=stack.name if stack else None,
                            tag=stack.tag if stack else None,
                            task_id=None,
                            duration=None,
                            is_finish=True,
                        )
                    )

            else:
                msg = f'Finished task: {t.text if t else ev.task_id}'
                log.append(
                    LogEntry(
                        ts=ev.ts,
                        message=msg,
                        stack_id=stack_id,
                        stack_name=stack.name if stack else None,
                        tag=stack.tag if stack else None,
                        task_id=ev.task_id,
                        duration=None,
                        is_finish=True,
                    )
                )

        elif ev.type == 'stack_created':
            s = ctx.stacks.get(ev.stack_id) if ev.stack_id else None
            log.append(
                LogEntry(
                    ts=ev.ts,
                    message=f'Stack created: {s.name if s else ev.stack_id}',
                    stack_id=ev.stack_id,
                    stack_name=s.name if s else None,
                    tag=s.tag if s else None,
                    task_id=None,
                    duration=None,
                    is_creation=True,
                )
            )

        elif ev.type == 'stack_finished':
            # finishing a stack does NOT assign time to specific task
            if tracking_on and current_task and ctx.stack_by_task.get(current_task) == ev.stack_id:
                end_segment(ev.ts)
                current_task = None
                current_start = None
            s = ctx.stacks.get(ev.stack_id) if ev.stack_id else None
            log.append(
                LogEntry(
                    ts=ev.ts,
                    message=f'Stack finished: {s.name if s else ev.stack_id}',
                    stack_id=ev.stack_id,
                    stack_name=s.name if s else None,
                    tag=s.tag if s else None,
                    task_id=None,
                    duration=None,
                    is_finish=True,
                )
            )

    return log
