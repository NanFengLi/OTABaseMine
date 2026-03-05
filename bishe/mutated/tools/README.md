# RRC 消息变异工具

基于 OTABase 项目的 BASE 变异策略，在 **UPER 比特流层面**直接替换字段，完全绕过 pycrate 约束校验，实现非法 ASN.1 编码的生成。

## 项目背景

本项目复现了 [OTABase](https://github.com/OTABase/OTABase) 项目中的 RRC 消息变异策略，用于生成针对不同字段类型的非法 ASN.1 变异测试用例。

**核心思路**：不再通过修改字典后调用 `set_val()` 触发 pycrate 抛出 `invalid value` 异常，而是：
1. `from_uper(hex)` 加载合法消息
2. 获取目标字段的 UPER 比特串（去除填充）
3. 手工构造违反规范的变异比特串
4. 在包比特流中定位字段位置
5. 原地替换后输出——完全绕过 pycrate 校验

## 功能特性

实现了 BASE 策略的四种字段类型变异：

1. **INTEGER 字段变异** - 利用位表示范围和规范约束之间的差异
2. **OCTET_STRING 字段变异** - 针对有约束和无约束两种情况的长度/内容不匹配
3. **BIT_STRING 字段变异** - 类似 OCTET_STRING，但操作位级别
4. **SEQUENCE OF 字段变异** - 长度声明与实际元素数量的不匹配

## 目录结构

```
bishe/mutated/
├── tools/
│   ├── __init__.py                    # 包导出（四个 mutate_xxx 函数）
│   ├── mutation_utils.py              # 通用工具（比特转换、长度编码等）
│   ├── integer_mutation.py            # INTEGER 字段变异
│   ├── integer_mutation_old.py        # 旧版实现（已废弃，仅供参考）
│   ├── octet_string_mutation.py       # OCTET STRING 字段变异
│   ├── bit_string_mutation.py         # BIT STRING 字段变异
│   ├── sequence_of_mutation.py        # SEQUENCE OF 字段变异
│   ├── example_usage.py               # 使用示例
│   └── README.md                      # 本文档
└── test/
    ├── test_integer_mutate_new.py     # INTEGER 变异测试
    └── test_octet_string_mutate.py    # OCTET STRING 变异测试
```

## 依赖

```bash
conda activate bishe
# 依赖 pycrate_asn1dir（RRCLTE）
```

## 使用方法

### 统一接口

四个工具的调用方式完全一致：

```python
from bishe.mutated.tools import mutate_integer, mutate_octet_string, mutate_bit_string, mutate_sequence_of

# 输入：合法消息的 UPER hex + 消息类型 + 目标字段路径
results = mutate_integer(
    uper_hex     = "0a501a2ba8a181f05b",
    message_type = "dlInformationTransfer",
    target_path  = ["message", "c1", "dlInformationTransfer",
                    "criticalExtensions", "c1",
                    "dlInformationTransfer-r15",
                    "timeReferenceInfo-r15", "time-r15", "refDays-r15"],
    seed         = 42,   # 可选，固定随机种子
)

# 输出：List[(mutated_uper_hex, message_type, target_path)]
for mut_hex, msg_type, path in results:
    print(f"变异后 hex: {mut_hex[:20]}...")
```

### 输入格式

与 `rrc_legitimate_payloads.txt` 格式对应：
```
uper_hex, message_type, path_1, path_2, ..., path_n
```

### 输出格式

```python
[
    ("0a501a2b...",  "dlInformationTransfer",  ["message", ..., "refDays-r15"]),  # 变异1
    ("0a501a2b...",  "dlInformationTransfer",  ["message", ..., "refDays-r15"]),  # 变异2
    ...
]
```

每个元组：`(变异后消息的 UPER hex, 消息类型, 目标路径)`

> `message_type` 和 `target_path` 原样透传，只有第一个元素（hex）发生变化。

### 运行测试

```bash
cd <项目根目录>
conda activate bishe
python -m bishe.mutated.test.test_integer_mutate_new
python -m bishe.mutated.test.test_octet_string_mutate
```

## API 文档

四个函数签名完全一致：

```python
mutate_xxx(
    uper_hex:     str,          # 合法消息的 UPER 十六进制字符串
    message_type: str,          # 消息类型名称（原样透传到输出）
    target_path:  List[str],    # 目标字段路径列表
    seed:         int = None,   # 随机数种子（可选）
) -> List[Tuple[str, str, List[str]]]
```

### 各字段类型变异策略

#### INTEGER（3 条）

| # | 变异内容 | 意图 |
|---|---|---|
| 1 | `randint(lb, ub)` | 合法范围内随机值 |
| 2 | `lb + 2^lbs - 1`（lbs 位全1）| 比特冗余空间溢出，真实值超出 ub |
| 3 | `ub + 1` | 上界 +1 边界溢出 |

#### OCTET STRING — 受约束（4 条）

| # | 长度头 | 内容 | 意图 |
|---|---|---|---|
| 1 | 随机合法值 | 空 | 声明长度 > 实际内容 |
| 2 | 0 | 100 字节 | 声明为空但填大量内容 |
| 3 | 随机合法值 | 比声明多 1 字节 | 内容越界 |
| 4 | maxe（lbs位最大值）| ub 字节 | 超出约束上界 |

#### OCTET STRING — 无约束（22 条）

10 个边界长度值（0, 127, 128, 16383, 16384, …, 65535），各生成 2 条（空内容 / 内容不足），再加 2 条非法长度编码变异。

#### BIT STRING — 受约束（4 条）

与 OCTET STRING 受约束逻辑相同，但 delta 单位为**比特**（非字节）。

#### BIT STRING — 无约束（12 条）

length_mutations = [0, 127, 128]，各生成 3 条（空 / 不足 / 溢出），再加 3 条非法长度编码变异。

#### SEQUENCE OF（4 条）

只替换长度头比特，内容不变，delta = 0：

| # | 长度头值 | 意图 |
|---|---|---|
| 1 | 0 | 声明 0 个元素 |
| 2 | 实际元素数 | 正常值（验证基准）|
| 3 | 随机值 | 随机错误长度 |
| 4 | maxe（lbs位最大值）| 超出上界最大编码 |

## 约束信息的获取

新接口（比特流方式）**不需要**手动传入 `lower_bound` / `upper_bound`，工具会在加载消息后自动从 pycrate 对象的 `_const_val` / `_const_sz` 属性中读取约束，无需额外输入。

 > 输入只需要：`uper_hex`、`message_type`、`target_path`。

## 与 OTABase 的对比

### 已实现
✅ BASE 策略全部四种字段类型变异  
✅ 受约束 / 无约束两种情况  
✅ UPER 比特流层面直接替换（绕过 pycrate 校验）  
✅ PER 编码边界测试  
✅ 长度/内容不匹配、溢出/下溢  

### 未实现（按需求扩展）
❌ TRUNCATE 策略（截断数据包）  
❌ ADD 策略（添加可选字段）  
❌ 祖先字段长度自动调整  
❌ OCTET STRING 中嵌入的 ASN.1 递归变异

## 输出格式

所有工具统一返回 `List[Tuple[str, str, List[str]]]`：

```python
[
    (mutated_uper_hex, message_type, target_path),
    ...
]
```

与 `rrc_legitimate_payloads.txt` 格式对应，可直接写入文件：

```python
for mut_hex, msg_type, path in results:
    line = ",".join([mut_hex, msg_type] + path)
    f.write(line + "\n")
```

## 参考资料

- OTABase GitHub: https://github.com/OTABase/OTABase
- 3GPP TS 36.331: RRC Protocol Specification

## 许可证

本项目基于 OTABase 的开源实现，遵循相同的许可证。
