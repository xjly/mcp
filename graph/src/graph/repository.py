"""Neo4j Graph Repository - 图数据库访问层

提供 Neo4j 图数据库的只读查询接口
"""

import os
from contextlib import contextmanager
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

# 加载 .env 配置
load_dotenv()


class Neo4jGraphRepository:
    """Neo4j 图数据库只读访问接口"""

    def __init__(self):
        self._uri = os.getenv("NEO4J_URI")
        self._username = os.getenv("NEO4J_USERNAME")
        self._password = os.getenv("NEO4J_PASSWORD")
        self._driver = None

        if not all([self._uri, self._username, self._password]):
            raise ValueError(
                "Neo4j configuration missing. Please set NEO4J_URI, NEO4J_USERNAME, "
                "and NEO4J_PASSWORD in .env file"
            )

    def _get_driver(self):
        """获取或创建 Neo4j 驱动实例（懒加载）"""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._username, self._password)
            )
        return self._driver

    def close(self):
        """关闭驱动连接"""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @contextmanager
    def _session(self):
        """上下文管理器：自动管理会话"""
        driver = self._get_driver()
        session = driver.session()
        try:
            yield session
        finally:
            session.close()

    def execute_cypher(
        self,
        query: str,
        params: dict | None = None,
        timeout: int = 30
    ) -> list[dict[str, Any]]:
        """
        执行只读 Cypher 查询

        Args:
            query: Cypher 查询语句
            params: 查询参数
            timeout: 超时时间（秒）

        Returns:
            查询结果列表
        """
        params = params or {}
        with self._session() as session:
            result = session.run(query, params, timeout=timeout)
            return [dict(record) for record in result]

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
        query = f"""
        MATCH (n:{label})
        WITH keys(n) as keys
        UNWIND keys as key
        RETURN key, count(*) as count
        ORDER BY count DESC
        LIMIT 50
        """
        results = self.execute_cypher(query)
        return [r["key"] for r in results]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()