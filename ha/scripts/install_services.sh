#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 1 ]]; then
    printf 'Usage: %s [checkout-directory]\n' "$0" >&2
    exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
checkout_dir=${1:-$(cd -- "$script_dir/../.." && pwd -P)}
if [[ ! -d "$checkout_dir/systemd" || ! -d "$checkout_dir/ha/scripts" ]]; then
    printf 'Not a Home Assistant checkout: %s\n' "$checkout_dir" >&2
    exit 1
fi
checkout_dir=$(cd -- "$checkout_dir" && pwd -P)

if [[ ! -t 0 ]]; then
    printf 'Interactive terminal required to select services.\n' >&2
    exit 2
fi

printf 'Which systemd services should be installed?\n'
printf '  1) Kitchen light control (continuous)\n'
printf '  2) Gas data (hourly)\n'
printf '  3) RPi data (every 10 minutes)\n'
printf '  4) Service status to MQTT (every 25 minutes)\n'
printf '  5) Latest gas image HTTP server (continuous)\n'
printf '  0) None\n'
read -r -p 'Select one or more, separated by spaces or commas [0-5]: ' service_choice
service_choice=${service_choice//,/ }
service_choice_compact=${service_choice//[[:space:]]/}
if [[ -z "$service_choice_compact" || "$service_choice_compact" == 0 ]]; then
    printf 'No services selected.\n'
    exit 0
fi

install_light=false
install_gas=false
install_rpi=false
install_status=false
install_vision_http=false
read -r -a service_choices <<< "$service_choice"
for choice in "${service_choices[@]}"; do
    case "$choice" in
        1) install_light=true ;;
        2) install_gas=true ;;
        3) install_rpi=true ;;
        4) install_status=true ;;
        5) install_vision_http=true ;;
        *) printf 'Invalid service selection: %s\n' "$choice" >&2; exit 2 ;;
    esac
done

unit_files=()
units_to_enable=()
selected_services=()
if [[ "$install_light" == true ]]; then
    unit_files+=(ha-light-control-konyha.service)
    units_to_enable+=(ha-light-control-konyha.service)
    selected_services+=(light)
fi
if [[ "$install_gas" == true ]]; then
    unit_files+=(ha-gas-data.service ha-gas-data.timer)
    units_to_enable+=(ha-gas-data.timer)
    selected_services+=(gas)
fi
if [[ "$install_rpi" == true ]]; then
    unit_files+=(ha-rpi-data.service ha-rpi-data.timer)
    units_to_enable+=(ha-rpi-data.timer)
    selected_services+=(rpi)
fi
if [[ "$install_status" == true ]]; then
    unit_files+=(ha-service-status.service ha-service-status.timer)
    units_to_enable+=(ha-service-status.timer)
    selected_services+=(status)
fi
if [[ "$install_vision_http" == true ]]; then
    unit_files+=(ha-vision-http.service)
    units_to_enable+=(ha-vision-http.service)
    selected_services+=(vision-http)
fi

for unit_file in "${unit_files[@]}"; do
    if [[ ! -r "$checkout_dir/systemd/$unit_file" ]]; then
        printf 'Unit file not found: %s\n' "$checkout_dir/systemd/$unit_file" >&2
        exit 1
    fi
done

for unit_file in "${unit_files[@]}"; do
    sudo install -m 644 "$checkout_dir/systemd/$unit_file" "/etc/systemd/system/$unit_file"
done
sudo systemctl daemon-reload
if [[ "$install_rpi" == true ]] \
    && sudo systemctl list-unit-files --no-legend ha-rpi-config.timer \
        | grep -q '^ha-rpi-config\.timer'; then
    sudo systemctl disable --now ha-rpi-config.timer
fi
sudo systemctl enable --now "${units_to_enable[@]}"
printf 'Installed and enabled systemd services: %s\n' "${selected_services[*]}"
