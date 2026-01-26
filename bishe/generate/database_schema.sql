-- ============================================
-- RRC Message Testing Database Schema
-- Simplified Version
-- ============================================

-- 1. RRC Path 表：存储 rrc_paths.json 的路径信息
-- ============================================
CREATE TABLE IF NOT EXISTS rrc_path (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    
    -- 基本信息
    rrc_version VARCHAR(50) NOT NULL COMMENT 'RRC版本号，如36331-j00',
    top_level_message VARCHAR(100) NOT NULL COMMENT '顶层消息类型，如DL_DCCH_Message',
    target_type VARCHAR(50) NOT NULL COMMENT '目标类型，如INTEGER, BIT_STRING, OCTET_STRING, SEQOF等',
    
    -- 路径信息（逗号分隔的字符串）
    path VARCHAR(500) NOT NULL COMMENT '完整路径，逗号分隔，如"message,c1,rrcConnectionReconfiguration"',
    choices VARCHAR(500) NOT NULL COMMENT '选择路径，逗号分隔，包含路径中的choice选择',
    
    -- 路径哈希（用于快速查找和去重）
    path_hash VARCHAR(64) NOT NULL COMMENT '路径的MD5/SHA256哈希值，用于快速匹配',
    
    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 索引
    INDEX idx_rrc_version (rrc_version),
    INDEX idx_top_level_message (top_level_message),
    INDEX idx_target_type (target_type),
    INDEX idx_path_hash (path_hash),
    UNIQUE KEY uk_version_path_hash (rrc_version, path_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RRC路径表';


-- 2. Message 表：存储生成的RRC消息
-- ============================================
CREATE TABLE IF NOT EXISTS rrc_message (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    
    -- 关联信息
    path_id BIGINT NOT NULL COMMENT '关联的路径ID',
    
    -- 消息内容
    message_content TEXT NOT NULL COMMENT 'RRC消息内容（Python字典的字符串表示）',
    encode_hex TEXT NOT NULL COMMENT 'UPER编码后的十六进制字符串',
    
    -- 验证信息
    is_valid BOOLEAN DEFAULT NULL COMMENT '是否通过验证（NULL=未验证，TRUE=通过，FALSE=失败）',
    validation_time TIMESTAMP NULL COMMENT '验证时间',
    
    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 外键约束
    FOREIGN KEY (path_id) REFERENCES rrc_path(id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    -- 索引
    INDEX idx_path_id (path_id),
    INDEX idx_is_valid (is_valid),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RRC消息表';


-- 3. Mutated Message 表：存储变异后的消息
-- ============================================
CREATE TABLE IF NOT EXISTS rrc_mutated_message (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    
    -- 关联信息
    message_id BIGINT NOT NULL COMMENT '原始消息ID',
    
    -- 变异信息
    mutation_type VARCHAR(50) NOT NULL COMMENT '变异类型：bit_flip, byte_insert, byte_delete, byte_replace, field_fuzz等',
    
    -- 变异结果
    encode_mutate TEXT NOT NULL COMMENT '变异后的十六进制编码',
    
    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 外键约束
    FOREIGN KEY (message_id) REFERENCES rrc_message(id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    -- 索引
    INDEX idx_message_id (message_id),
    INDEX idx_mutation_type (mutation_type),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='变异消息表';



-- ============================================
-- 初始化脚本完成
-- ============================================
