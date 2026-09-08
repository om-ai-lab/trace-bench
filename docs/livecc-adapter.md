# LiveCC Adapter (OSB Contract v4)

The bundled open_stream_bench.livecc_adapter:LiveCCAdapter runs
LiveCC-7B-Instruct from local weights through the OSB Core RGB observation
contract.

The adapter consumes the Observation.rgb arrays passed by Core. It does not
open video_path, use decord, or call LiveCC's file-replay helper. Each record
gets a new past_ids/past_key_values state, while the model and processor are
loaded once per adapter process.

## Environment

The maintainer's local handoff used private machine paths that are not part of
the public contract. Configure equivalent paths for your own environment:

    LiveCC source: /path/to/livecc
    LiveCC weights: /path/to/LiveCC-7B-Instruct
    Environment: /path/to/python-environment

Set the model and source paths through adapter configuration or environment
variables. The adapter accepts model_id and livecc_root; the equivalent
environment variables are LIVECC_MODEL_PATH and LIVECC_ROOT.

## Configuration

Example adapter configuration:

    {
      "model_id": "/path/to/LiveCC-7B-Instruct",
      "livecc_root": "/path/to/livecc",
      "device": "cuda",
      "frames_per_chunk": 2,
      "min_pixels": 78400,
      "max_pixels": 301056,
      "context_window_tokens": 32768,
      "pacing": "wall_clock"
    }

frames_per_chunk controls model-call cadence only. Core still delivers the
frozen 1 FPS RGB sequence to every adapter. pacing=wall_clock is required for
ranked response-latency measurements; use logical pacing for fast correctness
smoke tests with `examples/livecc/logical.json`. Before the processor call, the adapter applies a Qwen2-VL
factor-28 resize down to `max_pixels` when a Core frame is larger than the
configured budget. It never upscales a Core frame, and frame telemetry records
the resized dimensions submitted to LiveCC. The adapter does not truncate KV
history; it records a recoverable failure before generation if the input plus
requested output would exceed `context_window_tokens`.

Generation budgets are clamped to the remaining model context. Each model-call
telemetry row records both the configured and effective `max_new_tokens`.

LiveCC does not expose a native silence token in this adapter. Its provider
ellipsis (`...`) is retained as raw output and classified as a provider
continuation marker, not as native silence. The adapter therefore uses the
contract's minimal Proactive fallback system prompt once, sends the raw
instruction exactly once, and maps a standalone fallback `WAIT` to a canonical
`WAIT` event. Raw provider text and generated token IDs remain in the bundle.

GPU memory uses a lazy NVML process monitor when available. It records the
post-load process baseline, sampled process peak, peak-minus-baseline, device
identity, sample interval, and competing compute PIDs. If the process cannot be
isolated, allocator snapshots remain diagnostic and canonical GPU memory is
marked unavailable rather than estimated.

At the bounded final strict-window endpoint, Core asks the adapter to flush one
final partial chunk before applying any remaining grace when the source video
ends first. The later `close()` is only shutdown drain, so it cannot create a
new scoreable response after the evaluation boundary.

## Runs

    conda activate /path/to/python-environment

    osb run \
      --task qa \
      --release data/releases/v1.1.0 \
      --subset tiny \
      --adapter open_stream_bench.livecc_adapter:LiveCCAdapter \
      --adapter-config examples/livecc/wall_clock.json \
      --video-root /path/to/local/videos \
      --pacing wall_clock \
      --output runs/livecc-v4-qa-tiny

    osb run \
      --task proactive \
      --release data/releases/v1.1.0 \
      --subset tiny \
      --adapter open_stream_bench.livecc_adapter:LiveCCAdapter \
      --adapter-config examples/livecc/wall_clock.json \
      --video-root /path/to/local/videos \
      --pacing wall_clock \
      --proactive-history-window-s 5 \
      --proactive-window-s 5 \
      --output runs/livecc-v4-proactive-tiny

The adapter declares persistent state and autonomous proactive output, so it
is a Native Streaming candidate. The run bundle records Core RGB evidence,
model-call chunking, raw LiveCC output, token IDs, frame commits, and telemetry
coverage. A blocking runtime that cannot expose a first generated token leaves
TTFT null and marks that coverage as missing; it is never estimated from total
generation time.

## Full V4-Contract Run

To run the complete public release (833 QA records followed by 415 Proactive
records), configure the environment and use the repository wrapper (requires jq):

    export VIDEO_ROOT=/path/to/osb-media
    export LIVECC_ROOT=/path/to/livecc
    export LIVECC_MODEL_PATH=/path/to/LiveCC-7B-Instruct
    export OUTPUT_ROOT=/path/to/results/livecc-v1.1-full

    bash scripts/run_livecc_v1_full.sh

The wrapper validates the release, saves one preflight JSON per task, runs both
tasks with checkpoint/resume enabled, and validates both bundles. It defaults to
`CUDA_VISIBLE_DEVICES=0`, `pacing=wall_clock`, `PROACTIVE_WINDOW_S=5`, and
`JUDGE_MODE=auto`; override these environment variables when a separate run is
needed. The wrapper passes `examples/livecc/wall_clock.json` so the adapter capability
and Core pacing match. Outputs are `$OUTPUT_ROOT/qa` and `$OUTPUT_ROOT/proactive`;
without an override, OUTPUT_ROOT defaults to `runs/livecc-v1.1-full`.
