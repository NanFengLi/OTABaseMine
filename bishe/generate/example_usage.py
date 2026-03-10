"""
使用示例：如何使用RRC消息数据库
"""

from database_manager import RRCDatabaseManager
from binascii import hexlify
from bishe.pycrate_asn1obj.eutran_4g import RRCLTE


def example_insert_message():
    """示例：插入一个生成的消息到数据库"""
    
    # 连接数据库
    db = RRCDatabaseManager(
        host='localhost',
        database='rrc_testing',
        user='root',
        password='your_password'
    )
    
    if not db.connect():
        return
    
    # 定义消息内容（与你的is_message_correct.py中的格式一致）
    dl_dcch_message = {
       'message': ('c1',
       ('rrcConnectionReconfiguration',
       {
         'rrc-TransactionIdentifier': 0,
         'criticalExtensions': ('c1',
         ('rrcConnectionReconfiguration-r8',
         {
           'nonCriticalExtension': {
             'nonCriticalExtension': {
               'nonCriticalExtension': {
                 'nonCriticalExtension': {
                   'nonCriticalExtension': {
                     'nonCriticalExtension': {
                       'nonCriticalExtension': {
                         'nonCriticalExtension': {
                           'nonCriticalExtension': {
                             'nonCriticalExtension': {
                               'sl-SSB-PriorityEUTRA-r16': 1 
                            } 
                          } 
                        } 
                      } 
                    } 
                  } 
                } 
              } 
            } 
          } 
        })) 
      })) 
    }
    
    # 使用pycrate编码
    DL_DCCH = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    DL_DCCH.set_val(dl_dcch_message)
    encode_hex = hexlify(DL_DCCH.to_uper()).decode('ascii')
    
    print(f"编码结果: {encode_hex}")
    
    # 获取对应的path_id
    # 这里需要根据实际的path来查询，示例使用一个简化的path
    path = ['message', 'c1', 'rrcConnectionReconfiguration', 'criticalExtensions', 
            'c1', 'rrcConnectionReconfiguration-r8', 'nonCriticalExtension',
            'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension',
            'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension',
            'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension',
            'sl-SSB-PriorityEUTRA-r16']
    
    path_id = db.get_path_id_by_hash('36331-j00', path)
    
    if path_id is None:
        print("未找到对应的路径，可能需要先导入rrc_paths.json")
        db.disconnect()
        return
    
    # 插入消息
    message_id = db.insert_message(
        path_id=path_id,
        message_content=dl_dcch_message,
        encode_hex=encode_hex
    )
    
    if message_id:
        print(f"消息已插入，ID: {message_id}")
        
        # 创建一个变异版本
        # 这里演示一个简单的bit flip变异
        mutated_hex = bit_flip_mutation(encode_hex, position=0)
        
        mutation_id = db.insert_mutation(
            message_id=message_id,
            mutation_type='bit_flip',
            encode_mutate=mutated_hex
        )
        
        if mutation_id:
            print(f"变异消息已插入，ID: {mutation_id}")
    
    db.disconnect()


def bit_flip_mutation(hex_string: str, position: int) -> str:
    """
    简单的bit flip变异
    
    Args:
        hex_string: 十六进制字符串
        position: 要翻转的bit位置
    
    Returns:
        变异后的十六进制字符串
    """
    # 转换为字节
    data = bytes.fromhex(hex_string)
    data_list = list(data)
    
    # 计算字节和bit位置
    byte_pos = position // 8
    bit_pos = position % 8
    
    if byte_pos < len(data_list):
        # 翻转bit
        data_list[byte_pos] ^= (1 << (7 - bit_pos))
    
    # 转回十六进制
    return bytes(data_list).hex()


def example_query_statistics():
    """示例：查询统计信息"""
    
    db = RRCDatabaseManager(
        host='localhost',
        database='rrc_testing',
        user='root',
        password='your_password'
    )
    
    if not db.connect():
        return
    
    cursor = db.connection.cursor(dictionary=True)
    
    # 查询每种消息类型的统计
    sql = """
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
        GROUP BY p.rrc_version, p.top_level_message, p.target_type
        ORDER BY message_count DESC
    """
    
    cursor.execute(sql)
    results = cursor.fetchall()
    
    print("\n=== 消息统计 ===")
    for row in results:
        print(f"消息类型: {row['top_level_message']}")
        print(f"  目标类型: {row['target_type']}")
        print(f"  消息数量: {row['message_count']}")
        print(f"  变异数量: {row['mutation_count']}")
        print(f"  有效消息: {row['valid_message_count']}")
        print()
    
    cursor.close()
    db.disconnect()


def example_batch_import_messages():
    """示例：批量导入消息（可用于导入大模型生成的大量消息）"""
    
    db = RRCDatabaseManager(
        host='localhost',
        database='rrc_testing',
        user='root',
        password='your_password'
    )
    
    if not db.connect():
        return
    
    # 假设你有一个包含多个生成消息的列表
    messages = [
        # 每个元素包含：message_content, path, encode_hex
        # 这里只是示例结构
    ]
    
    success_count = 0
    for msg_data in messages:
        path_id = db.get_path_id_by_hash('36331-j00', msg_data['path'])
        if path_id:
            message_id = db.insert_message(
                path_id=path_id,
                message_content=msg_data['content'],
                encode_hex=msg_data['encode']
            )
            if message_id:
                success_count += 1
    
    print(f"批量导入完成，成功: {success_count}/{len(messages)}")
    db.disconnect()


if __name__ == '__main__':
    print("=== RRC消息数据库使用示例 ===\n")
    
    # 运行示例
    # example_insert_message()
    # example_query_statistics()
    
    print("\n请根据需要取消注释上面的示例函数")
