-- Ensure lsp.extend_lspconfig() is called before any lspconfig setups

local lsp = require('lsp-zero')
lsp.extend_lspconfig()


vim.api.nvim_create_autocmd('LspAttach', {
  group = vim.api.nvim_create_augroup('user_lsp_attach', {clear = true}),
  callback = function(event)
    local opts = {buffer = event.buf}

    vim.keymap.set('n', 'gd', function() vim.lsp.buf.definition() end, opts)
    vim.keymap.set('n', 'gr', function() vim.lsp.buf.references() end, opts)
    vim.keymap.set('n', 'K', function() vim.lsp.buf.hover() end, opts)
    vim.keymap.set('n', '<leader>vws', function() vim.lsp.buf.workspace_symbol() end, opts)
    vim.keymap.set('n', '<leader>vd', function() vim.diagnostic.open_float() end, opts)
    vim.keymap.set('n', '[d', function() vim.diagnostic.goto_next() end, opts)
    vim.keymap.set('n', ']d', function() vim.diagnostic.goto_prev() end, opts)
    vim.keymap.set('n', '<leader>vca', function() vim.lsp.buf.code_action() end, opts)
    vim.keymap.set('n', '<leader>vrr', function() vim.lsp.buf.references() end, opts)
    vim.keymap.set('n', '<leader>vrn', function() vim.lsp.buf.rename() end, opts)
    vim.keymap.set('i', '<C-h>', function() vim.lsp.buf.signature_help() end, opts)
  end,
})

local lsp_capabilities = require('cmp_nvim_lsp').default_capabilities()


require('mason').setup({})
require'nvim-treesitter.configs'.setup {
  ensure_installed = "python",
  highlight = {
    enable = true,
  },
}

require("mason-null-ls").setup({
  ensure_installed = { 
    -- Python formatters/linters
    "black",
    "ruff",
    "debugpy",
    -- JavaScript/TypeScript/Svelte formatters/linters
    "prettier",
    "eslint_d",
    -- Other tools you already had
    "gofmt", 
    "zig fmt"
  }
})

local null_ls = require("null-ls")

null_ls.setup({
  sources = {
    -- Python
    null_ls.builtins.formatting.black,
    null_ls.builtins.diagnostics.ruff,
    
    -- JavaScript/TypeScript/Svelte
    null_ls.builtins.formatting.prettier.with({
      filetypes = {
        "javascript",
        "typescript",
        "javascriptreact",
        "typescriptreact",
        "svelte",
        "json",
        "css",
        "html"
      },
    }),
    null_ls.builtins.diagnostics.eslint_d,
  },
})

require('mason-lspconfig').setup({
  ensure_installed = {'tsserver', 'rust_analyzer', 'ruff', 'pyright', 'gopls', 'svelte', 'eslint'},
  handlers = {
    function(server_name)
      require('lspconfig')[server_name].setup({
        capabilities = lsp_capabilities,
      })
    end,

    -- Lua LSP configuration
    lua_ls = function()
      require('lspconfig').lua_ls.setup({
        capabilities = lsp_capabilities,
        settings = {
          Lua = {
            runtime = {
              version = 'LuaJIT'
            },
            diagnostics = {
              globals = {'vim'},
            },
            workspace = {
              library = {
                vim.env.VIMRUNTIME,
              }
            }
          }
        }
      })
    end,

    -- TypeScript/JavaScript configuration
    tsserver = function()
      require('lspconfig').tsserver.setup({
        capabilities = lsp_capabilities,
        init_options = {
            plugins = {
                {
                    name = "@sveltejs/vite-plugin-svelte",
                    enabled = true,
                },
            },
        },
        settings = {
          typescript = {
            inlayHints = {
              includeInlayParameterNameHints = 'all',
              includeInlayParameterNameHintsWhenArgumentMatchesName = false,
              includeInlayFunctionParameterTypeHints = true,
              includeInlayVariableTypeHints = true,
              includeInlayPropertyDeclarationTypeHints = true,
              includeInlayFunctionLikeReturnTypeHints = true,
              includeInlayEnumMemberValueHints = true,
            },
          },
          javascript = {
            inlayHints = {
              includeInlayParameterNameHints = 'all',
              includeInlayParameterNameHintsWhenArgumentMatchesName = false,
              includeInlayFunctionParameterTypeHints = true,
              includeInlayVariableTypeHints = true,
              includeInlayPropertyDeclarationTypeHints = true,
              includeInlayFunctionLikeReturnTypeHints = true,
              includeInlayEnumMemberValueHints = true,
            },
          },
        },
        on_attach = function(client, bufnr)
            client.server_capabilities.definitionProvider = true
        end,
    })
    end,

    -- Svelte configuration
    svelte = function()
    local lspconfig = require('lspconfig')
    lspconfig.svelte.setup({
        cmd = { "svelteserver", "--stdio" },  -- Use globally installed server
        capabilities = vim.tbl_deep_extend('force', lsp_capabilities, {
            definitionProvider = true,
            referencesProvider = true,
        }),
        filetypes = { "svelte" },
        root_dir = lspconfig.util.root_pattern("package.json", "svelte.config.js", ".git"),
        settings = {
            svelte = {
                plugin = {
                    typescript = {
                        enabled = true,
                        diagnostics = {
                            enable = true,
                        },
                        hover = {
                            enable = true,
                        },
                        completions = {
                            enable = true,
                        },
                        definitions = {
                            enable = true,
                        },
                    },
                },
            },
        },
        on_attach = function(client, bufnr)
            print("Svelte LSP attached!")
            client.server_capabilities.definitionProvider = true
        end,
    })
    end,
    -- Python configuration
       pyright = function()
    require('lspconfig').pyright.setup({
        capabilities = vim.tbl_deep_extend('force', lsp_capabilities, {
            -- Explicitly enable code actions and completion
            codeActionProvider = true,
            completionProvider = {
                triggerCharacters = { ".", " ", "\t", "(" },
                resolveProvider = true,
            }
        }),
        settings = {
            python = {
                analysis = {
                    autoImportCompletions = true,
                    autoSearchPaths = true,
                    useLibraryCodeForTypes = true,
                    diagnosticMode = "workspace",
                    typeCheckingMode = "basic",
                    completeFunctionParens = true,
                    importFormat = "absolute",
                    -- Make missing imports more visible to trigger code actions
                    diagnosticSeverityOverrides = {
                        reportMissingImports = "error",  -- Changed to error to ensure code actions appear
                        reportUnusedImport = "warning",
                        reportGeneralTypeIssues = "information",
                    },
                    -- Help pyright find packages
                    extraPaths = { vim.fn.getcwd() },
                    pythonPath = os.getenv("CONDA_PREFIX") and (os.getenv("CONDA_PREFIX") .. "/bin/python"),
                    venvPath = os.getenv("CONDA_PREFIX"),
                }
            }
        },
        on_attach = function(client, bufnr)
            -- Ensure capabilities are properly set
            client.server_capabilities.codeActionProvider = true
            client.server_capabilities.completionProvider = {
                triggerCharacters = { ".", " ", "\t", "(" },
                resolveProvider = true
            }
            
            -- Existing PyrightInfo command
            vim.api.nvim_buf_create_user_command(bufnr, 'PyrightInfo', function()
                print("Python Path:", client.config.settings.python.analysis.pythonPath)
                print("Environment:", os.getenv("CONDA_PREFIX"))
                print("Workspace root:", client.config.root_dir)
                print("Settings:", vim.inspect(client.config.settings))
                print("Capabilities:", vim.inspect(client.server_capabilities))
            end, {})
        end,
    })
end,
}
})


local cmp = require('cmp')
local cmp_select = {behavior = cmp.SelectBehavior.Select}

-- this is the function that loads the extra snippets to luasnip
-- from rafamadriz/friendly-snippets
require('luasnip.loaders.from_vscode').lazy_load()

cmp.setup({
    sources = {
        {name = 'path'},
        {name = 'supermaven'},
        {name = 'nvim_lsp', keyword_length = 1},
        {name = 'luasnip', keyword_length = 2},
        {name = 'buffer', keyword_length = 3},
    },
  mapping = cmp.mapping.preset.insert({
    ['<C-p>'] = cmp.mapping.select_prev_item(cmp_select),
    ['<C-n>'] = cmp.mapping.select_next_item(cmp_select),
    ['<C-y>'] = cmp.mapping.confirm({ select = true }),
    ['<C-Space>'] = cmp.mapping.complete(),
  }),
  snippet = {
    expand = function(args)
      require('luasnip').lsp_expand(args.body)
    end,
  },
})
