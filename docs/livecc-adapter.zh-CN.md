# LiveCC Adapter（OSB 合约 v4）

本教程说明如何使用本地 LiveCC-7B-Instruct 权重接入 OSB Core。适配器只消费 Core 传入的 RGB 帧，不读取视频文件；每条记录独立维护历史状态。

## 环境

请按[上游安装说明](https://github.com/showlab/livecc)和[推理指南](https://github.com/showlab/livecc/blob/main/inference.md)安装，并下载[模型权重](https://huggingface.co/chenjoya/LiveCC-7B-Instruct)。还需要上游源码中的 `demo.infer`、CUDA 与 FlashAttention 2。请固定 `qwen-vl-utils==0.0.11`、`livecc-utils==0.0.2`。

```bash
export LIVECC_ROOT=/path/to/livecc
export LIVECC_MODEL_PATH=/path/to/LiveCC-7B-Instruct
export CUDA_VISIBLE_DEVICES=0
cd /path/to/open_stream_bench
python -m pip install 'qwen-vl-utils==0.0.11' 'livecc-utils==0.0.2'
python -m pip install -e .
```

## 运行

配置示例见 `examples/livecc/wall_clock.json`。Core 始终提供 1 FPS RGB 序列；正式延迟结果使用 `pacing=wall_clock`，logical pacing 只用于 smoke test。

```bash
osb run --task qa --release data/releases/v1.1.0 --subset tiny \
  --adapter open_stream_bench.livecc_adapter:LiveCCAdapter \
  --adapter-config examples/livecc/wall_clock.json \
  --video-root /path/to/local/videos --pacing wall_clock \
  --output runs/livecc-v4-qa-tiny
```

Proactive 将 `--task` 改为 `proactive`，并加入两个 5 秒窗口参数。结果会保存原始输出、token、帧提交和 telemetry；无法观测首 token 时 TTFT 保持 null。完整运行执行 `scripts/run_livecc_v1_full.sh`，支持断点续跑和 bundle 校验。该适配器是 Native Streaming 候选，最终分类以运行时证据为准。
