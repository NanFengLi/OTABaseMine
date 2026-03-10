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
                # 如果子节点跨越了 OCTET STRING 容器边界（'*'），
                # 说明它在容器内部，应该删除以精简容器内容
                if path[len(k)] == '*':
                    to_delete.append(path)
                else:
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


def _navigate_to(msg, path_keys):
    """
    沿路径导航到目标位置，返回 (当前节点, 父节点, 父中的键)。

    处理 CHOICE 元组、'^' 跳过和 '__elem__' 跳过。
    遇到 '*' (容器边界) 时停止。

    Args:
        msg:       消息字典
        path_keys: 路径键列表

    Returns:
        (curr, parent, key, consumed) 或 None（导航失败时）
        consumed: 已消费的键数量
    """
    curr = msg
    parent = msg
    last_key = ''
    skip_next = False

    for i, key in enumerate(path_keys):
        if skip_next:
            skip_next = False
            continue
        if key == '*':
            return curr, parent, last_key, i
        if key == '__elem__':
            continue
        if key == '^':
            skip_next = True
            continue
        if type(curr) is tuple:
            if key != curr[0]:
                return None
            parent = curr
            last_key = 1
            curr = curr[1]
        else:
            try:
                parent = curr
                last_key = key
                curr = curr[key]
            except Exception:
                return None

    return curr, parent, last_key, len(path_keys)


def delete_fields(msg, delete_paths: list, global_mod=None):
    """
    从 RRC 消息字典中删除指定路径的字段。

    支持处理：
    - 普通字典键删除
    - CHOICE 元组结构中的删除
    - 嵌套在 OCTET STRING 容器（以 '*' 标记）中的递归删除（批量处理）
    - SEQUENCE OF 元素标记（'^' 和 '__elem__'）的跳过

    Args:
        msg:          RRC 消息字典
        delete_paths: 要删除的字段路径列表
        global_mod:   GLOBAL.MOD 中的协议定义字典

    Returns:
        dict: 精简后的消息字典
    """
    # 将路径分为：直接删除路径 和 容器内删除路径（按容器分组）
    direct_paths = []
    # container_groups: { (container_prefix_tuple): { type_name: [sub_paths] } }
    container_groups = {}

    for p in delete_paths:
        # 找到第一个 '*'
        star_idx = None
        for i, key in enumerate(p):
            if key == '*':
                star_idx = i
                break

        if star_idx is None:
            direct_paths.append(p)
        else:
            prefix = tuple(p[:star_idx])
            type_name = p[star_idx + 1]
            sub_path = p[star_idx + 2:]
            container_groups.setdefault(prefix, {}).setdefault(type_name, []).append(sub_path)

    # 1. 处理直接删除（不涉及容器）
    simplified_message = msg
    for p in direct_paths:
        nav = _navigate_to(simplified_message, p[:-1])
        if nav is None:
            logging.debug(f'Cannot navigate to path {p}, skipping')
            continue
        curr, _, _, _ = nav
        try:
            del curr[p[-1]]
        except (KeyError, TypeError) as e:
            logging.debug(f'Could not delete {p[-1]}: {e}')

    # 2. 批量处理容器内删除（每个容器只解码/编码一次）
    for prefix, type_groups in container_groups.items():
        nav = _navigate_to(simplified_message, list(prefix))
        if nav is None:
            logging.debug(f'Cannot navigate to container prefix {prefix}, skipping')
            continue

        container_bytes, parent, last_key, _ = nav
        if not isinstance(container_bytes, bytes):
            logging.debug(f'Container at {prefix} is not bytes, skipping')
            continue

        for type_name, sub_paths in type_groups.items():
            try:
                embedded = global_mod[type_name]
                embedded.from_uper(container_bytes)
                inner_dict = embedded.get_val()

                # 递归删除容器内的所有路径
                inner_dict = delete_fields(inner_dict, sub_paths, global_mod=global_mod)

                embedded.set_val(inner_dict)
                container_bytes = embedded.to_uper()

                # 更新父节点中的容器字节
                if isinstance(parent, tuple):
                    # 父是 CHOICE 元组，无法直接修改；需要通过上层处理
                    logging.debug(f'Container parent is tuple at {prefix}, skipping')
                else:
                    parent[last_key] = container_bytes
            except Exception as e:
                logging.debug(f'Cannot process container {type_name} at {prefix}: {e}')

    return simplified_message

    return simplified_message


def simplify_message(packet_fields: dict, target_path: list,
                     optional_paths: list, global_mod=None) -> dict:
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
    simplified = delete_fields(packet_fields, reduced_paths, global_mod=global_mod)

    return simplified
