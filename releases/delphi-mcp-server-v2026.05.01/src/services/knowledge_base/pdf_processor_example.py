#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 处理器示例代码
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


class PDFProcessor:
    """PDF 文档处理器"""
    
    def __init__(self):
        self.supported_extensions = ['.pdf']
        self.has_pdfplumber = self._check_pdfplumber()
        self.has_pymupdf = self._check_pymupdf()
    
    def _check_pdfplumber(self) -> bool:
        try:
            import pdfplumber
            return True
        except ImportError:
            return False
    
    def _check_pymupdf(self) -> bool:
        try:
            import fitz  # PyMuPDF
            return True
        except ImportError:
            return False
    
    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.supported_extensions
    
    def process(self, file_path: Path) -> Optional[Dict]:
        """处理 PDF 文件"""
        
        # 优先使用 PyMuPDF（性能更好）
        if self.has_pymupdf:
            return self._process_with_pymupdf(file_path)
        
        # 备选：使用 pdfplumber
        if self.has_pdfplumber:
            return self._process_with_pdfplumber(file_path)
        
        # 都没有安装
        return {
            'title': file_path.stem,
            'content': f"PDF 处理需要安装: pip install pdfplumber 或 pip install PyMuPDF",
            'content_type': 'pdf',
            'size': 0,
            'line_count': 0,
            'hash': '',
            'sections': [],
            'code_examples': [],
            'requires_dependencies': True
        }
    
    def _process_with_pymupdf(self, file_path: Path) -> Optional[Dict]:
        """使用 PyMuPDF 处理"""
        try:
            import fitz
            
            doc = fitz.open(str(file_path))
            
            # 提取文本
            text_content = []
            sections = []
            
            for page_num, page in enumerate(doc):
                # 提取文本
                text = page.get_text()
                text_content.append(text)
                
                # 提取标题（基于字体大小）
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                # 大字体可能是标题
                                if span["size"] > 14:
                                    title = span["text"].strip()
                                    if title and len(title) < 100:
                                        sections.append({
                                            'level': 1,
                                            'title': title,
                                            'page': page_num + 1
                                        })
            
            full_text = '\n'.join(text_content)
            
            # 提取元数据
            metadata = doc.metadata
            title = metadata.get('title') or file_path.stem
            
            doc.close()
            
            return {
                'title': title,
                'content': full_text,
                'content_type': 'pdf',
                'size': len(full_text),
                'line_count': full_text.count('\n') + 1,
                'hash': self._compute_hash(full_text),
                'sections': sections[:50],  # 限制章节数
                'code_examples': [],
                'metadata': {
                    'author': metadata.get('author'),
                    'subject': metadata.get('subject'),
                    'keywords': metadata.get('keywords'),
                    'creator': metadata.get('creator'),
                    'producer': metadata.get('producer'),
                    'page_count': len(text_content)
                }
            }
        except Exception as e:
            return None
    
    def _process_with_pdfplumber(self, file_path: Path) -> Optional[Dict]:
        """使用 pdfplumber 处理"""
        try:
            import pdfplumber
            
            text_content = []
            sections = []
            
            with pdfplumber.open(str(file_path)) as pdf:
                # 提取元数据
                metadata = pdf.metadata or {}
                title = metadata.get('Title') or file_path.stem
                
                for page_num, page in enumerate(pdf.pages):
                    # 提取文本
                    text = page.extract_text()
                    if text:
                        text_content.append(text)
                    
                    # 尝试提取标题（基于字体大小）
                    chars = page.chars
                    if chars:
                        # 找出最大字体
                        font_sizes = [c['size'] for c in chars]
                        if font_sizes:
                            max_size = max(font_sizes)
                            # 提取大字体文本作为标题
                            for char in chars:
                                if char['size'] >= max_size * 0.9:
                                    # 简化处理：只提取前几个大字体文本
                                    pass
                
                full_text = '\n'.join(text_content)
                
                return {
                    'title': title,
                    'content': full_text,
                    'content_type': 'pdf',
                    'size': len(full_text),
                    'line_count': full_text.count('\n') + 1,
                    'hash': self._compute_hash(full_text),
                    'sections': sections[:50],
                    'code_examples': [],
                    'metadata': {
                        'author': metadata.get('Author'),
                        'subject': metadata.get('Subject'),
                        'keywords': metadata.get('Keywords'),
                        'creator': metadata.get('Creator'),
                        'producer': metadata.get('Producer'),
                        'page_count': len(pdf.pages)
                    }
                }
        except Exception as e:
            return None
    
    def _compute_hash(self, content: str) -> str:
        import hashlib
        return hashlib.md5(content.encode()).hexdigest()


# 使用示例
if __name__ == "__main__":
    processor = PDFProcessor()
    
    print("PDF 处理器状态:")
    print(f"  pdfplumber: {'✓ 已安装' if processor.has_pdfplumber else '✗ 未安装'}")
    print(f"  PyMuPDF:    {'✓ 已安装' if processor.has_pymupdf else '✗ 未安装'}")
    
    if not processor.has_pdfplumber and not processor.has_pymupdf:
        print("\n安装建议:")
        print("  pip install pdfplumber     # 推荐，纯 Python")
        print("  pip install PyMuPDF        # 高性能，C 扩展")
