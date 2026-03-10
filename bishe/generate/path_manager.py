import json
import logging
import sys
import os
from enum import Enum
from typing import List, Dict, Tuple, Any

# Ensure we can import from the artifact directory
# From bishe/generate to OTABase root is ../../

try:
    from pycrate.pycrate_rrc_version import RRCLTE_R17
    from pycrate.pycrate_asn1rt import *
    from pycrate.pycrate_asn1rt.utils import *
    from pycrate.pycrate_asn1rt.err import *
    from pycrate.pycrate_asn1rt.refobj import *
    from pycrate.pycrate_asn1rt.dictobj import *
    from pycrate.pycrate_asn1rt.setobj import *
    from pycrate.pycrate_asn1rt.codecs import *
except ImportError as e:
    logging.error(f"Failed to import pycrate or RRCLTE_R17: {e}")
    RRCLTE_R17 = None

from config import Config

class TargetType(Enum):
    """
    目标字段类型枚举，与 OTABase 的 Fields 保持概念一致
    """
    BIT_STRING = 1
    OCTET_STRING = 2
    INTEGER = 3
    SEQOF = 4

class PathManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.target_paths_file = Config.TARGET_PATH_FILE_ROOT + f"/{Config.RRC_VERSION}/rrc_paths.json"
        self.paths_cache = {}

    def extract_paths(self, message_name: str = 'DL-DCCH-Message', targets: List[TargetType] = None) -> List[Dict]:
        """
        提取通往指定目标类型的所有路径。
        
        Args:
            message_name: 起始消息名称,如'DL_DCCH_Message',必须使用下划线
            targets: 目标类型列表 (如果为 None, 则默认全部)
        
        Returns:
            只有路径信息的列表，每个元素包含 'path' (完整路径) 和 'choices' (决策路径)
        """
        if RRCLTE_R17 is None:
            self.logger.error("RRCLTE_R17 未加载，无法提取路径")
            return []

        if targets is None:
            targets = [TargetType.OCTET_STRING, TargetType.INTEGER, TargetType.BIT_STRING, TargetType.SEQOF]

        # 获取消息对象
        # 注意: RRCLTE_R17 结构比较特殊，通常在 GLOBAL.MOD['EUTRA-RRC-Definitions'] 下
        # 或者直接作为属性访问，取决于 pycrate 生成方式
        
        try:
            # 尝试直接从 EUTRA_RRC_Definitions 获取 DL_DCCH_Message的定义
            # message_name.replace('-', '_')不会改变message_name的内容
            msg_obj = getattr(RRCLTE_R17.EUTRA_RRC_Definitions, message_name, None)

            if not msg_obj:
                raise ValueError(f"无法在 RRCLTE_R17 中找到消息: {message_name}")

            self.logger.info(f"开始分析消息结构: {message_name}")
            
            # 适配 get_choices 需要的 targets
            # get_choices 中使用 target 枚举值比较
            otabase_targets = targets 

            _, _, raw_paths = self._get_choices(msg_obj, path=[], depth=0, targets=otabase_targets)
            
            # 格式化输出
            formatted_paths = []
            for choices, full_path, target_type in raw_paths:
                 # 将路径转换为字符串列表，方便序列化 (如果有非字符串对象)
                clean_path = [str(p) for p in full_path]

                # 修复：去除路径中的根消息名称 (如 DL-DCCH-Message)，避免生成冗余的顶层键
                if clean_path and (clean_path[0] == message_name or clean_path[0] == msg_obj._name):
                    clean_path = clean_path[1:]

                clean_choices = [str(c) for c in choices]
                formatted_paths.append({
                    "top_level_message": message_name,
                    "target_type": target_type, 
                    "path": clean_path,
                    "choices": clean_choices
                })
            
            self.logger.info(f"提取完成，共找到 {len(formatted_paths)} 条路径")
            return formatted_paths

        except Exception as e:
            self.logger.error(f"提取路径时发生错误: {e}", exc_info=True)
            return []

    def save_paths(self, paths: List[Dict]):
        """保存路径到 JSON 文件"""
        try:
            with open(self.target_paths_file, 'w', encoding='utf-8') as f:
                json.dump(paths, f, indent=2, ensure_ascii=False)
            self.logger.info(f"路径已保存到 {self.target_paths_file}")
        except Exception as e:
            self.logger.error(f"保存路径失败: {e}")

    def load_paths(self) -> List[Dict]:
        """从文件加载路径"""
        if not os.path.exists(self.target_paths_file):
            self.logger.warning(f"路径文件不存在: {self.target_paths_file}")
            return []
        try:
            with open(self.target_paths_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"加载路径失败: {e}")
            return []

    # 模仿pycrate中的asnobj.py中的get_proto方法写的
    def _get_choices(self, msg_obj, path=[], depth=0, targets=[TargetType.OCTET_STRING]) -> tuple:
        """
        从 rrc_choices.py 移植并适配的路径提取逻辑
        入参: 
            msg_obj: 当前 ASN.1 对象,pycrate中定义的类型
            path: 从根到当前对象的路径列表
            depth: 当前递归深度
            targets: 目标类型列表
        出参:
            num: 找到的目标字段数量
            recur: 递归跟踪信息 (未使用)
            choice_paths: 包含路径信息的列表，每个元素为 (choices, full_path, target_type)
        说明:
            该方法递归遍历 ASN.1 对象结构，寻找通往指定目标类型的路径。
            支持 SEQUENCE, SET, CHOICE, SEQUENCE OF, SET OF, BIT STRING, OCTET STRING, INTEGER 等类型。
        关键点:
            - 通过在 CHOICE 类型中记录选择路径，构建完整的决策路径。
            - 使用 _proto_recur 属性防止循环引用导致的无限递归。    
        """
        num, recur = 0,  []
        choice_paths = []

        if not hasattr(msg_obj, '_proto_recur'):
            root = True
            # 初始化递归跟踪属性,使用 id() 来防止无限递归：
            # ASN.1 结构可能存在循环引用：
            # 对象 A 包含对象 B
            # 对象 B 又引用回对象 A
            # 如果不检测，会无限递归导致栈溢出
            msg_obj._proto_recur = [id(msg_obj)]
            msg_obj._proto_path = []
        else:
            root = False

        # SEQUENCE / SET 
        if msg_obj.TYPE in (TYPE_SEQ, TYPE_SET, TYPE_CLASS):
            # items()是字典的一个方法,返回字典中的所有键值对
            # ident是组件名称(字符串),如'message','rrc-TransactionIdentifier'
            # Comp 是组件对象(ASN.1 对象)
            for (ident, Comp) in msg_obj._cont.items():
                if id(Comp) in msg_obj._proto_recur:
                    # 发生了循环饮用(出现了环),跳过
                    pass
                else:
                    Comp._proto_recur = msg_obj._proto_recur + [id(Comp)]
                    Comp._proto_path = msg_obj._proto_path + [ident]
                    # 递归调用获取Comp中的路径
                    # _name也是组件的名称,与ident相同,只不过ident是从_cont属性中临时获取到的变量
                    comp_num, comp_recur, c_paths = self._get_choices(
                        Comp, path + [msg_obj._name], depth, targets)
                    
                    # del Comp._proto_recur, Comp._proto_path 的作用是清理临时属性，避免污染 ASN.1 对象, 也是模仿asnobj中的方法写的
                    del Comp._proto_recur, Comp._proto_path
                    num += comp_num
                    # 将子组件 Comp 递归返回的跟踪信息 comp_recur 合并到当前的 recur 列表,收集整个子树的递归信息（虽然在当前代码中 recur 并未被实际使用）
                    recur.extend(comp_recur)
                    # 将子组件 Comp 中找到的所有路径 c_paths 合并到当前的 choice_paths 收集所有子树中通往目标类型的路径
                    choice_paths.extend(c_paths)

        # CHOICE
        elif msg_obj.TYPE == TYPE_CHOICE:
            for (ident, Comp) in msg_obj._cont.items():
                if id(Comp) in msg_obj._proto_recur:
                     pass
                else:
                    Comp._proto_recur = msg_obj._proto_recur + [id(Comp)]
                    Comp._proto_path = msg_obj._proto_path + [ident]
                    comp_num, comp_recur, c_paths = self._get_choices(
                        Comp, path + [msg_obj._name], depth + 1, targets)
                    
                    # 关键：将当前选择 (ident) 加入到 choices 列表中
                    for (choices, full_path, target_type) in c_paths:
                        choice_paths.append(([ident] + choices, full_path, target_type))

                    del Comp._proto_recur, Comp._proto_path
                    num += comp_num
                    recur.extend(comp_recur)

        # SEQUENCE OF / SET OF
        elif msg_obj.TYPE in (TYPE_SEQ_OF, TYPE_SET_OF):
            Comp = msg_obj._cont
            if id(Comp) in msg_obj._proto_recur:
                pass
            else:
                Comp._proto_recur = msg_obj._proto_recur + [id(Comp)]
                Comp._proto_path = msg_obj._proto_path + [None]
                comp_num, comp_recur, c_paths = self._get_choices(
                    Comp, path + [msg_obj._name], depth, targets)
                choice_paths = c_paths # 直接继承
                del Comp._proto_recur, Comp._proto_path
                num += comp_num
                recur.extend(comp_recur)

            # 这里的逻辑是 OTABase 特有的：如果有 SEQOF 且在 targets 里，我们也把它算作一条路径
            if msg_obj.TYPE in (TYPE_SEQ_OF) and TargetType.SEQOF in targets \
                    and getattr(msg_obj, '_const_sz', None) and msg_obj._const_sz.lb != msg_obj._const_sz.ub:
                choice_paths = choice_paths + [([msg_obj._name], path + [msg_obj._name], "SEQOF")]
                num += 1

        # BIT / OCTET STRING with continuation (pycrate specific structure for open types)
        elif msg_obj.TYPE in (TYPE_BIT_STR, TYPE_OCT_STR) and getattr(msg_obj, '_const_cont', None):
            # 遇到 BIT/OCTET STRING with continuation，直接跳过递归，不展开 _const_cont
            if (msg_obj.TYPE == TYPE_BIT_STR and TargetType.BIT_STRING in targets) \
                    or (msg_obj.TYPE == TYPE_OCT_STR and TargetType.OCTET_STRING in targets):
                num += 1
                target_type_str = "BIT_STRING" if msg_obj.TYPE == TYPE_BIT_STR else "OCTET_STRING"
                choice_paths = [([msg_obj._name], path + [msg_obj._name], target_type_str)]

        # BIT / OCTET STRING (Basic)
        elif msg_obj.TYPE in (TYPE_BIT_STR, TYPE_OCT_STR):
            if (msg_obj.TYPE == TYPE_BIT_STR and TargetType.BIT_STRING in targets) \
                    or (msg_obj.TYPE == TYPE_OCT_STR and TargetType.OCTET_STRING in targets):
                num += 1
                target_type_str = "BIT_STRING" if msg_obj.TYPE == TYPE_BIT_STR else "OCTET_STRING"
                choice_paths = [([msg_obj._name], path + [msg_obj._name], target_type_str)]
                # 如果长度固定，OTABase sometimes ignores it? 
                # 这里保留

        # INTEGER
        elif msg_obj.TYPE in TYPE_INT:
            # 检查是否为简单的整数范围，OTABase 只关心某些有“变异价值”的整数
            # 这里简化逻辑，只要是 INTEGER 且在 targets 里就返回
            if TargetType.INTEGER in targets:
                choice_paths = [([msg_obj._name], path + [msg_obj._name], "INTEGER")]
                num += 1

        else:
            # 其他基本类型
            num = 0
            choice_paths = []

        if root:
            if hasattr(msg_obj, '_proto_recur'): del msg_obj._proto_recur
            if hasattr(msg_obj, '_proto_path'): del msg_obj._proto_path
            
        return num, recur, choice_paths
