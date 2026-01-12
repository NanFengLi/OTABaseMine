import json
import logging
import sys
import os
from enum import Enum
from typing import List, Dict, Tuple, Any

# Ensure we can import from the artifact directory
# From bishe/generate to OTABase root is ../../

try:
    from pycrate_rrc_version import RRCLTE_R17
    from pycrate_asn1rt import *
    from pycrate_asn1rt.utils import *
    from pycrate_asn1rt.err import *
    from pycrate_asn1rt.refobj import *
    from pycrate_asn1rt.dictobj import *
    from pycrate_asn1rt.setobj import *
    from pycrate_asn1rt.codecs import *
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
            message_name: 起始消息名称
            targets: 目标类型列表 (如果为 None，则默认全部)
        
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
            for choices, full_path in raw_paths:
                 # 将路径转换为字符串列表，方便序列化 (如果有非字符串对象)
                clean_path = [str(p) for p in full_path]
                clean_choices = [str(c) for c in choices]
                formatted_paths.append({
                    "target_type": "DL_DCCH_MESSAGE", # get_choices 原版不返回类型，这里简化
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

    def _get_choices(self, sel, path=[], depth=0, targets=[TargetType.OCTET_STRING]) -> tuple:
        """
        从 rrc_choices.py 移植并适配的路径提取逻辑
        """
        num, recur = 0,  []
        choice_paths = []

        if not hasattr(sel, '_proto_recur'):
            root = True
            sel._proto_recur = [id(sel)]
            sel._proto_path = []
        else:
            root = False

        # SEQUENCE / SET
        if sel.TYPE in (TYPE_SEQ, TYPE_SET, TYPE_CLASS):
            for (ident, Comp) in sel._cont.items():
                if id(Comp) in sel._proto_recur:
                    # 递归无需处理
                    pass
                else:
                    Comp._proto_recur = sel._proto_recur + [id(Comp)]
                    Comp._proto_path = sel._proto_path + [ident]
                    comp_num, comp_recur, c_paths = self._get_choices(
                        Comp, path + [sel._name], depth, targets)
                    del Comp._proto_recur, Comp._proto_path
                    num += comp_num
                    recur.extend(comp_recur)
                    choice_paths.extend(c_paths)

        # CHOICE
        elif sel.TYPE == TYPE_CHOICE:
            for (ident, Comp) in sel._cont.items():
                if id(Comp) in sel._proto_recur:
                     pass
                else:
                    Comp._proto_recur = sel._proto_recur + [id(Comp)]
                    Comp._proto_path = sel._proto_path + [ident]
                    comp_num, comp_recur, c_paths = self._get_choices(
                        Comp, path + [sel._name], depth + 1, targets)
                    
                    # 关键：将当前选择 (ident) 加入到 choices 列表中
                    for (choices, full_path) in c_paths:
                        choice_paths.append(([ident] + choices, full_path))

                    del Comp._proto_recur, Comp._proto_path
                    num += comp_num
                    recur.extend(comp_recur)

        # SEQUENCE OF / SET OF
        elif sel.TYPE in (TYPE_SEQ_OF, TYPE_SET_OF):
            Comp = sel._cont
            if id(Comp) in sel._proto_recur:
                pass
            else:
                Comp._proto_recur = sel._proto_recur + [id(Comp)]
                Comp._proto_path = sel._proto_path + [None]
                comp_num, comp_recur, c_paths = self._get_choices(
                    Comp, path + [sel._name], depth, targets)
                choice_paths = c_paths # 直接继承
                del Comp._proto_recur, Comp._proto_path
                num += comp_num
                recur.extend(comp_recur)

            # 这里的逻辑是 OTABase 特有的：如果有 SEQOF 且在 targets 里，我们也把它算作一条路径
            if sel.TYPE in (TYPE_SEQ_OF) and TargetType.SEQOF in targets \
                    and getattr(sel, '_const_sz', None) and sel._const_sz.lb != sel._const_sz.ub:
                choice_paths = choice_paths + [([sel._name], path + [sel._name])]
                num += 1

        # BIT / OCTET STRING with continuation (pycrate specific structure for open types)
        elif sel.TYPE in (TYPE_BIT_STR, TYPE_OCT_STR) and getattr(sel, '_const_cont', None):
            Comp = sel._const_cont
            if id(Comp) in sel._proto_recur:
                pass
            else:
                Comp._proto_recur = sel._proto_recur + [id(Comp)]
                Comp._proto_path = sel._proto_path + [None]
                # 注意这里路径可能会变复杂
                try:
                    type_list = sel._const_cont.get_type_list()
                    cont_name = type_list[0] if type_list else "CONTAINER"
                except:
                    cont_name = "CONTAINER"
                    
                comp_num, comp_recur, c_paths = self._get_choices(
                    Comp, path + [sel._name] + [cont_name], depth, targets)
                del Comp._proto_recur, Comp._proto_path
                num += comp_num
                choice_paths = c_paths
                recur.extend(comp_recur)

            if (sel.TYPE == TYPE_BIT_STR and TargetType.BIT_STRING in targets) \
                    or (sel.TYPE == TYPE_OCT_STR and TargetType.OCTET_STRING in targets):
                num += 1
                choice_paths = choice_paths + [([sel._name], path + [sel._name])]

        # BIT / OCTET STRING (Basic)
        elif sel.TYPE in (TYPE_BIT_STR, TYPE_OCT_STR):
            if (sel.TYPE == TYPE_BIT_STR and TargetType.BIT_STRING in targets) \
                    or (sel.TYPE == TYPE_OCT_STR and TargetType.OCTET_STRING in targets):
                num += 1
                choice_paths = [([sel._name], path + [sel._name])]
                # 如果长度固定，OTABase sometimes ignores it? 
                # 这里保留

        # INTEGER
        elif sel.TYPE in TYPE_INT:
            # 检查是否为简单的整数范围，OTABase 只关心某些有“变异价值”的整数
            # 这里简化逻辑，只要是 INTEGER 且在 targets 里就返回
            if TargetType.INTEGER in targets:
                choice_paths = [([sel._name], path + [sel._name])]
                num += 1

        else:
            # 其他基本类型
            num = 0
            choice_paths = []

        if root:
            if hasattr(sel, '_proto_recur'): del sel._proto_recur
            if hasattr(sel, '_proto_path'): del sel._proto_path
            
        return num, recur, choice_paths
