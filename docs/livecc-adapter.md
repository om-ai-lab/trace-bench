# LiveCC adapter

English | [简体中文](livecc-adapter.zh-CN.md)

`trace_bench.livecc_adapter:LiveCCAdapter` runs local
[LiveCC-7B-Instruct](https://huggingface.co/chenjoya/LiveCC-7B-Instruct) weights.
It consumes Core's `Observation.rgb`; it does not open videos or replay files.
Weights/processor load once, while each record gets fresh `past_ids/past_key_values`.

## Environment

Follow [upstream installation](https://github.com/showlab/livecc) and
[inference instructions](https://github.com/showlab/livecc/blob/main/inference.md)
in a separate model environment. The source checkout is required for `demo.infer`.
Use an available NVIDIA GPU, CUDA and a compatible FlashAttention 2 build.

The previously tested runtime uses Python 3.12, PyTorch 2.8.0+cu126,
Transformers 4.57.3, FlashAttention 2.8.3, liger-kernel 0.7.0,
accelerate 1.12.0, livecc-utils 0.0.2, qwen-vl-utils 0.0.11,
NumPy 1.26.4 and OpenCV 4.11.0.86. FlashAttention must match PyTorch/CUDA/GLIBC.
Retain qwen-vl-utils 0.0.11: newer versions removed a livecc-utils dependency.

From the TRACE root in that environment, replace the two paths and run:

```bash
export LIVECC_ROOT=/path/to/livecc
export LIVECC_MODEL_PATH=/path/to/LiveCC-7B-Instruct
export CUDA_VISIBLE_DEVICES=0
export TOKENIZERS_PARALLELISM=false
python -m pip install 'qwen-vl-utils==0.0.11' 'livecc-utils==0.0.2'
python -m pip install -e .
python -c "import torch; from livecc_utils import prepare_multiturn_multimodal_inputs_for_generation; assert torch.cuda.is_available()"
```

Fix upstream import/CUDA errors before running TRACE. Development dependencies
are optional for inference; install `'.[dev]'` if running the test suite.

## Tiny execution check

Prepare videos using [data setup](data-setup.md), replace VIDEO_ROOT, then run:

```bash
export VIDEO_ROOT=/path/to/trace-media
python scripts/check_videos.py --release data/releases/v1.1.0 \
  --video-root "$VIDEO_ROOT" --subset tiny
trace run --task qa --release data/releases/v1.1.0 --subset tiny \
  --adapter trace_bench.livecc_adapter:LiveCCAdapter \
  --adapter-config examples/livecc/logical.json --pacing logical \
  --video-root "$VIDEO_ROOT" --output output/livecc-qa \
  --judge-mode exact --checkpoint-every 5 --preflight-only
for task in qa proactive; do
  trace run --task "$task" --release data/releases/v1.1.0 --subset tiny \
    --adapter trace_bench.livecc_adapter:LiveCCAdapter \
    --adapter-config examples/livecc/logical.json --pacing logical \
    --video-root "$VIDEO_ROOT" --output "output/livecc-$task" \
    --judge-mode exact --checkpoint-every 5 --proactive-window-s 5
  trace bundle validate "output/livecc-$task"
  trace score "output/livecc-$task" --judge-mode exact
done
```

Inspect completed records, failures, predictions and raw events. Logical pacing
and exact-only judging are diagnostic, not ranked timing or semantic quality.
A finalized bundle may contain failures. Use a new output directory for each
changed configuration; resume only with the original command.

## Timing experiments and full runs

For wall-clock measurements use `examples/livecc/wall_clock.json` and
`--pacing wall_clock` together. Configure the semantic judge as described in
[scoring](scoring-and-results.md). Full contains 833 QA and 415 Proactive records,
including sampling stress. The wrapper requires `jq`:

```bash
export VIDEO_ROOT=/path/to/trace-media
export LIVECC_ROOT=/path/to/livecc
export LIVECC_MODEL_PATH=/path/to/LiveCC-7B-Instruct
export OUTPUT_ROOT=output/livecc-full
bash scripts/run_livecc_v1_full.sh
```

The wrapper validates data, writes preflight snapshots, runs both tasks with
checkpoint/resume, and validates bundles. Defaults: GPU 0, wall-clock pacing,
5-second response tolerance, judge mode auto. Set `CUDA_VISIBLE_DEVICES`,
`PROACTIVE_WINDOW_S` and `JUDGE_MODE` to override. Outputs are
`$OUTPUT_ROOT/qa` and `$OUTPUT_ROOT/proactive`.

## Input, output and telemetry

`frames_per_chunk` controls model-call cadence, not Core's 1 FPS evidence.
The adapter resizes oversized frames on a factor-28 grid to `max_pixels`,
never upscales, and records submitted dimensions. It does not truncate KV history.
Context overflow yields a recoverable failure. Generation budgets are clamped
to remaining context; configured and effective budgets are recorded.

LiveCC's `...` is a provider continuation marker, not native silence.
The adapter uses the minimal fallback Proactive system prompt, sends the raw
instruction once and maps standalone fallback WAIT to a canonical WAIT event.
Raw provider text and generated token IDs remain in the bundle.

At the evidence endpoint Core flushes a partial chunk, then uses any remaining
strict-window grace if video ended earlier. Shutdown cannot start a newly
scoreable answer. The adapter declares persistent state and autonomous output;
these are Native Streaming candidate capabilities, subject to conformance review.

NVML measures process GPU baseline, sampled peak, increment, device identity,
sampling interval and competing processes where available. Unisolated memory
and an unobservable first token remain missing; allocator snapshots are
diagnostic and TTFT is never inferred from generation duration.
