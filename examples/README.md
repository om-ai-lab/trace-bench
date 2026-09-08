# Model examples

Implementations remain at their stable `open_stream_bench.*_adapter` imports;
configuration examples live here. Install upstream model dependencies and obtain
weights from upstream under their own licenses; OSB does not distribute them.

- [LiveCC upstream](https://github.com/showlab/livecc),
  [weights](https://huggingface.co/chenjoya/LiveCC-7B-Instruct),
  [OSB instructions](../docs/livecc-adapter.md).
- [ThinkStream upstream](https://github.com/CASIA-IVA-Lab/ThinkStream),
  [weights](https://huggingface.co/CASIA-IVA-Lab/ThinkStream-3B),
  [response contract](../docs/thinkstream-adapter-contract.md).

For ThinkStream, copy `thinkstream/config.json` to an external local file and
replace the source/weight paths. In the model's environment:

```bash
python -m pip install -e /path/to/open_stream_bench
osb run --task qa --release data/releases/v1.1.0 --subset tiny \
  --adapter open_stream_bench.thinkstream_adapter:ThinkStreamAdapter \
  --adapter-config /path/to/thinkstream-local.json --pacing wall_clock \
  --video-root /path/to/osb-media --output /path/to/results/thinkstream-qa \
  --preflight-only
```

Repeat without `--preflight-only` to infer; use `--task proactive` with a new
output directory and `--proactive-window-s 5` for Proactive. Run
`osb bundle validate /path/to/results/thinkstream-qa` afterwards.
See [scoring](../docs/scoring-and-results.md) before comparing results.
