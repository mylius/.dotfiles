require('telescope').setup{
  defaults = {
    file_ignore_patterns = {
      "node_modules",
      "dist",
      "build",
      ".git",
      ".next"
    }
  }
}

local builtin = require('telescope.builtin')

-- Rest of your keymaps
vim.keymap.set('n', '<C-p>', builtin.git_files, {})
vim.keymap.set('n', '<leader>pf', builtin.find_files, {})
vim.keymap.set('n', '<leader>vh', builtin.help_tags, {})
vim.keymap.set('n', '<leader>ps', builtin.live_grep, {})
vim.keymap.set('n', '<leader>pg', builtin.treesitter, {})
vim.keymap.set('n', '<leader>gd', builtin.lsp_definitions, {})
vim.keymap.set('n', '<keader>ff', builtin.quickfix, {})
