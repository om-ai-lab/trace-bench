# ThinkStream 集成（实验性）

[English](thinkstream-adapter.md) | 简体中文

仓库中的 `trace_bench.thinkstream_adapter:ThinkStreamAdapter`
支持本地权重接入。其接口有 CPU 模拟运行测试，但本轮发布修订没有重新使用真实
ThinkStream 权重验证。此前经过 GPU 检查的教程见 [LiveCC](livecc-adapter.zh-CN.md)。

## 配置

在独立 CUDA 环境内，按 [ThinkStream 上游](https://github.com/CASIA-IVA-Lab/ThinkStream)
说明安装源码和权重。适配器需要 `thinkstream.model`、
`thinkstream.model.inference`、`thinkstream.data.stream_data_processor`，
以及 PyTorch、Transformers 和 FlashAttention 2；仅有权重不足以运行。

在 TRACE 根目录创建 `output/`，将以下 JSON 保存为
`output/thinkstream.local.json`，替换为实际路径。该文件仅保留在本地并被 Git 忽略。
除非明确研究其他配置，否则保留上游 24576-token 上下文默认值。

```json
{
  "model_id": "/path/to/ThinkStream-3B",
  "thinkstream_root": "/path/to/ThinkStream",
  "frames_per_chunk": 2,
  "max_len": 24576,
  "device": "cuda:0"
}
```

## Tiny 运行

准备[源视频](data-setup.zh-CN.md)，保存上述配置后，在模型环境的 TRACE 根目录执行：

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

Preflight 不加载权重，只检查配置，不能证明 GPU 环境可运行。
使用结果前检查失败题、生成文本、帧提交、证据结束 flush 和遥测覆盖率。
Exact 评分只检查执行；语义质量使用[语义 judge](scoring-and-results.zh-CN.md)。
CLI 成功退出不能替代符合性审查。

## 适配器行为

适配器声明持久视觉状态、自主输出和 wall-clock pacing。
每条记录创建新的流式推理会话，按 chunk 处理 Core RGB 数组，不自行获取任意视频帧。
QA 在提问时刻帧之前排入原样 user 文本，只在该帧处理后回答；历史处理成本单独记录。

原生 `<silent>` 映射为 WAIT。回答片段保留原始文本、token ID、
稳定 response ID、顺序和结束标记，让 scorer 组装为一次回答，而非把每个片段当新答案。
最后未满 chunk 在证据终点 flush；shutdown 不能启动新的可评分回答。
无法观测的时间或资源指标保持缺失。

集成遵循 [adapter 合约](adapter-guide.zh-CN.md)。
这些命令不依赖私有启动脚本，仓库也不分发这些脚本。
