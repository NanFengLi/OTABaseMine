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
│   ├── __init__.py                    # 包导出（4G + 5G 共 10 个函数）
│   ├── mutation_utils.py              # 通用工具（比特转换、路径解析、类型查找等）
│   ├── field_type_inspector.py        # 4G 字段类型识别
│   ├── field_type_inspector_5g.py     # 5G 字段类型识别
│   ├── integer_mutation.py            # 4G INTEGER 变异
│   ├── integer_mutation_5g.py         # 5G INTEGER 变异
│   ├── octet_string_mutation.py       # 4G OCTET STRING 变异
│   ├── octet_string_mutation_5g.py    # 5G OCTET STRING 变异
│   ├── bit_string_mutation.py         # 4G BIT STRING 变异
│   ├── bit_string_mutation_5g.py      # 5G BIT STRING 变异
│   ├── sequence_of_mutation.py        # 4G SEQUENCE OF 变异
│   ├── sequence_of_mutation_5g.py     # 5G SEQUENCE OF 变异
│   ├── example_usage.py               # 使用示例
│   └── README.md                      # 本文档
├── langchain_agent_4g_mutator.py      # 4G 批量变异 + LangChain Agent 入口
├── langchain_agent_5g_mutator.py      # 5G 批量变异 + LangChain Agent 入口
├── mutate_output_4g/                  # 4G 变异结果
├── mutate_output_5g/                  # 5G 变异结果
└── test/
    ├── test_integer_mutate_new.py     # INTEGER 变异测试
    └── test_octet_string_mutate.py    # OCTET STRING 变异测试
```

## 依赖

```bash
conda activate bishe
# 核心依赖：pycrate（ASN.1 解析和 UPER 编解码）
```

## 使用方法

### 批量变异（推荐）

```bash
# 4G 批量变异：读取 generate_new/output_4g → 变异 → 输出到 mutate_output_4g
python -m bishe.mutated.langchain_agent_4g_mutator --batch

# 5G 批量变异：读取 generate_new/output_5g → 变异 → 输出到 mutate_output_5g
python -m bishe.mutated.langchain_agent_5g_mutator --batch

# 可选参数
#   --limit N           每个文件最多处理 N 行
#   --inspect-only      仅识别字段类型，不执行变异
```

### Python API（单条调用）

4G 和 5G 工具接口完全一致，仅函数名加 `_5g` 后缀：

```python
# ---- 4G LTE ----
from bishe.mutated.tools import mutate_integer, mutate_octet_string, mutate_bit_string, mutate_sequence_of
from bishe.mutated.tools import inspect_field_type

# ---- 5G NR ----
from bishe.mutated.tools import mutate_integer_5g, mutate_octet_string_5g, mutate_bit_string_5g, mutate_sequence_of_5g
from bishe.mutated.tools import inspect_field_type_5g

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

# 字段类型识别（批量变异内部自动调用）
info = inspect_field_type(uper_hex="0a501a2ba8a181f05b", target_path=["message", ...])
# 返回: {"field_type": "INTEGER", "tool_name": "integer_mutation", "supported": "true", ...}
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

### UPER 编码基础

理解变异策略前，需要先了解各字段类型在 UPER（Unaligned PER）中的编码方式。

#### INTEGER 的 UPER 编码

有约束 `INTEGER (lb..ub)` 时，编码为 constrained whole number：
- 占用 $lbs = \lceil \log_2(ub - lb + 1) \rceil$ 比特
- 编码值 = `actual_value - lb`（偏移量表示）
- 无长度头，定长编码

#### OCTET STRING 的 UPER 编码

分三种情况：

**1. 固定长度 `SIZE(n)`**
- 无长度头，直接编码 n 个字节的内容（n×8 bit）

**2. 有约束 `SIZE(lb..ub)`**
- `ub < 65536` 时：长度头用 constrained whole number 编码，占 $\lceil \log_2(ub - lb + 1) \rceil$ bit，值为 `actual_len - lb`，后跟内容字节
- `ub ≥ 65536` 时：使用分片编码（fragmentation）
- **不做字节对齐**，长度头紧接前面的比特流

**3. 无约束（无 SIZE 限制）**
- 先对齐到字节边界（padding 到 8 的整数倍）
- 长度头采用通用长度编码（见下方"长度决定子"表格）
- 后跟内容字节
- 长度头和内容都是 **octet-aligned**（按字节对齐）

#### BIT STRING 的 UPER 编码

与 OCTET STRING 类似，区别在于长度头和内容的单位是**比特**而非字节：

**1. 固定长度 `SIZE(n)`**
- 无长度头，直接编码 n 个比特

**2. 有约束 `SIZE(lb..ub)`**
- 长度头 $\lceil \log_2(ub - lb + 1) \rceil$ bit，值为 `actual_bitlen - lb`
- 后跟实际比特内容

**3. 无约束**
- 先对齐到字节边界
- 长度头采用通用长度编码（单位为比特数）
- 后跟比特内容

#### SEQUENCE OF 的 UPER 编码

有约束 `SIZE(lb..ub)` 时：
- 长度头用 constrained whole number 编码，占 $\lceil \log_2(ub - lb + 1) \rceil$ bit，值为 `count - lb`
- 后跟各元素的 UPER 编码（紧接排列）

#### 通用长度决定子（Length Determinant）

无约束类型统一使用的长度编码格式：

| 长度范围 | 编码字节数 | 首位模式 | 编码值范围 |
|---|---|---|---|
| 0 ~ 127 | 1 字节 | `0xxxxxxx` | `0x00` ~ `0x7F` |
| 128 ~ 16383 | 2 字节 | `10xxxxxx xxxxxxxx` | `0x8080` ~ `0xBFFF` |
| ≥ 16384 | 分片 | `11xxxxxx`（表示 n×16384） | `0xC1` ~ `0xC4` |

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

无约束 OCTET STRING 在 UPER 中必须用"长度决定子"告知接收方后面要读多少字节，格式为：

| 长度范围 | 编码字节数 | 首位模式 | 典型编码值 |
|---|---|---|---|
| 0 ~ 127 | 1 字节 | `0xxxxxxx` | `0x00` ~ `0x7F` |
| 128 ~ 16383 | 2 字节 | `10xxxxxx xxxxxxxx` | `0x8080` ~ `0xBFFF` |
| 16384 ~ 32767 | 2 字节分片头 + 递归 | `11000001` (`0xC1`) 表示 1×16384 | `0xC001 …` |
| 32768 ~ 49151 | 2 字节分片头 + 递归 | `11000010` (`0xC2`) 表示 2×16384 | `0xC002 …` |
| 49152 ~ 65535 | 2 字节分片头 + 递归 | `11000011` (`0xC3`) 表示 3×16384 | `0xC003 …` |

选取的 **10 个边界长度值**（专门覆盖上表各编码格式的切换点）：

| # | 长度值 | 选取原因 |
|---|---|---|
| 1 | 0 | 空串最小值 |
| 2 | 127 | 单字节编码最大值（切换点前）|
| 3 | 128 | 双字节编码最小值（切换点后）|
| 4 | 16383 | 双字节编码最大值（切换点前）|
| 5 | 16384 | 分片编码最小值 = 1×16384（切换点后）|
| 6 | 32768 | 2×16384 分片整数边界 |
| 7 | 32769 | 2×16384 分片边界 +1 |
| 8 | 49152 | 3×16384 分片整数边界 |
| 9 | 49153 | 3×16384 分片边界 +1 |
| 10 | 65535 | 协议允许的最大长度值（2^16 - 1）|

每个长度值各生成 **2 条变异**：
- **变异 A**：长度头写 L，但实际内容为空（0 字节）→ 长度声明 > 实际 payload
- **变异 B**：长度头写 L，但内容随机填 `1 ~ L-1` 字节 → 内容截断不足

再加 **2 条非法长度编码变异**（共 22 条）：
- `generate_invalid_length_encoding()` 随机生成 `0xC005 ~ 0xFFFE` 范围的 2 字节，不符合上表任何一种合法 PER 长度格式
- **变异 21**：非法长度头 + 空内容
- **变异 22**：非法长度头 + 少量随机内容

#### BIT STRING — 受约束（4 条）

BIT STRING 的 UPER 编码格式为：`[lbs 位长度头（单位：比特数）][实际比特内容]`  
其中 `lbs = floor(log2(ub - lb)) + 1`，`maxe = 2^lbs - 1`（lbs 位全 1，可能超出 ub）。

> **与 OCTET STRING 受约束的区别**：长度头和内容的单位都是**比特**而不是字节，因此 delta（包长变化量）同样以比特计。

| # | 长度头值（声明的比特数） | 实际填入比特数 | 意图 |
|---|---|---|---|
| 1 | 随机合法值 `r`（0 ~ maxl-1）| 0 比特（空）| 声明比特数 > 实际内容 |
| 2 | 0 | `lb + 100` 比特 | 声明 0 比特但填大量内容 |
| 3 | 随机合法值 | 随机合法值 + lb + 1 比特 | 内容超出声明 |
| 4 | `maxe`（lbs 位全 1，≥ ub）| `maxe + 100` 比特 | 长度超出约束上界且内容溢出 |

#### BIT STRING — 无约束（12 条）

无约束 BIT STRING 的长度编码格式与无约束 OCTET STRING 完全相同（PER 变长长度头），区别在于**长度头描述的是比特数而非字节数**，内容也是逐比特填充。

选取 **3 个边界长度值**（覆盖单字节/双字节切换点，不覆盖分片区间是因为协议中无约束 BIT STRING 实际长度极少超过 128 比特）：

| 长度值（比特数） | PER 编码 | 选取原因 |
|---|---|---|
| 0 | `0x00`（1 字节）| 空串 |
| 127 | `0x7F`（1 字节）| 单字节编码最大值（切换点前）|
| 128 | `0x8080`（2 字节）| 双字节编码最小值（切换点后）|

每个长度值各生成 **3 条变异**（比 OCTET STRING 无约束多一条溢出）：
- **变异 A**：长度头写 L，内容 0 比特（空）
- **变异 B**：长度头写 L，内容随机填 `1 ~ L-1` 比特（不足）
- **变异 C**：长度头写 L，内容填 `L + 100` 比特（溢出，OCTET STRING 无约束没有此条）

再加 **3 条非法长度编码变异**（共 12 条）：
- 用 `generate_invalid_length_encoding()` 生成不符合 PER 规范的 2 字节长度头
- **变异 10**：非法长度头 + 空内容（0 比特）
- **变异 11**：非法长度头 + 不足内容
- **变异 12**：非法长度头 + 溢出内容

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
