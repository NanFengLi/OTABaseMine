# 变异工具实现状态

## ✅ INTEGER 变异

**文件**: `integer_mutation.py`  
**状态**: 完成 ✅  
**变异数量**: 3 条

| # | 内容 | 意图 |
|---|---|---|
| 1 | `randint(lb, ub)` | 合法范围内随机值 |
| 2 | `lb + 2^lbs - 1` | 比特冗余空间溢出，真实值超出 ub |
| 3 | `ub + 1` | 上界 +1 边界溢出 |

**测试文件**: `test/test_integer_mutate_new.py`

---

## ✅ OCTET STRING 变异

**文件**: `octet_string_mutation.py`  
**状态**: 完成 ✅  
**变异数量**: 受约束 4 条 / 无约束 22 条

**受约束（4 条）**：

| # | 长度头 | 内容 | 意图 |
|---|---|---|---|
| 1 | 随机合法值 | 空 | 声明长度 > 实际内容 |
| 2 | 0 | 100 字节 | 声明为空但填大量内容 |
| 3 | 随机合法值 | 比声明多 1 字节 | 内容越界 |
| 4 | maxe（lbs 位最大值）| ub 字节 | 超出约束上界 |

**无约束（22 条）**：10 个边界长度各 2 条，再加 2 条非法长度编码。

**测试文件**: `test/test_octet_string_mutate.py`

---

## ✅ BIT STRING 变异

**文件**: `bit_string_mutation.py`  
**状态**: 完成 ✅  
**变异数量**: 受约束 4 条 / 无约束 12 条

内容与 OCTET STRING 逻辑相同，差异为 delta 单位是**比特**（非字节）。无约束变异 length_mutations = [0, 127, 128]，各 3 条，再加 3 条非法长度编码。

---

## ✅ SEQUENCE OF 变异

**文件**: `sequence_of_mutation.py`  
**状态**: 完成 ✅  
**变异数量**: 4 条

只替换长度头比特，元素内容不变，delta 始终为 0。

| # | 长度头值 | 意图 |
|---|---|---|
| 1 | 0 | 声明 0 个元素 |
| 2 | 实际元素数 | 正常值（基准）|
| 3 | 随机值 | 随机错误长度 |
| 4 | maxe（lbs 位最大值）| 超出上界最大编码 |

---

## 核心架构

### 旧方案（已废弃，保留在 `integer_mutation_old.py`）
```
修改 Python 字典 → set_val() → pycrate 抛 invalid value 异常 → 无法编码
```

### 新方案（当前）
```
from_uper(hex) → 获取字段 UPER 比特串（去填充）
→ 手工构造变异比特串 → 在包比特流中定位字段
→ 原地替换 → bit_str_to_bytes() 输出
```

**关键设置**：
```python
ASN1Obj._SAFE_BND = False  # 必须在所有 pycrate import 前设置
ASN1Obj._SILENT = True
```

---

## 统一接口

```python
mutate_xxx(uper_hex, message_type, target_path, seed=None)
# 返回: List[(mutated_uper_hex, message_type, target_path)]
```

**Status**: WORKING - Returns ASN.1 UPER encoded bytes
