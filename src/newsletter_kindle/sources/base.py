from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from newsletter_kindle.models import RawMessage


class Source(ABC):
    @abstractmethod
    def fetch_new(self, known_ids: set[str]) -> Iterator[RawMessage]: ...
