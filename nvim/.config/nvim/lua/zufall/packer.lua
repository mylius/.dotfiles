
 -- This file can be loaded by calling `lua require('plugins')` from your init.vim

-- Only required if you have packer configured as `opt`
vim.cmd [[packadd packer.nvim]]

return require('packer').startup(function(use)
  -- Packer can manage itself
  use 'wbthomason/packer.nvim'

  use {
  'nvim-telescope/telescope.nvim', requires = {
        'nvim-lua/plenary.nvim',
    }      
}

use "olimorris/onedarkpro.nvim"
use ('nvim-treesitter/nvim-treesitter', {run= ':TSUpdate'})
use 'nvim-treesitter/nvim-treesitter-refactor'
use ('theprimeagen/harpoon')
use ('theprimeagen/vim-be-good')
use ('mbbill/undotree')
use ('tpope/vim-fugitive')
use ('airblade/vim-gitgutter')
use {
  'f-person/git-blame.nvim',
  config = function()
    require('gitblame').setup {
      enabled = true,
      date_format = '%r',
      message_template = '  <author> • <date> • <summary>',
      highlight_group = "LineNr",
    }
  end
}
use {"folke/todo-comments.nvim", requires = "nvim-lua/plenary.nvim"}
use {
  'mikavilpas/yazi.nvim',
  config = function()
    vim.keymap.set({'n', 'v'}, '<leader>-', '<cmd>Yazi<cr>', { desc = "Open yazi at current file" })
    vim.keymap.set('n', '<leader>cw', '<cmd>Yazi cwd<cr>', { desc = "Open in working directory" })
    vim.keymap.set('n', '<c-up>', '<cmd>Yazi toggle<cr>', { desc = "Resume last session" })
  end
}
use ('mfussenegger/nvim-dap')
use {
  'mfussenegger/nvim-dap-python',
  requires = {"mfussenegger/nvim-dap", "rcarriga/nvim-dap-ui"}
}
use {
  "supermaven-inc/supermaven-nvim",
  config = function()
    require("supermaven-nvim").setup({})
  end,
}
use { "rcarriga/nvim-dap-ui", requires = {"mfussenegger/nvim-dap", "nvim-neotest/nvim-nio"}} 
use {
  'VonHeikemen/lsp-zero.nvim',
  branch = 'v3.x',
  requires = {

    {'neovim/nvim-lspconfig'},
    {'hrsh7th/nvim-cmp'},
    {'hrsh7th/cmp-nvim-lsp'},
    {'hrsh7th/cmp-buffer'},
    {'hrsh7th/cmp-path'},
    {'L3MON4D3/LuaSnip'},
    {'williamboman/mason.nvim'},
    {'williamboman/mason-lspconfig.nvim'},
    {'saadparwaiz1/cmp_luasnip'},
    {'L3MON4D3/LuaSnip'},
    {'rafamadriz/friendly-snippets'},

          -- null-ls and mason-null-ls for formatting
      {'jose-elias-alvarez/null-ls.nvim'},
      {'jay-babu/mason-null-ls.nvim'}
  }
}
end)

