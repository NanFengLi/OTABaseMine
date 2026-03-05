# RRC 消息变异工具——实现总结

## 项目概述

本项目复现了 [OTABase](https://github.com/OTABase/OTABase) 的 BASE 变异策略，实现了针对 RRC 消息不同字段类型的**比特流层面**变异工具。

**核心思路**：`from_uper()` 加载合法消息 → 获取字段 UPER 比特串 → 手工构造非法比特变异 → 在包比特流中定位字段 → 原地替换——完全绕过 pycrate 校验。

---

## 已完成的工作

### 变异工具汇总

| 字段类型 | 文件 | 状态 | 变异数量 |
|---------|------|------|----------|
| **INTEGER** | `integer_mutation.py` | ✅ 完成 | 3 条 |
| **OCTET STRING** | `octet_string_mutation.py` | ✅ 完成 | 受约束 4 条 / 无约束 22 条 |
| **BIT STRING** | `bit_string_mutation.py` | ✅ 完成 | 受约束 4 条 / 无约束 12 条 |
| **SEQUENCE OF** | `sequence_of_mutation.py` | ✅ 完成 | 4 条 |

### 辅助模块

**`mutation_utils.py`**——共生工具函数：

| 函数 | 功能 |
|---|---|
| `bytes_to_bit_str` | bytes 转 01 字符串 |
| `bit_str_to_bytes` | 01 字符串转 bytes |
| `n_random_bits` | 生成 n 个随机比特 |
| `generate_random_bytes` | 生成随机字节 |
| `encode_unbound_length` | 无约束长度 PER 编码 |
| `generate_invalid_length_encoding` | 生成非法长度编码 |

---

## 变异策略详解

### INTEGER（3 条）

设 `lbs = floor(log2(ub - lb)) + 1`（字段实际占用比特数）：

1. **合法随机值**：`randint(lb, ub) - lb`，合规但随机
2. **比特冗余溢出**：编码 = `2^lbs - 1`，真实值 = `lb + 2^lbs - 1 ≥ ub`
3. **上界 +1 溢出**：编码 = `ub - lb + 1`

### OCTET STRING — 受约束（4 条）

UPER 格式：`[长度头: lbs 位][内容字节]`

1. 合法长度，空内容
2. 长度声明为 0，但内容填 100 字节
3. 随机长度，内容比声明大 1
4. 长度头放 maxe，内容填 ub 字节

### OCTET STRING — 无约束（22 条）

变长长度编码格式：0∼127→1字节，128∼16383→2字节，≥16384→1分片。

- 10 个边界长度各 2 条：空内容 + 内容不足声明长度
- 2 条非法长度编码

### BIT STRING（与 OCTET STRING 类似）

- 受约束：4 条，delta 单位为**比特**
- 无约束：length_mutations = [0, 127, 128]，各 3 条 + 3 条非法编码 = 12 条

### SEQUENCE OF（4 条）

只替换长度头，元素内容不变，长度值分别为 0 / 实际元素数 / 随机值 / maxe。

---

## 统一接口

```python
mutate_xxx(
    uper_hex:     str,         # 合法消息的 UPER 十六进制字符串
    message_type: str,         # 消息类型名称
    target_path:  List[str],   # 目标字段路径
    seed:         int = None,  # 随机数种子（可选）
) -> List[Tuple[str, str, List[str]]]
# 返回: [(mutated_uper_hex, message_type, target_path), ...]
```

不需要手动传入约束信息，工具自动从 pycrate 对象读取。

---

## 文件结构

```
bishe/mutated/
├── tools/
│   ├── __init__.py
│   ├── mutation_utils.py
│   ├── integer_mutation.py          ← 新版（比特流方式）
│   ├── integer_mutation_old.py      ← 旧版（已废弃）
│   ├── octet_string_mutation.py
│   ├── bit_string_mutation.py
│   └── sequence_of_mutation.py
└── test/
    ├── test_integer_mutate_new.py
    └── test_octet_string_mutate.py
```

---

## 与 OTABase 对比

| 特性 | 状态 |
|---|---|
| BASE 策略四种字段类型 | ✅ |
| 受约束 / 无约束处理 | ✅ |
| UPER 比特流层面直接替换 | ✅ |
| PER 编码边界测试 | ✅ |
| TRUNCATE 策略 | ❌ |
| ADD 策略 | ❌ |
| 祖先字段长度自动调整 | ❌ |
| OCTET STRING 嵌入 ASN.1 递归变异 | ❌ |

