# from bishe.mutated.tools import integer_mutation_tool

# # 准备 RRC 消息
# dl_dcch_message = {
#    'message': ('c1',
#    ('csfbParametersResponseCDMA2000',
#    {
#      'rrc-TransactionIdentifier': 0,
#      'criticalExtensions': ('csfbParametersResponseCDMA2000-r8',
#      {
#        'rand': (0,
#        32),
#        'mobilityParameters': b'\x00',
#        'nonCriticalExtension': {
#          'lateNonCriticalExtension': b'\x00',
#          'nonCriticalExtension': {} 
#       } 
#     }) 
#   })) 
# }

# # 调用变异工具
# result = integer_mutation_tool(
#     message=dl_dcch_message,
#     target_path=['message', 'c1', 'csfbParametersResponseCDMA2000', 
#                  'rrc-TransactionIdentifier'],
#     lower_bound=0,
#     upper_bound=3,
#     message_type='csfbParametersResponseCDMA2000'
# )

# # 获取变异结果
# print(f"生成了 {result['count']} 个变异\n")

# for i, (mutation_bytes, description) in enumerate(zip(result['mutations'], result['descriptions']), 1):
#     print(f"变异 {i}: {description}")
#     print(f"  ASN.1编码(hex): {mutation_bytes.hex()}")
#     print(f"  ASN.1编码长度: {len(mutation_bytes)} 字节")
#     print()

from bishe.mutated.tools import integer_mutation_tool

# 准备 RRC 消息
dl_dcch_message = {
   'message': ('c1',
   ('dlDedicatedMessageSegment-r16',
   {
     'criticalExtensions': ('dlDedicatedMessageSegment-r16',
     {
       'segmentNumber-r16': 0,
       'rrc-MessageSegmentContainer-r16': b'\x00',
       'rrc-MessageSegmentType-r16': 'notLastSegment',
    }) 
  })) 
}

# 调用变异工具
result = integer_mutation_tool(
    message=dl_dcch_message,
    target_path=['message', 'c1', 'dlDedicatedMessageSegment-r16', 
                 'criticalExtensions', 'dlDedicatedMessageSegment-r16', 'segmentNumber-r16'],
    lower_bound=0,
    upper_bound=4,
    message_type='dlDedicatedMessageSegment-r16'
)

# 获取变异结果
print(f"生成了 {result['count']} 个变异\n")

for i, (mutation_bytes, description) in enumerate(zip(result['mutations'], result['descriptions']), 1):
    print(f"变异 {i}: {description}")
    print(f"  ASN.1编码(hex): {mutation_bytes.hex()}")
    print(f"  ASN.1编码长度: {len(mutation_bytes)} 字节")
    print()