"""
Delphi 帮助文档知识库服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

从 Delphi CHM 帮助文件中提取内容并构建知识库
支持分步骤操作：解压 -> 扫描 -> 构建索引
"""

import os
import re
import json
import time
import shutil
import hashlib
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Set
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
from bs4 import BeautifulSoup

from .sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase
from ...utils.logger import get_logger

logger = get_logger(__name__)


# 全局处理函数（用于多进程，必须是模块级函数才能被pickle）
def _process_html_file_worker(args: Tuple) -> Optional[Dict]:
    """
    处理单个 HTML 文件的worker函数（用于多进程）

    Args:
        args: (html_file_path, directory_path, save_markdown, markdown_dir_path)

    Returns:
        文档字典或None
    """
    html_file_path, directory_path, save_markdown, markdown_dir_path = args

    try:
        html_file = Path(html_file_path)
        directory = Path(directory_path)
        markdown_dir = Path(markdown_dir_path) if markdown_dir_path else None

        with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()

        # 创建提取器（每个进程独立创建）
        extractor = HTMLContentExtractor()

        # 提取内容
        extracted = extractor.extract_content(html_content, str(html_file))

        if not extracted['content'] or len(extracted['content']) <= 50:
            return None

        # 转换为 Markdown（如果需要）
        markdown_content = None
        if save_markdown:
            md_converter = HTMLToMarkdownConverter()
            markdown_content = md_converter.convert(html_content)

        # 保存 Markdown 文件
        markdown_file_path = None
        if markdown_content and markdown_dir:
            try:
                rel_path = html_file.relative_to(directory)
                md_file = markdown_dir / rel_path.with_suffix('.md')
                md_file.parent.mkdir(parents=True, exist_ok=True)

                with open(md_file, 'w', encoding='utf-8') as md_f:
                    md_f.write(markdown_content)

                markdown_file_path = str(md_file)
            except Exception:
                pass

        return {
            'path': str(html_file.relative_to(directory)),
            'full_path': str(html_file),
            'title': extracted['title'],
            'content': markdown_content if markdown_content else extracted['content'],
            'html_content': extracted['content'],
            'size': len(extracted['content']),
            'hash': hashlib.md5(extracted['content'].encode()).hexdigest(),
            'classes': extracted['classes'],
            'functions': extracted['functions'],
            'properties': extracted.get('properties', []),
            'events': extracted.get('events', []),
            'interfaces': extracted.get('interfaces', []),
            'types': extracted.get('types', []),
            'uses': extracted.get('uses', []),
            'code_examples': extracted.get('code_examples', []),
            'markdown_path': markdown_file_path
        }

    except Exception:
        return None


class HTMLToMarkdownConverter:
    """HTML 转 Markdown 转换器"""

    def __init__(self):
        # 延迟导入 html2text，避免 MCP 服务器启动时导入失败
        import html2text
        self.converter = html2text.HTML2Text()
        self.converter.ignore_links = False
        self.converter.ignore_images = True
        self.converter.ignore_tables = False
        self.converter.body_width = 0  # 不自动换行
        self.converter.wrap_links = False
        self.converter.wrap_list_items = False
        self.converter.single_line_break = True

        # 优化: 尝试使用更快的lxml解析器
        self.parser = self._get_fast_parser()

    def _get_fast_parser(self) -> str:
        """获取最快的HTML解析器"""
        try:
            import lxml
            return 'lxml'  # lxml比html.parser快3-5倍
        except ImportError:
            logger.info("lxml未安装,使用html.parser (建议安装lxml以提升性能: pip install lxml)")
            return 'html.parser'

    def convert(self, html_content: str) -> str:
        """将 HTML 转换为 Markdown"""
        try:
            # 先使用 BeautifulSoup 清理 HTML (使用更快的解析器)
            soup = BeautifulSoup(html_content, self.parser)

            # 移除脚本和样式
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()

            # 移除 Delphi/C++ 切换相关的元素
            for element in soup.find_all(id=['toggles', 'displayPrefs', 'displayPrefTab']):
                element.decompose()

            # 移除通知横幅
            for element in soup.find_all(id='siteNotice'):
                element.decompose()

            # 获取清理后的 HTML
            cleaned_html = str(soup)

            # 转换为 Markdown
            markdown = self.converter.handle(cleaned_html)

            # 清理 Markdown
            markdown = self._clean_markdown(markdown)

            return markdown

        except Exception as e:
            logger.warning(f"HTML 转 Markdown 失败: {e}")
            return self._extract_text_fallback(html_content)

    def _clean_markdown(self, markdown: str) -> str:
        """清理 Markdown 文本"""
        # 移除多余的空行
        markdown = re.sub(r'\n{4,}', '\n\n\n', markdown)

        # 移除 HTML 注释
        markdown = re.sub(r'<!--.*?-->', '', markdown, flags=re.DOTALL)

        # 清理链接中的 HTML 实体
        markdown = markdown.replace('&amp;', '&')
        markdown = markdown.replace('&lt;', '<')
        markdown = markdown.replace('&gt;', '>')

        # 移除横幅文本
        lines = markdown.split('\n')
        cleaned_lines = []
        skip_patterns = [
            r'13\.\d+ release available',
            r'Learn More!',
            r'Show:\s*Delphi\s*C\+\+',
            r'Display Preferences',
            r'From RAD Studio API Documentation',
            r'Help Feedback',
            r'Copyright \(C\) \d+ Embarcadero',
            r'Current Wiki Page',
        ]

        for line in lines:
            should_skip = False
            for pattern in skip_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    should_skip = True
                    break
            if not should_skip and line.strip():
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def _extract_text_fallback(self, html_content: str) -> str:
        """备用文本提取方法"""
        try:
            soup = BeautifulSoup(html_content, self.parser)
            return soup.get_text(separator='\n', strip=True)
        except:
            return ""


class HTMLContentExtractor:
    """HTML 内容提取器 - 增强版"""

    def __init__(self):
        self.md_converter = HTMLToMarkdownConverter()
        # 使用与HTMLToMarkdownConverter相同的解析器
        self.parser = self.md_converter.parser

    def extract_content(self, html_content: str, file_path: str) -> Dict:
        """
        从 HTML 中提取完整内容（完整版）

        Args:
            html_content: HTML 内容
            file_path: 文件路径

        Returns:
            包含 title, content(markdown), classes, functions, properties, events, interfaces, types, uses, code_examples 的字典
        """
        # 转换为 Markdown
        markdown_content = self.md_converter.convert(html_content)

        # 提取标题
        title = self._extract_title(html_content, markdown_content)

        # 提取结构化信息
        structured_info = self._extract_structured_info(markdown_content, html_content)

        return {
            'title': title,
            'content': markdown_content,
            'classes': structured_info.get('classes', []),
            'functions': structured_info.get('functions', []),
            'properties': structured_info.get('properties', []),
            'events': structured_info.get('events', []),
            'interfaces': structured_info.get('interfaces', []),
            'types': structured_info.get('types', []),
            'uses': structured_info.get('uses', []),
            'code_examples': structured_info.get('code_examples', [])
        }

    def _extract_title(self, html_content: str, markdown_content: str) -> str:
        """提取文档标题"""
        try:
            soup = BeautifulSoup(html_content, self.parser)
            if soup.title:
                return soup.title.get_text(strip=True)
            if soup.h1:
                return soup.h1.get_text(strip=True)
        except:
            pass

        # 从 Markdown 提取第一行
        lines = markdown_content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                return line[:100]
            elif line.startswith('#'):
                return line.lstrip('#').strip()[:100]

        return "Untitled"

    def _extract_structured_info(self, markdown: str, html_content: str) -> Dict:
        """从内容提取结构化信息（完整版）"""
        result = {
            'classes': [],
            'functions': [],
            'code_examples': [],
            'properties': [],
            'events': [],
            'interfaces': [],
            'types': [],
            'uses': []
        }

        try:
            soup = BeautifulSoup(html_content, self.parser)

            # 提取 Classes
            classes_header = soup.find(id='Classes') or soup.find(string=re.compile('^Classes$', re.I))
            if classes_header:
                table = classes_header.find_next('table') if hasattr(classes_header, 'find_next') else None
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 1:
                            name_cell = cells[0]
                            link = name_cell.find('a')
                            name = link.get_text(strip=True) if link else name_cell.get_text(strip=True)
                            name = re.sub(r'\s*\([^)]+\)\s*$', '', name)
                            desc = cells[1].get_text(strip=True) if len(cells) >= 2 else ""

                            if name and len(name) > 1:
                                result['classes'].append({
                                    'name': name,
                                    'base_class': '',
                                    'type_kind': 'class',
                                    'line': 0,
                                    'description': desc
                                })

            # 提取 Interfaces
            interfaces_header = soup.find(id='Interfaces') or soup.find(string=re.compile('^Interfaces$', re.I))
            if interfaces_header:
                table = interfaces_header.find_next('table') if hasattr(interfaces_header, 'find_next') else None
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 1:
                            name_cell = cells[0]
                            link = name_cell.find('a')
                            name = link.get_text(strip=True) if link else name_cell.get_text(strip=True)
                            name = re.sub(r'\s*\([^)]+\)\s*$', '', name)
                            desc = cells[1].get_text(strip=True) if len(cells) >= 2 else ""

                            if name and len(name) > 1:
                                result['interfaces'].append({
                                    'name': name,
                                    'type_kind': 'interface',
                                    'line': 0,
                                    'description': desc
                                })

            # 提取 Types
            types_header = soup.find(id='Types') or soup.find(string=re.compile('^Types$', re.I))
            if types_header:
                table = types_header.find_next('table') if hasattr(types_header, 'find_next') else None
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 1:
                            name = cells[0].get_text(strip=True)
                            desc = cells[1].get_text(strip=True) if len(cells) >= 2 else ""
                            type_def = cells[2].get_text(strip=True) if len(cells) >= 3 else ""

                            if name and len(name) > 1:
                                result['types'].append({
                                    'name': name,
                                    'type_kind': 'type',
                                    'line': 0,
                                    'description': desc,
                                    'definition': type_def
                                })

            # 提取 Methods（增强版，包含参数和返回值）
            methods_header = soup.find(id='Methods') or soup.find(string=re.compile('^Methods$', re.I))
            if methods_header:
                table = methods_header.find_next('table') if hasattr(methods_header, 'find_next') else None
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 1:
                            name = cells[0].get_text(strip=True)
                            desc = cells[1].get_text(strip=True) if len(cells) >= 2 else ""
                            if name and len(name) > 1:
                                # 尝试提取方法签名（从描述或链接）
                                signature = self._extract_method_signature(soup, name)

                                result['functions'].append({
                                    'name': name,
                                    'type': 'method',
                                    'line': 0,
                                    'description': desc,
                                    'signature': signature.get('signature', ''),
                                    'parameters': signature.get('parameters', []),
                                    'return_type': signature.get('return_type', '')
                                })

            # 提取 Properties
            properties_header = soup.find(id='Properties') or soup.find(string=re.compile('^Properties$', re.I))
            if properties_header:
                table = properties_header.find_next('table') if hasattr(properties_header, 'find_next') else None
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 1:
                            name = cells[0].get_text(strip=True)
                            desc = cells[1].get_text(strip=True) if len(cells) >= 2 else ""
                            prop_type = cells[2].get_text(strip=True) if len(cells) >= 3 else ""

                            if name and len(name) > 1:
                                result['properties'].append({
                                    'name': name,
                                    'type': 'property',
                                    'line': 0,
                                    'description': desc,
                                    'property_type': prop_type
                                })

            # 提取 Events
            events_header = soup.find(id='Events') or soup.find(string=re.compile('^Events$', re.I))
            if events_header:
                table = events_header.find_next('table') if hasattr(events_header, 'find_next') else None
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 1:
                            name = cells[0].get_text(strip=True)
                            desc = cells[1].get_text(strip=True) if len(cells) >= 2 else ""
                            event_type = cells[2].get_text(strip=True) if len(cells) >= 3 else ""

                            if name and len(name) > 1:
                                result['events'].append({
                                    'name': name,
                                    'type': 'event',
                                    'line': 0,
                                    'description': desc,
                                    'event_type': event_type
                                })

            # 提取 Constants
            constants_header = soup.find(id='Constants') or soup.find(string=re.compile('^Constants$', re.I))
            if constants_header:
                table = constants_header.find_next('table') if hasattr(constants_header, 'find_next') else None
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 1:
                            name = cells[0].get_text(strip=True)
                            definition = cells[1].get_text(strip=True) if len(cells) >= 2 else ""
                            if name and len(name) > 1:
                                result['functions'].append({
                                    'name': name,
                                    'type': 'constant',
                                    'line': 0,
                                    'description': definition,
                                    'value': definition
                                })

            # 提取 Uses（代码示例页面）
            uses_header = soup.find(id='Uses') or soup.find(string=re.compile('^Uses$', re.I))
            if uses_header:
                # Uses 通常在表格或列表中
                uses_table = uses_header.find_next('table') if hasattr(uses_header, 'find_next') else None
                if uses_table:
                    rows = uses_table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 1:
                            unit_name = cells[0].get_text(strip=True)
                            if unit_name and len(unit_name) > 1:
                                result['uses'].append(unit_name)
                else:
                    # 尝试查找列表
                    uses_list = uses_header.find_next(['ul', 'ol']) if hasattr(uses_header, 'find_next') else None
                    if uses_list:
                        for item in uses_list.find_all('li'):
                            unit_name = item.get_text(strip=True)
                            if unit_name and len(unit_name) > 1:
                                result['uses'].append(unit_name)

            # 提取代码示例（优先从 HTML 提取，更可靠）
            code_examples = self._extract_code_examples_from_html(soup)
            if not code_examples:
                # 如果 HTML 中没有，尝试从 Markdown 提取
                code_examples = self._extract_code_examples(markdown)
            result['code_examples'] = code_examples

        except Exception as e:
            logger.warning(f"提取结构化信息失败: {e}")

        return result

    def _extract_method_signature(self, soup: BeautifulSoup, method_name: str) -> Dict:
        """提取方法签名、参数和返回值信息（改进版，支持 Delphi 和 C++ 语法）"""
        result = {
            'signature': '',
            'delphi_signature': '',
            'cpp_signature': '',
            'parameters': [],
            'return_type': ''
        }

        try:
            # 查找方法详细说明区域
            method_anchor = soup.find('a', {'name': method_name}) or \
                           soup.find('a', {'id': method_name}) or \
                           soup.find(string=re.compile(f'^{re.escape(method_name)}$'))

            if method_anchor:
                parent = method_anchor.parent
                if parent:
                    # 查找 Delphi 语法（优先）
                    delphi_header = parent.find_next(string=re.compile('^Delphi$', re.I))
                    if delphi_header:
                        # 查找 Delphi 代码块（通常在 mw-highlight 或 pre 中）
                        delphi_block = delphi_header.find_next(['div', 'pre'], class_=re.compile('mw-highlight|delphi', re.I))
                        if delphi_block:
                            code = delphi_block.get_text(strip=True)
                            result['delphi_signature'] = code
                            result['signature'] = code
                            # 解析参数和返回值
                            result['parameters'] = self._parse_parameters(code)
                            result['return_type'] = self._parse_return_type(code)

                    # 查找 C++ 语法（备选）
                    cpp_header = parent.find_next(string=re.compile(r'^C\+\+$', re.I))
                    if cpp_header:
                        cpp_block = cpp_header.find_next(['div', 'pre'], class_=re.compile('mw-highlight|cpp', re.I))
                        if cpp_block:
                            result['cpp_signature'] = cpp_block.get_text(strip=True)
                            # 如果没有 Delphi 签名，使用 C++ 签名
                            if not result['signature']:
                                result['signature'] = result['cpp_signature']

                    # 备选：查找 codesig div
                    if not result['signature']:
                        codesig = parent.find_next('div', id='codesig') or parent.find_next('div', class_='cpp sig')
                        if codesig:
                            result['signature'] = codesig.get_text(strip=True)

        except Exception as e:
            logger.debug(f"提取方法签名失败 {method_name}: {e}")

        return result

    def _parse_parameters(self, signature: str) -> List[Dict]:
        """从方法签名解析参数"""
        params = []
        try:
            # 匹配 function/procedure 参数
            # 例如: function Create(AOwner: TComponent): TForm;
            param_match = re.search(r'\((.*?)\)', signature)
            if param_match:
                param_str = param_match.group(1)
                # 分割参数（处理逗号分隔）
                for param in param_str.split(';'):
                    param = param.strip()
                    if ':' in param:
                        # 格式: ParamName: Type
                        parts = param.split(':', 1)
                        if len(parts) == 2:
                            param_names = parts[0].strip()
                            param_type = parts[1].strip()
                            
                            # 处理多个参数共享同一类型（如 A, B: Integer）
                            for name in param_names.split(','):
                                params.append({
                                    'name': name.strip(),
                                    'type': param_type,
                                    'description': ''
                                })
        except Exception as e:
            logger.debug(f"解析参数失败: {e}")
        
        return params

    def _parse_return_type(self, signature: str) -> str:
        """从方法签名解析返回值类型"""
        try:
            # 匹配返回值（: Type; 或 ): Type; 结尾）
            return_match = re.search(r'\)\s*:\s*(\w+)', signature)
            if return_match:
                return return_match.group(1)
        except Exception as e:
            logger.debug(f"解析返回值失败: {e}")

        return ''

    def _extract_code_examples_from_html(self, soup: BeautifulSoup) -> List[Dict]:
        """从 HTML 提取代码示例（优先使用，格式更可靠）"""
        examples = []
        try:
            # 查找所有代码高亮块
            code_blocks = soup.find_all('div', class_='mw-highlight')

            for i, block in enumerate(code_blocks, 1):
                # 确定语言
                language = 'delphi'  # 默认 Delphi
                if 'lang-cpp' in str(block.get('class', [])):
                    language = 'cpp'
                elif 'lang-delphi' in str(block.get('class', [])):
                    language = 'delphi'

                # 提取代码
                pre = block.find('pre')
                if pre:
                    code = pre.get_text(strip=True)
                else:
                    code = block.get_text(strip=True)

                if len(code) > 30:  # 过滤太短的代码片段
                    # 提取描述（查找前面的标题或段落）
                    description = self._extract_code_description_from_html(soup, block)

                    examples.append({
                        'id': f'example_{i}',
                        'language': language,
                        'code': code,
                        'description': description
                    })

            # 如果没有找到 mw-highlight，尝试查找 pre 标签
            if not examples:
                pre_blocks = soup.find_all('pre')
                for i, pre in enumerate(pre_blocks, 1):
                    code = pre.get_text(strip=True)
                    if len(code) > 50:
                        examples.append({
                            'id': f'example_{i}',
                            'language': 'delphi',
                            'code': code,
                            'description': ''
                        })

        except Exception as e:
            logger.debug(f"从 HTML 提取代码示例失败: {e}")

        return examples

    def _extract_code_description_from_html(self, soup: BeautifulSoup, code_block) -> str:
        """从 HTML 提取代码示例前的描述"""
        try:
            # 查找代码块前的标题
            prev_heading = code_block.find_previous(['h2', 'h3', 'h4'])
            if prev_heading:
                return prev_heading.get_text(strip=True)

            # 查找代码块前的段落
            prev_p = code_block.find_previous('p')
            if prev_p:
                text = prev_p.get_text(strip=True)
                if len(text) > 10:
                    return text[:150]

        except Exception:
            pass

        return ''

    def _extract_code_examples(self, markdown: str) -> List[Dict]:
        """从 Markdown 提取代码示例"""
        examples = []
        try:
            # 查找代码块（Markdown 格式）
            # 匹配 ```delphi 或 ```pascal 代码块
            code_block_pattern = r'```(?:delphi|pascal)?\n(.*?)```'
            matches = re.finditer(code_block_pattern, markdown, re.DOTALL | re.IGNORECASE)
            
            for i, match in enumerate(matches, 1):
                code = match.group(1).strip()
                if len(code) > 20:  # 过滤太短的代码片段
                    examples.append({
                        'id': f'example_{i}',
                        'language': 'delphi',
                        'code': code,
                        'description': self._extract_example_description(markdown, match.start())
                    })
            
            # 如果没有 Markdown 代码块，尝试查找缩进代码块
            if not examples:
                indented_pattern = r'(?:^|\n)(    [\s\S]*?)(?=\n[^ ]|\Z)'
                matches = re.finditer(indented_pattern, markdown)
                for i, match in enumerate(matches, 1):
                    code = match.group(1).strip()
                    if len(code) > 50:
                        examples.append({
                            'id': f'example_{i}',
                            'language': 'delphi',
                            'code': code,
                            'description': ''
                        })
        
        except Exception as e:
            logger.debug(f"提取代码示例失败: {e}")
        
        return examples

    def _extract_example_description(self, markdown: str, code_start: int) -> str:
        """提取代码示例前的描述文字"""
        try:
            # 获取代码块前的文本
            before_code = markdown[:code_start]
            lines = before_code.strip().split('\n')
            
            # 查找最近的标题或段落
            for line in reversed(lines):
                line = line.strip()
                if line and not line.startswith('```'):
                    if line.startswith('#') or line.startswith('**'):
                        return line.lstrip('#').strip().lstrip('*').strip()
                    elif len(line) > 10:
                        return line[:100]
        except Exception:
            pass
        
        return ''


class DelphiHelpKnowledgeBase:
    """Delphi 帮助文档知识库 - 分步骤构建版"""

    # Delphi 帮助文件列表
    HELP_FILES = {
        'vcl': 'VCL (Visual Component Library) 帮助',
        'fmx': 'FireMonkey (FMX) 帮助',
        'system': 'System 单元帮助',
        'libraries': '运行时库帮助',
        'data': '数据库帮助',
        'codeexamples': '代码示例',
        'topics': '主题帮助',
        'Indy10': 'Indy 网络组件帮助',
        'TeeChart': 'TeeChart 图表帮助',
    }

    def __init__(self, kb_dir: Optional[str] = None):
        """
        初始化帮助文档知识库

        Args:
            kb_dir: 知识库目录路径
        """
        if kb_dir is None:
            server_root = Path(__file__).parent.parent.parent.parent
            kb_dir = server_root / "data" / "help-knowledge-base"

        self.kb_dir = Path(kb_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        self.kb_instance: Optional[SQLiteVectorKnowledgeBase] = None
        self.extractor = HTMLContentExtractor()

        # 7-Zip 路径
        self.sevenzip_path = self._find_7zip()

        # Delphi 帮助目录
        self.delphi_help_dir = self._find_delphi_help_dir()

        logger.info(f"帮助文档知识库初始化: {self.kb_dir}")

    def _should_process_file(self, file_path: Path) -> bool:
        """
        判断文件是否需要处理 (性能优化)
        
        新规则：
        1. 非HTML文件扩展名匹配 .html .htm .xhtml（由调用处处理）
        2. 跳过 .htaccess, robots.txt, sitemap.xml
        3. 跳过 index/toc/nav/menu/footer 开头，扩展名为 .htm/.html/.xhtml 的文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否需要处理
        """
        try:
            # 跳过太小的文件(通常是无用的占位文件)
            if file_path.stat().st_size < 100:
                return False
            
            # 获取文件名和扩展名
            file_name = file_path.name.lower()
            ext = file_path.suffix.lower()
            
            # 非HTML文件扩展名（调用处已处理，这里作为保险）
            if ext not in ['.html', '.htm', '.xhtml']:
                return False
            
            # 跳过系统配置文件
            if file_name in ['.htaccess', 'robots.txt', 'sitemap.xml']:
                return False
            
            # 跳过导航页面：index/toc/nav/menu/footer 开头，扩展名为 .htm/.html/.xhtml
            skip_names = ['index', 'toc', 'nav', 'menu', 'footer']
            name_without_ext = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
            if name_without_ext in skip_names:
                return False
            
            return True
            
        except Exception:
            return True  # 出错时默认处理

    def _calculate_optimal_workers(self) -> int:
        """
        计算最优工作线程数 (根据CPU核心数和可用内存)
        
        Returns:
            最优线程数
        """
        try:
            import os
            import psutil
            
            # 获取CPU核心数
            cpu_count = os.cpu_count() or 4
            
            # 获取可用内存(GB)
            available_memory_gb = psutil.virtual_memory().available / (1024 ** 3)
            
            # 计算基于CPU的线程数 (CPU核心数 * 2,因为HTML解析是IO+CPU混合型)
            cpu_based_workers = cpu_count * 2
            
            # 计算基于内存的线程数 (每GB内存支持2个线程,每个线程约占用500MB)
            memory_based_workers = int(available_memory_gb * 2)
            
            # 取较小值,避免资源耗尽
            optimal_workers = min(cpu_based_workers, memory_based_workers)
            
            # 限制在合理范围内 [4, 32]
            optimal_workers = max(4, min(32, optimal_workers))
            
            logger.info(f"自动计算线程数: CPU核心={cpu_count}, 可用内存={available_memory_gb:.1f}GB, 最优线程数={optimal_workers}")
            
            return optimal_workers
            
        except Exception as e:
            # 如果无法获取系统信息,使用默认值
            logger.warning(f"无法获取系统信息,使用默认线程数16: {e}")
            return 16

    def _calculate_chm_workers(self) -> int:
        """
        计算CHM解压的最优线程数
        
        Returns:
            最优线程数
        """
        try:
            import os
            
            # CHM解压主要是IO密集型,使用CPU核心数即可
            cpu_cores = os.cpu_count() or 4
            
            # 限制: 最小2, 最大cpu_count-1
            optimal_workers = max(2, cpu_cores - 1)
            
            logger.info(f"CHM解压线程数: {optimal_workers}")
            
            return optimal_workers
            
        except Exception:
            return 4  # 默认4线程

    def _find_7zip(self) -> Optional[str]:
        """查找 7-Zip 安装路径"""
        possible_paths = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
        ]
        for path in possible_paths:
            if Path(path).exists():
                return path
        return None

    def _find_delphi_help_dir(self) -> Optional[str]:
        """查找 Delphi 帮助目录"""
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Embarcadero\BDS")

            # 查找所有版本，选择最新的
            versions = []
            i = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, i)
                    versions.append(version_key)
                    i += 1
                except:
                    break

            winreg.CloseKey(key)

            # 按版本号排序，取最新的
            versions.sort(key=lambda x: float(x) if x.replace('.', '').isdigit() else 0, reverse=True)

            for version in versions:
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Embarcadero\BDS")
                    version_path = winreg.OpenKey(key, version)
                    root_dir = winreg.QueryValueEx(version_path, "RootDir")[0]
                    winreg.CloseKey(version_path)
                    winreg.CloseKey(key)

                    help_dir = Path(root_dir) / "Help" / "Doc"
                    if help_dir.exists():
                        logger.info(f"找到 Delphi 帮助目录 (版本 {version}): {help_dir}")
                        return str(help_dir)
                except Exception as e:
                    logger.warning(f"检查版本 {version} 失败: {e}")
                    continue

        except Exception as e:
            logger.warning(f"查找 Delphi 帮助目录失败: {e}")

        # 默认路径
        default_paths = [
            r"C:\Program Files (x86)\Embarcadero\Studio\23.0\Help\Doc",
            r"C:\Program Files (x86)\Embarcadero\Studio\22.0\Help\Doc",
        ]
        for default_path in default_paths:
            if Path(default_path).exists():
                logger.info(f"使用默认帮助目录: {default_path}")
                return default_path

        return None

    # ==================== 步骤1: 解压 CHM 文件 ====================

    def _get_chm_file_list(self, chm_path: str) -> Optional[Set[str]]:
        """
        使用7z列出CHM文件内容
        
        Args:
            chm_path: CHM文件路径
            
        Returns:
            文件列表或None（如果失败）
        """
        if not self.sevenzip_path:
            return None
            
        try:
            result = subprocess.run(
                [self.sevenzip_path, 'l', '-slt', chm_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return None
            
            files = set()
            in_archive = False
            for line in result.stdout.split('\n'):
                if line.strip() == 'Archive:':
                    in_archive = True
                elif in_archive and line.startswith('Path = '):
                    file_path = line[7:].strip()
                    if file_path and not file_path.endswith('/'):
                        files.add(file_path)
                        
            return files
        except Exception:
            return None

    def _check_chm_needs_extraction(self, name: str, chm_path: Path) -> bool:
        """
        检查CHM是否需要重新解压（增量构建核心）
        
        Args:
            name: 帮助文件名称
            chm_path: CHM文件路径
            
        Returns:
            是否需要解压
        """
        extracted_dir = self.kb_dir / "files" / name
        
        # 检查解压目录是否存在
        if not extracted_dir.exists():
            return True
            
        # 检查CHM文件是否存在
        if not chm_path.exists():
            return False
        
        # 获取CHM文件列表
        chm_files = self._get_chm_file_list(str(chm_path))
        if not chm_files:
            # 无法获取CHM列表，假设需要解压
            return True
        
        # 检查解压目录中的文件
        try:
            existing_files = set()
            for f in extracted_dir.rglob('*'):
                if f.is_file():
                    rel = f.relative_to(extracted_dir)
                    existing_files.add(str(rel).replace('\\', '/'))
            
            # 检查是否有文件被删除
            missing_files = chm_files - existing_files
            if missing_files:
                # 有文件缺失，需要重新解压
                if len(missing_files) <= 10:
                    print(f"    发现 {len(missing_files)} 个缺失文件: {list(missing_files)[:5]}...")
                else:
                    print(f"    发现 {len(missing_files)} 个缺失文件...")
                return True
            
            # 检查是否有新增文件（解压目录文件少于CHM文件）
            if len(existing_files) < len(chm_files):
                print(f"    文件数量不足: {len(existing_files)} < {len(chm_files)}")
                return True
            
            # 文件完整，不需要解压
            return False
            
        except Exception as e:
            print(f"    检查解压目录失败: {e}")
            return True  # 出错时假设需要解压

    def extract_chm(self, chm_path: str, output_dir: str, progress_callback: Optional[Callable] = None) -> bool:
        """
        解压 CHM 文件

        Args:
            chm_path: CHM 文件路径
            output_dir: 输出目录
            progress_callback: 进度回调函数(percent, message)

        Returns:
            是否成功
        """
        if not self.sevenzip_path:
            logger.error("未找到 7-Zip，无法解压 CHM 文件")
            return False

        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            if progress_callback:
                progress_callback(0, f"开始解压: {Path(chm_path).name}")

            # 使用 7-Zip 解压
            result = subprocess.run(
                [self.sevenzip_path, 'x', '-y', f'-o{output_dir}', chm_path],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                logger.info(f"成功解压: {chm_path}")
                if progress_callback:
                    progress_callback(100, f"解压完成: {Path(chm_path).name}")
                return True
            else:
                logger.error(f"解压失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"解压 CHM 文件失败: {e}")
            return False

    def extract_all_chm(self, help_names: Optional[List[str]] = None,
                       progress_callback: Optional[Callable] = None,
                       max_workers: Optional[int] = None) -> Dict[str, bool]:
        """
        解压所有 CHM 文件 (并行优化版本)

        Args:
            help_names: 要解压的帮助文件列表，None表示全部
            progress_callback: 进度回调函数(current, total, name, status)
            max_workers: 最大并行解压数,None表示自动计算

        Returns:
            每个帮助文件的解压结果
        """
        if not self.delphi_help_dir:
            logger.error("未找到 Delphi 帮助目录")
            return {}

        # 性能优化: 自动计算最优线程数
        if max_workers is None:
            max_workers = self._calculate_chm_workers()

        results = {}
        extracted_dir = self.kb_dir / "files"  # 使用 files 目录存储解压的HTML

        # 确定要处理的文件
        files_to_process = {}
        for name, desc in self.HELP_FILES.items():
            if help_names is None or name in help_names:
                chm_path = Path(self.delphi_help_dir) / f"{name}.chm"
                if chm_path.exists():
                    # 增量构建: 检查是否需要重新解压
                    if not self._check_chm_needs_extraction(name, chm_path):
                        print(f"跳过 {desc} (无需解压)")
                        results[name] = True
                        continue
                    files_to_process[name] = (chm_path, desc)
                else:
                    logger.warning(f"帮助文件不存在: {chm_path}")
                    results[name] = False

        total = len(files_to_process)
        
        if total == 0:
            print("所有帮助文件都已解压，跳过解压步骤")
            return results
        
        # 并行解压
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_name = {}
            
            for name, (chm_path, desc) in files_to_process.items():
                output_dir = extracted_dir / name
                future = executor.submit(self.extract_chm, str(chm_path), str(output_dir))
                future_to_name[future] = (name, desc)
            
            # 收集结果
            completed = 0
            for future in as_completed(future_to_name):
                completed += 1
                name, desc = future_to_name[future]
                
                try:
                    success = future.result()
                    results[name] = success
                    
                    if progress_callback:
                        status = f"完成 {desc}" if success else f"失败 {desc}"
                        progress_callback(completed, total, name, status)
                        
                except Exception as e:
                    logger.error(f"解压 {name} 失败: {e}")
                    results[name] = False
                    if progress_callback:
                        progress_callback(completed, total, name, f"失败 {desc}")

        return results

    # ==================== 步骤2: 扫描 HTML 文件 ====================

    def _process_single_html(self, html_file: Path, directory: Path, md_converter,
                            markdown_dir: Optional[Path], extractor) -> Optional[Dict]:
        """处理单个 HTML 文件（用于多线程）"""
        try:
            with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()

            # 提取内容
            extracted = extractor.extract_content(html_content, str(html_file))

            if not extracted['content'] or len(extracted['content']) <= 50:
                return None

            # 转换为 Markdown
            markdown_content = None
            if md_converter:
                markdown_content = md_converter.convert(html_content)

            # 保存 Markdown 文件
            markdown_file_path = None
            if markdown_content and markdown_dir:
                try:
                    # 保持相对路径结构
                    rel_path = html_file.relative_to(directory)
                    md_file = markdown_dir / rel_path.with_suffix('.md')
                    md_file.parent.mkdir(parents=True, exist_ok=True)

                    # 写入 Markdown 内容
                    with open(md_file, 'w', encoding='utf-8') as md_f:
                        md_f.write(markdown_content)

                    markdown_file_path = str(md_file)
                except Exception as e:
                    logger.warning(f"保存 Markdown 文件失败 {md_file}: {e}")

            return {
                'path': str(html_file.relative_to(directory)),
                'full_path': str(html_file),
                'title': extracted['title'],
                'content': markdown_content if markdown_content else extracted['content'],
                'html_content': extracted['content'],
                'size': len(extracted['content']),
                'hash': hashlib.md5(extracted['content'].encode()).hexdigest(),
                'classes': extracted['classes'],
                'functions': extracted['functions'],
                'properties': extracted.get('properties', []),
                'events': extracted.get('events', []),
                'interfaces': extracted.get('interfaces', []),
                'types': extracted.get('types', []),
                'uses': extracted.get('uses', []),
                'code_examples': extracted.get('code_examples', []),
                'markdown_path': markdown_file_path
            }

        except Exception as e:
            logger.warning(f"处理文件失败 {html_file}: {e}")
            return None

    def scan_html_files(self, directory: str, max_files: Optional[int] = None,
                       progress_callback: Optional[Callable] = None,
                       save_markdown: bool = False,
                       max_workers: Optional[int] = None) -> List[Dict]:
        """
        Scan HTML files in directory (parallel processing)

        Args:
            directory: Directory path
            max_files: Maximum files to process
            progress_callback: Progress callback function
            save_markdown: Whether to save as Markdown
            max_workers: Number of parallel workers (default: cpu_count//2)

        Returns:
            Document list
        """
        html_files = list(Path(directory).rglob("*.html")) + list(Path(directory).rglob("*.htm")) + list(Path(directory).rglob("*.xhtml"))

        # Filter unnecessary files
        html_files = [f for f in html_files if self._should_process_file(f)]

        if max_files:
            html_files = html_files[:max_files]

        total = len(html_files)
        
        # 计算worker数量
        if max_workers is None:
            max_workers = max(2, cpu_count() - 1)
        
        logger.info(f"Processing {total} HTML files with {max_workers} workers...")

        # Create Markdown save directory
        markdown_dir = None
        if save_markdown:
            base_dir = Path(directory)
            if base_dir.name == 'files':
                markdown_dir = base_dir.parent / 'markdown'
            else:
                markdown_dir = base_dir.parent / 'markdown'
            markdown_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Markdown conversion enabled")

        # 准备参数
        directory_path = Path(directory)
        markdown_dir_str = str(markdown_dir) if markdown_dir else None
        
        # 准备所有文件参数
        args_list = [
            (str(html_file), str(directory_path), save_markdown, markdown_dir_str)
            for html_file in html_files
        ]
        
        # 动态计算chunksize
        chunk_size = max(50, total // (max_workers * 4))
        
        # 并行处理
        documents = []
        processed = 0
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(_process_html_file_worker, args_list, chunksize=chunk_size)
            
            for result in results:
                if result:
                    documents.append(result)
                processed += 1
                
                # Update progress periodically
                if progress_callback and processed % 50 == 0:
                    progress_callback(processed, total, f"Processed {processed}/{total}")

        if progress_callback:
            progress_callback(total, total, "Done")

        logger.info(f"Successfully extracted {len(documents)} documents")
        if save_markdown:
            logger.info(f"Markdown files saved to: {markdown_dir}")
        return documents

    def scan_extracted_directory(self, help_name: str, max_files: Optional[int] = None,
                                 progress_callback: Optional[Callable] = None,
                                 source_dir: Optional[str] = None,
                                 save_markdown: bool = False) -> List[Dict]:
        """
        扫描已解压的目录

        Args:
            help_name: 帮助文件名称（如 'fmx', 'vcl'）
            max_files: 最大处理文件数
            progress_callback: 进度回调函数
            source_dir: 源目录路径，默认使用 self.kb_dir / "files"
            save_markdown: 是否保存为 Markdown 文件（默认False，提升性能）

        Returns:
            文档列表
        """
        if source_dir is None:
            source_path = self.kb_dir / "files" / help_name
        else:
            source_path = Path(source_dir) / help_name

        if not source_path.exists():
            logger.error(f"目录不存在: {source_path}")
            return []

        logger.info(f"扫描目录: {source_path}")
        documents = self.scan_html_files(str(source_path), max_files, progress_callback, save_markdown)

        # 添加来源信息
        for doc in documents:
            doc['source'] = help_name
            doc['source_desc'] = self.HELP_FILES.get(help_name, help_name)

        return documents

    # ==================== 步骤3: 构建向量索引 ====================

    def build_vector_index(self, documents: List[Dict],
                          progress_callback: Optional[Callable] = None) -> bool:
        """
        构建向量索引 - 纯SQLite存储 (统一Schema)

        Args:
            documents: 文档列表
            progress_callback: 进度回调函数(percent, message)

        Returns:
            是否成功
        """
        try:
            if progress_callback:
                progress_callback(0, "准备构建索引...")

            db_file = self.kb_dir / "knowledge.sqlite"
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()

            # 确保表结构存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_path TEXT,
                    relative_path TEXT,
                    extension TEXT,
                    size INTEGER,
                    line_count INTEGER,
                    hash TEXT,
                    last_modified TEXT,
                    category TEXT,
                    units_defined TEXT,
                    units_imported TEXT,
                    description TEXT,
                    scan_timestamp REAL,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vocabularies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    name TEXT,
                    name_lower TEXT,
                    file_id INTEGER,
                    line INTEGER,
                    base_class TEXT,
                    description TEXT,
                    vector BLOB,
                    vector_status TEXT,
                    attributes TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)

            if progress_callback:
                progress_callback(10, "写入文件数据...")

            batch_size = 1000
            current_time = datetime.now().timestamp()

            for i, doc in enumerate(documents):
                if progress_callback and i % 1000 == 0:
                    progress_callback(int(10 + i / len(documents) * 40), f"处理文档 {i}/{len(documents)}")

                content = doc.get('content', '')
                uses_list = doc.get('uses', [])
                if isinstance(uses_list, list):
                    uses_str = ','.join(uses_list)
                else:
                    uses_str = str(uses_list) if uses_list else ''

                cursor.execute("""
                    INSERT INTO files (full_path, relative_path, extension, size, line_count, hash, 
                        last_modified, category, units_defined, units_imported, description, 
                        scan_timestamp, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc['full_path'],
                    doc['path'],
                    '.html',
                    doc['size'],
                    content.count('\n'),
                    doc['hash'],
                    datetime.now().isoformat(),
                    'help',
                    '',
                    uses_str,
                    (doc.get('title', '') + '\n' + content[:500]) if content else doc.get('title', ''),
                    current_time,
                    current_time,
                    current_time
                ))

                file_id = cursor.lastrowid

                # 插入 vocabularies (类)
                for cls in doc.get('classes', []):
                    cursor.execute("""
                        INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, 
                            description, vector, vector_status, attributes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        'class',
                        cls.get('name', ''),
                        cls.get('name', '').lower() if cls.get('name') else '',
                        file_id,
                        cls.get('line', 0),
                        cls.get('base_class', ''),
                        cls.get('description', ''),
                        None, 'pending', None, current_time, current_time
                    ))

                # 插入 vocabularies (函数)
                for func in doc.get('functions', []):
                    cursor.execute("""
                        INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, 
                            description, vector, vector_status, attributes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        'function',
                        func.get('name', ''),
                        func.get('name', '').lower() if func.get('name') else '',
                        file_id,
                        func.get('line', 0),
                        '',
                        func.get('description', ''),
                        None, 'pending', None, current_time, current_time
                    ))

                # 插入 vocabularies (属性)
                for prop in doc.get('properties', []):
                    cursor.execute("""
                        INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, 
                            description, vector, vector_status, attributes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        'property',
                        prop.get('name', ''),
                        prop.get('name', '').lower() if prop.get('name') else '',
                        file_id,
                        prop.get('line', 0),
                        '',
                        prop.get('description', ''),
                        None, 'pending', None, current_time, current_time
                    ))

                # 插入 vocabularies (事件)
                for event in doc.get('events', []):
                    cursor.execute("""
                        INSERT INTO vocabularies (type, name, name_lower, file_id, line, base_class, 
                            description, vector, vector_status, attributes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        'event',
                        event.get('name', ''),
                        event.get('name', '').lower() if event.get('name') else '',
                        file_id,
                        event.get('line', 0),
                        '',
                        event.get('description', ''),
                        None, 'pending', None, current_time, current_time
                    ))

                if (i + 1) % batch_size == 0:
                    conn.commit()

            conn.commit()

            if progress_callback:
                progress_callback(100, "完成")

            logger.info(f"向量索引构建完成: {len(documents)} 个文档")
            return True

        except Exception as e:
            logger.error(f"构建向量索引失败: {e}")
            return False

        except Exception as e:
            logger.error(f"构建向量索引失败: {e}")
            return False

        except Exception as e:
            logger.error(f"构建向量索引失败: {e}")
            return False

    # ==================== 完整构建流程 ====================

    def build_knowledge_base(self, help_names: Optional[List[str]] = None,
                            max_files_per_help: Optional[int] = None,
                            progress_callback: Optional[Callable] = None,
                            save_markdown: bool = False,
                            cleanup_original: bool = False,
                            is_cancelled_check: Optional[Callable[[], bool]] = None) -> bool:
        """
        完整构建帮助文档知识库

        Args:
            help_names: 要构建的帮助文件列表，None表示全部
            max_files_per_help: 每个帮助文件最大处理文档数
            progress_callback: 进度回调函数(stage, current, total, message)
                stage: 'extract', 'scan', 'index', 'cleanup'
            save_markdown: 是否保存为 Markdown 文件（默认False，提升性能）
            cleanup_original: 是否清理原始 HTML 文件（默认False，保留HTML文件）
            is_cancelled_check: 取消检查函数，返回True表示任务已被取消

        Returns:
            是否成功
        """
        def check_cancelled():
            if is_cancelled_check and is_cancelled_check():
                raise KeyboardInterrupt("任务已被用户取消")

        if not self.delphi_help_dir:
            logger.error("未找到 Delphi 帮助目录")
            return False

        # 步骤1: 解压 CHM
        check_cancelled()
        if progress_callback:
            progress_callback('extract', 0, 1, "开始解压 CHM 文件...")

        extract_results = self.extract_all_chm(help_names,
            lambda current, total, name, msg: (check_cancelled(), progress_callback('extract', current, total, msg))[1] if progress_callback else None)

        if not any(extract_results.values()):
            logger.error("没有成功解压任何 CHM 文件")
            return False

        # 步骤2: 扫描 HTML 并转换为 Markdown
        check_cancelled()
        if progress_callback:
            progress_callback('scan', 0, 1, "开始扫描 HTML 文件并转换为 Markdown...")

        all_documents = []
        successful_helps = [name for name, success in extract_results.items() if success]

        for i, help_name in enumerate(successful_helps):
            check_cancelled()
            if progress_callback:
                progress_callback('scan', i, len(successful_helps), f"扫描 {self.HELP_FILES.get(help_name, help_name)}...")

            documents = self.scan_extracted_directory(help_name, max_files_per_help,
                lambda current, total, name: (check_cancelled(), progress_callback('scan', i, len(successful_helps), f"处理 {name}"))[1] if progress_callback else None,
                save_markdown=save_markdown)
            all_documents.extend(documents)

        if not all_documents:
            logger.error("未提取到任何文档")
            return False

        if progress_callback:
            progress_callback('scan', len(successful_helps), len(successful_helps), f"扫描完成，共 {len(all_documents)} 个文档")

        # 步骤3: 构建索引
        check_cancelled()
        if progress_callback:
            progress_callback('index', 0, 100, "开始构建向量索引...")

        success = self.build_vector_index(all_documents,
            lambda percent, msg: (check_cancelled(), progress_callback('index', percent, 100, msg))[1] if progress_callback else None)

        if not success:
            logger.error("构建向量索引失败")
            return False

        # 步骤4: 清理原始 HTML 文件
        check_cancelled()
        if cleanup_original:
            if progress_callback:
                progress_callback('cleanup', 0, 1, "清理原始 HTML 文件...")

            try:
                extracted_dir = self.kb_dir / "files"
                if extracted_dir.exists():
                    logger.info("正在删除原始 HTML 文件...")
                    shutil.rmtree(extracted_dir)
                    logger.info(f"已删除原始 HTML 文件目录: {extracted_dir}")

                if progress_callback:
                    progress_callback('cleanup', 1, 1, "清理完成")
            except Exception as e:
                logger.warning(f"清理原始 HTML 文件失败: {e}")
                if progress_callback:
                    progress_callback('cleanup', 1, 1, "清理失败（已跳过）")

        return success

    def build_knowledge_base_incremental(self, help_names: Optional[List[str]] = None,
                                        max_files_per_help: Optional[int] = None,
                                        progress_callback: Optional[Callable] = None,
                                        source_dir: Optional[str] = None,
                                        save_markdown: bool = False) -> bool:
        """
        增量构建帮助文档知识库（跳过解压，直接扫描已解压的 HTML）

        Args:
            help_names: 要构建的帮助文件列表，None表示全部
            max_files_per_help: 每个帮助文件最大处理文档数
            progress_callback: 进度回调函数
            source_dir: 源目录路径，默认使用 self.kb_dir / "files"
            save_markdown: 是否保存为 Markdown 文件（默认False，提升性能）

        Returns:
            是否成功
        """
        if source_dir is None:
            extracted_dir = self.kb_dir / "files"
        else:
            extracted_dir = Path(source_dir)

        if not extracted_dir.exists():
            logger.error(f"已解压目录不存在: {extracted_dir}")
            return False

        # 确定要处理的文件
        if help_names is None:
            help_names = list(self.HELP_FILES.keys())

        # 扫描 HTML
        if progress_callback:
            progress_callback('scan', 0, len(help_names), "开始扫描 HTML 文件...")

        all_documents = []
        for i, help_name in enumerate(help_names):
            source_path = extracted_dir / help_name
            if not source_path.exists():
                logger.warning(f"目录不存在，跳过: {source_path}")
                continue

            if progress_callback:
                progress_callback('scan', i, len(help_names), f"扫描 {self.HELP_FILES.get(help_name, help_name)}...")

            documents = self.scan_extracted_directory(help_name, max_files_per_help, source_dir=str(extracted_dir), save_markdown=save_markdown)
            all_documents.extend(documents)

        if not all_documents:
            logger.error("未提取到任何文档")
            return False

        if progress_callback:
            progress_callback('scan', len(help_names), len(help_names), f"扫描完成，共 {len(all_documents)} 个文档")

        # 构建索引
        if progress_callback:
            progress_callback('index', 0, 100, "开始构建向量索引...")

        success = self.build_vector_index(all_documents,
            lambda percent, msg: progress_callback('index', percent, 100, msg) if progress_callback else None)

        return success

    # ==================== 查询功能 ====================

    def load_knowledge_base(self) -> bool:
        """加载知识库 - 从SQLite"""
        try:
            if self.kb_instance is None:
                db_file = self.kb_dir / "knowledge.sqlite"
                if not db_file.exists():
                    logger.warning("SQLite数据库不存在")
                    return False
                self.kb_instance = SQLiteVectorKnowledgeBase(str(self.kb_dir))
            return True
        except Exception as e:
            logger.error(f"加载知识库失败: {e}")
            return False

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        搜索帮助文档 - 从SQLite查询 (统一Schema)

        Args:
            query: 搜索查询
            top_k: 返回结果数量

        Returns:
            搜索结果
        """
        results = []
        
        try:
            db_file = self.kb_dir / "knowledge.sqlite"
            if not db_file.exists():
                logger.warning("数据库不存在")
                return results
                
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query_lower = f"%{query.lower()}%"
            
            # 搜索 vocabularies (类/函数/属性/事件)
            cursor.execute("""
                SELECT v.name, v.type, v.base_class, v.description, f.relative_path, f.full_path
                FROM vocabularies v
                JOIN files f ON v.file_id = f.id
                WHERE v.name_lower LIKE ?
                ORDER BY 
                    CASE v.type 
                        WHEN 'class' THEN 1 
                        WHEN 'function' THEN 2 
                        WHEN 'property' THEN 3 
                        WHEN 'event' THEN 4 
                    END
                LIMIT ?
            """, (query_lower, top_k * 2))
            
            for row in cursor.fetchall():
                type_name = row['type']
                if type_name == 'class':
                    results.append({
                        'type': 'class',
                        'name': row['name'],
                        'title': row['name'],
                        'path': row['relative_path'],
                        'file_path': row['relative_path'],
                        'full_path': row['full_path'],
                        'base_class': row['base_class'],
                        'description': row['description'] or '',
                        'score': 100
                    })
                elif type_name == 'function':
                    results.append({
                        'type': 'function',
                        'name': row['name'],
                        'title': row['name'],
                        'path': row['relative_path'],
                        'file_path': row['relative_path'],
                        'full_path': row['full_path'],
                        'description': row['description'] or '',
                        'score': 90
                    })
                elif type_name == 'property':
                    results.append({
                        'type': 'property',
                        'name': row['name'],
                        'title': row['name'],
                        'path': row['relative_path'],
                        'file_path': row['relative_path'],
                        'full_path': row['full_path'],
                        'description': row['description'] or '',
                        'score': 80
                    })
                elif type_name == 'event':
                    results.append({
                        'type': 'event',
                        'name': row['name'],
                        'title': row['name'],
                        'path': row['relative_path'],
                        'file_path': row['relative_path'],
                        'full_path': row['full_path'],
                        'description': row['description'] or '',
                        'score': 70
                    })
            
            # 如果 vocabularies 没找到足够结果，搜索 files
            if len(results) < top_k:
                cursor.execute("""
                    SELECT relative_path, full_path, description
                    FROM files 
                    WHERE LOWER(relative_path) LIKE ? OR LOWER(description) LIKE ?
                    LIMIT ?
                """, (query_lower, query_lower, top_k))
                
                existing_paths = {r.get('path', r.get('full_path', '')) for r in results}
                for row in cursor.fetchall():
                    if row['relative_path'] not in existing_paths:
                        results.append({
                            'type': 'document',
                            'name': row['relative_path'],
                            'title': row['relative_path'],
                            'path': row['relative_path'],
                            'file_path': row['relative_path'],
                            'full_path': row['full_path'],
                            'description': (row['description'] or '')[:200],
                            'score': 50
                        })
            
            conn.close()
            
            # 按分数排序并去重
            results.sort(key=lambda x: x['score'], reverse=True)
            
            seen_paths = set()
            unique_results = []
            for r in results:
                path = r.get('path', r.get('full_path', ''))
                if path not in seen_paths:
                    seen_paths.add(path)
                    unique_results.append(r)
            
            return unique_results[:top_k]
            
        except Exception as e:
            logger.error(f"搜索帮助文档失败: {e}")
            return results

    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """关键词搜索"""
        return self.search(keyword, 10)

    def search_class(self, class_name: str, top_k: int = 10) -> List[Dict]:
        """搜索类"""
        return self._search_by_type(class_name, 'class', top_k)

    def search_function(self, func_name: str, top_k: int = 10) -> List[Dict]:
        """搜索函数"""
        return self._search_by_type(func_name, 'function', top_k)

    def _search_by_type(self, name: str, vocab_type: str, top_k: int = 10) -> List[Dict]:
        """按类型搜索词汇"""
        results = []
        try:
            db_file = self.kb_dir / "knowledge.sqlite"
            if not db_file.exists():
                return results
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            name_lower = f"%{name.lower()}%"
            cursor.execute("""
                SELECT v.name, v.type, v.base_class, v.description, f.relative_path, f.full_path, v.line
                FROM vocabularies v
                JOIN files f ON v.file_id = f.id
                WHERE v.name_lower LIKE ? AND v.type = ?
                LIMIT ?
            """, (name_lower, vocab_type, top_k))
            for row in cursor.fetchall():
                results.append({
                    'type': vocab_type,
                    'name': row['name'],
                    'line': row['line'],
                    'base_class': row['base_class'],
                    'description': row['description'] or '',
                    'file_path': row['relative_path'],
                    'full_path': row['full_path']
                })
            conn.close()
        except Exception as e:
            logger.error(f"搜索失败: {e}")
        return results

    def get_statistics(self) -> Dict:
        """获取统计信息 - 从SQLite读取 (统一Schema)"""
        stats = {
            'total_documents': 0,
            'total_classes': 0,
            'total_functions': 0,
            'total_properties': 0,
            'total_events': 0,
            'total_interfaces': 0,
            'total_types': 0,
            'total_code_examples': 0,
            'sources': {},
            'database_size_mb': 0
        }

        try:
            db_file = self.kb_dir / "knowledge.sqlite"
            if db_file.exists():
                conn = sqlite3.connect(str(db_file))
                cursor = conn.cursor()
                
                cursor.execute("SELECT COUNT(*) FROM files")
                stats['total_documents'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='class'")
                stats['total_classes'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='function'")
                stats['total_functions'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='property'")
                stats['total_properties'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='event'")
                stats['total_events'] = cursor.fetchone()[0]
                
                stats['database_size_mb'] = round(db_file.stat().st_size / (1024 * 1024), 2)
                
                conn.close()

        except Exception as e:
            logger.warning(f"获取统计信息失败: {e}")

        return stats

    def is_kb_exists(self) -> bool:
        """检查知识库是否存在"""
        db_file = self.kb_dir / "knowledge.sqlite"
        return db_file.exists()

    def close(self):
        """关闭知识库"""
        if self.kb_instance:
            self.kb_instance.close()
            self.kb_instance = None
