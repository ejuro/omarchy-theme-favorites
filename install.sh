#!/usr/bin/env bash
set -euo pipefail
umask 077
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
plugin_id=io.github.ejuro.theme-favorites
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy"
target="$config_dir/plugins/$plugin_id"
command -v python3 >/dev/null
python3 -c 'import sqlite3, tomllib'
omarchy plugin validate "$source_dir"
mkdir -p -- "$config_dir/plugins"
if [[ -e $target || -L $target ]]; then
    [[ $(readlink -f -- "$target") == "$source_dir" ]] || {
        echo "A different installation already exists at $target" >&2
        exit 1
    }
else
    ln -s -- "$source_dir" "$target"
fi
if [[ -f $config_dir/shell.json ]]; then
    backup_dir="${XDG_STATE_HOME:-$HOME/.local/state}/theme-favorites/backups"
    mkdir -p -m 700 -- "$backup_dir"
    chmod 700 -- "$(dirname -- "$backup_dir")" "$backup_dir"
    backup_file=$(mktemp "$backup_dir/shell.XXXXXXXX.json")
    cat -- "$config_dir/shell.json" > "$backup_file"
fi
omarchy-shell shell rescanPlugins
omarchy plugin enable "$plugin_id" --section right
printf 'Theme Favorites is enabled. Open the palette icon in the bar.\n'
