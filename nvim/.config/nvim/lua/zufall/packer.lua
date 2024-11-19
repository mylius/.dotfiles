
 -- This file can be loaded by calling `lua require('plugins')` from your init.vim

-- Only required if you have packer configured as `opt`
vim.cmd [[packadd packer.nvim]]

return require('packer').startup(function(use)
  -- Packer can manage itself
  use 'wbthomason/packer.nvim'

  use {
  'nvim-telescope/telescope.nvim', tag = '0.1.6',
-- or                            , branch = '0.1.x',
  requires = { {'nvim-lua/plenary.nvim'} }
}

use "olimorris/onedarkpro.nvim"

use ('nvim-treesitter/nvim-treesitter', {run= ':TSUpdate'})
use ('theprimeagen/harpoon')
use ('theprimeagen/vim-be-good')
use ('mbbill/undotree')
use ('tpope/vim-fugitive')
use ('mfussenegger/nvim-dap')
ususe {'mfussenegger/nvim-dap-python'}
e {'mfussenegger/nvim-dap-python',
  requires = {"mfussenegger/nvim-dap", "rcarriga/nvim-dap-ui"},
  config = function()
    local dap_python = require("dap-python")
    
    -- Function to find the Python path
    local function get_python_path()
      local cwd = vim.fn.getcwd()
      if vim.fn.executable(cwd .. '/venv/bin/python') == 1 then
        return cwd .. '/venv/bin/python'
      elseif vim.fn.executable(cwd .. '/.venv/bin/python') == 1 then
        return cwd .. '/.venv/bin/python'
      else
        return '~/miniconda3/envs/zufall/bin/python'
      end
    end

    -- Setup dap-python
    dap_python.setup(get_python_path())

    -- Set Python path for debugging
    table.insert(require('dap').configurations.python, {
      type = 'python',
      request = 'launch',
      name = 'Python: Current File',
      program = '${file}',
      pythonPath = get_python_path,
    })
  end
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
    --- Uncomment the two plugins below if you want to manage the language servers from neovim
    -- {'williamboman/mason.nvim'},
    -- {'williamboman/mason-lspconfig.nvim'},

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

