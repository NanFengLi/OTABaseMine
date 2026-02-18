# RRC 合法测试样例生成器

## 概述

本模块从 OTABase 的 `artifact/test-case-generator/rrc` 中抽取了 **RRC 合法消息生成**的核心逻辑，
去除了变异（mutation）和模糊测试（fuzzing）策略，专注于生成符合 3GPP RRC 规范的合法 DL-DCCH-Message。

### 与原始代码的关系

| 原始文件 | 本模块文件 | 说明 |
|---------|-----------|------|
| `rrc/rrc_fields.py` | `rrc_fields.py` | 字段类型枚举，增加了辅助方法 |
| `rrc/rrc_choices.py` | `rrc_choices.py` | CHOICE 路径分析，原样保留 |
| `rrc/rrc_stats.py` | `rrc_stats.py` | 统计分析，原样保留 |
| `rrc/rrc_generator.py` | `rrc_generator.py` | 核心生成器，去除了对 abstract_classes 的依赖 |
| `rrc/rrc_utils.py`（精简部分） | `rrc_utils.py` | 消息精简工具函数（路径过滤、字段删除） |
| `rrc/rrc_fuzzer.py` | ❌ 不包含 | 变异策略（BASE、TRUNCATE、ADD 等）|
| `rrc/rrc_controller.py` | `rrc_batch_generator.py` | 批量生成控制器，替代了 Controller+Fuzzer |
| `main_rrc.py` | `main.py` | 命令行入口，简化为仅生成功能 |
| `rrc/releaseLTE_R17/` | `releaseLTE_R17/` → symlink | ASN.1 定义文件（符号链接） |

### 去除的依赖

- `abstract_classes/generator.py` — 抽象生成器基类（直接实现）
- `abstract_classes/fuzzer.py` — 抽象模糊器基类（不需要）
- `utils/rollback_queue.py` — 回滚队列（变异专用）
- `utils/logging_config.py` — 日志配置（内置实现）
- `pandas` — 统计数据分析（仅变异/调试用）

## 消息精简机制

对于每条目标字段路径，生成器会输出一个**最小合法 RRC 消息**，而不是包含所有可选字段的完整消息：

1. **生成完整消息**：先递归遍历 ASN.1 结构，生成包含所有必需字段和可选字段的完整消息
2. **路径分析**：对每条新覆盖的目标路径，分析 optional_paths 中哪些是到达目标所必需的（祖先/子节点），哪些是无关的
3. **字段删除**：删除所有与目标路径无关的可选字段，包括嵌套在 OCTET STRING 容器中的字段
4. **重新编码**：将精简后的消息字典重新 UPER 编码

精简效果示例（OCTET_STRING 目标，116 条路径）：

| 指标 | 值 |
|------|----|
| 最小消息 | 11 bytes |
| 中位数 | 40 bytes |
| 平均值 | 65.9 bytes |
| 最大消息 | 587 bytes（深度嵌套路径）|

## 安装

```bash
pip install pycrate
```

## 用法

### 命令行

```bash
# 从项目根目录运行
cd /path/to/OTABaseMine

# 生成覆盖所有 OCTET_STRING 路径的合法载荷（默认）
python -m bishe.generate_new.main

# 指定多种目标字段类型
python -m bishe.generate_new.main -f BIT_STRING OCTET_STRING INTEGER SEQOF

# 指定输出文件、种子和循环次数
python -m bishe.generate_new.main -f OCTET_STRING -s 42 -c 2 -o output/my_payloads.txt

# 生成单个数据包（测试）
python -m bishe.generate_new.main -t single -v

# 显示字段统计信息
python -m bishe.generate_new.main -t stats

# 基准测试（默认 100 个包）
python -m bishe.generate_new.main -t benchmark -n 200
```

### Python API

```python
from bishe.generate_new.rrc_generator import RRCGenerator
from bishe.generate_new.rrc_batch_generator import RRCBatchGenerator
from bishe.generate_new.rrc_fields import Fields

# 方式1: 使用生成器直接生成单个完整数据包
generator = RRCGenerator(
    targets=[Fields.OCTET_STRING, Fields.BIT_STRING],
    seed=42
)
uper_bytes, result_dict, mutation_paths, optional_paths = generator.generate_packet()
print(f"完整消息 UPER hex: {uper_bytes.hex()}")

# 方式2: 生成单个精简数据包（仅保留到达目标字段的最小结构）
batch_gen = RRCBatchGenerator(
    targets=[Fields.OCTET_STRING],
    seed=42,
    cycles=1
)
simp_hex, target_path, msg_type = batch_gen.generate_single_simplified()
print(f"精简消息 hex: {simp_hex}")
print(f"目标路径: {target_path}")

# 方式3: 批量生成覆盖所有路径的精简载荷
result = batch_gen.generate_all(output_file="output/payloads.txt")
print(f"生成了 {result['total_count']} 个最小合法载荷")
```

## 输出格式

输出文件格式兼容 OTABase 执行框架：

```
<total_payload_count>
<payload_id>,<hex_payload>,<target_message_type>,<target_field_path>
<payload_id>,<hex_payload>,<target_message_type>,<target_field_path>
...
```

例如：
```
000042
1,28a3f1...,rrcConnectionReconfiguration,message,c1,rrcConnectionReconfiguration,...
2,18b2e0...,rrcConnectionSetup,message,c1,rrcConnectionSetup,...
...
```

## 命令行参数

| 参数 | 短名 | 说明 | 默认值 |
|------|------|------|--------|
| `--fields` | `-f` | 目标字段类型 | `OCTET_STRING` |
| `--cycles` | `-c` | 生成循环次数 | `1` |
| `--seed` | `-s` | 随机种子 | `1` |
| `--output` | `-o` | 输出文件路径 | `output/rrc_legitimate_payloads.txt` |
| `--report` | `-r` | 生成报告 JSON 文件 | `output/generation_report.json` |
| `--test` | `-t` | 测试模式 (`single`/`stats`/`benchmark`) | 无 |
| `--recur-depth` | — | 最大递归展开深度 | `0` |
| `--no-optional` | — | 不生成可选字段 | `False` |
| `--debug` | `-d` | 启用调试日志 | `False` |
| `--verbose` | `-v` | 详细输出 | `False` |
| `--benchmark-count` | `-n` | 基准测试包数量 | `100` |

## 架构

```
generate_new/
├── __init__.py              # 模块初始化
├── config.py                # 配置
├── main.py                  # 命令行入口
├── rrc_fields.py            # 字段类型枚举
├── rrc_choices.py           # CHOICE 路径分析
├── rrc_stats.py             # 统计分析
├── rrc_generator.py         # 核心 ASN.1 递归生成器
├── rrc_utils.py             # 消息精简工具（路径过滤、字段删除）
├── rrc_batch_generator.py   # 批量生成控制器（含精简逻辑）
├── releaseLTE_R17/ -> symlink  # ASN.1 定义文件
└── output/                  # 默认输出目录
```
