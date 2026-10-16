"""Bounded main-thread diagnostics; clearing the view preserves evidence/state."""

from collections import deque


class DiagnosticHistory:
    def __init__(self, capacity=2000):
        self.records = deque(maxlen=capacity)
        self.total_messages = 0

    def append(self, message):
        self.total_messages += 1
        self.records.append((self.total_messages, message))


def append_visible_log(widget, history, message, visible_lines, limit=1000):
    for old, new in (("[SAFE]", "[INFO]"), ("[NOTICE]", "[WARN]"), ("[CANCELLED]", "[INFO]"), ("[READBACK MISMATCH]", "[READBACK]")):
        message = message.replace(old, new)
    if not message.startswith("["):
        message = "[INFO] " + message
    history.append(message)
    displayed = message[:4000]
    try:
        follow = float(widget.yview()[1]) >= .995
    except (AttributeError, TypeError, ValueError, IndexError):
        follow = True
    widget.configure(state="normal")
    widget.insert("end", displayed + "\n")
    visible_lines += displayed.count("\n") + 1
    if visible_lines > limit:
        widget.delete("1.0", f"{visible_lines - limit + 1}.0")
        visible_lines = limit
    if follow:
        widget.see("end")
    widget.configure(state="disabled")
    return visible_lines
