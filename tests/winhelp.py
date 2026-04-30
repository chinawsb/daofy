class HLPParser(DocumentParser):
    """HLP (Windows Help) 文件解析器"""

    def can_parse(self, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext == '.hlp'

    def parse(self, file_path: str) -> Dict:
        """
        解析 HLP 文件
        HLP 是 Windows 旧版帮助文件格式，需要特殊工具转换
        """
        try:
            file_path_obj = Path(file_path)
            file_size = file_path_obj.stat().st_size

            # 尝试提取 HLP 文件中的文本内容
            content = self._extract_hlp_content(file_path)

            # 尝试从内容中提取标题
            title = self._extract_title_from_content(content, file_path_obj.stem)

            return {
                'title': title,
                'content': content,
                'metadata': {
                    'file_type': 'hlp',
                    'file_size': file_size,
                    'source_file': file_path,
                    'extraction_method': 'binary_parse'
                }
            }

        except Exception as e:
            logger.error(f"解析 HLP 文件失败 {file_path}: {e}")
            return self._create_error_result(file_path, str(e))

    def _extract_hlp_content(self, file_path: str) -> str:
        """
        从 HLP 文件中提取文本内容
        HLP 文件是二进制格式，尝试提取可读的文本内容
        """
        content_parts = []

        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            # HLP 文件格式分析：
            # 1. 文件头包含文件信息
            # 2. 后续是压缩的文本内容
            # 3. 尝试提取所有可读的 ASCII/Unicode 文本

            # 提取 ASCII 文本（长度 >= 4 的可打印字符序列）
            ascii_text = self._extract_ascii_text(data)
            if ascii_text:
                content_parts.append(ascii_text)

            # 尝试解码 UTF-16LE 文本（Windows 常用编码）
            try:
                utf16_text = data.decode('utf-16le', errors='ignore')
                # 过滤出可打印字符
                clean_utf16 = self._clean_extracted_text(utf16_text)
                if clean_utf16 and len(clean_utf16) > 10:
                    content_parts.append(clean_utf16)
            except:
                pass

            # 尝试解码 GBK 中文文本
            try:
                gbk_text = data.decode('gbk', errors='ignore')
                clean_gbk = self._clean_extracted_text(gbk_text)
                if clean_gbk and len(clean_gbk) > 10:
                    content_parts.append(clean_gbk)
            except:
                pass

            # 合并所有提取的内容
            combined_content = '\n\n'.join(content_parts)

            # 如果内容太少，添加文件信息
            if len(combined_content) < 100:
                combined_content = f"[HLP Help File: {Path(file_path).name}]\n\n{combined_content}"

            return combined_content

        except Exception as e:
            logger.warning(f"提取 HLP 内容时出错: {e}")
            return f"[Unable to extract content from HLP file: {Path(file_path).name}]"

    def _extract_ascii_text(self, data: bytes) -> str:
        """从二进制数据中提取 ASCII 文本"""
        text_parts = []
        current_text = []

        for byte in data:
            # 可打印 ASCII 字符 (32-126) 或常见控制字符
            if 32 <= byte <= 126 or byte in (9, 10, 13):
                current_text.append(chr(byte))
            else:
                # 遇到非文本字节，保存当前文本段
                if len(current_text) >= 4:  # 至少4个字符才算有效文本
                    text_parts.append(''.join(current_text))
                current_text = []

        # 保存最后一段
        if len(current_text) >= 4:
            text_parts.append(''.join(current_text))

        # 合并并清理文本
        combined = '\n'.join(text_parts)
        return self._clean_extracted_text(combined)

    def _clean_extracted_text(self, text: str) -> str:
        """清理提取的文本内容"""
        if not text:
            return ""

        # 替换多个空白字符为单个空格
        import re
        text = re.sub(r'\s+', ' ', text)

        # 移除过短的行（可能是乱码）
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            # 保留长度 >= 2 的行，或者包含中文字符的行
            if len(line) >= 2 or any('\u4e00' <= char <= '\u9fff' for char in line):
                clean_lines.append(line)

        return '\n'.join(clean_lines)

    def _extract_title_from_content(self, content: str, default_title: str) -> str:
        """从内容中提取标题"""
        if not content:
            return default_title

        lines = content.split('\n')

        # 查找第一行非空且长度合适的行作为标题
        for line in lines[:10]:  # 检查前10行
            line = line.strip()
            # 标题应该有一定长度，但不能太长
            if 5 <= len(line) <= 200:
                # 排除常见的非标题行
                if not line.startswith('[') and not line.startswith('Copyright'):
                    return line

        return default_title

    def _create_error_result(self, file_path: str, error: str) -> Dict:
        return {
            'title': Path(file_path).stem,
            'content': '',
            'metadata': {'error': error},
            'parse_error': True
        }