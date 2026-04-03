"""JSON-backed persistence for the weekly automation job state."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AutomationState:
    """Persisted state for the weekly invoice automation job."""

    last_attempt_at: str = ""
    last_success_at: str = ""
    processed_message_ids: list[str] = field(default_factory=list)
    downloaded_attachment_hashes: list[str] = field(default_factory=list)
    last_task_summary: dict[str, object] = field(default_factory=dict)


class AutomationStateStore:
    """Store automation state as a small UTF-8 JSON document."""

    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file

    def load(self) -> AutomationState:
        """Load the saved state or return the default empty state."""
        if not self.state_file.exists():
            return AutomationState()

        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        return AutomationState(
            last_attempt_at=data.get("last_attempt_at", ""),
            last_success_at=data.get("last_success_at", ""),
            processed_message_ids=list(data.get("processed_message_ids", [])),
            downloaded_attachment_hashes=list(
                data.get("downloaded_attachment_hashes", [])
            ),
            last_task_summary=dict(data.get("last_task_summary", {})),
        )

    def save(self, state: AutomationState) -> Path:
        """Persist state and preserve the last success cursor on failed runs."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        if self.state_file.exists():
            existing = self.load()
            if not state.last_success_at and existing.last_success_at:
                state = AutomationState(
                    last_attempt_at=state.last_attempt_at,
                    last_success_at=existing.last_success_at,
                    processed_message_ids=list(state.processed_message_ids),
                    downloaded_attachment_hashes=list(
                        state.downloaded_attachment_hashes
                    ),
                    last_task_summary=dict(state.last_task_summary),
                )

        self.state_file.write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.state_file
