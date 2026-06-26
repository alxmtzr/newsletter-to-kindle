from __future__ import annotations

from abc import ABC, abstractmethod

from newsletter_kindle.models import Document, SendReceipt
from newsletter_kindle.state.db import StateDB


class Sender(ABC):
    @abstractmethod
    def send(self, document: Document, attempt_no: int) -> SendReceipt: ...

    def reconcile(self, db: StateDB) -> None:  # noqa: B027
        """Check for async outcomes (e.g. Amazon bounce emails). No-op by default."""
