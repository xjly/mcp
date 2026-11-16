"""Neo4j Graph Repository - 图数据库访问层

提供 Neo4j 图数据库的只读查询接口
"""

import os
from contextlib import contextmanager
from threading import Lock
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase, READ_ACCESS

# 加载 .env 配置
load_dotenv()


class Neo4jGraphRepository:
    """Neo4j 图数据库只读访问接口"""

    def __init__(self):
        self._uri = os.getenv("NEO4J_URI")
        self._username = os.getenv("NEO4J_USERNAME")
        self._password = os.getenv("NEO4J_PASSWORD")
        self._driver = None
        self._driver_lock = Lock()

        if not all([self._uri, self._username, self._password]):
            raise ValueError(
                "Neo4j configuration missing. Please set NEO4J_URI, NEO4J_USERNAME, "
                "and NEO4J_PASSWORD in .env file"
            )

    def _get_driver(self):
        """获取或创建 Neo4j 驱动实例（懒加载）"""
        with self._driver_lock:
            if self._driver is None:
                self._driver = GraphDatabase.driver(
                    self._uri,
                    auth=(self._username, self._password),
                    connection_timeout=5,
                    connection_acquisition_timeout=5,
                )
            return self._driver

    def close(self):
        """关闭驱动连接"""
        with self._driver_lock:
            if self._driver is not None:
                self._driver.close()
                self._driver = None

    @contextmanager
    def _session(self):
        """上下文管理器：自动管理会话"""
        driver = self._get_driver()
        session = driver.session(default_access_mode=READ_ACCESS, fetch_size=100)
        try:
            yield session
        finally:
            session.close()

    def execute_cypher(
        self,
        query: str,
        params: dict | None = None,
        timeout: int = 30,
        *,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        执行只读 Cypher 查询

        Args:
            query: Cypher 查询语句
            params: 查询参数
            timeout: 超时时间（秒）
            limit: 最多读取的结果行数

        Returns:
            查询结果列表
        """
        if not 1 <= limit <= 500 or not 0 < timeout <= 120:
            raise ValueError("Neo4j 查询的超时或结果行数超出范围")
        with (
            self._session() as session,
            session.begin_transaction(timeout=timeout) as transaction,
        ):
            result = transaction.run(query, params or {})
            return [dict(record) for record in result.fetch(limit)]

    def get_all_labels(self) -> list[str]:
        """获取所有节点标签"""
        query = "CALL db.labels() YIELD label RETURN label ORDER BY label"
        results = self.execute_cypher(query)
        return [r["label"] for r in results]

    def get_all_relationship_types(self) -> list[str]:
        """获取所有关系类型"""
        query = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
        results = self.execute_cypher(query)
        return [r["relationshipType"] for r in results]

    def get_node_property_keys(self, label: str) -> list[str]:
        """获取指定标签的节点所有属性键"""
        counts = self.get_node_property_counts([label], limit=50)
        return [row["key"] for row in counts.get(label, [])]

    def get_node_property_counts(
        self, labels: list[str], limit: int = 20
    ) -> dict[str, list[dict[str, Any]]]:
        """一次扫描统计各标签最常见的属性。"""
        if not labels:
            return {}
        query = """
        MATCH (n)
        UNWIND labels(n) AS label
        WITH n, label
        WHERE label IN $labels
        UNWIND keys(n) AS key
        WITH label, key, count(*) AS count
        ORDER BY label, count DESC, key
        RETURN label, collect({key: key, count: count})[..$limit] AS properties
        """
        rows = self.execute_cypher(
            query, {"labels": labels, "limit": limit}, limit=len(labels)
        )
        return {row["label"]: row["properties"] for row in rows}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
