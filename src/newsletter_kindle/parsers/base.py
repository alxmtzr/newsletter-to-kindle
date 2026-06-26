from __future__ import annotations

from abc import ABC, abstractmethod

from newsletter_kindle.models import Newsletter, RawMessage


class Parser(ABC):
    @abstractmethod
    def parse(self, raw: RawMessage, metadata: dict[str, object]) -> Newsletter: ...
