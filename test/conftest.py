import contextlib
import os
import socket
import subprocess
import tempfile
import time
from typing import Generator

import pynvim
import pytest


def find_free_port() -> int:
    """Find a free, available port number."""
    with socket.socket() as sock:
        sock.bind(("", 0))  # Bind to a free port provided by the host.
        return sock.getsockname()[1]


@pytest.fixture
def nvim_port() -> Generator[tuple[pynvim.Nvim, int], None, None]:
    """Get a temporary UNIX socket file."""
    # see cpython#93914
    tmp_socket = tempfile.mktemp(prefix="test_python_", suffix=".sock")
    port = find_free_port()
    port = str(port)
    process_server = subprocess.Popen(
        ["elva", "server", "-h", "localhost", "-p", port, "--unsafe"]
    )
    time.sleep(0.5)
    # do we need
    # `nvim -u vimrc --headless  -c "UpdateRemotePlugins" -c "q"`
    # before this?
    process_nvim = subprocess.Popen(
        [
            "nvim",
            "--headless",
            "-u",
            "./vimrc",
            "-c",
            f"ElvaConnect localhost {port} 1234567890",
            "--listen",
            tmp_socket,
        ]
    )
    try:
        time.sleep(1)  # wait a bit until nvim starts up
        nvim: pynvim.Nvim = pynvim.attach("socket", path=tmp_socket)
        yield (nvim, int(port))
    finally:
        with contextlib.suppress(OSError):
            process_nvim.terminate()
            process_server.terminate()
        if os.path.exists(tmp_socket):
            with contextlib.suppress(OSError):
                os.unlink(tmp_socket)
