###################
# Created : 2026-10-03 GB
# Purpose : Defines the runtime identity and connection state of a D.I.P.S.H.I.T. idiot.
# Notes   : Runtime entities are intentionally independent of future persistence.
###################

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(slots=True)
class Personality:
    curiosity: int
    friendliness: int
    sociability: int


@dataclass(slots=True)
class Idiot:
    name: str
    personality: Personality
    connected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    connection_id: UUID = field(default_factory=uuid4)
    state: str = "IDLE"
    trace: str = ""

    def connected_payload(self):
        return {
            "connection_id": str(self.connection_id),
            "name": self.name,
            "state": self.state,
            "type": "connected"
        }
