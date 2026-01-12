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

dl_dcch_message = {
   'message': ('c1',
   ('csfbParametersResponseCDMA2000',
   {
     'rrc-TransactionIdentifier': 0,
     'criticalExtensions': ('csfbParametersResponseCDMA2000-r8',
     {
       'rand': (0,
       32),
       'mobilityParameters': b'\x00',
       'nonCriticalExtension': {
         'lateNonCriticalExtension': b'\x00' 
      } 
    }) 
  })) 
}


def asn1tools__3GPP():
    DL_DCCH = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    DL_DCCH.set_val(dl_dcch_message)

    print(hexlify(DL_DCCH.to_uper()))


if __name__ == "__main__":

    asn1tools__3GPP()
    # str_to_dict(BCCH_DL_SCH_Message)
