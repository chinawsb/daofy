"""
Embedding 服务 —— 为知识库提供真语义搜索

使用 intfloat/multilingual-e5-small 模型：
- 中英双语支持
- 本地 CPU 运行，无 API 依赖
- 自动降级：模型未安装/加载失败时返回 None，调用方走兜底

模型约 70MB，首次加载约 1-2s，后续 <100ms
"""

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# 全局单例
_model = None
_model_name = "intfloat/multilingual-e5-small"


def is_available() -> bool:
    """检查 embedding 依赖是否可用"""
    try:
        import sentence_transformers  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def load_model():
    """懒加载模型（全局单例）"""
    global _model
    if _model is not None:
        return _model

    from sentence_transformers import SentenceTransformer
    import os

    # 尝试多个镜像源
    # 用户可通过 HF_ENDPOINT 环境变量强制指定
    default_endpoint = os.environ.get("HF_ENDPOINT")
    _endpoints = []
    if default_endpoint:
        _endpoints = [default_endpoint]
    else:
        _endpoints = [
            None,  # huggingface.co（默认）
            "https://hf-mirror.com",
        ]

    for ep in _endpoints:
        try:
            if ep:
                logger.info(f"加载 embedding 模型（镜像: {ep}）: {_model_name}")
                old_endpoint = os.environ.get("HF_ENDPOINT")
                os.environ["HF_ENDPOINT"] = ep
            else:
                logger.info(f"加载 embedding 模型: {_model_name}")

            _model = SentenceTransformer(_model_name)
            logger.info("embedding 模型加载完成")
            return _model
        except Exception as e:
            logger.warning(f"  镜像 {ep or 'default'} 失败: {e}")
            if ep:
                # 恢复原来的端点（如果有的话）
                if old_endpoint:
                    os.environ["HF_ENDPOINT"] = old_endpoint
                else:
                    os.environ.pop("HF_ENDPOINT", None)
            continue

    logger.warning("所有镜像源均无法加载 embedding 模型")
    return None


def encode_texts(texts: List[str], prefix: str = "query") -> Optional["numpy.ndarray"]:
    """
    对文本列表进行编码，返回归一化的 embedding 数组

    Args:
        texts: 文本列表
        prefix: E5 前缀，query 搜索时用 "query"，入库时用 "passage"

    Returns:
        numpy.ndarray shape=(n, 384)，归一化后可直接点积算 cosine
        失败时返回 None
    """
    model = load_model()
    if model is None:
        return None

    try:
        import numpy as np
        prefixed = [f"{prefix}: {t}" for t in texts]
        # normalize_embeddings=True 确保输出已归一化，dot = cosine
        embeddings = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
        return np.array(embeddings, dtype=np.float32)
    except Exception as e:
        logger.warning(f"embedding 编码失败: {e}")
        return None


def encode_single(text: str, prefix: str = "query") -> Optional["numpy.ndarray"]:
    """编码单个文本"""
    result = encode_texts([text], prefix=prefix)
    if result is not None:
        return result[0]
    return None


def cosine_similarity(query_emb: "numpy.ndarray", db_embs: "numpy.ndarray") -> "numpy.ndarray":
    """
    计算 query 与一批向量的余弦相似度

    Args:
        query_emb: (dim,) 归一化 query 向量
        db_embs: (n, dim) 归一化向量矩阵

    Returns:
        (n,) 相似度分数
    """
    import numpy as np
    # 已归一化 → dot = cosine
    return np.dot(db_embs, query_emb)


def vector_to_blob(vector: "numpy.ndarray") -> bytes:
    """numpy 向量 → SQLite BLOB"""
    import numpy as np
    return np.array(vector, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes) -> Optional["numpy.ndarray"]:
    """SQLite BLOB → numpy 向量"""
    import numpy as np
    try:
        return np.frombuffer(blob, dtype=np.float32)
    except Exception:
        return None


def batch_encode_and_store(cursor, rows, prefix: str = "passage") -> int:
    """
    批量编码 vocabularies 并写入 vector 列

    Args:
        cursor: SQLite cursor
        rows: [(id, name), ...] 待编码的 (vocab_id, name) 列表
        prefix: E5 前缀

    Returns:
        成功编码并写入的数量
    """
    import numpy as np

    if not rows:
        return 0

    names = [r[1] for r in rows]
    embs = encode_texts(names, prefix=prefix)
    if embs is None:
        return 0

    count = 0
    for (vid, _), vec in zip(rows, embs):
        if vec is not None and not np.all(vec == 0):
            blob = vec.tobytes()
            cursor.execute(
                "UPDATE vocabularies SET vector=?, vector_status='ready' WHERE id=?",
                (blob, vid)
            )
            count += 1
    return count
