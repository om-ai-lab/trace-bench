# ThinkStream integration (experimental)

English | [简体中文](thinkstream-adapter.zh-CN.md)

The bundled `trace_bench.thinkstream_adapter:ThinkStreamAdapter`
provides a local-weight integration. Its contract has CPU fake-runtime tests;
this release revision has not been revalidated with real ThinkStream weights.
Use [LiveCC](livecc-adapter.md) for the previously GPU-checked walkthrough.

## Setup

Install [ThinkStream](https://github.com/CASIA-IVA-Lab/ThinkStream) and its
checkpoint following upstream instructions in a separate CUDA environment.
The adapter requires upstream `thinkstream.model`,
`thinkstream.model.inference` and `thinkstream.data.stream_data_processor`,
plus PyTorch, Transformers and FlashAttention 2. Weights alone are insufficient.

In the TRACE root, create `output/` and save this JSON as
`output/thinkstream.local.json`, replacing paths with your locations.
This file stays local and ignored. Retain the upstream 24576-token context
default unless explicitly studying a different configuration.

```json
{
  "model_id": "/path/to/ThinkStream-3B",
  "thinkstream_root": "/path/to/ThinkStream",
  "frames_per_chunk": 2,
  "max_len": 24576,
  "device": "cuda:0"
}
```

## Tiny run

Prepare the [source videos](data-setup.md). Execute in the model environment
from the TRACE root after saving the configuration above:

```bash
mkdir -p output
export CUDA_VISIBLE_DEVICES=0
export VIDEO_ROOT=/path/to/trace-media
python -m pip install -e .
trace run --task qa --release data/releases/v1.1.0 --subset tiny \
  --adapter trace_bench.thinkstream_adapter:ThinkStreamAdapter \
  --adapter-config output/thinkstream.local.json --pacing wall_clock \
  --video-root "$VIDEO_ROOT" --output output/thinkstream-qa \
  --judge-mode exact --checkpoint-every 5 --preflight-only
for task in qa proactive; do
  trace run --task "$task" --release data/releases/v1.1.0 --subset tiny \
    --adapter trace_bench.thinkstream_adapter:ThinkStreamAdapter \
    --adapter-config output/thinkstream.local.json --pacing wall_clock \
    --video-root "$VIDEO_ROOT" --output "output/thinkstream-$task" \
    --judge-mode exact --checkpoint-every 5 --proactive-window-s 5
  trace bundle validate "output/thinkstream-$task"
  trace score "output/thinkstream-$task" --judge-mode exact
done
```

Preflight checks configuration without loading weights; it cannot prove the
GPU runtime works. Inspect failed records, generated text, frame commits,
end-of-evidence flush and telemetry coverage before using results.
Exact scores only check execution. Configure a [semantic judge](scoring-and-results.md)
for semantic quality; do not treat a successful CLI exit as conformance proof.

## Adapter behavior

The adapter declares persistent visual state, autonomous output and wall-clock
pacing. Each record gets a new streaming inference session. It processes Core
RGB arrays in chunks; it does not fetch arbitrary video frames. QA queues its
unchanged user text before the question-time frame and answers only after that
frame is processed. History work is recorded separately.

Provider `<silent>` maps to WAIT. Response fragments preserve raw text, token IDs,
stable response IDs, ordering and finalization so scoring assembles one answer
episode rather than counting every fragment as a new answer. The final partial
chunk is flushed at the evidence boundary; shutdown cannot start new scoreable
responses. Missing timing/resource measurements remain missing.

The integration is an example of the [adapter contract](adapter-guide.md).
Private launch scripts are not needed by these commands and are not distributed.
