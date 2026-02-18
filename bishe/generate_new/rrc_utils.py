"""
RRC 消息精简工具函数

提供将生成的 RRC 消息精简为最小合法消息的功能：
- 识别到达目标字段所需保留的可选字段路径
- 删除不必要的可选字段
- 处理嵌套的 OCTET STRING 容器中的字段删除

从 OTABase artifact/test-case-generator/rrc/rrc_utils.py 抽取精简相关函数。
"""
import logging
import os

from .releaseLTE_R17 import RRCLTE_R17


def find_paths_to_delete_multi(keep: list, optional_paths: list) -> tuple:
    """
    找出所有应该删除的可选字段路径。

    保留策略：
    - 保留 keep 列表中的路径本身
    - 保留 keep 路径的祖先（到达目标必经之路）
    - 保留 keep 路径的子节点（嵌套在目标字段内的内容）
    - 删除其他所有可选字段路径

    Args:
        keep:           需要保留的路径列表
        optional_paths: 所有可选字段路径列表

    Returns:
        (to_delete, ancestors, childrens) 三元组
    """
    to_delete = []
    ancestors = []
    childrens = []

    for path in optional_paths:
        found = False
        for k in keep:
            if path == k:
                found = True
                break
            # path 是 keep 路径的祖先
            if path != k and len(k) > len(path) and k[:len(path)] == path:
                ancestors.append(path)
                found = True
                break
            # path 是 keep 路径的子节点
            elif path != k and len(k) < len(path) and path[:len(k)] == k:
                childrens.append(path)
                found = True
                break
        if not found:
            to_delete.append(path)

    return to_delete, ancestors, childrens


def reduce_paths(paths: list, children_paths: list) -> list:
    """
    通过利用祖先路径的删除来减少需要删除的路径数量。

    因为路径是按 DFS 遍历顺序收集的，祖先路径会在子路径之前出现。
    删除祖先路径会自动删除其所有后代，因此无需单独删除。

    Args:
        paths:           待删除路径列表
        children_paths:  子节点路径列表（不能删除）

    Returns:
        list: 最少量的需要删除的路径
    """
    unique_paths = list()
    for path in paths:
        if len(unique_paths) == 0 and path not in children_paths:
            unique_paths.append(path)
        else:
            if len(unique_paths) > 0:
                last_path = unique_paths[-1]
                if path[:len(last_path)] != last_path and path not in children_paths:
                    unique_paths.append(path)
            elif path not in children_paths:
                unique_paths.append(path)

    return unique_paths


def delete_fields(msg, delete_paths: list):
    """
    从 RRC 消息字典中删除指定路径的字段。

    支持处理：
    - 普通字典键删除
    - CHOICE 元组结构中的删除
    - 嵌套在 OCTET STRING 容器（以 '*' 标记）中的递归删除
    - SEQUENCE OF 元素标记（'^' 和 '__elem__'）的跳过

    Args:
        msg:          RRC 消息字典
        delete_paths: 要删除的字段路径列表

    Returns:
        dict: 精简后的消息字典
    """
    simplified_message = msg
    for p in delete_paths:
        skip_del = False
        skip_next_key = False
        curr_msg = simplified_message
        parent_msg = simplified_message
        last_key = ''

        for i, key in enumerate(p[:-1]):
            if skip_next_key:
                skip_next_key = False
                continue
            # 处理嵌套在 OCTET STRING 中的字段
            if key == '*' and type(curr_msg) is bytes:
                embedded = RRCLTE_R17.GLOBAL.MOD['EUTRA-RRC-Definitions'][p[i + 1]]
                embedded.from_uper(curr_msg)
                r = delete_fields(embedded.get_val(), [p[i + 2:]])
                embedded.set_val(r)
                parent_msg[last_key] = embedded.to_uper()
                skip_del = True
                break
            if key == '*' or '__elem__' == key:
                continue
            if key == '^':
                skip_next_key = True
                continue
            if type(curr_msg) is tuple:
                assert key == curr_msg[0]
                parent_msg = curr_msg
                last_key = 1
                curr_msg = curr_msg[1]
            else:
                try:
                    parent_msg = curr_msg
                    last_key = key
                    curr_msg = curr_msg[key]
                except Exception:
                    logging.debug(f'Exception accessing {key} in path {p}, skipping')
                    skip_del = True
                    break

        if not skip_del:
            try:
                del curr_msg[p[-1]]
            except (KeyError, TypeError) as e:
                logging.debug(f'Could not delete {p[-1]}: {e}')

    return simplified_message


def simplify_message(packet_fields: dict, target_path: list,
                     optional_paths: list) -> dict:
    """
    将 RRC 消息精简为到达目标字段的最小合法消息。

    步骤：
    1. 找出所有与目标路径无关的可选字段
    2. 通过祖先关系优化删除路径数量
    3. 从消息字典中删除不必要的字段

    Args:
        packet_fields:  完整消息字典
        target_path:    目标字段路径
        optional_paths: 所有可选字段路径列表

    Returns:
        dict: 精简后的消息字典
    """
    # 找出要删除的路径（保留目标路径及其祖先/子节点）
    paths_to_delete, _, childrens = find_paths_to_delete_multi(
        [target_path], optional_paths)

    # 优化删除路径
    reduced_paths = reduce_paths(paths_to_delete, childrens)

    # 执行删除
    simplified = delete_fields(packet_fields, reduced_paths)

    return simplified
