"""
RRC Message Database Manager
用于管理RRC消息测试数据库的工具类
"""

import json
import hashlib
import mysql.connector
from mysql.connector import Error
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class RRCDatabaseManager:
    """RRC消息数据库管理器"""
    
    def __init__(self, host='localhost', database='rrc_testing', user='root', password=''):
        """
        初始化数据库连接
        
        Args:
            host: 数据库主机
            database: 数据库名称
            user: 用户名
            password: 密码
        """
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.connection = None
    
    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password
            )
            if self.connection.is_connected():
                print(f"成功连接到MySQL数据库: {self.database}")
                return True
        except Error as e:
            print(f"连接数据库失败: {e}")
            return False
    
    def disconnect(self):
        """关闭数据库连接"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("数据库连接已关闭")
    
    def create_database(self):
        """创建数据库（如果不存在）"""
        try:
            conn = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database} "
                          f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print(f"数据库 {self.database} 已创建或已存在")
            cursor.close()
            conn.close()
        except Error as e:
            print(f"创建数据库失败: {e}")
    
    def execute_sql_file(self, sql_file_path: str):
        """
        执行SQL文件
        
        Args:
            sql_file_path: SQL文件路径
        """
        if not self.connection:
            print("请先连接数据库")
            return
        
        try:
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            # 分割SQL语句（处理存储过程等复杂情况）
            cursor = self.connection.cursor()
            
            # 简单处理：按分号分割，跳过注释
            statements = []
            current_statement = []
            in_delimiter = False
            
            for line in sql_content.split('\n'):
                line = line.strip()
                
                # 跳过注释
                if line.startswith('--') or not line:
                    continue
                
                # 处理DELIMITER
                if line.upper().startswith('DELIMITER'):
                    in_delimiter = not in_delimiter
                    continue
                
                current_statement.append(line)
                
                # 判断语句结束
                if not in_delimiter and line.endswith(';'):
                    statement = ' '.join(current_statement)
                    if statement.strip():
                        statements.append(statement)
                    current_statement = []
                elif in_delimiter and line == '//':
                    statement = ' '.join(current_statement[:-1])  # 移除最后的 //
                    if statement.strip():
                        statements.append(statement)
                    current_statement = []
            
            # 执行所有语句
            for statement in statements:
                try:
                    cursor.execute(statement)
                except Error as e:
                    print(f"执行SQL语句失败: {e}")
                    print(f"语句: {statement[:100]}...")
            
            self.connection.commit()
            print(f"SQL文件执行完成: {sql_file_path}")
            cursor.close()
            
        except Exception as e:
            print(f"执行SQL文件时出错: {e}")
            self.connection.rollback()
    
    def calculate_path_hash(self, rrc_version: str, path: List[str]) -> str:
        """
        计算路径的哈希值
        
        Args:
            rrc_version: RRC版本
            path: 路径列表
        
        Returns:
            SHA256哈希值
        """
        path_str = ','.join(path)
        hash_input = f"{rrc_version}:{path_str}"
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def import_paths_from_json(self, json_file_path: str, rrc_version: str):
        """
        从rrc_paths.json文件导入路径数据
        
        Args:
            json_file_path: JSON文件路径
            rrc_version: RRC版本号（如 '36331-j00'）
        """
        if not self.connection:
            print("请先连接数据库")
            return
        
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                paths_data = json.load(f)
            
            cursor = self.connection.cursor()
            
            insert_count = 0
            update_count = 0
            
            for item in paths_data:
                top_level_message = item.get('top_level_message')
                target_type = item.get('target_type')
                path = item.get('path')
                choices = item.get('choices')
                
                # 计算路径哈希
                path_hash = self.calculate_path_hash(rrc_version, path)
                
                # 转换为逗号分隔的字符串
                path_str = ','.join(path)
                choices_str = ','.join(choices)
                
                # 插入或更新
                sql = """
                    INSERT INTO rrc_path (rrc_version, top_level_message, target_type, path, choices, path_hash)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        top_level_message = VALUES(top_level_message),
                        target_type = VALUES(target_type),
                        choices = VALUES(choices),
                        updated_at = CURRENT_TIMESTAMP
                """
                
                cursor.execute(sql, (rrc_version, top_level_message, target_type, 
                                   path_str, choices_str, path_hash))
                
                if cursor.lastrowid > 0:
                    insert_count += 1
                else:
                    update_count += 1
            
            self.connection.commit()
            print(f"路径导入完成: 新增 {insert_count} 条，更新 {update_count} 条")
            cursor.close()
            
        except Exception as e:
            print(f"导入路径数据失败: {e}")
            self.connection.rollback()
    
    def insert_message(self, path_id: int, message_content: Dict, encode_hex: str) -> Optional[int]:
        """
        插入RRC消息
        
        Args:
            path_id: 路径ID
            message_content: 消息内容（字典格式）
            encode_hex: 编码的十六进制字符串
        
        Returns:
            插入的消息ID，失败返回None
        """
        if not self.connection:
            print("请先连接数据库")
            return None
        
        try:
            cursor = self.connection.cursor()
            
            # 将Python字典转换为字符串存储
            message_str = str(message_content)
            
            sql = """
                INSERT INTO rrc_message 
                (path_id, message_content, encode_hex)
                VALUES (%s, %s, %s)
            """
            
            cursor.execute(sql, (path_id, message_str, encode_hex))
            
            self.connection.commit()
            message_id = cursor.lastrowid
            print(f"消息插入成功，ID: {message_id}")
            cursor.close()
            return message_id
            
        except Exception as e:
            print(f"插入消息失败: {e}")
            self.connection.rollback()
            return None
    
    def insert_mutation(self, message_id: int, mutation_type: str, encode_mutate: str) -> Optional[int]:
        """
        插入变异消息
        
        Args:
            message_id: 原始消息ID
            mutation_type: 变异类型
            encode_mutate: 变异后的编码
        
        Returns:
            插入的变异消息ID，失败返回None
        """
        if not self.connection:
            print("请先连接数据库")
            return None
        
        try:
            cursor = self.connection.cursor()
            
            sql = """
                INSERT INTO rrc_mutated_message 
                (message_id, mutation_type, encode_mutate)
                VALUES (%s, %s, %s)
            """
            
            cursor.execute(sql, (message_id, mutation_type, encode_mutate))
            
            self.connection.commit()
            mutation_id = cursor.lastrowid
            print(f"变异消息插入成功，ID: {mutation_id}")
            cursor.close()
            return mutation_id
            
        except Exception as e:
            print(f"插入变异消息失败: {e}")
            self.connection.rollback()
            return None
    
    def get_path_id_by_hash(self, rrc_version: str, path: List[str]) -> Optional[int]:
        """
        根据版本和路径获取path_id
        
        Args:
            rrc_version: RRC版本
            path: 路径列表
        
        Returns:
            path_id或None
        """
        if not self.connection:
            return None
        
        try:
            path_hash = self.calculate_path_hash(rrc_version, path)
            cursor = self.connection.cursor()
            cursor.execute("SELECT id FROM rrc_path WHERE rrc_version = %s AND path_hash = %s",
                         (rrc_version, path_hash))
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else None
        except Exception as e:
            print(f"查询path_id失败: {e}")
            return None
    
    def get_path_by_id(self, path_id: int) -> Optional[Dict[str, Any]]:
        """
        根据path_id获取路径信息
        
        Args:
            path_id: 路径ID
        
        Returns:
            包含路径信息的字典，包括path和choices的列表格式
        """
        if not self.connection:
            return None
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM rrc_path WHERE id = %s", (path_id,))
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                # 将逗号分隔的字符串转换回列表
                result['path'] = result['path'].split(',') if result['path'] else []
                result['choices'] = result['choices'].split(',') if result['choices'] else []
            
            return result
        except Exception as e:
            print(f"查询路径信息失败: {e}")
            return None


def main():
    """示例用法"""
    # 初始化数据库管理器
    db = RRCDatabaseManager(
        host='localhost',
        database='rrc_testing',
        user='root',
        password='your_password'  # 请修改为实际密码
    )
    
    # 创建数据库
    db.create_database()
    
    # 连接数据库
    if db.connect():
        # 执行SQL建表脚本
        sql_file = Path(__file__).parent / 'database_schema.sql'
        db.execute_sql_file(str(sql_file))
        
        # 导入rrc_paths.json数据
        json_file = Path(__file__).parent / 'doc_version_control/rrc_paths/36331-j00/rrc_paths.json'
        if json_file.exists():
            db.import_paths_from_json(str(json_file), '36331-j00')
        
        # 断开连接
        db.disconnect()


if __name__ == '__main__':
    main()
