local builtin = require('telescope.builtin')

vim.g.mapleader = " "

vim.keymap.set("v", "J", ":m '>+1<CR>gv=gv")
vim.keymap.set("v", "K", ":m '<-2<CR>gv=gv")

vim.keymap.set("n", '<leader>pv', vim.cmd.Ex)

vim.keymap.set("n", "<leader>st", function()
    vim.cmd.vnew()
    vim.cmd.term()
    vim.cmd.wincmd("J")
    vim.api.nvim_win_set_height(0, 10)
    vim.cmd.startinsert() 
end)

vim.keymap.set("t", "<leader><esc>", "<C-\\><C-n>:q<CR>")

-- Format on save
vim.api.nvim_create_autocmd("BufWritePre", {
  pattern = {
    "*.js",
    "*.jsx",
    "*.ts",
    "*.tsx",
    "*.svelte",
    "*.py",
  },
  callback = function()
    vim.lsp.buf.format()
  end,
})

vim.api.nvim_create_user_command('LspCapabilities', function()
    local clients = vim.lsp.get_active_clients()
    for _, client in pairs(clients) do
        print(string.format("Client: %s", client.name))
        print(vim.inspect(client.server_capabilities))
    end
end, {})

vim.keymap.set({'n', 'v'}, '<leader>-', '<cmd>Yazi<cr>', { desc = "Open yazi at the current file" })
vim.keymap.set('n', '<leader>cw', '<cmd>Yazi cwd<cr>', { desc = "Open the file manager in nvim's working directory" })
vim.keymap.set('n', '<c-up>', '<cmd>Yazi toggle<cr>', { desc = "Resume the last yazi session" })
