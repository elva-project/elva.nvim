from pynvim import Nvim


def nvim_get_buffer_lines(nvim: Nvim):
    return nvim.current.buffer[:]


def nvim_input_lines_at_cursor(nvim: Nvim, lines: list[str]):
    nvim.api.put(lines, "c", True, False)


def nvim_multi_input(nvim: Nvim, *commands: list[str]):
    for command in commands:
        nvim.input(command)


def nvim_set_cursor(nvim: Nvim, row: int, col: int):
    nvim.api.win_set_cursor(0, (row, col))
