#!/usr/bin/env python3
"""Test Neo4j connectivity without writing any data.

Usage:
  python scripts/check_neo4j_connection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.common.neo4j_client import check_connection, neo4j_config


def main():
    uri, user, password, database = neo4j_config()

    print("Neo4j 连接测试")
    print("=" * 50)
    print(f"  URI:       {uri}")
    print(f"  User:      {user}")
    print(f"  Database:  {database}")
    print(f"  Password:  {'*' * len(password)} (length={len(password)})")
    print()

    result = check_connection(database)

    if result["ok"]:
        print("✅ 连接成功")
        print(f"   URI:       {result.get('uri', uri)}")
        print(f"   Database:  {result.get('database', database)}")
    else:
        print("❌ 连接失败")
        print(f"   {result['error']}")
        print()
        print("故障排查：")
        print("  1. 确认 Neo4j Desktop 已启动且数据库正在运行")
        print("  2. 检查 .env 中 NEO4J_URI 是否正确")
        print("  3. 检查 .env 中 NEO4J_PASSWORD 是否与 Neo4j Desktop 中设置的一致")
        print("  4. 密码中如有特殊字符（如 @ # $ %），请直接写，不要加引号")
        print("     正确: NEO4J_PASSWORD=GeoriskLab@2026")
        print("     错误: NEO4J_PASSWORD='GeoriskLab@2026'")
        print("     错误: NEO4J_PASSWORD=\"GeoriskLab@2026\"")
        sys.exit(1)


if __name__ == "__main__":
    main()
