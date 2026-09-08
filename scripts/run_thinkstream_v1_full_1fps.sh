#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python}"
THINKSTREAM_ROOT="${THINKSTREAM_ROOT:?Set THINKSTREAM_ROOT to a local ThinkStream checkout}"
VIDEO_ROOT="${VIDEO_ROOT:?Set VIDEO_ROOT to the local source-video root}"
export PYTHONPATH="$ROOT/src:$THINKSTREAM_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

RELEASE="${RELEASE:-data/releases/v1.1.0}"
ADAPTER=open_stream_bench.thinkstream_adapter:ThinkStreamAdapter
ADAPTER_CONFIG="${ADAPTER_CONFIG:?Set ADAPTER_CONFIG to a local ThinkStream OSB config}"
OUTPUT_ROOT="${OUTPUT_ROOT:-runs/thinkstream-v1.1-full}"
QA_OUTPUT="$OUTPUT_ROOT/qa"
PRO_OUTPUT="$OUTPUT_ROOT/proactive"
command -v jq >/dev/null || { echo "Install jq to use this wrapper" >&2; exit 1; }

if [[ ! -f "$ADAPTER_CONFIG" ]]; then
  echo "Missing adapter config: $ADAPTER_CONFIG" >&2
  exit 1
fi

mkdir -p "$QA_OUTPUT" "$PRO_OUTPUT"

COMMON_ARGS=(
  --release "$RELEASE"
  --subset full
  --adapter "$ADAPTER"
  --video-root "$VIDEO_ROOT"
  --stream-fps 1
  --pacing wall_clock
  --proactive-history-window-s 5
  --proactive-window-s 5
  --max-width 960
  --temperature 0.2
  --checkpoint-every 10
  --adapter-config "$ADAPTER_CONFIG"
)

echo "=== QA preflight ==="
"$PYTHON" -m open_stream_bench.cli run --task qa --output "$QA_OUTPUT" "${COMMON_ARGS[@]}" --preflight-only \
  > "$QA_OUTPUT/preflight.json"
jq -e '.preflight_schema == "osb-preflight-v4" and .protocol.contract == "osb-contract-v4" and .protocol.config_version == "v4" and .protocol.pacing == "wall_clock" and .scoring.scorer_version == "osb-scoring-v5"' \
  "$QA_OUTPUT/preflight.json" >/dev/null

echo "=== Proactive preflight ==="
"$PYTHON" -m open_stream_bench.cli run --task proactive --output "$PRO_OUTPUT" "${COMMON_ARGS[@]}" --preflight-only \
  > "$PRO_OUTPUT/preflight.json"
jq -e '.preflight_schema == "osb-preflight-v4" and .protocol.contract == "osb-contract-v4" and .protocol.config_version == "v4" and .scoring.scorer_version == "osb-scoring-v5" and .protocol.proactive_history_window_s == 5 and .protocol.proactive_window_s == 5 and .execution_track.proactive_primary_eligible == true' \
  "$PRO_OUTPUT/preflight.json" >/dev/null

echo "=== Full QA (833 records; resume enabled) ==="
"$PYTHON" -m open_stream_bench.cli run --task qa --output "$QA_OUTPUT" "${COMMON_ARGS[@]}"

echo "=== Validate QA bundle ==="
"$PYTHON" -m open_stream_bench.cli bundle validate "$QA_OUTPUT"

echo "=== Full Proactive (415 records; resume enabled) ==="
"$PYTHON" -m open_stream_bench.cli run --task proactive --output "$PRO_OUTPUT" "${COMMON_ARGS[@]}"

echo "=== Validate Proactive bundle ==="
"$PYTHON" -m open_stream_bench.cli bundle validate "$PRO_OUTPUT"

echo "=== Complete ==="
echo "QA metrics: $QA_OUTPUT/metrics.json"
echo "Proactive metrics: $PRO_OUTPUT/metrics.json"
