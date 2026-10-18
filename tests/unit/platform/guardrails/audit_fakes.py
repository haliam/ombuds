"""An in-memory `AuditLog` for unit tests of the audited wrappers."""

from ombuds.platform.guardrails.audit_log import AuditEvent


class RecordingAuditLog:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)
