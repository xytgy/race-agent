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
    embedding_mode = vs.embedding_service.mode

    print(f"Embedding 模式: {embedding_mode}")
    if embedding_mode == "fallback_hash":
        print("警告: 正在使用 fallback hash embedding，检索质量较差！")
        print(f"请确保 BGE 模型已缓存到本地: ~/.cache/huggingface/hub/models--{settings.embedding_model.replace('/', '--')}/")
        print("可运行以下命令下载模型:")
        print(f"  python3 -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('{settings.embedding_model}')\"")
        print()

    try:
        result = vs.rebuild_index()
        print(f"索引重建完成:")
        print(f"  索引文件: {vs.index_path}")
        print(f"  元数据文件: {vs.meta_path}")
        print(f"  索引 chunks 数: {result['indexed_chunks']}")
        print(f"  向量维度: {result['dimension']}")
        print(f"  Embedding 模式: {embedding_mode}")

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
