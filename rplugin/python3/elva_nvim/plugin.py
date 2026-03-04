import asyncio
import logging
import sys
import time
from pathlib import Path

import greenlet
import pynvim
from elva.awareness import Awareness
from elva.provider import WebsocketProvider
from pycrdt import Doc, Text
from pynvim import Nvim, NvimError

# Add the local elva library to sys.path
# Assuming the structure is vim_elva/elva and vim_elva/rplugin/...
PROJECT_ROOT = Path(__file__).parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pynvim.plugin
class ElvaPlugin:
    def __init__(self, nvim: Nvim):
        self.nvim: Nvim  = nvim
        self.buffers = {}  # buf_id -> {ydoc, provider, awareness, applying_remote}
        
        # Setup logging
        self.logger = logging.getLogger("elva_nvim")
        self.logger.setLevel(logging.DEBUG)
        # Log to a file in the plugin directory for debugging
        #log_file = Path(__file__).parent / "elva_nvim.log"
        log_file = Path("./elva_nvim.log")
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    @pynvim.command('ElvaConnect', nargs='+', sync=False)
    def connect(self, args):
        if not Doc:
            self.nvim.out_write("pycrdt library not found. Please check your installation.\n")
        if not WebsocketProvider:
            self.nvim.out_write("Elva library not found. Please check your installation.\n")
            return

        if len(args) < 2:
            self.nvim.out_write("Usage: :ElvaConnect <host> <port> <room>\n")
            return

        host, port, room = args[0], args[1], args[2]
        win = self.nvim.current.window
        buf = win.buffer # self.nvim.current.buffer
        buf_id = buf.number
        # win_id = win.number

        
        if buf_id in self.buffers:
            self.nvim.out_write(f"Buffer {buf_id} is already connected.\n")
            return
        self.attach_callback(buf_id)
        self.nvim.async_call(self._connect, host, port, room, buf_id)

    def attach_callback(self, buf_id):
        """
            Attatch on_bytes_callback (nvim fn name `ElvaOnBytesCallback`) to the buffer
        """
        self.nvim.exec_lua("""
                           local attached = vim.api.nvim_buf_attach(..., false, {
                                    on_bytes=function(...)
                                                vim.fn.ElvaOnBytesCallback(...)
                                            end
                               })
                           """, buf_id)


    # the reported positions of on_bytes are just bugged rn
    # if we wanna attatch to line changes `on_lines` callback:
    # it's documented here: https://github.com/neovim/neovim/blob/6435c61bd61ce910da6659394d918f7f36e932ba/runtime/doc/api.txt#L2306
    # nvim_buf_get_lines

    @pynvim.function('ElvaOnBytesCallback', sync=False)
    def on_bytes_callback(self, args:list):
        """
        on_bytes:
        Called on granular changes (compared to on_lines). Not called on buffer
        reload (`:checktime`, `:edit`, …), see `on_reload:`. Return a [lua-truthy] value
        to detach.
        
        Args:
        - the string "bytes"
        - buffer id
        - b:changedtick
        - start row of the changed text (zero-indexed)
        - start column of the changed text
        - byte offset of the changed text (from the start of
            the buffer)
        - old end row of the changed text (offset from start row)
        - old end column of the changed text
            (if old end row = 0, offset from start column)
        - old end byte length of the changed text
        - new end row of the changed text (offset from start row)
        - new end column of the changed text
            (if new end row = 0, offset from start column)
        - new end byte length of the changed text

        source: https://github.com/neovim/neovim/blob/08f4811061c9fde22b730e5d73f7fb49f61f7184/src/nvim/api/buffer.c#L139
        """
        _str_bytes, _bufnr, _changedtick, start_row, start_col, byte_offset, _old_end_row, _old_end_col, old_byte_len, new_row, new_col, new_byte_len = args
        self.logger.debug("ElvaOnBytesCallback called")
        #self.logger.debug(f" {_bufnr = }, {start_row = }, {start_col = }, {byte_offset = }, {old_byte_len = }, {new_byte_len =}, {new_col =}, {new_row =}")
        self.logger.debug(f"{start_row = }, {start_col = }, {byte_offset = }, {_old_end_row = }, {_old_end_col = }, {old_byte_len = }, {new_row = }, {new_col = }, {new_byte_len = }")
                
        if _bufnr not in self.buffers:
            return

        if self.buffers[_bufnr]["applying_remote"]:
            self.logger.debug("ElvaOnBytesCallback doing nothing because of remote update")
            return
        
        new_text = ""

        end_row = start_row + new_row

        # from doc string:
        # - new end column of the changed text
        #     (if new end row = 0, offset from start column)
        if new_row == 0:
            end_col = start_col + new_col
        else:
            end_col = new_col
        
        if old_byte_len > 0:  # we are deleting somthing
            if new_row-start_row == 1: # there is 1 new line
                if new_byte_len == 1: # only one new byte -> only line
                    # new_text = ""
                    new_byte_len = 0
                    end_row = start_row
                    # we could call on_bytes and return here


        if new_byte_len > 0:
            try:
                lines = self.nvim.api.buf_get_text(_bufnr, start_row, start_col, end_row, end_col, {})
                self.logger.debug(str(lines))
                new_text = "\n".join(lines)
            except NvimError as e:
                # The exception is expected and not helpful!
                # This is probably an neovim bug if the second buf_get_text doesn't raise an exception!
                # It only happens in buffer changes including the last line of the buffer
                # For more info see: https://github.com/neovim/neovim/issues/37989
                self.logger.debug("Got expected Exception in on_bytes_callback from nvim.api.buf_get_text")
                # if this is not followed by a second exception this is an expected neovim index bug of the on_bytes callback from nvim_buf_attach
                assert str(e) == "Index out of bounds" # if this fails it's not the neovim bug

                if new_byte_len == 1:
                    new_text = "\n"
                    byte_offset -= 1
                elif new_byte_len > 1: # inserting more then a newline
                    end_col = self.nvim.api.buf_get_offset(_bufnr, end_row-1)
                    lines = self.nvim.api.buf_get_text(_bufnr, start_row, start_col, end_row-1, end_col, {})
                    new_text += "\n".join(lines)
        
        self.nvim.async_call(self.on_bytes, _bufnr, start_row, start_col, byte_offset, old_byte_len, new_byte_len, new_text)

    def _connect(self, host, port, room, buf_id):
        self.logger.info(f"Starting session for buffer {buf_id} in room {room}")
        ydoc = Doc()
        ytext = Text()
        ydoc["ytext"] = ytext

        provider = WebsocketProvider(ydoc, room, host, port=port, safe=False)
        awareness: Awareness = provider.awareness

        self.nvim.windows


        self.buffers[buf_id] = {
            "ydoc": ydoc,
            "ytext": ytext,
            "provider": provider,
            "awareness": awareness,
            "applying_remote": False
        }

        # Observe remote changes
        ytext.observe(lambda event, transaction: self.on_remote_change(buf_id, event, transaction))

        self.nvim.out_write(f"Elva: Connected to {room}\n")

        self.nvim.async_call(self.start_session, provider)

        # Start the async session
        asyncio.create_task(self.start_session(provider))

    async def start_session(self, provider):
        try:
            # Start the provider (assuming it's an async context manager)
            async with provider:
                await asyncio.Future()  # Keep running until cancelled

        except Exception as e:
            self.logger.exception("Error in Elva session")
            self.nvim.err_write(f"Elva Error: {e}\n")

    def on_remote_change(self, buf_id, event, transaction):
        """Handle remote changes from Yjs."""

        if hasattr(transaction, 'origin'):
            self.logger.debug(f"transaction origion: {transaction.origin}")
            if transaction.origin == "nvim":
                return
        
        # Schedule the update on the main thread
        gr = greenlet.greenlet(lambda:self.nvim.async_call(self._apply_remote_change_safe, buf_id, event))
        gr.switch()
        #self.nvim.async_call(self._apply_remote_change_safe, buf_id, event)

    def _apply_remote_change_safe(self, buf_id, event):
        state = self.buffers.get(buf_id)
        if not state:
            return


        state["applying_remote"] = True
        try:
            # We need to track the current position in the Neovim buffer as we apply edits.
            # (row, col) are 0-indexed.
            cur_row, cur_col = 0, 0
            
            for delta in event.delta:
                if 'retain' in delta:
                    count = delta['retain']
                    # Advance our cursor by 'count' characters in the buffer
                    cur_row, cur_col = self._advance_position(buf_id, cur_row, cur_col, count)
                    
                elif 'insert' in delta:
                    text = delta['insert']
                    lines = text.split('\n')
                    
                    # Insert text at current position
                    self.nvim.api.buf_set_text(buf_id, cur_row, cur_col, cur_row, cur_col, lines)
                    
                    # Advance cursor by the length of inserted text
                    # We can calculate this directly from the text we just inserted
                    if len(lines) == 1:
                        cur_col += len(lines[0].encode('utf-8')) # Neovim cols are bytes
                    else:
                        cur_row += len(lines) - 1
                        cur_col = len(lines[-1].encode('utf-8'))
                    
                elif 'delete' in delta:
                    length = delta['delete']
                    # Determine the end position of the deletion
                    end_row, end_col = self._advance_position(buf_id, cur_row, cur_col, length)
                    
                    # Delete text
                    self.nvim.api.buf_set_text(buf_id, cur_row, cur_col, end_row, end_col, [])
                    # Cursor stays at start of deletion
        except Exception:
            self.logger.exception("Failed to apply remote change")
        finally:
            state["applying_remote"] = False

        #awareness: Awareness = self.buffers[buf_id]["awareness"]

        #self.logger.debug(str(awareness.client_states))

    def _advance_position(self, buf_id, row, col, char_count):
        """Advance (row, col) by char_count characters based on buffer content."""
        remaining = char_count
        cur_row, cur_col = row, col
        
        while remaining > 0:
            # Get current line content
            lines = self.nvim.api.buf_get_lines(buf_id, cur_row, cur_row + 1, False)
            if not lines:
                break
            line = lines[0]
            
            # Decode current line part to chars
            # cur_col is in bytes
            text_part = line.encode('utf-8')[cur_col:].decode('utf-8')
            
            if remaining <= len(text_part):
                # Target is on this line
                # Convert char count back to bytes for the new column
                added_bytes = len(text_part[:remaining].encode('utf-8'))
                return cur_row, cur_col + added_bytes
            else:
                # Skip to next line
                remaining -= (len(text_part) + 1) # +1 for newline
                cur_row += 1
                cur_col = 0
        
        return cur_row, cur_col

    def on_bytes(self, buf_id, start_row, start_col, byte_offset, old_byte_len, new_byte_len, new_text):
        """Handle local changes from Neovim."""
        deleted_state, inserted_state = False, False

        self.logger.debug("ElvaOnBytes called")
        self.logger.debug(f" {buf_id = }, {start_row = }, {start_col = }, {byte_offset = }, {old_byte_len = }, {new_byte_len =}, {new_text = }")
        state = self.buffers[buf_id]
        ytext = state["ytext"]

        # Apply to YText
        with state["ydoc"].transaction(origin="nvim"):
            buffer_size = len(ytext)
            self.logger.debug(f"{buffer_size = }")

            if old_byte_len > 0:
                del_len = old_byte_len

                self.logger.debug(f"got: {byte_offset = }, {del_len = }")
                if byte_offset + del_len > buffer_size:
                    if buffer_size - del_len >= 0: # nur >?
                        byte_offset =  buffer_size - del_len
                    elif del_len == 1:
                        del_len = 0
                    else:
                        byte_offset = 0
                        del_len = buffer_size+1

                if del_len != 0:

                    self.logger.debug(f"deleting at {byte_offset = }, {del_len = }")
                    del ytext[byte_offset: byte_offset+del_len]
                    self.logger.debug(f"sucessfully deleted {byte_offset = }, {del_len = }")
                    deleted_state = True
                else:
                    self.logger.debug(f"not deleting at {byte_offset = } because {del_len = }")
            if new_text:
                if byte_offset - buffer_size == 1:
                    new_text = "\n" + new_text
                self.logger.debug(f"inserting at {byte_offset =}, {new_text =}")
                ytext.insert(byte_offset, new_text)
                inserted_state = True

            new_buffer_size = len(ytext)
            self.logger.debug(f"on_bytes done with {int(deleted_state)} delete and {int(inserted_state)} insert operation,  {new_buffer_size = }")
            
            
    @pynvim.function('ElvaOnCursorMoved', sync=False)
    def on_cursor_moved(self, args):
        """Handle cursor movements from Neovim."""
        buf_id, row, col = args
        
        if buf_id not in self.buffers:
            return
            
        state = self.buffers[buf_id]
        ytext = state["ytext"]
        awareness: Awareness = state["awareness"]
        
        try:
            # Convert (row, col_bytes) to absolute character offset
            index = self._get_char_offset(ytext, row, col)
            
            # Update local awareness state
            current_state = awareness.get_local_state() or {}
            
            # Update cursor info (standard Yjs format)
            current_state["cursor"] = {
                "anchor": index,
                "head": index
            }
            
            awareness.set_local_state(current_state)
            
        except Exception as e:
            self.logger.error(f"Error updating cursor: {e}")

    def _get_char_offset(self, ytext, row, col_bytes):
        """Convert (row, col_bytes) to absolute character offset in ytext."""
        text = str(ytext)
        lines = text.split('\n')
        
        offset = 0
        # Sum lengths of previous lines
        for i in range(min(row, len(lines))):
            offset += len(lines[i]) + 1  # +1 for newline
            
        # Add column offset
        if row < len(lines):
            line = lines[row]
            # Count chars that fit in col_bytes
            try:
                # Neovim ensures valid UTF-8 split at cursor
                byte_slice = line.encode('utf-8')[:col_bytes]
                offset += len(byte_slice.decode('utf-8'))
            except Exception:
                pass
        return offset


    @pynvim.function('ElvaLogDebug', sync=False)
    def on_text(self, args):
        self.logger.debug(" ".join(map(str, args)))
