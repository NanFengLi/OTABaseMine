# RRC消息变异工具

基于 OTABase 项目的 BASE 变异策略实现的 RRC 消息字段变异工具集。

## 项目背景

本项目复现了 [OTABase](https://github.com/OTABase/OTABase) 项目中的 RRC 消息变异策略，用于生成针对不同字段类型的变异测试用例。所有变异工具都实现为独立的函数，可以作为 Agent 的 tools 使用。

## 功能特性

实现了 BASE 策略的四种字段类型变异：

1. **INTEGER 字段变异** - 利用位表示范围和规范约束之间的差异
2. **OCTET_STRING 字段变异** - 针对有约束和无约束两种情况的长度/内容不匹配
3. **BIT_STRING 字段变异** - 类似 OCTET_STRING，但操作位级别
4. **SEQUENCE OF 字段变异** - 长度声明与实际元素数量的不匹配

## 目录结构
## 目录结构

```
bishe/mutated/
├── __init__.py                    # 包导出
├── mutation_utils.py              # 通用工具函数
├── integer_mutation.py            # INTEGER 字段变异
├── octet_string_mutation.py       # OCTET_STRING 字段变异
├── bit_string_mutation.py         # BIT_STRING 字段变异
├── sequence_of_mutation.py        # SEQUENCE OF 字段变异
├── example_usage.py               # 使用示例
└── README.md                      # 本文档
```

## 安装依赖

```bash
# 无额外依赖，仅使用 Python 标准库
```

## 使用方法

### 基本用法

```python
from bishe.mutated import integer_mutation_tool

# 准备 RRC 消息
dl_dcch_message = {
    'message': ('c1', ('csfbParametersResponseCDMA2000', {
        'rrc-TransactionIdentifier': 0,
        'criticalExtensions': ...
    }))
}

# 调用变异工具
result = integer_mutation_tool(
    message=dl_dcch_message,
    target_path=['message', 'c1', 'csfbParametersResponseCDMA2000', 
                 'rrc-TransactionIdentifier'],
    lower_bound=0,
    upper_bound=3,
    message_type='csfbParametersResponseCDMA2000'
)

# 获取变异结果
print(f"生成了 {result['count']} 个变异")
for mutation in result['mutations']:
    print(mutation['mutation_description'])
```

### 运行示例

```bash
cd /home/lab221/Projects/OTABase
python -m bishe.mutated.example_usage
```

## API 文档

### 1. INTEGER 字段变异

```python
integer_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    lower_bound: int,
    upper_bound: int,
    message_type: str,
    seed: int = None
) -> Dict[str, Any]
```

**参数：**
- `message`: 完整的 RRC 消息字典
- `target_path`: 目标 INTEGER 字段的路径
- `lower_bound`: INTEGER 约束的下界
- `upper_bound`: INTEGER 约束的上界
- `message_type`: RRC 消息类型
- `seed`: 随机种子（可选）

**变异策略：**
1. 随机有效值
2. 最大可表示值（利用位溢出）
3. 范围溢出（upper_bound + 1）

### 2. OCTET_STRING 字段变异

```python
octet_string_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    constrained: bool = True,
    lower_bound: Optional[int] = None,
    upper_bound: Optional[int] = None,
    current_value: Optional[bytes] = None,
    seed: int = None
) -> Dict[str, Any]
```

**参数：**
- `constrained`: 是否有长度约束
- `lower_bound`: 长度约束下界（constrained 时需要）
- `upper_bound`: 长度约束上界（constrained 时需要）
- `current_value`: 当前字段值（bytes）

**变异策略（有约束）：**
1. 有效长度，空内容
2. 长度=0，溢出内容
3. 长度下溢（content_length - 1）
4. 最大编码长度，最大内容

**变异策略（无约束）：**
1. 各种 PER 编码边界值
2. 无效长度编码
3. 长度/内容不匹配

### 3. BIT_STRING 字段变异

```python
bit_string_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    constrained: bool = True,
    lower_bound: Optional[int] = None,
    upper_bound: Optional[int] = None,
    current_value: Optional[Tuple[int, int]] = None,
    seed: int = None
) -> Dict[str, Any]
```

**参数：**
- `current_value`: 当前值 (bit_value, bit_length) 元组

**变异策略：** 类似 OCTET_STRING，但操作位而非字节

### 4. SEQUENCE OF 字段变异

```python
sequence_of_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    message_type: str,
    lower_bound: int,
    upper_bound: int,
    current_value: Optional[List] = None,
    seed: int = None
) -> Dict[str, Any]
```

**参数：**
- `current_value`: 当前元素列表

**变异策略：**
1. 长度=0，非空内容
2. 随机长度，原始内容
3. 长度/元素数量不匹配
4. 最大编码长度
5. 空列表
6. 超出上界

## 用户输入要求分析

根据对 OTABase 的分析，你当前的输入：

### ✅ 已有的输入
1. 变异的消息类型 (message_type)
2. 变异的字段类型 (field_type)
3. 到达目标字段的路径 (path)
4. CHOICE 字段路径 (choices)
5. 完整的 RRC 消息字典（大模型生成）

### ⚠️ **缺少的关键输入**

**字段约束信息 (Field Constraints)** - 这是最重要的缺失！

具体需要：

1. **INTEGER 字段**：
   - `lower_bound`: 取值下界
   - `upper_bound`: 取值上界

2. **OCTET_STRING / BIT_STRING**：
   - `constrained`: 是否有长度约束 (bool)
   - `lower_bound`: 长度下界（如果 constrained=True）
   - `upper_bound`: 长度上界（如果 constrained=True）

3. **SEQUENCE OF**：
   - `lower_bound`: 最小元素数
   - `upper_bound`: 最大元素数

### 建议获取方式

你可以从 `rrc_paths.json` 文件中提取这些约束信息，该文件应该包含每个字段的约束定义。例如：

```json
{
  "path": ["DL-DCCH-Message", "message", "c1", 
           "csfbParametersResponseCDMA2000", "rrc-TransactionIdentifier"],
  "field_type": "INTEGER",
  "constraints": {
    "lower_bound": 0,
    "upper_bound": 3
  }
}
```

## 与 OTABase 的对比

### 已实现的特性
✅ BASE 策略的所有字段类型变异  
✅ Constrained 和 Unconstrained 变异  
✅ PER 编码边界测试  
✅ 长度/内容不匹配测试  
✅ 溢出和下溢测试  

### 未实现的特性（按需求）
❌ TRUNCATE 策略（截断数据包）  
❌ ADD 策略（添加可选字段）  
❌ 祖先字段长度调整（适配变异后的字段）  
❌ 嵌入字段处理（OCTET_STRING 中的嵌入 ASN.1）

## 输出格式

所有变异工具返回统一格式：

```python
{
    'mutations': [
        {
            'message': {...},                    # 变异后的消息
            'mutation_type': 'random_valid',     # 变异类型
            'mutation_description': '...',       # 描述
            'target_field_path': [...],          # 目标路径
            'message_type': '...',               # 消息类型
            # 其他元数据...
        },
        ...
    ],
    'count': 3,                                  # 变异数量
    'strategy': 'BASE',                          # 策略名称
    'field_type': 'INTEGER',                     # 字段类型
    'target_path': [...],                        # 目标路径
    'message_type': '...'                        # 消息类型
}
```

## Agent 集成

这些工具设计为可直接用作 Agent 的 tools：

```python
# 在 Agent 中注册工具
tools = [
    {
        'name': 'mutate_integer',
        'description': 'Mutate INTEGER field in RRC message',
        'function': integer_mutation_tool
    },
    {
        'name': 'mutate_octet_string',
        'description': 'Mutate OCTET_STRING field in RRC message',
        'function': octet_string_mutation_tool
    },
    # ... 其他工具
]
```

## 参考资料

- OTABase GitHub: https://github.com/OTABase/OTABase
- OTABase 论文: 参见项目 README
- 3GPP TS 36.331: RRC Protocol Specification

## 许可证

本项目基于 OTABase 的开源实现，遵循相同的许可证。
