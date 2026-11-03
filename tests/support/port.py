"""tests/support/port: a localhost port nobody listens on, for a server a test opens and closes."""

import socket


def free_port() -> int:
    """A port the kernel just handed out and released: free unless another process grabs it in between."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
