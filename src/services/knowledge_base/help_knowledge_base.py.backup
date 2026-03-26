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
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from datetime import datetime
from bs4 import BeautifulSoup

from .sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase
from ...utils.logger import get_logger

logger = get_logger(__name__)


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

    def convert(self, html_content: str) -> str:
        """将 HTML 转换为 Markdown"""
        try:
            # 先使用 BeautifulSoup 清理 HTML
            soup = BeautifulSoup(html_content, 'html.parser')

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
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text(separator='\n', strip=True)
        except:
            return ""


class HTMLContentExtractor:
    """HTML 内容提取器 - 增强版"""

    def __init__(self):
        self.md_converter = HTMLToMarkdownConverter()

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
            soup = BeautifulSoup(html_content, 'html.parser')
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
            soup = BeautifulSoup(html_content, 'html.parser')

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
        (self.kb_dir / "index").mkdir(exist_ok=True)
        (self.kb_dir / "extracted").mkdir(exist_ok=True)

        self.kb_instance: Optional[SQLiteVectorKnowledgeBase] = None
        self.extractor = HTMLContentExtractor()

        # 7-Zip 路径
        self.sevenzip_path = self._find_7zip()

        # Delphi 帮助目录
        self.delphi_help_dir = self._find_delphi_help_dir()

        logger.info(f"帮助文档知识库初始化: {self.kb_dir}")

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
            version_key = winreg.EnumKey(key, 0)
            version_path = winreg.OpenKey(key, version_key)
            root_dir = winreg.QueryValueEx(version_path, "RootDir")[0]
            winreg.CloseKey(version_path)
            winreg.CloseKey(key)

            help_dir = Path(root_dir) / "Help" / "Doc"
            if help_dir.exists():
                return str(help_dir)
        except Exception as e:
            logger.warning(f"查找 Delphi 帮助目录失败: {e}")

        # 默认路径
        default_path = r"C:\Program Files (x86)\Embarcadero\Studio\22.0\Help\Doc"
        if Path(default_path).exists():
            return default_path

        return None

    # ==================== 步骤1: 解压 CHM 文件 ====================

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
                       progress_callback: Optional[Callable] = None) -> Dict[str, bool]:
        """
        解压所有 CHM 文件

        Args:
            help_names: 要解压的帮助文件列表，None表示全部
            progress_callback: 进度回调函数(current, total, name, status)

        Returns:
            每个帮助文件的解压结果
        """
        if not self.delphi_help_dir:
            logger.error("未找到 Delphi 帮助目录")
            return {}

        results = {}
        extracted_dir = self.kb_dir / "extracted"

        # 确定要处理的文件
        files_to_process = {}
        for name, desc in self.HELP_FILES.items():
            if help_names is None or name in help_names:
                chm_path = Path(self.delphi_help_dir) / f"{name}.chm"
                if chm_path.exists():
                    files_to_process[name] = (chm_path, desc)
                else:
                    logger.warning(f"帮助文件不存在: {chm_path}")
                    results[name] = False

        total = len(files_to_process)
        for i, (name, (chm_path, desc)) in enumerate(files_to_process.items(), 1):
            if progress_callback:
                progress_callback(i, total, name, f"正在解压 {desc}")

            output_dir = extracted_dir / name
            success = self.extract_chm(str(chm_path), str(output_dir))
            results[name] = success

        return results

    # ==================== 步骤2: 扫描 HTML 文件 ====================

    def scan_html_files(self, directory: str, max_files: Optional[int] = None,
                       progress_callback: Optional[Callable] = None) -> List[Dict]:
        """
        扫描目录中的 HTML 文件

        Args:
            directory: 目录路径
            max_files: 最大处理文件数
            progress_callback: 进度回调函数(current, total, filename)

        Returns:
            文档列表
        """
        documents = []
        html_files = list(Path(directory).rglob("*.html")) + list(Path(directory).rglob("*.htm"))

        if max_files:
            html_files = html_files[:max_files]

        total = len(html_files)
        logger.info(f"开始处理 {total} 个 HTML 文件...")

        for i, html_file in enumerate(html_files):
            try:
                if progress_callback and i % 10 == 0:
                    progress_callback(i, total, html_file.name)

                with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    html_content = f.read()

                # 提取内容
                extracted = self.extractor.extract_content(html_content, str(html_file))

                if extracted['content'] and len(extracted['content']) > 50:
                    documents.append({
                        'path': str(html_file.relative_to(directory)),
                        'full_path': str(html_file),
                        'title': extracted['title'],
                        'content': extracted['content'],
                        'size': len(extracted['content']),
                        'hash': hashlib.md5(extracted['content'].encode()).hexdigest(),
                        'classes': extracted['classes'],
                        'functions': extracted['functions'],
                        'properties': extracted.get('properties', []),
                        'events': extracted.get('events', []),
                        'interfaces': extracted.get('interfaces', []),
                        'types': extracted.get('types', []),
                        'uses': extracted.get('uses', []),
                        'code_examples': extracted.get('code_examples', [])
                    })

            except Exception as e:
                logger.warning(f"处理文件失败 {html_file}: {e}")

        if progress_callback:
            progress_callback(total, total, "完成")

        logger.info(f"成功提取 {len(documents)} 个文档")
        return documents

    def scan_extracted_directory(self, help_name: str, max_files: Optional[int] = None,
                                 progress_callback: Optional[Callable] = None,
                                 source_dir: Optional[str] = None) -> List[Dict]:
        """
        扫描已解压的目录

        Args:
            help_name: 帮助文件名称（如 'fmx', 'vcl'）
            max_files: 最大处理文件数
            progress_callback: 进度回调函数
            source_dir: 源目录路径，默认使用 self.kb_dir / "extracted"

        Returns:
            文档列表
        """
        if source_dir is None:
            source_path = self.kb_dir / "extracted" / help_name
        else:
            source_path = Path(source_dir) / help_name

        if not source_path.exists():
            logger.error(f"目录不存在: {source_path}")
            return []

        logger.info(f"扫描目录: {source_path}")
        documents = self.scan_html_files(str(source_path), max_files, progress_callback)

        # 添加来源信息
        for doc in documents:
            doc['source'] = help_name
            doc['source_desc'] = self.HELP_FILES.get(help_name, help_name)

        return documents

    # ==================== 步骤3: 构建向量索引 ====================

    def build_vector_index(self, documents: List[Dict],
                          progress_callback: Optional[Callable] = None) -> bool:
        """
        构建向量索引

        Args:
            documents: 文档列表
            progress_callback: 进度回调函数(percent, message)

        Returns:
            是否成功
        """
        try:
            if progress_callback:
                progress_callback(0, "准备构建索引...")

            files_data = []
            total_classes = 0
            total_functions = 0
            total_properties = 0
            total_events = 0
            total_interfaces = 0
            total_types = 0
            total_code_examples = 0

            for i, doc in enumerate(documents):
                if progress_callback and i % 100 == 0:
                    progress_callback(int(i / len(documents) * 50), f"处理文档 {i}/{len(documents)}")

                content = doc.get('content', '')
                max_desc_length = 3000
                truncated_content = content[:max_desc_length] if len(content) > max_desc_length else content

                classes = doc.get('classes', [])
                functions = doc.get('functions', [])
                properties = doc.get('properties', [])
                events = doc.get('events', [])
                interfaces = doc.get('interfaces', [])
                types = doc.get('types', [])
                uses_list = doc.get('uses', [])
                code_examples = doc.get('code_examples', [])

                total_classes += len(classes)
                total_functions += len(functions)
                total_properties += len(properties)
                total_events += len(events)
                total_interfaces += len(interfaces)
                total_types += len(types)
                total_code_examples += len(code_examples)

                files_data.append({
                    'path': doc['path'],
                    'full_path': doc['full_path'],
                    'extension': '.html',
                    'size': doc['size'],
                    'line_count': content.count('\n'),
                    'hash': doc['hash'],
                    'last_modified': datetime.now().isoformat(),
                    'units': uses_list,  # 使用提取的 uses 信息
                    'uses': uses_list,
                    'classes': classes,
                    'functions': functions,
                    'properties': properties,
                    'events': events,
                    'interfaces': interfaces,
                    'types': types,
                    'code_examples': code_examples,
                    'title': doc.get('title', ''),
                    'content': content,
                    'description': f"{doc.get('title', '')}\n{truncated_content}"
                })

            if progress_callback:
                progress_callback(50, "保存索引文件...")

            scan_result = {
                'files': files_data,
                'statistics': {
                    'total_files': len(files_data),
                    'total_lines': sum(f['line_count'] for f in files_data),
                    'total_classes': total_classes,
                    'total_functions': total_functions,
                    'total_properties': total_properties,
                    'total_events': total_events,
                    'total_interfaces': total_interfaces,
                    'total_types': total_types,
                    'total_code_examples': total_code_examples,
                    'build_time': datetime.now().isoformat()
                }
            }

            # 保存索引
            index_file = self.kb_dir / "index" / "source_index.json"
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(scan_result, f, ensure_ascii=False, indent=2)

            # 保存元数据
            metadata = {
                'version': '1.0',
                'source_directory': str(self.delphi_help_dir),
                'scan_date': datetime.now().isoformat(),
                'statistics': scan_result['statistics']
            }

            metadata_file = self.kb_dir / "index" / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            if progress_callback:
                progress_callback(60, "构建向量索引...")

            # 构建向量索引
            self.kb_instance = SQLiteVectorKnowledgeBase(str(self.kb_dir), force_rebuild=True)

            if progress_callback:
                progress_callback(100, "完成")

            logger.info(f"向量索引构建完成: {len(files_data)} 个文件, {total_classes} 个类, {total_functions} 个函数")
            return True

        except Exception as e:
            logger.error(f"构建向量索引失败: {e}")
            return False

    # ==================== 完整构建流程 ====================

    def build_knowledge_base(self, help_names: Optional[List[str]] = None,
                            max_files_per_help: Optional[int] = None,
                            progress_callback: Optional[Callable] = None) -> bool:
        """
        完整构建帮助文档知识库

        Args:
            help_names: 要构建的帮助文件列表，None表示全部
            max_files_per_help: 每个帮助文件最大处理文档数
            progress_callback: 进度回调函数(stage, current, total, message)
                stage: 'extract', 'scan', 'index'

        Returns:
            是否成功
        """
        if not self.delphi_help_dir:
            logger.error("未找到 Delphi 帮助目录")
            return False

        # 步骤1: 解压 CHM
        if progress_callback:
            progress_callback('extract', 0, 1, "开始解压 CHM 文件...")

        extract_results = self.extract_all_chm(help_names,
            lambda current, total, name, msg: progress_callback('extract', current, total, msg) if progress_callback else None)

        if not any(extract_results.values()):
            logger.error("没有成功解压任何 CHM 文件")
            return False

        # 步骤2: 扫描 HTML
        if progress_callback:
            progress_callback('scan', 0, 1, "开始扫描 HTML 文件...")

        all_documents = []
        successful_helps = [name for name, success in extract_results.items() if success]

        for i, help_name in enumerate(successful_helps):
            if progress_callback:
                progress_callback('scan', i, len(successful_helps), f"扫描 {self.HELP_FILES.get(help_name, help_name)}...")

            documents = self.scan_extracted_directory(help_name, max_files_per_help)
            all_documents.extend(documents)

        if not all_documents:
            logger.error("未提取到任何文档")
            return False

        if progress_callback:
            progress_callback('scan', len(successful_helps), len(successful_helps), f"扫描完成，共 {len(all_documents)} 个文档")

        # 步骤3: 构建索引
        if progress_callback:
            progress_callback('index', 0, 100, "开始构建向量索引...")

        success = self.build_vector_index(all_documents,
            lambda percent, msg: progress_callback('index', percent, 100, msg) if progress_callback else None)

        return success

    def build_knowledge_base_incremental(self, help_names: Optional[List[str]] = None,
                                        max_files_per_help: Optional[int] = None,
                                        progress_callback: Optional[Callable] = None,
                                        source_dir: Optional[str] = None) -> bool:
        """
        增量构建帮助文档知识库（跳过解压，直接扫描已解压的 HTML）

        Args:
            help_names: 要构建的帮助文件列表，None表示全部
            max_files_per_help: 每个帮助文件最大处理文档数
            progress_callback: 进度回调函数
            source_dir: 源目录路径，默认使用 self.kb_dir / "extracted"

        Returns:
            是否成功
        """
        if source_dir is None:
            extracted_dir = self.kb_dir / "extracted"
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

            documents = self.scan_extracted_directory(help_name, max_files_per_help, source_dir=str(extracted_dir))
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
        """加载知识库"""
        try:
            if self.kb_instance is None:
                self.kb_instance = SQLiteVectorKnowledgeBase(str(self.kb_dir))
            return True
        except Exception as e:
            logger.error(f"加载知识库失败: {e}")
            return False

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        搜索帮助文档

        Args:
            query: 搜索查询
            top_k: 返回结果数量

        Returns:
            搜索结果
        """
        if not self.load_knowledge_base():
            return []

        results = []

        # 1. 语义搜索类
        class_results = self.kb_instance.semantic_search_classes(query, top_k)
        for name, score in class_results:
            exact_results = self.kb_instance.search_by_class_name(name)
            if exact_results:
                result = exact_results[0]
                results.append({
                    'type': 'class',
                    'name': result['class']['name'],
                    'kind': result['class'].get('type_kind', 'class'),
                    'base_class': result['class'].get('base_class', ''),
                    'description': result['class'].get('description', '')[:200],
                    'file_path': result['file']['path'],
                    'full_path': result['file']['full_path'],
                    'score': score
                })

        # 2. 语义搜索函数
        func_results = self.kb_instance.semantic_search_functions(query, top_k)
        for name, score in func_results:
            exact_results = self.kb_instance.search_by_function_name(name)
            if exact_results:
                result = exact_results[0]
                results.append({
                    'type': 'function',
                    'name': result['function']['name'],
                    'func_type': result['function'].get('type', 'function'),
                    'description': result['function'].get('description', '')[:200],
                    'file_path': result['file']['path'],
                    'full_path': result['file']['full_path'],
                    'score': score
                })

        # 3. 关键词搜索
        keyword_results = self.kb_instance.search_by_keyword(query)
        for file_info in keyword_results[:top_k]:
            existing = [r for r in results if r.get('full_path') == file_info['full_path']]
            if not existing:
                results.append({
                    'type': 'document',
                    'name': file_info['path'],
                    'file_path': file_info['path'],
                    'full_path': file_info['full_path'],
                    'score': 0.5
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """关键词搜索"""
        if not self.load_knowledge_base():
            return []
        return self.kb_instance.search_by_keyword(keyword)

    def get_statistics(self) -> Dict:
        """获取统计信息（完整版）"""
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
            index_file = self.kb_dir / "index" / "source_index.json"
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stats['total_documents'] = data.get('statistics', {}).get('total_files', 0)
                    stats['total_classes'] = data.get('statistics', {}).get('total_classes', 0)
                    stats['total_functions'] = data.get('statistics', {}).get('total_functions', 0)
                    stats['total_properties'] = data.get('statistics', {}).get('total_properties', 0)
                    stats['total_events'] = data.get('statistics', {}).get('total_events', 0)
                    stats['total_interfaces'] = data.get('statistics', {}).get('total_interfaces', 0)
                    stats['total_types'] = data.get('statistics', {}).get('total_types', 0)
                    stats['total_code_examples'] = data.get('statistics', {}).get('total_code_examples', 0)

            db_file = self.kb_dir / "index" / "knowledge_base_vector.sqlite"
            if db_file.exists():
                stats['database_size_mb'] = round(db_file.stat().st_size / (1024 * 1024), 2)

        except Exception as e:
            logger.warning(f"获取统计信息失败: {e}")

        return stats

    def is_kb_exists(self) -> bool:
        """检查知识库是否存在"""
        index_file = self.kb_dir / "index" / "source_index.json"
        return index_file.exists()

    def close(self):
        """关闭知识库"""
        if self.kb_instance:
            self.kb_instance.close()
            self.kb_instance = None
