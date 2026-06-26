from __future__ import annotations

from datetime import UTC

from newsletter_kindle.models import Newsletter


def test_newsletter_defaults() -> None:
    from datetime import datetime

    nl = Newsletter(
        source_name="test",
        title="Test",
        date="2024-01-15",
        message_id="<t1>",
        received_at=datetime(2024, 1, 15, tzinfo=UTC),
    )
    assert nl.sections == []
    assert nl.subjects == []
    assert nl.language == "en"
