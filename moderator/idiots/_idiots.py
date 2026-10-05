###################
# Created : 2026-10-03 GB
# Purpose : Maintains the moderator's authoritative live registry of connected idiots.
# Notes   : The registry is runtime state only; durable persistence will be added later.
###################

from idiots.idiot import Idiot


class IdiotAlreadyConnectedError(ValueError):
    pass


class IdiotRegistry:
    @staticmethod
    def _key(name):
        return name.casefold()

    def __init__(self):
        self._idiots = {}

    def add(self, idiot: Idiot):
        key = self._key(idiot.name)

        if key in self._idiots:
            raise IdiotAlreadyConnectedError(
                f'Idiot "{idiot.name}" is already connected.'
            )

        self._idiots[key] = idiot

    def get(self, name):
        return self._idiots.get(self._key(name))

    def idiots(self):
        return list(self._idiots.values())

    def remove(self, idiot: Idiot):
        key = self._key(idiot.name)

        if self._idiots.get(key) is idiot:
            del self._idiots[key]

    def snapshot(self):
        return [
            {
                "connected_at": idiot.connected_at.isoformat(),
                "connection_id": str(idiot.connection_id),
                "name": idiot.name,
                "state": idiot.state,
                "trace": idiot.trace
            }
            for idiot in sorted(
                self._idiots.values(),
                key=lambda item: item.name.casefold()
            )
        ]
