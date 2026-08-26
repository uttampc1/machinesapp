#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="/usr/local/etc"
source ${CONFIG_DIR}/reservation.config

LIST_CMD="/usr/local/bin/list_machines"
WEB_URL="${SERVER}"
SUBJECT="Machine reservation reminder"
TEST_EMAIL="${TEST_EMAIL:-}"
TEST_EMAIL="upawar"
DRY_RUN=0

get_reserved_json() {
    "$LIST_CMD" -s reserved -j
}

has_any_reserved_machines() {
    local json="$1"
    [[ "$(printf '%s\n' "$json" | jq 'length')" -gt 0 ]]
}

get_attention_users() {
    local json="$1"

    printf '%s\n' "$json" | jq -r '
        map(
            select(
                .reserved_by != null and
                (.reserved_by | gsub("^\\s+|\\s+$"; "")) != "" and
                .motd != null and
                (.motd | gsub("^\\s+|\\s+$"; "")) != "" and
                (.motd | test("^\\[(INFO|WARNING|CONFIRM)\\]"))
            )
        )
        | map(.reserved_by)
        | unique
        | .[]
    '
}

get_attention_count_for_user() {
    local json="$1"
    local user_email="$2"

    printf '%s\n' "$json" | jq --arg user "$user_email" '
        map(
            select(
                .reserved_by == $user and
                .motd != null and
                (.motd | gsub("^\\s+|\\s+$"; "")) != "" and
                (.motd | test("^\\[(INFO|WARNING|CONFIRM)\\]"))
            )
        ) | length
    '
}

get_attention_machines_for_user() {
    local json="$1"
    local user_email="$2"

    printf '%s\n' "$json" | jq -r --arg user "$user_email" '
        map(
            select(
                .reserved_by == $user and
                .motd != null and
                (.motd | gsub("^\\s+|\\s+$"; "")) != "" and
                (.motd | test("^\\[(INFO|WARNING|CONFIRM)\\]"))
            )
        )
        | .[]
        | "- " + .machine_name + " " + .motd
    '
}

get_active_machines_for_user() {
    local json="$1"
    local user_email="$2"

    printf '%s\n' "$json" | jq -r --arg user "$user_email" '
        map(
            select(
                .reserved_by == $user and
                (
                    .motd == null or
                    (.motd | gsub("^\\s+|\\s+$"; "")) == ""
                )
            )
        )
        | .[]
        | "- " + .machine_name
    '
}

build_email_body() {
    local attention_machines="$1"
    local active_machines="$2"
    local user_email="$3"

    cat <<EOF
Hello $user_email,

This is your daily machine reservation reminder.

Needs attention:
$attention_machines

Go to Machine reservation system:
$WEB_URL
EOF

    if [[ -n "${active_machines//[$'\t\r\n ']}" ]]; then
        cat <<EOF

Other reserved machines in active use:
$active_machines
EOF
    fi

    cat <<'EOF'

Please release machines that are no longer needed.

Thanks,
Machine Reservation System
EOF
}

print_email() {
    local user_email="$1"
    local email_body="$2"
    local recipient="$user_email"

    if [[ -n "$TEST_EMAIL" ]]; then
      recipient="${TEST_EMAIL}"
    fi

    echo "=================================================="
    echo "TO: $recipient"
    echo "SUBJECT: $SUBJECT"
    echo "=================================================="
    printf '%s\n' "$email_body"
    echo
}

send_email() {
    local user_email="$1"
    local email_body="$2"
    local recipient="$user_email"

    if [[ -n "$TEST_EMAIL" ]]; then
      recipient="${TEST_EMAIL}"
    fi

    #printf '%s\n' "$email_body" 
    #printf  'Rec:%s\n', "$recipient"
    printf '%s\n' "$email_body" | mail -s "$SUBJECT" "$recipient"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --send)
                DRY_RUN=0
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown argument: $1" >&2
                usage
                exit 1
                ;;
        esac
    done
}

main() {

    parse_args "$@"

    local json
    json="$(get_reserved_json)"

    if ! has_any_reserved_machines "$json"; then
        exit 0
    fi

    local attention_users
    attention_users="$(get_attention_users "$json")"

    if [[ -z "${attention_users//[$'\t\r\n ']}" ]]; then
        exit 0
    fi

    while IFS= read -r user_email; do
        [[ -z "$user_email" ]] && continue

        local attention_count
        attention_count="$(get_attention_count_for_user "$json" "$user_email")"
        [[ "$attention_count" -eq 0 ]] && continue

        local attention_machines
        attention_machines="$(get_attention_machines_for_user "$json" "$user_email")"

        local active_machines
        active_machines="$(get_active_machines_for_user "$json" "$user_email")"

        local email_body
        email_body="$(build_email_body "$attention_machines" "$active_machines" "$user_email")"

        if [[ "$DRY_RUN" -eq 1 ]]; then
            print_email "$user_email" "$email_body"
        else
            send_email "$user_email" "$email_body"
        fi
    done <<< "$attention_users"
}

main "$@"
