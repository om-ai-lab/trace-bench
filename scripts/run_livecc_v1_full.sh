#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

# Set model-specific paths in the environment. The public repository does not
# assume a particular machine, Conda environment, GPU, or weight location.
OSB_PYTHON="${OSB_PYTHON:-python}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
RELEASE="${RELEASE:-$ROOT/data/releases/v1.1.0}"
VIDEO_ROOT="${VIDEO_ROOT:?Set VIDEO_ROOT to the local source-video root}"
LIVECC_ROOT="${LIVECC_ROOT:?Set LIVECC_ROOT to a local LiveCC checkout}"
LIVECC_MODEL_PATH="${LIVECC_MODEL_PATH:?Set LIVECC_MODEL_PATH to local LiveCC weights}"
ADAPTER="${ADAPTER:-open_stream_bench.livecc_adapter:LiveCCAdapter}"
ADAPTER_CONFIG="${ADAPTER_CONFIG:-}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$ROOT/runs/livecc-v1.1-full}"
PACING="${PACING:-wall_clock}"
PROACTIVE_WINDOW_S="${PROACTIVE_WINDOW_S:-5}"
if [[ -z "$ADAPTER_CONFIG" ]]; then
  if [[ "$PACING" == "wall_clock" ]]; then
    ADAPTER_CONFIG="$ROOT/examples/livecc/wall_clock.json"
  else
    ADAPTER_CONFIG="$ROOT/examples/livecc/logical.json"
  fi
fi
# Auto uses the configured VLM judge for proactive semantic windows and falls
# back to an explicitly recorded exact score when no endpoint is configured.
JUDGE_MODE="${JUDGE_MODE:-auto}"
CHECKPOINT_EVERY="${CHECKPOINT_EVERY:-10}"

export CUDA_VISIBLE_DEVICES LIVECC_ROOT LIVECC_MODEL_PATH
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

command -v "$OSB_PYTHON" >/dev/null || die "Python executable is not runnable: $OSB_PYTHON"
command -v jq >/dev/null || die "Install jq to use this wrapper"
[[ -d "$RELEASE" ]] || die "Release directory does not exist: $RELEASE"
[[ -d "$VIDEO_ROOT" ]] || die "Video root does not exist: $VIDEO_ROOT"
[[ -d "$LIVECC_ROOT" ]] || die "LiveCC source directory does not exist: $LIVECC_ROOT"
[[ -d "$LIVECC_MODEL_PATH" ]] || die "LiveCC model directory does not exist: $LIVECC_MODEL_PATH"
[[ -z "$ADAPTER_CONFIG" || -f "$ADAPTER_CONFIG" ]] || die "Adapter config does not exist: $ADAPTER_CONFIG"
[[ "$PACING" == "logical" || "$PACING" == "wall_clock" ]] || die "PACING must be logical or wall_clock"
[[ "$PROACTIVE_WINDOW_S" == "5" || "$PROACTIVE_WINDOW_S" == "10" ]] || die "PROACTIVE_WINDOW_S must be 5 or 10"
[[ "$JUDGE_MODE" == "auto" || "$JUDGE_MODE" == "exact" || "$JUDGE_MODE" == "vlm" ]] || die "JUDGE_MODE must be auto, exact, or vlm"
[[ "$CHECKPOINT_EVERY" =~ ^[1-9][0-9]*$ ]] || die "CHECKPOINT_EVERY must be a positive integer"

mkdir -p "$OUTPUT_ROOT"

run_osb() {
  "$OSB_PYTHON" -m open_stream_bench.cli "$@"
}

COMMON_ARGS=(
  --release "$RELEASE"
  --subset full
  --adapter "$ADAPTER"
  --video-root "$VIDEO_ROOT"
  --stream-fps 1
  --max-width 960
  --temperature 0.2
  --pacing "$PACING"
  --proactive-history-window-s 5
  --proactive-window-s "$PROACTIVE_WINDOW_S"
  --judge-mode "$JUDGE_MODE"
  --checkpoint-every "$CHECKPOINT_EVERY"
)
if [[ -n "$ADAPTER_CONFIG" ]]; then
  COMMON_ARGS+=(--adapter-config "$ADAPTER_CONFIG")
fi

echo "=== Environment ==="
echo "Python: $OSB_PYTHON"
echo "CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"
echo "Release: $RELEASE"
echo "Video root: $VIDEO_ROOT"
echo "Output root: $OUTPUT_ROOT"
echo

echo "=== Validate release ==="
run_osb data validate --release "$RELEASE" \
  | tee "$OUTPUT_ROOT/release.validate.json"

run_task() {
  local task="$1"
  local expected_count="$2"
  local output="$OUTPUT_ROOT/$task"
  local preflight="$OUTPUT_ROOT/${task}.preflight.json"
  local preflight_stderr="$OUTPUT_ROOT/${task}.preflight.stderr.log"
  local run_log="$OUTPUT_ROOT/${task}.run.log"
  local validation="$OUTPUT_ROOT/${task}.validate.json"

  echo
  echo "=== $task preflight ($expected_count records) ==="
  if [[ -f "$output/manifest.json" ]] && grep -Eq '"finalized"[[:space:]]*:[[:space:]]*true' "$output/manifest.json"; then
    if ! jq -e '
      .preflight.preflight_schema == "osb-preflight-v4" and
      .preflight.protocol.contract == "osb-contract-v4" and
      .scorer_version == "osb-scoring-v5" and
      .config_version == "v4"
    ' "$output/resolved_config.json" >/dev/null; then
      die "finalized bundle uses an older protocol; choose a new OUTPUT_ROOT: $output"
    fi
    echo "Existing finalized bundle found; skipping inference: $output"
    run_osb bundle validate "$output" | tee "$validation"
    return
  fi

  run_osb run --task "$task" --output "$output" "${COMMON_ARGS[@]}" \
    --preflight-only >"$preflight" 2>"$preflight_stderr"

  echo "Preflight: $preflight"
  echo "Preflight stderr: $preflight_stderr"
  echo
  echo "=== Full $task ($expected_count records; resume enabled) ==="
  run_osb run --task "$task" --output "$output" "${COMMON_ARGS[@]}" \
    2>&1 | tee "$run_log"

  echo
  echo "=== Validate $task bundle ==="
  run_osb bundle validate "$output" | tee "$validation"
  echo "Bundle: $output"
  echo "Run log: $run_log"
}

run_task qa 833
run_task proactive 415

echo
echo "=== Complete ==="
echo "QA metrics: $OUTPUT_ROOT/qa/metrics.json"
echo "Proactive metrics: $OUTPUT_ROOT/proactive/metrics.json"
