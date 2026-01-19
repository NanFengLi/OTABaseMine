# RRC消息变异工具 - 实现总结

## 📋 项目概述

本项目成功复现了 [OTABase](https://github.com/OTABase/OTABase) 的 BASE 变异策略，实现了针对 RRC 消息不同字段类型的变异工具。所有工具都设计为可作为 React 模式 Agent 的 tools 使用。

## ✅ 已完成的工作

### 1. 核心变异工具（BASE 策略）

| 字段类型 | 文件 | 状态 | 变异数量 |
|---------|------|------|---------|
| **INTEGER** | `integer_mutation.py` | ✅ 完成 | 3种变异 |
| **OCTET_STRING** | `octet_string_mutation.py` | ✅ 完成 | 4-13种变异 |
| **BIT_STRING** | `bit_string_mutation.py` | ✅ 完成 | 3-10种变异 |
| **SEQUENCE_OF** | `sequence_of_mutation.py` | ✅ 完成 | 4-6种变异 |

### 2. 辅助工具模块

**文件：** `mutation_utils.py`

包含所有变异策略需要的通用函数：
- 位/字节转换函数
- PER 编码/解码函数
- 随机数据生成
- 路径导航工具

### 3. 文档和示例

- ✅ `README.md` - 完整的 API 文档和使用说明
- ✅ `example_usage.py` - 可运行的示例代码
- ✅ `SUMMARY.md` - 本总结文档

## 📊 变异策略详解

### INTEGER 字段变异

**核心思想：** 利用位表示范围与规范约束的差异

```
如果字段约束为 0-9，但使用 4 位编码：
- 规范范围: 0-9
- 实际可表示: 0-15
- 变异策略: 测试 10-15 的值
```

**3种变异：**
1. 随机有效值（范围内）
2. 最大可表示值（位溢出）
3. 范围溢出（upper_bound + 1）

### OCTET_STRING 字段变异

**核心思想：** 长度字段与内容不匹配

**有约束（Constrained）- 4种变异：**
1. 有效长度，空内容
2. 长度=0，溢出内容（100字节）
3. 长度 = 内容长度 - 1（下溢）
4. 最大编码长度，最大内容

**无约束（Unconstrained）- 13种变异：**
- 针对 PER 编码边界：0, 127, 128, 2^14-1, 2^14, ...
- 每个长度值测试：空内容、长度不匹配
- 无效长度编码测试

### BIT_STRING 字段变异

**核心思想：** 与 OCTET_STRING 类似，但操作位

**有约束 - 3种变异：**
1. 有效长度，空内容
2. 长度=0，溢出内容
3. 最大编码长度，溢出内容

**无约束 - 10种变异：**
- 类似 OCTET_STRING，针对位级别操作

### SEQUENCE_OF 字段变异

**核心思想：** 声明的元素数量与实际列表长度不匹配

**4-6种变异：**
1. 长度=0，非空内容
2. 随机长度，原始内容
3. 长度/元素数量不匹配
4. 最大编码长度
5. 空列表
6. 超出上界

## 🔍 输入需求分析

### 用户当前的输入

```python
{
    "message_type": "csfbParametersResponseCDMA2000",
    "field_type": "INTEGER",
    "path": ["DL-DCCH-Message", "message", "c1", 
             "csfbParametersResponseCDMA2000", "rrc-TransactionIdentifier"],
    "choices": ["c1", "csfbParametersResponseCDMA2000", ...],
    "message": {完整的RRC消息字典}
}
```

### ⚠️ 缺少的关键输入

**字段约束信息（Field Constraints）** - 这是最重要的缺失！

#### 需要补充的信息：

1. **INTEGER 字段：**
   ```python
   {
       "lower_bound": 0,
       "upper_bound": 3
   }
   ```

2. **OCTET_STRING / BIT_STRING：**
   ```python
   {
       "constrained": True,  # 或 False
       "lower_bound": 0,     # 如果 constrained=True
       "upper_bound": 255    # 如果 constrained=True
   }
   ```

3. **SEQUENCE_OF：**
   ```python
   {
       "lower_bound": 1,  # 最小元素数
       "upper_bound": 8   # 最大元素数
   }
   ```

### 📝 建议的完整输入格式

```python
mutation_input = {
    # 现有输入
    "message_type": "csfbParametersResponseCDMA2000",
    "field_type": "INTEGER",
    "path": ["DL-DCCH-Message", "message", "c1", 
             "csfbParametersResponseCDMA2000", "rrc-TransactionIdentifier"],
    "choices": ["c1", "csfbParametersResponseCDMA2000", "rrc-TransactionIdentifier"],
    "message": {完整的RRC消息字典},
    
    # 需要补充的约束信息
    "constraints": {
        "lower_bound": 0,
        "upper_bound": 3
    }
}
```

## 🛠️ Agent 工具使用方法

### 1. 注册工具

```python
tools = [
    {
        "name": "mutate_integer_field",
        "description": "Mutate INTEGER field in RRC message using BASE strategy",
        "function": integer_mutation_tool,
        "parameters": {
            "message": "Complete RRC message dict",
            "target_path": "List of keys to target field",
            "lower_bound": "Integer constraint lower bound",
            "upper_bound": "Integer constraint upper bound",
            "message_type": "RRC message type"
        }
    },
    # ... 其他工具
]
```

### 2. Agent 调用示例

```python
# Agent 接收用户输入
user_input = {
    "message_type": "csfbParametersResponseCDMA2000",
    "field_type": "INTEGER",
    "path": [...],
    "constraints": {"lower_bound": 0, "upper_bound": 3},
    "message": {...}
}

# Agent 根据 field_type 选择对应的工具
if user_input["field_type"] == "INTEGER":
    result = integer_mutation_tool(
        message=user_input["message"],
        target_path=user_input["path"],
        lower_bound=user_input["constraints"]["lower_bound"],
        upper_bound=user_input["constraints"]["upper_bound"],
        message_type=user_input["message_type"]
    )
    
    # 返回变异结果
    return {
        "mutations": result["mutations"],
        "count": result["count"],
        "strategy": result["strategy"]
    }
```

## 📂 文件结构

```
bishe/mutated/
├── __init__.py                    # 包导出
├── mutation_utils.py              # 通用工具（219行）
├── integer_mutation.py            # INTEGER变异（203行）
├── octet_string_mutation.py       # OCTET_STRING变异（393行）
├── bit_string_mutation.py         # BIT_STRING变异（421行）
├── sequence_of_mutation.py        # SEQUENCE_OF变异（212行）
├── example_usage.py               # 示例代码（165行）
├── README.md                      # 完整文档
└── SUMMARY.md                     # 本文档
```

**总代码行数：** ~1600+ 行（含注释和文档）

## ✨ 与 OTABase 的对比

### 已实现 ✅

- [x] BASE 策略所有字段类型
- [x] Constrained 和 Unconstrained 处理
- [x] PER 编码边界测试
- [x] 长度/内容不匹配
- [x] 溢出和下溢测试
- [x] 完整的工具接口

### 未实现（可选）❌

OTABase 还包含以下高级特性，这些不是 BASE 策略的核心部分：

- [ ] **TRUNCATE 策略** - 截断数据包
- [ ] **ADD 策略** - 添加可选字段
- [ ] **祖先字段长度调整** - 自动调整包含字段的长度
- [ ] **嵌入字段处理** - OCTET_STRING 中的嵌入 ASN.1
- [ ] **位级操作** - 实际的位编码和解码

**注意：** 这些特性在 OTABase 中用于生成实际可发送的二进制数据包。你的用例是生成 Python 字典形式的变异消息，然后交给大模型或其他工具处理，因此不需要这些底层的二进制操作。

## 🎯 使用场景

### 场景1：单字段变异

```python
# 用户提供完整的 RRC 消息和目标字段信息
result = integer_mutation_tool(
    message=rrc_message,
    target_path=["message", "c1", "...", "rrc-TransactionIdentifier"],
    lower_bound=0,
    upper_bound=3,
    message_type="csfbParametersResponseCDMA2000"
)

# 获得 3 个变异后的消息
for mut in result["mutations"]:
    print(mut["mutation_description"])
    # 使用 mut["message"] 进行后续处理
```

### 场景2：批量变异

```python
# 从 rrc_paths.json 读取所有字段
with open("rrc_paths.json") as f:
    paths = json.load(f)

all_mutations = []
for field_info in paths:
    if field_info["field_type"] == "INTEGER":
        result = integer_mutation_tool(
            message=base_message,
            target_path=field_info["path"],
            lower_bound=field_info["constraints"]["lower_bound"],
            upper_bound=field_info["constraints"]["upper_bound"],
            message_type=field_info["message_type"]
        )
        all_mutations.extend(result["mutations"])
```

## 🔧 测试验证

运行示例代码验证：

```bash
cd /home/lab221/Projects/OTABase
conda activate bishe
python -m bishe.mutated.example_usage
```

**测试结果：** ✅ 所有变异工具正常工作

## 📖 下一步建议

1. **提取约束信息：** 从 `rrc_paths.json` 或 ASN.1 定义中提取字段约束
2. **集成到 Agent：** 将这些工具注册为 Agent 的可用工具
3. **批处理脚本：** 创建批量处理多个字段的脚本
4. **结果验证：** 使用 pycrate 验证变异后的消息是否有效

## 📚 参考资料

- **OTABase GitHub:** https://github.com/OTABase/OTABase
- **OTABase README:** 详细的变异策略说明
- **本项目文档:** [bishe/mutated/README.md](README.md)

## 🏆 总结

✅ **完成度：** 100%（BASE 策略核心功能）  
✅ **代码质量：** 完整注释、类型提示、错误处理  
✅ **文档完整性：** API文档、使用示例、总结文档  
✅ **可用性：** 可直接作为 Agent 工具使用  

**最重要的发现：** 你还需要为每个字段提供**约束信息（constraints）**，这是 OTABase 变异策略的核心输入之一！
