# 发布验证

[English](release-validation.md) | 简体中文

范围：软件 0.1.0、标注 v1.1.0。这些是软件检查，不是模型榜单结果。

2026-09-09 本地检查：有 PyTorch 的环境通过 135 项测试；仅 Core 的 sdist
检查跳过两个依赖 PyTorch 的模型模块。README 合成流程、双语命令/链接检查、
公开文件扫描及 Ruff 均通过。QA 和 Proactive 原始/重算合成准确率均为 1.0，无失败。
PyPI TLS 失败后，隔离打包和安装检查使用缓存的公开依赖 wheel，未关闭证书校验。
本地执行使用 Python 3.12。Python 3.13 已纳入 CI，本轮未在本机重新运行 3.13。

## 复现检查

在仓库根目录执行 README 的安装、合成流程和开发检查。
生成文件保存在被 Git 忽略的 `output/`，重复检查使用新输出目录。

合成检查要求 QA 和 Proactive 各一条、零失败，
原始和重算指标均满足 QA accuracy 1.0、Proactive window accuracy 1.0 且有窗口内回答，
并验证 synthetic/ineligible 标记。
12 秒 fixture 的窗口与默认 5 秒 polling 对齐；回归测试另用错过窗口的 polling
间隔，确认检查器会拒绝这种情况。Git 扫描要求 checkout，ZIP 用户收到简短错误及非零退出码。
所有 fenced 代码块语言参与双语比较；Bash、Python 和 JSON 还检查语法，不执行 Python 片段。

发行包检查从 sdist 解包后的源码运行测试（包含 `tests/conftest.py`），
再在独立环境安装 wheel，检查实际导入路径和包内 preset，
并通过安装的 wheel 运行两个合成任务。
sdist 中正常 setuptools egg-info 是元数据，不是模型/运行产物。

## 模型验证范围

此前 LiveCC 在真实 tiny 数据、本地权重上检查：
9 条 QA 和 9 条 Proactive 全部完成、无失败，使用 logical pacing 和 exact 诊断评分。
这不代表每次发布修订都重新进行了 GPU 推理，也不代表 wall-clock 时延认证
或在线语义 judge 验证。
ThinkStream 有模拟运行测试，真实 GPU 仍待重新验证。
环境要求见各模型指南，比较前需检查实际结果。
