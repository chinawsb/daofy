"""
第三方库知识库服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

为 Delphi 第三方库提供知识库功能:
1. 从注册表读取 Delphi 版本的 Library 路径
2. 解析 Browsing Path 和 Search Path
3. 展开环境变量并去重
4. 排除 Delphi 自带路径
5. 构建第三方库知识库
"""

import os
import re
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable
from datetime import datetime

try:
    from ...constants import REG_KEY_EMBARCADERO_BDS, REG_KEY_EMBARCADERO_STUDIO
    from .zvec_adapter import ZVecKnowledgeBaseAdapter
    from ...utils.logger import get_logger
    from ...utils.delphi_env import expand_delphi_path_macros, get_delphi_version, get_catalog_repository_paths
    logger = get_logger(__name__)
except ImportError:
    # 支持直接运行测试
    from src.constants import REG_KEY_EMBARCADERO_BDS, REG_KEY_EMBARCADERO_STUDIO
    from zvec_adapter import ZVecKnowledgeBaseAdapter
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(handler)

    # 测试模式下 fallback 实现
    def expand_delphi_path_macros(path: str, version: Optional[str] = None) -> str:
        return os.path.expandvars(path)

    def get_delphi_version() -> Optional[str]:
        return None

    def get_catalog_repository_paths(version: Optional[str] = None) -> list:
        return []


class ThirdPartyKnowledgeBase:
    """第三方库知识库管理器"""

    def __init__(self, kb_dir: Optional[str] = None, progress_callback: Optional[Callable] = None) -> None:
        """
        初始化第三方库知识库

        Args:
            kb_dir: 知识库目录路径,如果为 None 则使用默认路径
            progress_callback: 进度回调函数
        """
        self.kb_dir: Path
        if kb_dir is None:
            # 默认路径: MCP 服务器目录下的 data/thirdparty-knowledge-base
            server_root = Path(__file__).parent.parent.parent.parent
            kb_dir = server_root / "data" / "thirdparty-knowledge-base"
        else:
            kb_dir = Path(kb_dir)

        self.kb_dir = kb_dir
        self.kb_instance = None
        self.delphi_versions = []
        self.environment_variables = {}  # 环境变量缓存
        self.progress_callback = progress_callback

        # 创建必要的目录
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        # 元数据文件
        self.metadata_file = self.kb_dir / "thirdparty_metadata.json"
        self.paths_file = self.kb_dir / "thirdparty_paths.json"

        # 加载元数据
        self.metadata = self._load_metadata()

        # 检测 Delphi 版本
        self.detect_delphi_versions()

        logger.info("第三方库知识库初始化完成")

    def _load_metadata(self) -> Dict:
        """加载元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载元数据失败: {e}")

        return {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "version": "1.0",
            "total_paths": 0,
            "scanned_paths": []
        }

    def _save_metadata(self):
        """保存元数据"""
        self.metadata["last_updated"] = datetime.now().isoformat()
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def detect_delphi_versions(self) -> List[Dict]:
        """
        检测已安装的 Delphi 版本

        Returns:
            Delphi 版本列表
        """
        import winreg

        versions = []

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS)

            i = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, i)
                    i += 1

                    version_path = winreg.OpenKey(key, version_key)
                    try:
                        root_dir = winreg.QueryValueEx(version_path, "RootDir")[0]
                    except OSError:
                        continue
                    finally:
                        winreg.CloseKey(version_path)

                    version_name = self._get_delphi_name_by_version_key(version_key)

                    versions.append({
                        "version": version_key,
                        "name": version_name,
                        "root_dir": root_dir
                    })

                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            logger.warning(f"检测 Delphi 版本失败: {e}")

        self.delphi_versions = versions
        return versions

    def get_latest_version(self) -> Optional[Dict]:
        """获取最新安装的 Delphi 版本"""
        if not self.delphi_versions:
            return None
        # 按版本号排序，返回最新版本
        sorted_versions = sorted(
            self.delphi_versions,
            key=lambda x: tuple(int(p) for p in x["version"].split('.')),
            reverse=True
        )
        return sorted_versions[0]

    def _get_delphi_name_by_version_key(self, version_key: str) -> str:
        """根据注册表版本键（如 "22.0"）获取 Delphi 版本名称

        注意与 config_manager._get_delphi_version_name 的区别：
        后者按安装路径解析版本名，本方法按注册表键名解析。
        """
        from src.utils.delphi_versions import get_version_name
        return get_version_name(version_key)

    def _load_environment_variables(self, version: str) -> Dict[str, str]:
        """
        加载指定 Delphi 版本的环境变量

        Args:
            version: Delphi 版本号 (如 "37.0")

        Returns:
            环境变量字典
        """
        import winreg

        env_vars = {}

        try:
            key_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Environment Variables"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    env_vars[name] = value
                    i += 1
                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            logger.warning(f"加载环境变量失败 (版本 {version}): {e}")

        return env_vars

    def _expand_path_variables(self, path: str, env_vars: Dict[str, str]) -> str:
        """
        展开路径中的环境变量

        Args:
            path: 原始路径 (可能包含 $(VAR) 格式)
            env_vars: 环境变量字典

        Returns:
            展开后的路径
        """
        # 匹配 $(VAR) 格式的变量
        pattern = r'\$\(([^)]+)\)'

        def replace_var(match):
            var_name = match.group(1)
            if var_name in env_vars:
                return env_vars[var_name]
            # 保留未定义的变量
            return match.group(0)

        return re.sub(pattern, replace_var, path)

    def _is_delphi_system_path(self, path: str, version_key: Optional[str] = None) -> bool:
        """
        检查路径是否是 Delphi 系统路径

        Args:
            path: 路径字符串
            version_key: Delphi 版本号

        Returns:
            是否是系统路径
        """
        path_lower = path.lower()

        # 检查是否包含 Delphi 系统路径变量
        system_vars = ['$(bdsccommondir)', '$(bdslib)', '$(bds)', '$(bdsbin)', '$(bdsuserdir)']
        for var in system_vars:
            if var in path_lower:
                return True

        # 检查是否在 Delphi 安装目录下
        for version in self.delphi_versions:
            root_dir = version.get("root_dir", "")
            if root_dir and path_lower.startswith(root_dir.lower()):
                return True

        # 检查是否是公共文档下的 Delphi 系统目录
        user_docs = os.path.expanduser("~\\Documents").lower()
        delphi_common_dirs = ['imports', 'bpl', 'dcp', 'bpl\\win32', 'bpl\\win64', 'dcp\\win32', 'dcp\\win64']
        if path_lower.startswith(user_docs + '\\embarcadero\\studio\\'):
            relative = path_lower[len(user_docs + '\\embarcadero\\studio\\'):]
            for sys_dir in delphi_common_dirs:
                if relative.startswith(sys_dir):
                    return True

        return False

    def get_library_paths(self, version: Optional[str] = None) -> List[str]:
        """
        获取指定 Delphi 版本的 Library 路径

        Args:
            version: Delphi 版本号,如果为 None 则使用最新版本

        Returns:
            第三方库路径列表
        """
        import winreg

        # 选择 Delphi 版本
        if not self.delphi_versions:
            logger.error("未检测到 Delphi 版本")
            return []

        if version is None:
            selected_version = self.get_latest_version()
        else:
            selected_version = None
            for v in self.delphi_versions:
                if v["version"] == version or v["name"] == version:
                    selected_version = v
                    break

        if not selected_version:
            logger.error(f"未找到 Delphi 版本: {version}")
            return []

        version_key = selected_version["version"]
        logger.info(f"使用 Delphi 版本: {selected_version['name']} ({version_key})")

        # 加载环境变量
        env_vars = self._load_environment_variables(version_key)
        self.environment_variables = env_vars

        all_paths = []

        # 读取 BDS Library 路径
        try:
            library_key_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version_key}\\Library"
            library_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, library_key_path)
            all_paths.extend(self._read_library_paths(library_key, version_key))
            winreg.CloseKey(library_key)
        except Exception as e:
            logger.debug(f"读取 BDS Library 路径失败: {e}")

        # 读取 Studio Library 路径（公共库路径）
        try:
            studio_key_path = f"{REG_KEY_EMBARCADERO_STUDIO}\\{version_key}\\Library"
            studio_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, studio_key_path)
            all_paths.extend(self._read_library_paths(studio_key, version_key))
            winreg.CloseKey(studio_key)
        except Exception as e:
            logger.debug(f"读取 Studio Library 路径失败: {e}")

        # 去重并保持顺序
        seen = set()
        unique_paths = []
        for path in all_paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        logger.info(f"从注册表读取到 {len(unique_paths)} 个唯一路径")

        # 展开环境变量并过滤
        thirdparty_paths = []
        for path in unique_paths:
            # 先展开环境变量，再用展开后的路径判断是否系统路径
            try:
                expanded_path = expand_delphi_path_macros(path, version=version_key)
            except Exception:
                # 回退到原有的展开方法
                expanded_path = self._expand_path_variables(path, env_vars)

            # 跳过 Delphi 系统路径（展开后判断，避免 $(BDS) 宏误杀所有路径）
            if self._is_delphi_system_path(expanded_path):
                logger.debug(f"跳过 Delphi 系统路径: {expanded_path}")
                continue

            # 检查路径是否存在
            path_obj = Path(expanded_path)
            if path_obj.exists():
                thirdparty_paths.append(str(path_obj.resolve()))
            else:
                # 尝试展开 GetIt CatalogRepository 路径
                if 'CatalogRepository' in expanded_path:
                    logger.debug(f"GetIt 路径不存在: {expanded_path}")

        # 最终去重
        seen = set()
        final_paths = []
        for path in thirdparty_paths:
            if path not in seen:
                seen.add(path)
                final_paths.append(path)

        logger.info(f"过滤后得到 {len(final_paths)} 个第三方库路径")

        # 额外添加 GetIt CatalogRepository 中的组件源码路径
        try:
            getit_paths = get_catalog_repository_paths(version_key)
            for getit_path in getit_paths:
                if getit_path not in final_paths:
                    final_paths.append(getit_path)
                    logger.debug(f"添加 GetIt 组件路径: {getit_path}")
        except Exception as e:
            logger.warning(f"获取 GetIt 路径失败: {e}")

        logger.info(f"最终得到 {len(final_paths)} 个第三方库路径")

        # 保存路径列表
        self._save_paths(final_paths, selected_version)

        return final_paths

    def _read_library_paths(self, library_key, version_key: str) -> List[str]:
        """从注册表 Library 键读取路径"""
        import winreg
        paths = []
        
        # 遍历所有平台 (Win32, Win64, etc.)
        i = 0
        while True:
            try:
                platform_name = winreg.EnumKey(library_key, i)
                i += 1

                platform_key = winreg.OpenKey(library_key, platform_name)

                try:
                    # 读取 Browsing Path
                    try:
                        browsing_path = winreg.QueryValueEx(platform_key, "Browsing Path")[0]
                        if browsing_path:
                            p_list = [p.strip() for p in browsing_path.split(';') if p.strip()]
                            paths.extend(p_list)
                            logger.debug(f"平台 {platform_name} Browsing Path: {len(p_list)} 个路径")
                    except OSError:
                        pass

                    # 读取 Search Path
                    try:
                        search_path = winreg.QueryValueEx(platform_key, "Search Path")[0]
                        if search_path:
                            p_list = [p.strip() for p in search_path.split(';') if p.strip()]
                            paths.extend(p_list)
                            logger.debug(f"平台 {platform_name} Search Path: {len(p_list)} 个路径")
                    except OSError:
                        pass

                finally:
                    winreg.CloseKey(platform_key)

            except WindowsError:
                break
        
        return paths

    def _report_progress(self, percent: float, message: str) -> None:
        """报告进度（安全调用 progress_callback）"""
        if self.progress_callback:
            try:
                self.progress_callback(percent, message)
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))

    def _save_paths(self, paths: List[str], version_info: Dict):
        """保存路径列表"""
        data = {
            "version": version_info,
            "paths": paths,
            "count": len(paths),
            "saved_at": datetime.now().isoformat()
        }

        with open(self.paths_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"路径列表已保存到: {self.paths_file}")

    def build_thirdparty_knowledge_base(self, version: Optional[str] = None, rebuild: bool = False) -> bool:
        "构建三方库知识库 (ZVec)"
        import time, shutil
        from pathlib import Path
        _bt = time.time()
        logger.info("Building thirdparty KB (ZVec)")

        dirs = self.get_library_paths(version)
        if not dirs:
            logger.warning("No thirdparty dirs"); return True

        self._report_progress(5, "Scanning dirs...")
        files = self._collect_thirdparty_files(dirs)
        if not files:
            logger.warning("No thirdparty files to index"); return True
        logger.info("Collected " + str(len(files)) + " files")

        from .delphi_chunker import chunk_file_list
        chunks = chunk_file_list(files)
        if not chunks:
            logger.warning("No chunks"); return False
        logger.info("Chunked: " + str(len(chunks)))

        # 迁移旧版 zvec_thirdparty/ 子目录到根目录
        from .zvec_adapter import _migrate_old_zvec_data
        old_zvec = self.kb_dir / "zvec_thirdparty"
        if old_zvec.exists() and old_zvec != self.kb_dir:
            _migrate_old_zvec_data(old_zvec, self.kb_dir)

        kv_dir = str(self.kb_dir)
        import zvec
        from zvec import CollectionSchema, FieldSchema, DataType, FtsIndexParam, InvertIndexParam, Doc

        # 打开或创建集合：存在有效集合则 open，否则删除目录后 create_and_open
        kv_path = Path(kv_dir)
        has_valid = kv_path.exists() and any(
            f.name.startswith("manifest") for f in kv_path.iterdir()
        )
        if has_valid:
            col = zvec.open(kv_dir)
            if rebuild:
                # 重建：删集合目录，下一行 create_and_open 重新创建
                import shutil as _shutil
                _shutil.rmtree(kv_dir, ignore_errors=True)
                has_valid = False  # fall through to create_and_open
        if not has_valid:
            if kv_path.exists():
                import shutil as _shutil
                _shutil.rmtree(kv_dir, ignore_errors=True)
            # 简化 schema：entity_name 合并到 chunk_text 中
            schema = CollectionSchema("thirdparty_kb", fields=[
                FieldSchema("chunk_text", DataType.STRING),
                FieldSchema("chunk_type", DataType.STRING),
                FieldSchema("base_class", DataType.STRING),
                FieldSchema("file_path", DataType.STRING),
                FieldSchema("start_line", DataType.INT32),
                FieldSchema("end_line", DataType.INT32),
            ])
            col = zvec.create_and_open(path=kv_dir, schema=schema)

        # 先插入数据
        for offset in range(0, len(chunks), 500):
            batch = chunks[offset:offset+500]
            docs = []
            for i, c in enumerate(batch):
                docs.append(Doc(id="c%07d" % (offset+i), fields={
                    "chunk_text": (str(c['entity_name'])[:500] + "\n" + str(c['chunk_text'])[:99480]),
                    "chunk_type": str(c['chunk_type']),
                    "base_class": str(c['base_class'])[:200],
                    "file_path": str(c['file_path'])[:500],
                    "start_line": c['start_line'],
                    "end_line": c['end_line'],
                }))
            col.insert(docs)
        col.flush()

        # 再建索引（对已有集合重复 create_index 安全，zvec 不会报错）
        col.create_index("chunk_text", FtsIndexParam(tokenizer_name="jieba"))
        col.create_index("chunk_type", InvertIndexParam())
        col.create_index("base_class", InvertIndexParam())
        col.optimize()
        col.flush()

        # 保存构建元数据
        class_count = sum(1 for c in chunks if c.get('chunk_type') in ('class', 'record', 'interface'))
        try:
            metadata = {
                "files": len(files),
                "classes": class_count,
                "chunks": len(chunks),
            }
            (self.kb_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"保存三方库 KB metadata 失败: {e}")

        self.kb_instance = ZVecKnowledgeBaseAdapter(str(self.kb_dir), source_dirs=dirs)
        logger.info("3rd party KB done: %d chunks in %ds" % (len(chunks), int(time.time()-_bt)))
        return True

    def _collect_thirdparty_files(self, dirs: list) -> list:
        """收集三方库目录下的 .pas 文件"""
        files = []
        for d in dirs:
            p = Path(d)
            if p.exists():
                for f in p.rglob("*.pas"):
                    if f.is_file():
                        files.append(str(f))
        return files

    def _scan_help_documents(self, base_path: str) -> List[Dict]:
        """
        扫描帮助文档 (HTML/CHM)
        
        Args:
            base_path: 基础路径
            
        Returns:
            帮助文档列表
        """
        help_docs = []
        
        # 扫描 HTML 文件 - 更宽松的扫描
        for root, dirs, files in os.walk(base_path):
            # 跳过隐藏目录和常见无关目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                'node_modules', 'vendor', 'lib', 'dist', 'bin', 'obj', '__pycache__'
            ]]
            
            for file in files:
                if file.lower().endswith(('.html', '.htm')):
                    # 跳过索引文件
                    if file.lower() in ['index.html', 'index.htm', 'toc.html', 'contents.html']:
                        continue
                    
                    file_path = os.path.join(root, file)
                    try:
                        # 只处理较小的文件 (帮助文档通常不会太大)
                        if os.path.getsize(file_path) > 5 * 1024 * 1024:  # 5MB
                            continue
                            
                        doc = self._parse_html_help(file_path, base_path)
                        if doc and (doc.get('classes') or doc.get('functions')):
                            help_docs.append(doc)
                    except Exception as e:
                        logger.debug(f"解析帮助文档失败: {file_path}, {e}")
        
        return help_docs

    def _parse_html_help(self, file_path: str, base_path: str) -> Optional[Dict]:
        """
        解析 HTML 帮助文档
        
        Args:
            file_path: 文件路径
            base_path: 基础路径
            
        Returns:
            解析后的文档
        """
        try:
            from bs4 import BeautifulSoup
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # 提取标题
            title = ''
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text().strip()
            if not title:
                title_elem = soup.find('title')
                if title_elem:
                    title = title_elem.get_text().strip()
            if not title:
                title = os.path.basename(file_path)
            
            # 提取类名 (从标题或内容中)
            classes = []
            functions = []
            properties = []
            events = []
            
            # 常见模式: TClassName, TInterfaceName
            import re
            class_pattern = re.compile(r'\b(T[A-Z][A-Za-z0-9_]+)\b')
            
            # 从标题提取
            if title:
                matches = class_pattern.findall(title)
                for match in matches:
                    if match not in [c['name'] for c in classes]:
                        classes.append({
                            'name': match,
                            'base_class': '',
                            'description': title
                        })
            
            # 从内容提取
            text = soup.get_text()
            matches = class_pattern.findall(text)
            for match in matches:
                if match not in [c['name'] for c in classes]:
                    classes.append({
                        'name': match,
                        'base_class': '',
                        'description': ''
                    })
            
            # 提取函数/方法
            func_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9_]+)\s*\([^)]*\)\s*(?:of\s+object)?;?', re.IGNORECASE)
            func_matches = func_pattern.findall(text)
            for func_name in func_matches[:20]:  # 限制数量
                if func_name not in [f['name'] for f in functions]:
                    functions.append({
                        'name': func_name,
                        'description': ''
                    })
            
            # 提取属性
            prop_pattern = re.compile(r'\bproperty\s+([A-Za-z_][A-Za-z0-9_]*)', re.IGNORECASE)
            prop_matches = prop_pattern.findall(text)
            for prop_name in prop_matches[:20]:
                if prop_name not in [p['name'] for p in properties]:
                    properties.append({
                        'name': prop_name,
                        'description': ''
                    })
            
            # 提取事件
            event_pattern = re.compile(r'\bOn([A-Z][a-zA-Z0-9_]+)', re.IGNORECASE)
            event_matches = event_pattern.findall(text)
            for event_name in event_matches[:20]:
                full_name = 'On' + event_name
                if full_name not in [e['name'] for e in events]:
                    events.append({
                        'name': full_name,
                        'description': ''
                    })
            
            stat = os.stat(file_path)
            
            return {
                'full_path': file_path,
                'path': os.path.relpath(file_path, base_path),
                'extension': '.html',
                'size': stat.st_size,
                'line_count': content.count('\n'),
                'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'title': title,
                'classes': classes,
                'functions': functions,
                'properties': properties,
                'events': events
            }
            
        except Exception as e:
            logger.debug(f"解析HTML失败: {file_path}, {e}")
            return None

    def load_knowledge_base(self) -> bool:
        try:
            # 迁移旧版 zvec_thirdparty/ 子目录到根目录
            from .zvec_adapter import _migrate_old_zvec_data
            old_zvec = self.kb_dir / "zvec_thirdparty"
            if old_zvec.exists() and old_zvec != self.kb_dir:
                _migrate_old_zvec_data(old_zvec, self.kb_dir)
            # 检查展平后的 ZVec 数据
            if any(f.name.startswith("manifest") for f in self.kb_dir.iterdir()):
                self.kb_instance = ZVecKnowledgeBaseAdapter(str(self.kb_dir))
                return True
            return False
        except Exception as e:
            logger.error("Load 3rd KB failed: %s" % e)
            return False

    def search_by_class_name(self, class_name: str) -> List[Dict]:
        if not self.kb_instance: return []
        return self.kb_instance.search_by_name(class_name)

    def search_by_function_name(self, function_name: str) -> List[Dict]:
        if not self.kb_instance: return []
        return self.kb_instance.search_by_name(function_name)

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List:
        if not self.kb_instance: return []
        return self.kb_instance.semantic_search_classes(query, top_k)
    def semantic_search_functions(self, query: str, top_k: int = 10) -> List:
        if not self.kb_instance: return []
        return self.kb_instance.semantic_search_functions(query, top_k)
    def get_statistics(self) -> Dict:
        # 优先从 metadata.json 读取实际统计
        metadata_file = self.kb_dir / "metadata.json"
        if metadata_file.exists():
            try:
                meta = json.loads(metadata_file.read_text(encoding="utf-8"))
                sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(self.kb_dir) for f in fs)
                return {
                    "files": meta.get("files", 0),
                    "classes": meta.get("classes", 0),
                    "database_size_mb": round(sz / (1024 * 1024), 1),
                }
            except Exception:
                pass
        # fallback: zvec 内部文件计数（旧数据）
        if not any(f.name.startswith("manifest") for f in self.kb_dir.iterdir() if self.kb_dir.exists()):
            return {"files": 0, "classes": 0, "database_size_mb": 0}
        chunk_count = 0
        for root, dirs, files in os.walk(self.kb_dir):
            for f in files:
                if f.endswith('.sst') or f.endswith('.ipc') or f.endswith('.proxima'):
                    chunk_count += 1
        sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(self.kb_dir) for f in fs)
        return {"files": chunk_count, "classes": chunk_count // 2, "database_size_mb": round(sz / (1024*1024), 1)}

    def close(self):
        """关闭知识库连接"""
        if self.kb_instance:
            self.kb_instance.close()
            self.kb_instance = None
