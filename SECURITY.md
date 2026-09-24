# Security / 安全

Report vulnerabilities privately using the repository's
[security reporting page](https://github.com/om-ai-lab/trace-bench/security/advisories/new)
if enabled. Otherwise open an issue requesting a private contact channel,
without exploit details or credentials. Do not post secrets, private endpoints,
videos or personal data in public issues.

若仓库已启用私密安全报告，请通过上述链接报告漏洞。否则先提 issue 请求私密联系渠道，
不要公开漏洞利用细节、凭据、私有服务地址、视频或个人数据。

Adapters execute Python code with your process permissions; install only trusted
code. Judge requests send question/reference/prediction text to your configured
service. Sanitize bundles before sharing. Fixes target the current main branch;
use the latest reviewed software release.

Adapter 以当前进程权限执行 Python，请仅安装可信代码。
Judge 会将问题、参考答案和预测文本发送到指定服务。共享 bundle 前需脱敏。
修复面向当前 main 分支，请使用最新经审阅的软件版本。
