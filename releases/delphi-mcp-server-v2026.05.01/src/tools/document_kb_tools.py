"""
文档知识库辅助函数
用于 delphi_kb 工具的文档操作
"""

from typing import Any
from mcp.types import CallToolResult
from pathlib import Path

from ..services.knowledge_base.scan_generic_documents import (
    GenericDocumentScanner,
    WebDocumentProcessor
)


_doc_scanner = None


def _get_scanner() -> GenericDocumentScanner:
    """获取文档扫描器实例"""
    global _doc_scanner
    
    if _doc_scanner is None:
        server_root = Path(__file__).parent.parent.parent
        kb_dir = str(server_root / "data" / "document-knowledge-base")
        
        kb_path = Path(kb_dir)
        kb_path.mkdir(parents=True, exist_ok=True)
        
        _doc_scanner = GenericDocumentScanner(kb_dir)
    
    return _doc_scanner


async def scan_documents(arguments: Any) -> CallToolResult:
    """扫描目录中的文档"""
    directory = arguments.get("directory")
    extensions = arguments.get("extensions")
    max_workers = arguments.get("max_workers")
    
    if not directory:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供 directory 参数"}],
            isError=True
        )
    
    dir_path = Path(directory)
    if not dir_path.exists():
        return CallToolResult(
            content=[{"type": "text", "text": f"目录不存在: {directory}"}],
            isError=True
        )
    
    scanner = _get_scanner()
    result = scanner.scan_directory(
        directory=directory,
        extensions=extensions,
        max_workers=max_workers
    )
    
    if 'error' in result:
        return CallToolResult(
            content=[{"type": "text", "text": f"扫描失败: {result['error']}"}],
            isError=True
        )
    
    output = f"文档扫描完成:\n"
    output += f"  总文件数: {result['total_files']}\n"
    output += f"  处理成功: {result['processed']}\n"
    output += f"  处理失败: {result['failed']}\n"
    
    stats = scanner.get_statistics()
    if stats.get('by_type'):
        output += f"\n按类型统计:\n"
        for content_type, count in stats['by_type'].items():
            output += f"  {content_type}: {count}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def add_web_document(arguments: Any) -> CallToolResult:
    """添加网页文档"""
    url = arguments.get("url")
    
    if not url:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供 url 参数"}],
            isError=True
        )
    
    if not url.startswith(('http://', 'https://')):
        return CallToolResult(
            content=[{"type": "text", "text": "URL 必须以 http:// 或 https:// 开头"}],
            isError=True
        )
    
    scanner = _get_scanner()
    result = scanner.add_web_document(url)
    
    if result is None:
        return CallToolResult(
            content=[{"type": "text", "text": f"添加网页失败: {url}"}],
            isError=True
        )
    
    if isinstance(result, dict) and 'error' in result:
        return CallToolResult(
            content=[{"type": "text", "text": f"添加网页失败: {result['error']}"}],
            isError=True
        )
    
    output = f"网页添加成功:\n"
    output += f"  标题: {result.get('title', 'N/A')}\n"
    output += f"  URL: {url}\n"
    output += f"  大小: {result.get('size', 0)} 字节\n"
    output += f"  行数: {result.get('line_count', 0)}\n"
    output += f"  章节数: {len(result.get('sections', []))}\n"
    output += f"  代码块数: {len(result.get('code_examples', []))}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def search_documents(arguments: Any) -> CallToolResult:
    """搜索文档"""
    query = arguments.get("query")
    content_type = arguments.get("content_type")
    top_k = arguments.get("top_k", 10)
    
    if not query:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供 query 参数"}],
            isError=True
        )
    
    scanner = _get_scanner()
    results = scanner.search(query, content_type=content_type, top_k=top_k)
    
    if not results:
        msg = f"未找到匹配 '{query}' 的文档"
        
        import re
        if re.search(r'[\u4e00-\u9fff]', query):
            # 中文查询，检查文档库语言
            stats = scanner.get_statistics()
            languages = stats.get('by_language', {})
            total = stats.get('total_documents', 0)
            
            # 构建语言提示
            lang_hints = []
            if languages.get('en', 0) > 0:
                pct = languages['en'] / total * 100
                lang_hints.append(f"英文({pct:.0f}%)")
            if languages.get('ja', 0) > 0:
                pct = languages['ja'] / total * 100
                lang_hints.append(f"日文({pct:.0f}%)")
            if languages.get('ko', 0) > 0:
                pct = languages['ko'] / total * 100
                lang_hints.append(f"韩文({pct:.0f}%)")
            
            if lang_hints:
                msg += f"\n\n💡 文档库包含: {', '.join(lang_hints)}"
                msg += "\n   AI可自动翻译关键词后重试，例如："
                msg += "\n   - '创建表' → 'CREATE TABLE'"
                msg += "\n   - '索引语法' → 'CREATE INDEX'"
        
        return CallToolResult(content=[{"type": "text", "text": msg}])
    
    output = f"搜索 '{query}'"
    if content_type:
        output += f" (类型: {content_type})"
    output += f" - 找到 {len(results)} 个结果:\n\n"
    
    for i, doc in enumerate(results, 1):
        doc_id = doc.get('id')
        output += f"{i}. [ID:{doc_id}] {doc.get('title', 'N/A')}\n"
        output += f"   类型: {doc.get('content_type', 'N/A')}\n"
        
        if doc.get('url'):
            output += f"   URL: {doc.get('url')}\n"
        else:
            output += f"   路径: {doc.get('path', 'N/A')}\n"
        
        output += f"   大小: {doc.get('size', 0)} 字节\n"
        
        content = doc.get('content', '')
        if content:
            preview = content[:200].replace('\n', ' ')
            output += f"   预览: {preview}...\n"
        
        output += "\n"
    
    output += f"提示: 使用 delphi_kb(action=read, doc_id={results[0].get('id')}) 读取完整内容\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def get_document_statistics(arguments: Any) -> CallToolResult:
    """获取文档统计信息"""
    scanner = _get_scanner()
    stats = scanner.get_statistics()
    
    output = "文档知识库统计:\n"
    output += f"  总文档数: {stats.get('total_documents', 0)}\n\n"
    
    by_type = stats.get('by_type', {})
    if by_type:
        output += "按类型统计:\n"
        for content_type, count in by_type.items():
            output += f"  {content_type}: {count}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def read_document(arguments: Any) -> CallToolResult:
    """读取文档内容"""
    import sqlite3
    
    url = arguments.get("url")
    doc_id = arguments.get("doc_id")
    offset = arguments.get("offset", 0)
    limit = arguments.get("limit", 5000)
    
    if not url and not doc_id:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供 url 或 doc_id 参数"}],
            isError=True
        )
    
    scanner = _get_scanner()
    db_path = scanner.db_path
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if doc_id:
            cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        else:
            cursor.execute("SELECT * FROM documents WHERE url = ?", (url,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return CallToolResult(
                content=[{"type": "text", "text": f"未找到文档: {url or doc_id}"}],
                isError=True
            )
        
        doc = dict(row)
        content = doc.get('content', '')
        content_len = len(content)
        
        if offset < 0:
            offset = 0
        if limit > 20000:
            limit = 20000
        
        content_slice = content[offset:offset + limit]
        
        output = f"文档: {doc.get('title', 'N/A')}\n"
        output += f"类型: {doc.get('content_type', 'N/A')}\n"
        if doc.get('url'):
            output += f"URL: {doc.get('url')}\n"
        output += f"大小: {doc.get('size', 0)} 字节\n"
        output += f"内容长度: {content_len} 字符\n"
        output += f"显示范围: {offset} - {offset + len(content_slice)}\n"
        output += "=" * 60 + "\n\n"
        output += content_slice
        
        if offset + limit < content_len:
            remaining = content_len - (offset + limit)
            output += f"\n... (还有 {remaining} 字符未显示) ...\n"
            output += f"提示: 使用 offset={offset + limit} 继续读取\n"
        
        return CallToolResult(content=[{"type": "text", "text": output}])
        
    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"读取文档失败: {str(e)}"}],
            isError=True
        )
