# LiveCC 适配器

[English](livecc-adapter.md) | 简体中文

`trace_bench.livecc_adapter:LiveCCAdapter` 运行本地
[LiveCC-7B-Instruct](https://huggingface.co/chenjoya/LiveCC-7B-Instruct) 权重。
只消费 Core 的 `Observation.rgb`，不自行打开视频或回放文件。
权重和 processor 加载一次，每条记录独立创建 `past_ids/past_key_values`。

## 环境

在独立模型环境内完成[上游安装](https://github.com/showlab/livecc)和
[推理配置](https://github.com/showlab/livecc/blob/main/inference.md)。
需要源码中的 `demo.infer`，并准备空闲 NVIDIA GPU、CUDA 和兼容的 FlashAttention 2。

此前测试环境：Python 3.12、PyTorch 2.8.0+cu126、Transformers 4.57.3、
FlashAttention 2.8.3、liger-kernel 0.7.0、accelerate 1.12.0、
livecc-utils 0.0.2、qwen-vl-utils 0.0.11、NumPy 1.26.4、OpenCV 4.11.0.86。
FlashAttention 必须匹配 PyTorch/CUDA/GLIBC。保留 qwen-vl-utils 0.0.11，
新版本删除了 livecc-utils 依赖的符号。

在该环境内进入 TRACE 根目录，替换两个路径并执行：

```bash
export LIVECC_ROOT=/path/to/livecc
export LIVECC_MODEL_PATH=/path/to/LiveCC-7B-Instruct
export CUDA_VISIBLE_DEVICES=0
export TOKENIZERS_PARALLELISM=false
python -m pip install 'qwen-vl-utils==0.0.11' 'livecc-utils==0.0.2'
python -m pip install -e .
python -c "import torch; from livecc_utils import prepare_multiturn_multimodal_inputs_for_generation; assert torch.cuda.is_available()"
```

先解决上游导入/CUDA 错误。推理不需要开发依赖；运行测试套件时安装 `'.[dev]'`。

## Tiny 执行检查

按[数据准备](data-setup.zh-CN.md)配置视频，替换 VIDEO_ROOT 后执行：

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

检查完成题目、失败、预测及原始事件。Logical pacing 和 exact-only 评分是诊断流程，
不能作为正式时延或语义质量结果。Finalized bundle 也可能包含失败题。
每次变更配置使用新输出目录；续跑必须使用原命令。

## 时延实验与全量运行

测量 wall-clock 时延时，同时使用 `examples/livecc/wall_clock.json` 和
`--pacing wall_clock`。按[评分教程](scoring-and-results.zh-CN.md)配置语义 judge。
Full 包含 833 条 QA、415 条 Proactive（含采样压力子集）。运行脚本需要 `jq`：

```bash
export VIDEO_ROOT=/path/to/trace-media
export LIVECC_ROOT=/path/to/livecc
export LIVECC_MODEL_PATH=/path/to/LiveCC-7B-Instruct
export OUTPUT_ROOT=output/livecc-full
bash scripts/run_livecc_v1_full.sh
```

脚本验证数据、写入 preflight 快照、执行两个任务并启用 checkpoint/resume，最后验证 bundle。
默认 GPU 0、wall-clock pacing、5 秒响应容差、judge mode auto。
可通过 `CUDA_VISIBLE_DEVICES`、`PROACTIVE_WINDOW_S`、`JUDGE_MODE` 覆盖。
结果位于 `$OUTPUT_ROOT/qa` 和 `$OUTPUT_ROOT/proactive`。

## 输入、输出与遥测

`frames_per_chunk` 控制模型调用频率，不改变 Core 的 1 FPS 证据。
适配器将过大帧按 factor-28 网格缩小至 `max_pixels`，不放大，并记录提交尺寸。
不截断 KV 历史；上下文溢出记录为可恢复失败。
生成预算受剩余上下文限制，同时记录配置值和实际值。

LiveCC 的 `...` 是 provider 续写标记，不是原生 silence。
适配器使用最小 Proactive fallback system prompt，只发送一次原始指令，
将独立的 fallback WAIT 映射为标准 WAIT 事件。原始文本和生成 token ID 保留在 bundle 中。

证据结束时 Core flush 未满 chunk；视频提前结束时使用严格窗口剩余 grace。
Shutdown 不能启动新的可评分回答。适配器声明持久状态和自主输出，
因此是 Native Streaming 候选能力，仍需符合性审查。

条件允许时，NVML 测量进程 GPU 基线、采样峰值、增量、设备、采样间隔及竞争进程。
无法隔离的显存或不可观测首 token 保持缺失；allocator 快照只作诊断，
不使用总生成时间估算 TTFT。
