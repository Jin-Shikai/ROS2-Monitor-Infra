#!/usr/bin/env bash
# Shared helpers for the E5 no-SSH, three-terminal GUI run.

E5_MANUAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E5_REPO_ROOT="$(cd "$E5_MANUAL_DIR/../../.." && pwd)"

e5_set_run() {
  local run_id="${1:-}"
  if [ -z "$run_id" ]; then
    echo "A RUN_ID is required (for example: run_gui_20260715_120000)." >&2
    return 2
  fi
  case "$run_id" in
    *[!A-Za-z0-9._-]*)
      echo "RUN_ID may contain only letters, digits, '.', '_' and '-'." >&2
      return 2
      ;;
  esac

  cd "$E5_REPO_ROOT"
  RUN_ID="$run_id"
  REMOTE_RUN="eval/e5/results/$RUN_ID"
  BROKER="${BROKER:-192.168.2.18}"
  SEP_MIN="${SEP_MIN:-1.0}"
  SPEED_MAX="${SPEED_MAX:-0.3}"
  export RUN_ID REMOTE_RUN BROKER SEP_MIN SPEED_MAX
}

e5_refuse_reuse() {
  if [ -d "$REMOTE_RUN" ] && [ -n "$(find "$REMOTE_RUN" -mindepth 1 -print -quit 2>/dev/null)" ]; then
    echo "Refusing to reuse non-empty run directory: $REMOTE_RUN" >&2
    echo "Choose one new RUN_ID and use that exact value on all three machines." >&2
    return 1
  fi
}

e5_prepare_config() {
  local python_bin="$1"
  mkdir -p "$REMOTE_RUN/config" "$REMOTE_RUN/control"
  cp eval/e5/request.json "$REMOTE_RUN/request.json"
  "$python_bin" monitor/config_gen.py "$REMOTE_RUN/request.json" \
    -o "$REMOTE_RUN/config" \
    --var "REMOTE_RUN=$REMOTE_RUN" --var "BROKER=$BROKER" \
    --var "SEP_MIN=$SEP_MIN" --var "SPEED_MAX=$SPEED_MAX"
}

e5_require_started() {
  local marker="$1"
  if [ ! -e "$REMOTE_RUN/control/$marker" ]; then
    echo "Run $RUN_ID is not ready on this machine (missing $marker)." >&2
    return 1
  fi
}

e5_show_markers() {
  if [ ! -d "$REMOTE_RUN/control" ]; then
    echo "No local state for $RUN_ID"
    return 0
  fi
  echo "Control markers for $RUN_ID:"
  find "$REMOTE_RUN/control" -maxdepth 1 -type f -printf '  %f\n' 2>/dev/null \
    || find "$REMOTE_RUN/control" -maxdepth 1 -type f -exec basename {} \;
}
