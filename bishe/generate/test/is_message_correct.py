import ast
import json
# import RRC_LET_R19 as RRC_LTE_R19
from pycrate_asn1dir import RRCLTE
from binascii import unhexlify, hexlify



# dl_dcch_message ={
#   'message': ('c1',
#    ('csfbParametersResponseCDMA2000',
#    {
#     'rrc-TransactionIdentifier': 0,
#      'criticalExtensions': ('csfbParametersResponseCDMA2000-r8',
#      {
#       'rand': (3184935163,32),
#       'mobilityParameters': b'F>9#\xbc\x1a\xad\xbd\xe4\x8b\x16\x97l\x08\x07\x177;\x81\x9a\x06\x8f2\xb7\xa6\xb3\x8bk8r\x96G',
#       'nonCriticalExtension': {
#         'lateNonCriticalExtension': b"\xcf\xde\x01\xc2\xce(\xb2lWG'7\xf5\xc3V\x1a\x17a\x18[\xd8X\x9aC\xce\x0b\xbau\x89\x1f\xf9\xec",
#         'nonCriticalExtension': {
#           }
#         }
#       })
#     }))
#   }

# dl_dcch_message = {
#     'message': (
#         'c1',
#         (
#             'csfbParametersResponseCDMA2000',
#             {
#                 'rrc-TransactionIdentifier': 1,
#                 'criticalExtensions': (
#                     'csfbParametersResponseCDMA2000-r8',
#                     {
#                         'rand': (1234567890, 32),
#                         'mobilityParameters': b'\x01\x23\x45\x67\x89\xab\xcd\xef\x10\x32\x54\x76\x98\xba\xdc\xfe',
#                         'nonCriticalExtension': {
#                             'lateNonCriticalExtension': b'\xde\xad\xbe\xef\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb',
#                             'nonCriticalExtension': {}
#                         }
#                     }
#                 )
#             }
#         )
#     )
# }

# 生成的有些许问题：
# 缺少 'nonCriticalExtension': {} 这个非OPTIONAL字段
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
#          'lateNonCriticalExtension': b'\x00' 
#       } 
#     }) 
#   })) 
# }

# dl_dcch_message = {
#    'message': ('c1',
#    ('dlDedicatedMessageSegment-r16',
#    {
#      'criticalExtensions': ('dlDedicatedMessageSegment-r16',
#      {
#        'segmentNumber-r16': 0,
#        'rrc-MessageSegmentContainer-r16': b'\x00',
#        'rrc-MessageSegmentType-r16': 'notLastSegment',
#     }) 
#   })) 
# }

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


def to_uper():
    DL_DCCH = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    DL_DCCH.set_val(dl_dcch_message)

    print(hexlify(DL_DCCH.to_uper()))

def from_uper():
    DL_DCCH = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    # uper_data = 

def method_test():
    DL_DCCH = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    DL_DCCH.set_val(dl_dcch_message)
    
    """1、print(DL_DCCH())输出示例
    {'message': ('c1', ('rrcConnectionReconfiguration', {'rrc-TransactionIdentifier': 0, 'criticalExtensions': ('c1', ('rrcConnectionReconfiguration-r8', {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'sl-SSB-PriorityEUTRA-r16': 1}}}}}}}}}}}))}))}
    """
    # print(DL_DCCH())

    """2、print(DL_DCCH.to_asn1())输出示例
        {
      message c1 : rrcConnectionReconfiguration : {
        rrc-TransactionIdentifier 0,
        criticalExtensions c1 : rrcConnectionReconfiguration-r8 : {
          nonCriticalExtension {
            nonCriticalExtension {
              nonCriticalExtension {
                nonCriticalExtension {
                  nonCriticalExtension {
                    nonCriticalExtension {
                      nonCriticalExtension {
                        nonCriticalExtension {
                          nonCriticalExtension {
                            nonCriticalExtension {
                              sl-SSB-PriorityEUTRA-r16 1
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
        }
      }
    }
    """
    # print(DL_DCCH.to_asn1())


    """3、print(DL_DCCH.get_proto()) 输出示例，放入了文件当中"""
    # with open('a.txt','w') as f:
    #     try:
    #         f.write(str(DL_DCCH.get_proto()))
    #     except Exception as e:
    #         print(e)
    

    """4、获取对应路径的对象 Obj.get_at(path)"""
    # print(obj)输出示例 : <dl-CarrierFreq ([ARFCN-ValueEUTRA] INTEGER)>
    """ print(obj._cont)输出示例 : 
    {
    csfbParametersResponseCDMA2000: <csfbParametersResponseCDMA2000 ([CSFBParametersResponseCDMA2000] SEQUENCE)>,
    dlInformationTransfer: <dlInformationTransfer ([DLInformationTransfer] SEQUENCE)>,
    handoverFromEUTRAPreparationRequest: <handoverFromEUTRAPreparationRequest ([HandoverFromEUTRAPreparationRequest] SEQUENCE)>,
    mobilityFromEUTRACommand: <mobilityFromEUTRACommand ([MobilityFromEUTRACommand] SEQUENCE)>,
    rrcConnectionReconfiguration: <rrcConnectionReconfiguration ([RRCConnectionReconfiguration] SEQUENCE)>,
    rrcConnectionRelease: <rrcConnectionRelease ([RRCConnectionRelease] SEQUENCE)>,
    securityModeCommand: <securityModeCommand ([SecurityModeCommand] SEQUENCE)>,
    ueCapabilityEnquiry: <ueCapabilityEnquiry ([UECapabilityEnquiry] SEQUENCE)>,
    counterCheck: <counterCheck ([CounterCheck] SEQUENCE)>,
    ueInformationRequest-r9: <ueInformationRequest-r9 ([UEInformationRequest-r9] SEQUENCE)>,
    loggedMeasurementConfiguration-r10: <loggedMeasurementConfiguration-r10 ([LoggedMeasurementConfiguration-r10] SEQUENCE)>,
    rnReconfiguration-r10: <rnReconfiguration-r10 ([RNReconfiguration-r10] SEQUENCE)>,
    rrcConnectionResume-r13: <rrcConnectionResume-r13 ([RRCConnectionResume-r13] SEQUENCE)>,
    dlDedicatedMessageSegment-r16: <dlDedicatedMessageSegment-r16 ([DLDedicatedMessageSegment-r16] SEQUENCE)>,
    spare2: <spare2 (NULL)>,
    spare1: <spare1 (NULL)>
    } """
    # obj = DL_DCCH.get_at([
    #   "message",
    #   "c1",
    #   ])
    # print(obj._cont)

    """5、获取对应路径的值"""
    # get_val_at（Obj，路径）使用和输出示例
    # get_val_at(Obj, path)
    print(DL_DCCH.get_val_at(['message', 'c1']))

    """6、获取对象中“有值的属性”对应的所有路径,使用前需要先赋值"""
    # 方法 get_val_paths（） 也有助于收集给定对象的所有路径列表及其对应值。
    # get_val_paths()
    """ 比如： dl_dcch_message = {
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
      则输出示例为：
      [  (['message', 'c1', 'rrcConnectionReconfiguration', 'rrc-TransactionIdentifier'], 0), 
        (['message', 'c1', 'rrcConnectionReconfiguration', 'criticalExtensions', 'c1', 'rrcConnectionReconfiguration-r8', 'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension', 'nonCriticalExtension', 'sl-SSB-PriorityEUTRA-r16'], 1)
      ],把所有路径及其对应值都列出来了。

      再比如：
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
      输出示例为：
      [ (['message', 'c1', 'dlDedicatedMessageSegment-r16', 'criticalExtensions', 'dlDedicatedMessageSegment-r16', 'segmentNumber-r16'], 0), 
        (['message', 'c1', 'dlDedicatedMessageSegment-r16', 'criticalExtensions', 'dlDedicatedMessageSegment-r16', 'rrc-MessageSegmentContainer-r16'], b'\x00'), 
        (['message', 'c1', 'dlDedicatedMessageSegment-r16', 'criticalExtensions', 'dlDedicatedMessageSegment-r16', 'rrc-MessageSegmentType-r16'], 'notLastSegment')
      ]
    """
    # print(DL_DCCH.get_val_paths())

def attr_test():
    # 常规类型属性
    DL_DCCH = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    DL_DCCH.set_val(dl_dcch_message)
    """ 
    输出示例:
    {'message': ('c1', ('rrcConnectionReconfiguration', {'rrc-TransactionIdentifier': 0, 'criticalExtensions': ('c1', ('rrcConnectionReconfiguration-r8', {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'nonCriticalExtension': {'sl-SSB-PriorityEUTRA-r16': 1}}}}}}}}}}}))}))}
    """
    # print(DL_DCCH._val)

    """输出示例:输出拥有的属性名和对应的obj对象
    {
    message: <message ([DL-DCCH-MessageType] CHOICE)>
    }
    """
    print(DL_DCCH._cont)

  # =======================================================================================
    # MeasConfig = RRCLTE.EUTRA_RRC_Definitions.MeasConfig
    # (SEQ类型拥有的属性: _root_mand, _root_opt, _ext)
    # 必须存在的属性
    # print(MeasConfig._root_mand)
    # 可选属性
    # print(MeasConfig._root_opt)
    # 扩展属性
    # print(MeasConfig._ext)
  


if __name__ == "__main__":

    # to_uper()
    method_test()
    # attr_test()
    # str_to_dict(BCCH_DL_SCH_Message)
