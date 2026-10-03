#!/bin/bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    printf 'Usage: %s <checkout-directory>\n' "$0" >&2
    exit 2
fi

target_dir=$1
if [[ ! -d "$target_dir/ha/scripts" ]]; then
    printf 'Not a Home Assistant checkout: %s\n' "$target_dir" >&2
    exit 1
fi
target_dir=$(cd -- "$target_dir" && pwd -P)

prod_link="$HOME/PROD"
if [[ -e "$prod_link" && ! -L "$prod_link" ]]; then
    printf 'Refusing to replace non-symlink: %s\n' "$prod_link" >&2
    exit 1
fi
if ! command -v crontab >/dev/null 2>&1; then
    printf 'crontab command is required to update the scheduled RPi job\n' >&2
    exit 1
fi

configure_gas=false
if [[ -t 0 ]]; then
    read -r -p 'Also configure Gas to run at minute 15 every hour? [y/N] ' answer
    case "$answer" in
        y|Y|yes|YES|Yes) configure_gas=true ;;
    esac
else
    printf 'Skipping optional Gas cron setup in non-interactive mode\n'
fi

printf 'Installing package from %s\n' "$target_dir"
(cd -- "$target_dir" && python3 -m pip install -e . --break-system-packages)

temp_dir=$(mktemp -d "$HOME/.PROD-switch.XXXXXX")
trap 'rm -rf -- "$temp_dir"' EXIT
ln -s "$target_dir" "$temp_dir/PROD"
mv -Tf -- "$temp_dir/PROD" "$prod_link"

current_crontab=$(crontab -l 2>/dev/null || true)
printf '%s\n' "$current_crontab" \
    | awk -v remove_gas="$configure_gas" \
        '/^[[:space:]]*#/ { print; next } !/rpi(_psutils_send_data)?\.sh/ && (remove_gas != "true" || !/gas\.sh/) { print }' \
    > "$temp_dir/crontab"
printf '%s\n' '*/10 * * * * /bin/bash "$HOME/PROD/ha/scripts/rpi_psutils_send_data.sh"' \
    >> "$temp_dir/crontab"
if [[ "$configure_gas" == true ]]; then
    printf '%s\n' '15 * * * * /bin/bash "$HOME/PROD/ha/scripts/gas_send_data.sh"' \
        >> "$temp_dir/crontab"
fi
crontab "$temp_dir/crontab"

printf 'PROD now points to %s\n' "$target_dir"
printf 'Updated crontab: RPi publisher runs every 10 minutes\n'
if [[ "$configure_gas" == true ]]; then
    printf 'Updated crontab: Gas publisher runs at minute 15 every hour\n'
fi