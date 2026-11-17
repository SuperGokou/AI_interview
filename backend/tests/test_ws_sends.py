"""Only one task may write to the interview socket at a time."""

import asyncio

from app.api.interview_ws import _serialize_sends


class _Socket:
    """Fails the way the websocket library does when two sends overlap."""

    def __init__(self):
        self.busy = False
        self.sent = []

    async def send(self, message):
        assert not self.busy, "two tasks are writing to the socket at once"
        self.busy = True
        await asyncio.sleep(0.005)  # the connection is backed up
        self.sent.append(message)
        self.busy = False


def test_concurrent_sends_are_queued_not_interleaved():
    async def scenario():
        ws = _Socket()
        _serialize_sends(ws)
        await asyncio.gather(*(ws.send(n) for n in range(20)))
        return ws.sent

    assert asyncio.run(scenario()) == list(range(20))
