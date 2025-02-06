require("yazi").setup({
    open_for_directories = true,

    use_ya_for_events_reading = false,

    use_yazi_client_id_flag = false,

    highlight_groups = {
      -- NOTE: this only works if `use_ya_for_events_reading` is enabled, etc.
      hovered_buffer = nil,
    },

    floating_window_scaling_factor = 1,

    yazi_floating_window_winblend = 0,

    log_level = vim.log.levels.OFF,

    keymaps = {
      show_help = '<f1>',
      open_file_in_vertical_split = '<c-v>',
      open_file_in_horizontal_split = '<c-x>',
      open_file_in_tab = '<c-t>',
      grep_in_directory = '<c-s>',
      replace_in_directory = '<c-g>',
      cycle_open_buffers = '<tab>',
      copy_relative_path_to_selected_files = '<c-y>',
    },

   -- yazi_floating_window_border = 'rounded',

    clipboard_register = "*",

})

vim.keymap.set("n", "<leader>pv", require("yazi").yazi)
