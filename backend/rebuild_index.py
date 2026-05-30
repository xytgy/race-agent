#!/usr/bin/env python3
"""重建 FAISS 索引脚本。
读取 chunks 目录下所有 JSON 文件，生成向量并写入 FAISS 索引。
优先使用 SentenceTransformer 模型（如 BGE），若不可用则降级为 fallback hash 模式。
"""
import sys
from pathlib import Path

# 确保能导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.service.vector_service import VectorService
from app.utils.logger import setup_logging
from app.config.settings import settings


def main() -> None:
    setup_logging(settings.log_dir)

    vs = VectorService()

    try:
        result = vs.rebuild_index()
        embedding_mode = vs.embedding_service.mode
        print(f"索引重建完成:")
        print(f"  索引文件: {vs.index_path}")
        print(f"  元数据文件: {vs.meta_path}")
        print(f"  索引 chunks 数: {result['indexed_chunks']}")
        print(f"  向量维度: {result['dimension']}")
        print(f"  Embedding 模式: {embedding_mode}")
        if embedding_mode == "fallback_hash":
            print("提示: 正在使用内置中文 hash embedding。若需要更高质量检索，可配置远程 embedding 或安装本地模型。")
            print("  pip install -r backend/requirements-embedding.txt")

        # 验证
        import json
        meta = json.loads(vs.meta_path.read_text(encoding="utf-8"))
        source_files = set(m.get("source_file") for m in meta)
        print(f"  涉及文件: {source_files}")

    except Exception as exc:
        print(f"索引重建失败: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
