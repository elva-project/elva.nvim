#!/usr/bin/env python3

"""Simple test script to verify Neovim plugin testing setup"""

import asyncio

import pytest
from elva.provider import WebsocketProvider
from pycrdt import Doc, Text
from pynvim import Nvim
from utils import nvim_get_buffer_lines, nvim_input_lines_at_cursor


def test_nvim_available(nvim_port: tuple[Nvim, int]):
    nvim, port = nvim_port

    assert 42 == nvim.eval("42")
    assert "?" == nvim.command_output('echo "?"')


@pytest.mark.asyncio
async def test_simple_ydoc_to_nvim_sync(nvim_port: tuple[Nvim, int]):
    nvim, port = nvim_port

    ydoc = Doc()
    ytext = Text()
    ydoc["ytext"] = ytext

    async with WebsocketProvider(
        ydoc, "1234567890", "localhost", port=port, safe=False
    ):
        # Wait for the connection to be established.
        # Use `asyncio.sleep` instead of `time.sleep` to not block the event loop.
        # await asyncio.sleep(1)

        ytext.insert(0, "hi")
        await asyncio.sleep(0.5)  # Wait for change to propagate

        # Run blocking nvim calls in a separate thread to avoid blocking the event loop
        lines = await asyncio.to_thread(nvim_get_buffer_lines, nvim)
        assert lines == ["hi"]


@pytest.mark.asyncio
async def test_simple_nvim_to_ydoc_sync(nvim_port: tuple[Nvim, int]):
    nvim, port = nvim_port

    ydoc = Doc()
    ytext = Text()
    ydoc["ytext"] = ytext

    provider = WebsocketProvider(ydoc, "1234567890", "localhost", port=port, safe=False)
    async with provider:
        await asyncio.to_thread(nvim_input_lines_at_cursor, nvim, ["hi"])
        await asyncio.sleep(0.5)  # Wait for change to propagatey
        assert str(ytext) == "hi"
