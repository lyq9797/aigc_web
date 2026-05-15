# SECURITY.md
## 1 安全说明
本项目采用`Bandit(Python静态代码扫描)`、`Safety(第三方依赖漏洞检测)`、`Semgrep(Python通用规则)`、`Semgrep(OWASP安全规则审计)`四种自动化安全扫描工具开展代码安全常态化检测，已完成首轮全量安全漏洞整改，所有中低危安全问题修复完毕。

## 2 已修复安全漏洞清单
### 2.1 Bandit 静态代码漏洞修复（原14处告警全部修复）
| 漏洞类型 | 风险编号 | 涉及文件 | 整改内容 |
| ---- | ---- | ---- | ---- |
| 命令注入风险（CWE-78，subprocess滥用 B404/B603） | LOW | app/detectors/sentence_level.py、app/detectors/word_level.py | 1.优化subprocess调用逻辑，命令统一使用**列表传参**，禁用字符串拼接外部可控输入；<br>2.非必要场景移除subprocess依赖，改用原生Python实现功能 |
| HuggingFace模型远程下载无版本锁定（CWE-494 B615，恶意模型劫持） | MEDIUM | app/detectors/word_level.py、app/detectors/word_model_runtime.py、work1/test_single_text.py、work2/deberta_CRF(new)_single_text.py | `from_pretrained()`全部新增`revision=固定commit哈希`参数，锁定模型版本，防止远程仓库投毒 |
| PyTorch不安全反序列化（CWE-502 B614，恶意权重文件代码执行） | MEDIUM | app/detectors/word_level.py、work1/test_single_text.py、work2/deberta_CRF(new)_single_text.py | 所有`torch.load()`配置`weights_only=True`，关闭不安全对象反序列化 |

### 2.2 Semgrep OWASP安全漏洞修复（OWASP A09、CWE-532 日志敏感信息泄露）
- 涉及文件：`app/detectors/word_model_runtime.py:268`
- 问题：日志明文打印模型内部标识符，存在日志敏感数据泄露风险
- 整改：移除敏感字段日志打印或对输出内容脱敏，避免内部关键数据落地日志文件。

### 2.3 Safety 第三方依赖包漏洞修复
原`torch==2.6.0+cu124`存在2个拒绝服务漏洞（CVE-2025-3730、CVE-2025-2953），已升级`torch/torchaudio/torchvision`至安全版本（≥2.8.0），配套更新相关CUDA版本，消除本地DoS攻击风险；其余27个依赖包无高危安全漏洞。

## 3 项目安全管控规范
### 3.1 代码提交规范
1. 代码合并前必须执行**Bandit+Semgrep**自动化扫描，无新增安全漏洞方可合并代码；
2. 禁止未经安全校验的`subprocess/os.system`系统调用，禁止动态反序列化未知来源`.pth/.bin`权重文件。

### 3.2 依赖管理规范
1. 项目新增Python依赖前，使用`safety scan`校验依赖安全漏洞，存在高危漏洞不引入；
2. 每季度定期执行全量依赖漏洞巡检，同步更新存在安全缺陷的第三方库版本。

### 3.3 模型加载安全规范
1. HuggingFace预训练模型加载强制锁定revision哈希值，不使用默认最新版；
2. 外部导入PyTorch权重文件统一启用`weights_only=True`，不加载自定义Python对象。

## 4 漏洞上报方式
1. 如在项目使用过程中发现新安全漏洞，请通过项目Issues提交安全反馈；
2. 漏洞描述需附带漏洞路径、复现步骤、风险等级，项目维护人员收到后优先处理安全类缺陷。


> 扫描基准日期：2026-05-08到2026-05-13