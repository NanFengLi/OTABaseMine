"""
SQLite-backed prefix tree (trie) for path deduplication with resume support.

将 RRC 路径以前缀树形式存储在 SQLite 数据库中，支持：
- 高效的路径插入 / 查重（内存缓存 + SQLite 持久化）
- 进程中断后断点续传（generation_state 表）
"""

import json
import sqlite3
from typing import Dict, Optional, Set, Tuple


class PathTrieDB:
    """
    SQLite 持久化前缀树。

    表结构：
        trie_node(id, parent_id, component, is_leaf)
        generation_state(key, value)

    内部维护 (parent_id, component) -> node_id 的内存缓存，
    运行期间 insert / contains 全部走缓存，仅写入时落盘。
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS trie_node (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id  INTEGER,
        component  TEXT NOT NULL,
        is_leaf    INTEGER DEFAULT 0,
        UNIQUE(parent_id, component)
    );
    CREATE INDEX IF NOT EXISTS idx_trie_parent ON trie_node(parent_id);

    CREATE TABLE IF NOT EXISTS generation_state (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

        # (parent_id, component) -> node_id   ;  parent_id=None 代表根的直接子节点
        self._cache: Dict[Tuple[Optional[int], str], int] = {}
        # node_id -> is_leaf
        self._leaf: Dict[int, bool] = {}
        self._leaf_count: int = 0

        self._load_cache()

    # ------------------------------------------------------------------
    # 缓存加载
    # ------------------------------------------------------------------

    def _load_cache(self) -> None:
        """从 DB 全量加载到内存缓存。"""
        cur = self._conn.execute("SELECT id, parent_id, component, is_leaf FROM trie_node")
        self._leaf_count = 0
        for row in cur:
            nid, pid, comp, leaf = row
            self._cache[(pid, comp)] = nid
            self._leaf[nid] = bool(leaf)
            if leaf:
                self._leaf_count += 1

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def insert(self, path: tuple) -> bool:
        """
        插入一条路径。

        Returns:
            True  — 新插入（之前不存在）
            False — 已存在，未做修改
        """
        parent_id: Optional[int] = None
        for i, comp in enumerate(path):
            comp = str(comp)
            key = (parent_id, comp)
            if key in self._cache:
                parent_id = self._cache[key]
            else:
                # 写入 DB
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO trie_node(parent_id, component, is_leaf) "
                    "VALUES (?, ?, 0)",
                    (parent_id, comp),
                )
                if cur.lastrowid and cur.rowcount:
                    nid = cur.lastrowid
                else:
                    row = self._conn.execute(
                        "SELECT id FROM trie_node WHERE parent_id IS ? AND component=?",
                        (parent_id, comp),
                    ).fetchone()
                    nid = row[0]
                self._cache[key] = nid
                self._leaf[nid] = False
                parent_id = nid

        # parent_id 现在指向路径最后一个节点
        nid = parent_id
        if self._leaf.get(nid, False):
            return False  # 已存在

        self._conn.execute("UPDATE trie_node SET is_leaf=1 WHERE id=?", (nid,))
        self._conn.commit()
        self._leaf[nid] = True
        self._leaf_count += 1
        return True

    def contains(self, path: tuple) -> bool:
        """检查路径是否已在前缀树中。"""
        parent_id: Optional[int] = None
        for comp in path:
            comp = str(comp)
            key = (parent_id, comp)
            if key not in self._cache:
                return False
            parent_id = self._cache[key]
        return self._leaf.get(parent_id, False)

    def count(self) -> int:
        """返回已存储的完整路径（叶子）数量。"""
        return self._leaf_count

    def all_paths(self) -> Set[tuple]:
        """
        重建并返回所有已存储路径的集合。

        通过从每个 is_leaf=1 的节点回溯到根来重建路径。
        """
        # 建立 id -> (parent_id, component) 映射
        id_to_info: Dict[int, Tuple[Optional[int], str]] = {}
        for (pid, comp), nid in self._cache.items():
            id_to_info[nid] = (pid, comp)

        paths: Set[tuple] = set()
        for nid, is_leaf in self._leaf.items():
            if not is_leaf:
                continue
            parts = []
            cur = nid
            while cur is not None:
                info = id_to_info.get(cur)
                if info is None:
                    break
                parts.append(info[1])
                cur = info[0]
            paths.add(tuple(reversed(parts)))
        return paths

    # ------------------------------------------------------------------
    # 生成状态持久化
    # ------------------------------------------------------------------

    def save_state(self, key: str, value) -> None:
        """保存单个状态键值对。"""
        self._conn.execute(
            "INSERT OR REPLACE INTO generation_state(key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self._conn.commit()

    def save_states(self, mapping: dict) -> None:
        """批量保存状态键值对。"""
        for k, v in mapping.items():
            self._conn.execute(
                "INSERT OR REPLACE INTO generation_state(key, value) VALUES (?, ?)",
                (k, json.dumps(v, ensure_ascii=False)),
            )
        self._conn.commit()

    def load_state(self) -> dict:
        """加载所有状态键值对。"""
        cur = self._conn.execute("SELECT key, value FROM generation_state")
        return {row[0]: json.loads(row[1]) for row in cur}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """强制提交当前事务。"""
        self._conn.commit()

    def close(self) -> None:
        """提交并关闭连接。"""
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
