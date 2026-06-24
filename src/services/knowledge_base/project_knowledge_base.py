"""
项目知识库服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

为用户项目提供知识库功能:
1. 从 .dproj 文件读取三方库目录并构建知识库
2. 为项目源码构建知识库,支持增量更新
3. 支持 .dproj/.dpr/.dpk 项目文件类型（仅 .dproj 可提取三方库路径）
"""

import os
import json
import time
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable
from src.utils.logger import get_logger
from src.utils.dproj_parser import DprojParser
from .delphi_chunker import chunk_file_list
from .zvec_adapter import ZVecKnowledgeBaseAdapter

logger = get_logger(__name__)


class ProjectKnowledgeBase:
    """项目知识库管理器（ZVec 版）"""

    def __init__(self, project_path: str, progress_callback: Optional[Callable] = None):
        """
        初始化项目知识库

        Args:
            project_path: 项目文件路径 (.dproj / .dpr / .dpk)
            progress_callback: 进度回调函数
        """
        self.project_path = Path(project_path)
        self.project_dir = self.project_path.parent
        self.project_name = self.project_path.stem
        self.progress_callback = progress_callback

        # 项目知识库目录
        self.kb_dir = self.project_dir / ".delphi-kb"
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        # ZVec 知识库适配器
        self.project_kb: Optional[ZVecKnowledgeBaseAdapter] = None
        self.thirdparty_kb: Optional[ZVecKnowledgeBaseAdapter] = None

        logger.info(f"项目知识库初始化: {self.project_name}")

    def _get_delphi_install_paths(self) -> Set[str]:
        """
        获取 Delphi 安装路径列表

        Returns:
            Delphi 安装路径集合
        """
        delphi_paths = set()

        try:
            import winreg

            # 打开 Delphi 注册表键
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Embarcadero\BDS")

            # 遍历所有版本
            i = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, i)
                    i += 1

                    # 获取版本信息
                    version_path = winreg.OpenKey(key, version_key)
                    try:
                        root_dir = winreg.QueryValueEx(version_path, "RootDir")[0]
                        if root_dir:
                            # 添加 Delphi 安装路径及其子目录
                            delphi_paths.add(Path(root_dir).resolve())
                    except OSError:
                        pass
                    finally:
                        winreg.CloseKey(version_path)

                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            logger.warning(f"获取 Delphi 安装路径失败: {e}")

        return delphi_paths

    def get_thirdparty_paths_from_dproj(self) -> List[str]:
        """
        从 .dproj 文件中提取三方库路径

        Returns:
            三方库路径列表
        """
        if self.project_path.suffix.lower() != '.dproj':
            logger.debug("项目文件不是 .dproj 格式（%s），跳过三方库路径提取", self.project_path.suffix)
            return []

        parser = DprojParser(str(self.project_path))
        if not parser.parse():
            logger.error("解析 .dproj 文件失败")
            return []

        # 获取单元搜索路径
        unit_paths = parser.get_unit_search_paths()

        # 获取 Delphi 安装路径（用于排除）
        delphi_install_paths = self._get_delphi_install_paths()

        # 过滤出三方库路径 (排除项目自身目录和 Delphi 安装目录)
        thirdparty_paths = []
        for path in unit_paths:
            path_obj = Path(path)

            # 检查路径是否存在
            if not path_obj.exists():
                continue

            # 解析为绝对路径
            path_obj = path_obj.resolve()

            # 检查是否在 Delphi 安装目录下
            is_delphi_path = False
            for delphi_path in delphi_install_paths:
                try:
                    path_obj.relative_to(delphi_path)
                    is_delphi_path = True
                    break
                except ValueError:
                    pass

            if is_delphi_path:
                # 跳过 Delphi 安装目录下的路径
                continue

            # 检查是否在项目目录外
            try:
                # 相对路径检查
                path_obj.relative_to(self.project_dir)
            except ValueError:
                # 在项目目录外,是三方库
                thirdparty_paths.append(str(path_obj))
            else:
                # 在项目目录内,检查是否是常见的三方库目录名
                path_lower = str(path_obj).lower()
                thirdparty_keywords = ['thirdpart', 'thirdparty', 'vendor', 'lib', 'libs', 'packages', 'components']
                if any(kw in path_lower for kw in thirdparty_keywords):
                    thirdparty_paths.append(str(path_obj))

        logger.info(f"从 .dproj 提取到 {len(thirdparty_paths)} 个三方库路径")
        return thirdparty_paths

    def _calculate_paths_hash(self, paths: List[str]) -> str:
        """计算路径列表的签名（排序后用分号连接，无需 MD5）"""
        return ";".join(sorted(paths))

    def _calculate_source_hash(self, source_dir: Path, extensions: Set[str] = None) -> str:
        """
        计算源码目录的变更签名（基于文件数量+总大小+最新修改时间）

        跳过第三方库路径和 .delphi-kb 目录，避免将 KB 自身或第三方库的变更
        误判为项目源码变更，同时大幅加快计算速度。

        使用 `文件数|总字节数|最新mtime` 三元组而非 MD5 哈希，因为：
        - 不需要逐文件计算 MD5（IO + CPU 开销大）
        - 文件数/总大小/最新时间的变化能覆盖所有增删改场景
        - config.json 中指定 hash_mode=md5 时才需逐文件 MD5

        Args:
            source_dir: 源码目录
            extensions: 文件扩展名集合

        Returns:
            签名值 (文件数|总大小|最新修改时间)
        """
        if extensions is None:
            extensions = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc'}

        # 需要跳过的目录名（第三方库、知识库、系统目录等）
        skip_dir_names = {'.delphi-kb', 'thirdpart', 'vendor', 'lib', 'packages',
                          '__pycache__', '.git', '.svn', 'node_modules', 'dist', 'bin', 'obj',
                          'Win32', 'Win64', '__history', '__recovery', 'backup', 'logs'}

        # 读取经过 .dproj 交叉验证的三方库路径前缀，精确跳过
        # （仅跳过那些同时出现在共享KB和.dproj三方库路径中的目录，
        #  避免项目源码目录因意外出现在 IDE 全局库路径中被误跳）
        skip_paths_normalized = self._get_verified_thirdparty_prefixes()

        total_files = 0
        total_size = 0
        latest_mtime = 0.0

        for root, dirs, files in os.walk(source_dir):
            # 跳过不需要的目录（不进入遍历）
            dirs[:] = [d for d in dirs if d.lower() not in skip_dir_names]

            root_normalized = str(Path(root).resolve())
            if root_normalized in skip_paths_normalized:
                dirs[:] = []
                continue

            for file in files:
                if Path(file).suffix.lower() in extensions:
                    try:
                        stat = (Path(root) / file).stat()
                        total_files += 1
                        total_size += stat.st_size
                        if stat.st_mtime > latest_mtime:
                            latest_mtime = stat.st_mtime
                    except Exception as e:
                        logger.debug("忽略非致命异常: %s", str(e))

        return f"{total_files}|{total_size}|{latest_mtime}"

    def _get_shared_thirdparty_paths(self) -> Set[str]:
        """
        读取 MCP 服务器共享第三方知识库中已扫描的路径列表。

        共享知识库路径:
          <项目根>/data/thirdparty-knowledge-base/thirdparty_paths.json

        Returns:
            已扫描的路径集合 (绝对路径,已规范化)
        """
        # 从当前文件位置推导项目根目录: src/services/know_base/ → 上3层 = 项目根
        _project_root = Path(__file__).parent.parent.parent.parent
        shared_paths_file = (
            _project_root / "data" / "thirdparty-knowledge-base" / "thirdparty_paths.json"
        )
        if not shared_paths_file.exists():
            logger.info("共享第三方知识库路径文件不存在,跳过检查")
            return set()

        try:
            with open(shared_paths_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw_paths = data.get("paths", [])
            # 规范化所有路径 (解析真实大小写)
            normalized = set()
            for p in raw_paths:
                try:
                    normalized.add(str(Path(p).resolve()))
                except Exception:
                    normalized.add(p)
            logger.info(f"从共享知识库读取到 {len(normalized)} 个已扫描路径")
            return normalized
        except Exception as e:
            logger.warning(f"读取共享第三方知识库路径失败: {e}")
            return set()

    def _get_verified_thirdparty_prefixes(self) -> Set[str]:
        """
        获取经过验证的三方库路径前缀集合。

        只返回**同时满足**以下条件的路径：
        1. 出现在共享知识库 thirdparty_paths.json 中
        2. 在项目目录内 (self.project_dir 下)
        3. 也被 .dproj 文件认定为三方库路径

        三重校验确保项目源码目录不会因意外出现在 IDE 全局库路径中
        而被误判为三方库跳过的 bug。

        Returns:
            需要跳过的绝对路径集合 (已规范化)
        """
        shared = self._get_shared_thirdparty_paths()
        if not shared:
            return set()

        # 收集 .dproj 中在项目目录内的三方库路径
        dproj_inside = set()
        for p in self.get_thirdparty_paths_from_dproj():
            try:
                pp = Path(p).resolve()
                pp.relative_to(self.project_dir.resolve())
                dproj_inside.add(str(pp))
            except ValueError:
                pass  # 不在项目目录内，不参与排除判断

        if not dproj_inside:
            return set()

        # 交集：同时出现在共享 KB 和 .dproj 三方库路径中
        verified = set()
        for p in shared:
            pp_str = str(Path(p).resolve())
            if pp_str in dproj_inside:
                verified.add(pp_str)

        if verified:
            logger.info(f"项目源码扫描将跳过 {len(verified)} 个经验证的三方库目录")
        return verified


    def _should_skip_shared_path(self, file_path: Path, exclude_prefixes: Set[str]) -> bool:
        """检查文件是否在需要跳过的共享知识库路径下"""
        if not exclude_prefixes:
            return False
        file_str = str(file_path.resolve())
        for prefix_str in exclude_prefixes:
            if file_str == prefix_str or file_str.startswith(prefix_str + os.sep):
                return True
        return False

    def build_project_knowledge_base(self, rebuild: bool = False) -> bool:
        """
        构建项目源码知识库（ZVec 版）

        Args:
            rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        _build_start = time.time()

        # 迁移旧版 zvec_project/ 子目录到根目录
        from .zvec_adapter import _migrate_old_zvec_data
        old_zvec = self.kb_dir / "zvec_project"
        if old_zvec.exists() and old_zvec != self.kb_dir:
            _migrate_old_zvec_data(old_zvec, self.kb_dir)

        current_hash = self._calculate_source_hash(self.project_dir)
        if not rebuild:
            cached_hash = None
            hash_file = self.kb_dir / "source_hash.txt"
            if hash_file.exists():
                cached_hash = hash_file.read_text(encoding='utf-8').strip()
            if cached_hash == current_hash and any(f.name.startswith("manifest") for f in self.kb_dir.iterdir()):
                logger.info("项目源码知识库已是最新,跳过构建")
                return True

        logger.info("开始构建项目源码知识库 (ZVec)")
        self._report_progress(5, "扫描项目源码文件...")
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        # 收集项目源码文件
        exclude_prefixes = self._get_verified_thirdparty_prefixes()
        skip_dir_names = {'.delphi-kb', 'thirdpart', 'vendor', 'lib', 'packages',
                          '__pycache__', '.git', '.svn', 'node_modules', 'dist', 'bin', 'obj',
                          'Win32', 'Win64', '__history', '__recovery', 'backup', 'logs'}
        delphi_extensions = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc'}

        project_files: List[str] = []
        for root, dirs, files in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if d.lower() not in skip_dir_names]
            root_path = Path(root)
            if self._should_skip_shared_path(root_path, exclude_prefixes):
                dirs[:] = []
                continue
            for file in files:
                if Path(file).suffix.lower() in delphi_extensions:
                    project_files.append(str(root_path / file))

        self._report_progress(30, f"收集到 {len(project_files)} 个文件，开始 chunk...")

        # Chunk 所有文件
        chunks = chunk_file_list(project_files)
        if not chunks:
            logger.warning("项目源码未产生任何 chunk")
            return False
        logger.info(f"Chunk 完成: {len(chunks)} chunks 来自 {len(project_files)} 文件")
        self._report_progress(50, f"{len(chunks)} chunks，导入 ZVec...")

        # 构建 ZVec 知识库（展平到 kb_dir 根目录）
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
                # 重建：删集合目录后重新 create_and_open
                import shutil as _shutil
                _shutil.rmtree(kv_dir, ignore_errors=True)
                has_valid = False
        if not has_valid:
            if kv_path.exists():
                import shutil as _shutil
                _shutil.rmtree(kv_dir, ignore_errors=True)
            # 简化 schema：entity_name 合并到 chunk_text 中
            schema = CollectionSchema("project_kb", fields=[
                FieldSchema("chunk_text", DataType.STRING),
                FieldSchema("chunk_type", DataType.STRING),
                FieldSchema("base_class", DataType.STRING),
                FieldSchema("file_path", DataType.STRING),
                FieldSchema("start_line", DataType.INT32),
                FieldSchema("end_line", DataType.INT32),
            ])
            col = zvec.create_and_open(path=kv_dir, schema=schema)

        # 先插入数据
        BATCH = 500
        for offset in range(0, len(chunks), BATCH):
            batch = chunks[offset:offset + BATCH]
            docs = []
            for i, c in enumerate(batch):
                docs.append(Doc(
                    id=f"c{offset + i:07d}",
                    fields={
                        "chunk_text": (str(c['entity_name'])[:500] + "\n" + str(c['chunk_text'])[:99480]),
                        "chunk_type": c['chunk_type'],
                        "base_class": c['base_class'][:200],
                        "file_path": c['file_path'][:500],
                        "start_line": c['start_line'],
                        "end_line": c['end_line'],
                    },
                ))
            col.insert(docs)
            if (offset // BATCH) % 10 == 0:
                pct = 50 + int(offset / len(chunks) * 40)
                self._report_progress(pct, f"导入 {offset + BATCH}/{len(chunks)}")

        col.flush()

        # 再建索引
        col.create_index("chunk_text", FtsIndexParam(tokenizer_name="jieba"))
        col.create_index("chunk_type", InvertIndexParam())
        col.create_index("base_class", InvertIndexParam())
        col.optimize()
        col.flush()

        # 保存 source_hash
        hash_file = self.kb_dir / "source_hash.txt"
        hash_file.write_text(current_hash, encoding='utf-8')

        # 保存构建元数据
        class_count = sum(1 for c in chunks if c.get('chunk_type') in ('class', 'record', 'interface'))
        try:
            metadata = {
                "files": len(project_files),
                "classes": class_count,
                "chunks": len(chunks),
            }
            (self.kb_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"保存项目 KB metadata 失败: {e}")

        # 设置 project_kb 为 ZVec 适配器
        self.project_kb = ZVecKnowledgeBaseAdapter(str(self.kb_dir), source_dirs=[str(self.project_dir)])

        _duration = int(time.time() - _build_start)
        logger.info(f"项目知识库构建完成! {len(chunks)} chunks, 耗时 {_duration}s")
        self._report_progress(100, f"项目 KB: {len(chunks)} chunks, {_duration}s")
        return True

    def check_and_update_project_kb(self) -> bool:
        """
        检查项目源码是否有变更（ZVec 版用 source_hash.txt）

        Returns:
            True 表示知识库最新，False 表示已检测到变更
        """
        current_hash = self._calculate_source_hash(self.project_dir)
        cached_hash = None
        hash_file = self.kb_dir / "source_hash.txt"
        if hash_file.exists():
            cached_hash = hash_file.read_text(encoding='utf-8').strip()

        if current_hash != cached_hash:
            logger.info("检测到项目源码变动（搜索将使用旧知识库，请手动触发重建）")
            return False
        return True

    def load_knowledge_bases(self) -> bool:
        """
        加载 ZVec 知识库

        Returns:
            是否加载成功
        """
        try:
            # 迁移旧版 zvec_project/ 子目录到根目录
            from .zvec_adapter import _migrate_old_zvec_data
            old_zvec = self.kb_dir / "zvec_project"
            if old_zvec.exists() and old_zvec != self.kb_dir:
                _migrate_old_zvec_data(old_zvec, self.kb_dir)
            # 检查展平后的 ZVec 数据
            if any(f.name.startswith("manifest") for f in self.kb_dir.iterdir()):
                self.project_kb = ZVecKnowledgeBaseAdapter(str(self.kb_dir), source_dirs=[str(self.project_dir)])
                self.thirdparty_kb = self.project_kb
                logger.info(f"ZVec 知识库加载成功: {self.kb_dir}")
                return True
            return False
        except Exception as e:
            logger.error(f"加载 ZVec 知识库失败: {e}")
            return False

    def search_class(self, class_name: str, search_in: str = "all") -> List[Dict]:
        """
        搜索类

        Args:
            class_name: 类名
            search_in: 搜索范围 ("project", "thirdparty", "all")

        Returns:
            搜索结果
        """
        results = []

        # 检查并更新项目知识库
        self.check_and_update_project_kb()

        if search_in in ("project", "all") and self.project_kb:
            results.extend(self.project_kb.search_by_class_name(class_name))

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            results.extend(self.thirdparty_kb.search_by_class_name(class_name))

        return results

    def search_function(self, function_name: str, search_in: str = "all") -> List[Dict]:
        """
        搜索函数

        Args:
            function_name: 函数名
            search_in: 搜索范围 ("project", "thirdparty", "all")

        Returns:
            搜索结果
        """
        results = []

        # 检查并更新项目知识库
        self.check_and_update_project_kb()

        if search_in in ("project", "all") and self.project_kb:
            results.extend(self.project_kb.search_by_function_name(function_name))

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            results.extend(self.thirdparty_kb.search_by_function_name(function_name))

        return results

    def semantic_search(self, query: str, top_k: int = 10, search_in: str = "all") -> Dict:
        """
        语义搜索

        Args:
            query: 搜索查询
            top_k: 返回结果数量
            search_in: 搜索范围 ("project", "thirdparty", "all")

        Returns:
            搜索结果 {"classes": [...], "functions": [...]}
        """
        # 检查并更新项目知识库
        self.check_and_update_project_kb()

        result = {
            "classes": [],
            "functions": []
        }

        if search_in in ("project", "all") and self.project_kb:
            class_results = self.project_kb.semantic_search_classes(query, top_k)
            func_results = self.project_kb.semantic_search_functions(query, top_k)

            for class_name, score in class_results:
                exact = self.project_kb.search_by_class_name(class_name)
                if exact:
                    result["classes"].append({
                        "source": "project",
                        "score": score,
                        "data": exact[0]
                    })

            for func_name, score in func_results:
                exact = self.project_kb.search_by_function_name(func_name)
                if exact:
                    result["functions"].append({
                        "source": "project",
                        "score": score,
                        "data": exact[0]
                    })

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            class_results = self.thirdparty_kb.semantic_search_classes(query, top_k)
            func_results = self.thirdparty_kb.semantic_search_functions(query, top_k)

            for class_name, score in class_results:
                exact = self.thirdparty_kb.search_by_class_name(class_name)
                if exact:
                    result["classes"].append({
                        "source": "thirdparty",
                        "score": score,
                        "data": exact[0]
                    })

            for func_name, score in func_results:
                exact = self.thirdparty_kb.search_by_function_name(func_name)
                if exact:
                    result["functions"].append({
                        "source": "thirdparty",
                        "score": score,
                        "data": exact[0]
                    })

        # 按相似度排序
        result["classes"].sort(key=lambda x: x["score"], reverse=True)
        result["functions"].sort(key=lambda x: x["score"], reverse=True)

        return result

    def get_statistics(self) -> Dict:
        """
        获取知识库统计信息（ZVec 版）

        Returns:
            统计信息
        """
        stats = {"project": None, "thirdparty": None}

        # 优先从 metadata.json 读取实际统计
        metadata_file = self.kb_dir / "metadata.json"
        if metadata_file.exists():
            try:
                meta = json.loads(metadata_file.read_text(encoding="utf-8"))
                total_size = sum(
                    os.path.getsize(os.path.join(dp, f))
                    for dp, _, fs in os.walk(self.kb_dir) for f in fs
                )
                stats["project"] = {
                    "files": meta.get("files", 0),
                    "classes": meta.get("classes", 0),
                    "chunks": meta.get("chunks", 0),
                    "database_size_mb": round(total_size / (1024 * 1024), 1),
                }
                return stats
            except Exception:
                pass

        # fallback: zvec 内部文件计数（旧/无 metadata 数据）
        zvec_dir = self.kb_dir
        if not any(f.name.startswith("manifest") for f in zvec_dir.iterdir() if zvec_dir.exists()):
            return stats

        try:
            chunk_count = 0
            for root, dirs, files in os.walk(zvec_dir):
                for f in files:
                    if f.endswith('.sst') or f.endswith('.ipc') or f.endswith('.proxima'):
                        chunk_count += 1

            total_size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(zvec_dir) for f in fs
            )
            stats["project"] = {
                "files": chunk_count,
                "classes": chunk_count // 2,
                "database_size_mb": round(total_size / (1024 * 1024), 1),
            }
        except Exception as e:
            logger.debug(f"ZVec 统计失败: {e}")
        return stats

    def _report_progress(self, percent: float, message: str) -> None:
        """报告进度（安全调用 progress_callback）"""
        if self.progress_callback:
            try:
                self.progress_callback(percent, message)
            except Exception as e:
                logger.warning("progress_callback 执行失败: %s", e)

    def build_vectors(self, progress_callback=None) -> dict:
        """ZVec 版：索引已在插入时创建，此处无需操作"""
        return {"project": 0, "thirdparty": 0}

    def close(self):
        """关闭知识库连接"""
        if self.project_kb:
            try:
                self.project_kb.close()
            except Exception:
                pass
            self.project_kb = None
        self.thirdparty_kb = None
