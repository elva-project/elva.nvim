local M = {}

function M.attach(bufnr)
    bufnr = bufnr or vim.api.nvim_get_current_buf()
    -- Listen to byte-level changes to sync with Yjs (which uses linear indices)
    local attached = vim.api.nvim_buf_attach(bufnr, false, {
        on_bytes = function(_str_bytes, _bufnr, _changedtick, start_row, start_col, byte_offset, _old_end_row, _old_end_col, old_byte_len, new_row, new_col, new_byte_len)
            local new_text = ""
            vim.notify("Elva: buffer changed")
            vim.fn.ElvaLogDebug("_bufnr = ", _bufnr, "start_row =", start_row, "start_col =", start_col, "byte_offset = ", byte_offset, "old_byte_len =", old_byte_len, "new_byte_len =", new_byte_len)
            
            if new_byte_len > 0 then
                local end_row = start_row + new_row
                local end_col
                if new_row == 0 then
                    end_col = start_col + new_col
                else
                    end_col = new_col
                end

                local status, lines = pcall(vim.api.nvim_buf_get_text, bufnr, start_row, start_col, end_row, end_col, {})
                --local lines = vim.api.nvim_buf_get_text(bufnr, start_row, start_col, end_row, end_col, {})
                if status then
                    new_text = table.concat(lines, "\n")
                else
                    -- catch the pressed `o` on last line error and set `new_text` manually 
                    byte_offset = byte_offset - 1 -- we don't use byte_offset so we don't have to change it,
                                                    -- but it is different for `o` and Enter on the last line
                    new_text = "\n"
                end

            end
            -- Forward the change to the Python host
            -- new_bytes is passed as a string (or bytes in msgpack)
            vim.fn.ElvaOnBytes(bufnr, start_row, start_col, byte_offset, old_byte_len, new_text)
        end
    })
    if not attached then
        vim.notify("Elva: Failed to attach to buffer " .. bufnr, vim.log.levels.ERROR)
    end

    -- Awareness: Track local cursor movements
    local group = vim.api.nvim_create_augroup("ElvaAwareness" .. bufnr, { clear = true })
    vim.api.nvim_create_autocmd({"CursorMoved", "CursorMovedI"}, {
        group = group,
        buffer = bufnr,
        callback = function()
            local cursor = vim.api.nvim_win_get_cursor(0)
            -- cursor is {row, col} (1-based row, 0-based col)
            vim.fn.ElvaOnCursorMoved(bufnr, cursor[1] - 1, cursor[2])
        end
    })
end





return M
