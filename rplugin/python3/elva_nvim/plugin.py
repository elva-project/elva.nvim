import pynvim
import asyncio
import logging
import sys
from pathlib import Path
import greenlet
#try:
from elva.provider import WebsocketProvider
from pycrdt import Doc, Text
from elva.awareness import Awareness
from pynvim import Nvim
#except ImportError:
#    # This might happen during initial setup before paths are correct
#    Doc = None
#    WebsocketProvider = None
#    Awareness = None


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
        buf = win.buffer # current buffer
        #buf = self.nvim.current.buffer
        buf_id = buf.number
        win_id = win.number
        #self.nvim.session.

        
        if buf_id in self.buffers:
            self.nvim.out_write(f"Buffer {buf_id} is already connected.\n")
            return
        

        # Attach the Lua listener for local changes
        #self.nvim.exec_lua("require('elva').attach(...)", buf_id)
        self.attach_callback(buf_id)
        self.nvim.async_call(self._connect, host, port, room, buf_id)

    def attach_callback(self, buf_id):
        """
            Attatch on_bytes_callback (nvim fn name `ElvaOnBytesCallback`) to the buffer
        """
        self.nvim.exec_lua("""
                           local attached = vim.api.nvim_buf_attach(..., false, {
                                    on_bytes=function(_str_bytes, _bufnr, _changedtick, start_row, start_col, byte_offset, _old_end_row, _old_end_col, old_byte_len, new_row, new_col, new_byte_len)
                                                vim.fn.ElvaOnBytesCallback(_str_bytes, _bufnr, _changedtick, start_row, start_col, byte_offset, _old_end_row, _old_end_col, old_byte_len, new_row, new_col, new_byte_len)
                                            end
                               })
                           """, buf_id)

    @pynvim.function('ElvaOnBytesCallback', sync=False)
    def on_bytes_callback(self, args:list):
        _str_bytes, _bufnr, _changedtick, start_row, start_col, byte_offset, _old_end_row, _old_end_col, old_byte_len, new_row, new_col, new_byte_len = args
        self.logger.debug("ElvaOnBytesWrapper called")
        self.logger.debug(f" {_bufnr = }, {start_row = }, {start_col = }, {byte_offset = }, {old_byte_len = }, {new_byte_len =}, {new_col =}")
        
        if new_byte_len is None:
            pass
                
        if _bufnr not in self.buffers:
            return

        if self.buffers[_bufnr]["applying_remote"]:
            return
        
        new_text = ""

        if new_byte_len > 0:
            end_row = start_row + new_row
            #if new_col == 0:
            #    end_col = start_col + new_col
            #else:
            #    end_col = new_col
            end_col = start_col + new_col # works

        
            try:
                lines = self.nvim.api.buf_get_text(_bufnr, start_row, start_col, end_row, end_col, {})
                self.logger.debug(str(lines))
                new_text = "\n".join(lines)
            except:
                #start_row -= 1
                byte_offset -= 1  # we don't use byte_offset so we don't have to change it,
                                                # but it is different for `o` and Enter on the last line

                new_text = "\n"
            

        self.on_bytes([_bufnr, start_row, start_col, byte_offset, old_byte_len, new_text])

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
        except Exception as e:
            self.logger.exception("Failed to apply remote change")
        finally:
            state["applying_remote"] = False

        awareness: Awareness = self.buffers[buf_id]["awareness"]
        
        self.logger.debug(str(awareness.client_states))

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


    #@pynvim.function('ElvaOnBytes', sync=False)
    def on_bytes(self, args):
        """Handle local changes from Neovim."""
        buf_id, start_row, start_col, byte_offset, old_byte_len, new_bytes = args
        # byte_offset is not used, remove it?

        self.logger.debug("ElvaOnBytes called")
        self.logger.debug(f" {buf_id = }, {start_row = }, {start_col = }, {byte_offset = }, {old_byte_len = }, {new_bytes = }")
        
        if buf_id not in self.buffers:
            return

        state = self.buffers[buf_id]
        if state["applying_remote"]:
            return

        ytext = state["ytext"]
        
        # Decode bytes to string for Yjs (assuming UTF-8 buffer)
        if isinstance(new_bytes, bytes):
            new_text = new_bytes.decode('utf-8')
        else:
            new_text = new_bytes

        # Apply to YText
        with state["ydoc"].transaction(origin="nvim"):
            # Convert byte offset to char offset for Yjs
            # We use the current ytext state (which matches pre-edit buffer) to find the position
            char_offset = self._get_char_offset(ytext, start_row, start_col)
            
            if old_byte_len > 0:
                # Calculate how many characters correspond to the deleted bytes
                del_len = self._get_delete_length(ytext, char_offset, old_byte_len)
                del ytext[char_offset: char_offset+del_len] 
            if new_text:
                ytext.insert(char_offset, new_text)

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

    def _get_delete_length(self, ytext, char_offset, byte_len):
        """Calculate how many chars starting at char_offset sum up to byte_len bytes."""
        if byte_len == 0:
            return 0
        text = str(ytext)
        current_bytes = 0
        count = 0
        i = char_offset
        while current_bytes < byte_len and i < len(text):
            char = text[i]
            current_bytes += len(char.encode('utf-8'))
            count += 1
            i += 1
        return count



    @pynvim.function('ElvaLogDebug', sync=False)
    def on_text(self, args):
        self.logger.debug(" ".join(map(str, args)))
