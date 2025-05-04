local dap_python = require('dap-python')
local dap, dapui = require("dap"), require("dapui")

---dap---

dapui.setup()

dap_python.setup('/Users/mylius/miniconda3/envs/hari/bin/python', {
    include_configs = true,
    pythonPath = '/Users/mylius/miniconda3/envs/hari/bin/python',
    debuggerPath = '/Users/mylius/miniconda3/envs/hari/lib/python3.11/site-packages/debugpy'
})
vim.keymap.set('n', '<leader>db',dap.toggle_breakpoint)
vim.keymap.set('n', '<leader>dpr',dap_python.test_method)
vim.keymap.set('n', '<leader>dc', dap.continue)
vim.keymap.set('n', '<leader>ds', dap.step_over)
vim.keymap.set('n', '<leader>di', dap.step_into)
vim.keymap.set('n', '<leader>do', dap.step_out)
vim.keymap.set('n', '<leader>dt', dapui.toggle)
vim.keymap.set('n', '<leader>dr', function()
    require('dap').continue()
end)

dap.listeners.after.event_initialized["dapui_config"] = function()
  dapui.open()
end
dap.listeners.before.event_terminated["dapui_config"] = function()
  dapui.close()
end
