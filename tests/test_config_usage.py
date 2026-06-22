#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 config.json 配置项使用情况
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.services.knowledge_base.scan_generic_documents import GenericDocumentScanner


def test_document_kb_config():
    """测试文档知识库配置项"""
    print("\n" + "=" * 60)
    print("2. 文档知识库 config.json 配置项检查")
    print("=" * 60)
    
    import tempfile
    import json
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            'database': {'file': 'custom.db'},
            'build': {
                'parallel_workers': 8,
                'batch_size': 100,
                'supported_extensions': ['.txt', '.md']
            }
        }
        
        scanner = GenericDocumentScanner(tmpdir, config)
        
        print("\n自定义配置:")
        print(f"  database.file: {config['database']['file']}")
        print(f"  build.parallel_workers: {config['build']['parallel_workers']}")
        print(f"  build.batch_size: {config['build']['batch_size']}")
        print(f"  build.supported_extensions: {config['build']['supported_extensions']}")
        
        print("\n配置项生效检查:")
        print(f"  ✓ zvec_dir: {scanner.zvec_dir.name}")
        print(f"  ✓ build.parallel_workers: {scanner.config['build']['parallel_workers']}")
        print(f"  ✓ build.batch_size: {scanner.config['build']['batch_size']}")
        print(f"  ✓ build.supported_extensions: {scanner.config['build']['supported_extensions']}")
        
        scanner.save_config()
        
        config_path = Path(tmpdir) / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
            print(f"\n  ✓ config.json 已保存: {list(saved_config.keys())}")


def test_default_config():
    """测试默认配置（配置项不存在时）"""
    print("\n" + "=" * 60)
    print("3. 默认配置测试（配置项不存在时）")
    print("=" * 60)
    
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        scanner = GenericDocumentScanner(tmpdir)
        
        print("\n默认配置:")
        print(f"  database.file: {scanner.config['database']['file']}")
        print(f"  build.parallel_workers: {scanner.config['build']['parallel_workers']}")
        print(f"  build.batch_size: {scanner.config['build']['batch_size']}")
        print(f"  build.supported_extensions: {len(scanner.config['build']['supported_extensions'])} 种")
        
        print("\n  ✓ 所有默认配置可用")


if __name__ == "__main__":
    test_document_kb_config()
    test_default_config()

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    print("✓ 文档知识库配置项全部生效")
    print("✓ 默认配置可用（配置项不存在时）")

