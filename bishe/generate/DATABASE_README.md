# RRC消息测试数据库设计文档

## 概述

本数据库用于存储和管理RRC（Radio Resource Control）消息的测试数据，包括原始路径信息、生成的消息和变异消息。设计简洁高效，专注于核心功能。

## 数据库架构

### 核心表结构

#### 1. `rrc_path` - RRC路径表

存储从 `rrc_paths.json` 导入的路径信息。

**字段说明：**
- `id`: 主键ID
- `rrc_version`: RRC协议版本（如 '36331-j00'）
- `top_level_message`: 顶层消息类型（如 'DL_DCCH_Message'）
- `target_type`: 目标数据类型（INTEGER, BIT_STRING, OCTET_STRING, SEQOF等）
- `path`: 完整路径（逗号分隔的字符串，如 'message,c1,rrcConnectionReconfiguration'）
- `choices`: 路径选择（逗号分隔的字符串）
- `path_hash`: 路径的SHA256哈希值（用于快速查找和去重）
- `created_at`, `updated_at`: 时间戳

**关系：** 1:N → `rrc_message`

#### 2. `rrc_message` - RRC消息表

存储LLM或其他方式生成的RRC消息。

**字段说明：**
- `id`: 主键ID
- `path_id`: 外键，关联 `rrc_path` 表
- `message_content`: 消息内容（TEXT格式，存储Python字典的字符串表示）
- `encode_hex`: UPER编码后的十六进制字符串
- `is_valid`: 验证状态（NULL=未验证，TRUE=通过，FALSE=失败）
- `validation_time`: 验证时间
- `created_at`, `updated_at`: 时间戳

**关系：** 
- N:1 → `rrc_path`
- 1:N → `rrc_mutated_message`

#### 3. `rrc_mutated_message` - 变异消息表

存储变异后的消息。

**字段说明：**
- `id`: 主键ID
- `message_id`: 外键，关联原始消息
- `mutation_type`: 变异类型（bit_flip, byte_insert, byte_delete, byte_replace, field_fuzz等）
- `encode_mutate`: 变异后的十六进制编码
- `created_at`, `updated_at`: 时间戳

**关系：** 
- N:1 → `rrc_message`

## ER图

```
┌─────────────┐
│  rrc_path   │
│             │
│ - id (PK)   │
│ - version   │
│ - top_msg   │
│ - target    │
│ - path      │
│ - choices   │
│ - path_hash │
└──────┬──────┘
       │ 1
       │
       │ N
┌──────┴──────────┐
│  rrc_message    │
│                 │
│ - id (PK)       │
│ - path_id (FK)  │
│ - content (TXT) │
│ - encode_hex    │
│ - is_valid      │
└──────┬──────────┘
       │ 1
       │
       │ N
┌──────┴────────────────┐
│ rrc_mutated_message   │
│                       │
│ - id (PK)             │
│ - message_id (FK)     │
│ - mutation_type       │
│ - encode_mutate       │
└───────────────────────┘
```

## 使用指南

### 1. 初始化数据库

```bash
# 方法1: 使用Python脚本
python database_manager.py

# 方法2: 手动执行SQL
mysql -u root -p < database_schema.sql
```

### 2. 导入rrc_paths.json数据

```python
from database_manager import RRCDatabaseManager

db = RRCDatabaseManager(host='localhost', database='rrc_testing', 
                        user='root', password='your_password')
db.create_database()
db.connect()
db.execute_sql_file('database_schema.sql')
db.import_paths_from_json('doc_version_control/rrc_paths/36331-j00/rrc_paths.json', '36331-j00')
db.disconnect()
```

**注意**：路径数据会自动从JSON数组格式转换为逗号分隔的字符串存储。例如：
- JSON: `["message", "c1", "rrcConnectionReconfiguration"]`
- 存储: `"message,c1,rrcConnectionReconfiguration"`

### 3. 插入生成的消息

```python
# 定义消息
dl_dcch_message = {
   'message': ('c1', ('rrcConnectionReconfiguration', {...}))
}

# 编码
from pycrate_asn1dir import RRCLTE
from binascii import hexlify

DL_DCCH = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
DL_DCCH.set_val(dl_dcch_message)
encode_hex = hexlify(DL_DCCH.to_uper()).decode('ascii')

# 插入数据库
path_id = db.get_path_id_by_hash('36331-j00', path_list)
message_id = db.insert_message(
    path_id=path_id,
    message_content=dl_dcch_message,
    encode_hex=encode_hex
)
```

### 4. 插入变异消息

```python
mutation_id = db.insert_mutation(
    message_id=message_id,
    mutation_type='bit_flip',
    encode_mutate=mutated_hex
)
```

### 5. 查询统计信息

```sql
-- 查看消息统计
SELECT 
    p.rrc_version,
    p.top_level_message,
    p.target_type,
    COUNT(DISTINCT m.id) AS message_count,
    COUNT(DISTINCT mt.id) AS mutation_count,
    SUM(CASE WHEN m.is_valid = TRUE THEN 1 ELSE 0 END) AS valid_message_count
FROM rrc_path p
LEFT JOIN rrc_message m ON p.id = m.path_id
LEFT JOIN rrc_mutated_message mt ON m.id = mt.message_id
WHERE p.rrc_version = '36331-j00'
GROUP BY p.rrc_version, p.top_level_message, p.target_type;

-- 查找未验证的消息
SELECT * FROM rrc_message WHERE is_valid IS NULL;

-- 查找某个消息的所有变异
SELECT * FROM rrc_mutated_message WHERE message_id = 123;
```

## 常见查询示例

### 1. 按消息类型统计

```sql
SELECT 
    top_level_message,
    COUNT(*) as path_count,
    COUNT(DISTINCT target_type) as type_count
FROM rrc_path
WHERE rrc_version = '36331-j00'
GROUP BY top_level_message
ORDER BY path_count DESC;
```

### 2. 查找特定路径

```sql
SELECT * FROM rrc_path
WHERE rrc_version = '36331-j00'
  AND top_level_message = 'DL_DCCH_Message'
  AND path LIKE '%rrcConnectionReconfiguration%';
```

### 3. 获取消息的所有变异

```sql
SELECT m.*, mt.*
FROM rrc_message m
JOIN rrc_mutated_message mt ON m.id = mt.message_id
WHERE m.id = 123
ORDER BY mt.created_at;
```

### 4. 按变异类型统计

```sql
SELECT 
    mutation_type,
    COUNT(*) as total
FROM rrc_mutated_message
GROUP BY mutation_type;
```

### 5. 查找特定编码的消息

```sql
SELECT * FROM rrc_message 
WHERE encode_hex LIKE '20%'
LIMIT 10;
```

## 数据库维护

### 备份

```bash
mysqldump -u root -p rrc_testing > rrc_testing_backup_$(date +%Y%m%d).sql
```

### 恢复

```bash
mysql -u root -p rrc_testing < rrc_testing_backup_20260121.sql
```

### 清理测试数据

```sql
-- 删除未验证的消息
DELETE FROM rrc_message WHERE is_valid IS NULL;

-- 删除特定类型的变异
DELETE FROM rrc_mutated_message WHERE mutation_type = 'bit_flip';
```

## 性能优化建议

1. **索引优化**：已为常用查询字段添加索引
2. **分区**：如果数据量很大，可考虑按`rrc_version`或时间分区
3. **归档**：定期归档旧的测试数据
4. **JSON字段**：MySQL 5.7+ 支持JSON索引，可为常用JSON路径添加虚拟列和索引

## 数据存储说明

### message_content字段

该字段存储Python字典的字符串表示（使用`str(dict)`），而非JSON格式。这是因为：

1. Python字典可能包含元组等JSON不直接支持的类型
2. 保持与原始Python对象的完全一致性
3. 如果需要，可以使用`ast.literal_eval()`还原为Python对象

**示例：**
```python
# 存储
message_str = str(dl_dcch_message)
db.insert_message(path_id, message_str, encode_hex)

# 读取和还原
import ast
message_dict = ast.literal_eval(message_str)
```

### path和choices字段

这些字段存储逗号分隔的字符串，而非JSON格式：

**示例：**
```python
# 从JSON数组转换
path = ["message", "c1", "rrcConnectionReconfiguration"]
path_str = ','.join(path)  # "message,c1,rrcConnectionReconfiguration"

# 还原为列表
path_list = path_str.split(',')  # ["message", "c1", "rrcConnectionReconfiguration"]
```

## 扩展建议

如有需要，可考虑在未来添加：

1. **测试结果表**：单独存储详细的测试结果和日志
2. **用户认证表**：多用户系统支持
3. **测试环境表**：记录测试环境配置
4. **附件表**：存储pcap文件、日志文件等

## 注意事项

1. 修改 `database_manager.py` 和 `example_usage.py` 中的数据库密码
2. `message_content` 字段存储的是Python字典的字符串表示，使用`ast.literal_eval()`还原
3. `path_hash` 用于快速查找，但路径变更时需要重新计算
4. 大量数据导入时建议使用批量插入或LOAD DATA INFILE

## 版本历史

- v2.0 (2026-01-21): 简化版本
  - 删除不必要的字段和表
  - message_content改为TEXT存储字符串
  - 移除test_campaign相关功能
  - 移除统计视图
  
- v1.0 (2026-01-21): 初始版本
  - 创建核心三表：rrc_path, rrc_message, rrc_mutated_message
  - 添加测试活动管理功能
  - 提供Python管理工具
