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
install_light=false
install_gas=false
install_rpi=false
install_status=false
install_vision_http=false
if [[ -t 0 ]]; then
    printf 'Which systemd services should be installed?\n'
    printf '  1) Kitchen light control (continuous)\n'
    printf '  2) Gas data (hourly)\n'
    printf '  3) RPi data (every 10 minutes)\n'
    printf '  4) Service status to MQTT (every 10 minutes)\n'
    printf '  5) Latest gas image HTTP server (continuous)\n'
    printf '  0) None\n'
    read -r -p 'Select one or more, separated by spaces or commas [0-5]: ' service_choice
    service_choice=${service_choice//,/ }
    service_choice_compact=${service_choice//[[:space:]]/}
    if [[ -n "$service_choice_compact" && "$service_choice_compact" != 0 ]]; then
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
    fi
else
    printf 'Skipping optional systemd service setup in non-interactive mode\n'
fi

system_python_bin=''
if [[ -r /etc/environment ]]; then
    system_python_bin=$(sed -nE 's/^[[:space:]]*PYTHON_BIN[[:space:]]*=[[:space:]]*"?([^"[:space:]]+)"?[[:space:]]*$/\1/p' /etc/environment | tail -n 1)
fi

if [[ -n "$system_python_bin" ]]; then
    python_bin=$system_python_bin
    printf 'Using existing PYTHON_BIN from /etc/environment: %s\n' "$python_bin"
else
    python_bin=${PYTHON_BIN:-$(command -v python3)}
    requested_python_bin=$python_bin
    if [[ -t 0 ]]; then
        printf 'Available Python interpreters:\n'
        python_options=()
        python_option_count=0
        python_candidates=$(compgen -c | grep -E '^python([0-9]+(\.[0-9]+)*)?$' | sort -u || true)
        while IFS= read -r candidate; do
            [[ -n "$candidate" ]] || continue
            candidate_path=$(command -v "$candidate" || true)
            [[ -n "$candidate_path" && -x "$candidate_path" ]] || continue
            candidate_version=$(
                "$candidate_path" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || true
            )
            [[ -n "$candidate_version" ]] || continue
            python_options+=("$candidate_path")
            python_option_count=$((python_option_count + 1))
            printf '  %d) %s (Python %s)\n' "$python_option_count" "$candidate_path" "$candidate_version"
        done <<< "$python_candidates"

        read -r -p "Select a number or enter a Python path [$python_bin]: " requested_python_bin
        requested_python_bin=${requested_python_bin:-$python_bin}
        if [[ "$requested_python_bin" =~ ^[0-9]+$ ]]; then
            if ((requested_python_bin < 1 || requested_python_bin > python_option_count)); then
                printf 'Invalid Python interpreter selection: %s\n' "$requested_python_bin" >&2
                exit 2
            fi
            python_bin=${python_options[$((requested_python_bin - 1))]}
        else
            python_bin=$requested_python_bin
        fi
    else
        printf 'Using Python interpreter: %s\n' "$python_bin"
    fi

    if ! python_bin=$(command -v "$python_bin"); then
        printf 'Python interpreter not found: %s\n' "$requested_python_bin" >&2
        exit 1
    fi
    printf 'PYTHON_BIN=%s\n' "$python_bin" | sudo tee -a /etc/environment >/dev/null
    printf 'Added PYTHON_BIN to /etc/environment\n'
fi

if ! command -v "$python_bin" >/dev/null 2>&1 || ! "$python_bin" -m pip --version >/dev/null 2>&1; then
    printf 'Python interpreter or pip is unavailable: %s\n' "$python_bin" >&2
    exit 1
fi

printf 'Installing package from %s\n' "$target_dir"
pip_install_args=(--disable-pip-version-check install -e .)
pip_install_options=$("$python_bin" -m pip --disable-pip-version-check install --help)
if grep -q -- '--break-system-packages' <<<"$pip_install_options"; then
    pip_install_args+=(--break-system-packages)
fi
(cd -- "$target_dir" && "$python_bin" -m pip "${pip_install_args[@]}")

temp_dir=$(mktemp -d "$HOME/.PROD-switch.XXXXXX")
trap 'rm -rf -- "$temp_dir"' EXIT
ln -s "$target_dir" "$temp_dir/PROD"
mv -Tf -- "$temp_dir/PROD" "$prod_link"

printf 'PROD now points to %s\n' "$target_dir"

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

if [[ ${#unit_files[@]} -gt 0 ]]; then
    for unit_file in "${unit_files[@]}"; do
        sudo install -m 644 "$target_dir/systemd/$unit_file" "/etc/systemd/system/$unit_file"
    done
    sudo systemctl daemon-reload
    if [[ "$install_rpi" == true ]] \
        && sudo systemctl list-unit-files --no-legend ha-rpi-config.timer \
            | grep -q '^ha-rpi-config\.timer'; then
        sudo systemctl disable --now ha-rpi-config.timer
    fi
    sudo systemctl enable --now "${units_to_enable[@]}"
    printf 'Installed and enabled systemd services: %s\n' "${selected_services[*]}"
fi

chmod 755 "$target_dir"/ha/scripts/*.sh