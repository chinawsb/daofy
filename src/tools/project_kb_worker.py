"""
项目知识库构建 Worker（独立子进程）
通过 sys.argv 接收参数，输出 JSON 结果到 stdout
"""

import sys
import os
import json
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def main():
    # 解析参数
    project_path = None
    rebuild = False
    progress_file = None
    
    for arg in sys.argv[1:]:
        if arg.startswith('--project-path='):
            project_path = arg.split('=', 1)[1]
        elif arg == '--force-rebuild':
            rebuild = True
        elif arg.startswith('--progress-file='):
            progress_file = arg.split('=', 1)[1]
    
    if not project_path:
        print(json.dumps({"error": "project_path is required"}), flush=True)
        sys.exit(1)
    
    # 添加项目根目录到 Python 路径
    script_dir = Path(__file__).resolve().parent.parent.parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    
    # 自定义进度回调
    def progress_callback(info):
        if progress_file:
            try:
                with open(progress_file, 'w', encoding='utf-8') as f:
                    # info 可能是 dict 或 ProgressInfo 对象
                    if hasattr(info, 'percent'):
                        percent = info.percent
                        msg = getattr(info, 'message', '')
                    elif isinstance(info, dict):
                        percent = info.get('percent', 0)
                        msg = info.get('message', '')
                    else:
                        percent = getattr(info, 'percent', 0)
                        msg = getattr(info, 'message', '')
                    f.write(json.dumps({
                        'percent': percent,
                        'message': str(msg),
                    }))
            except Exception as e:
                logger.debug("进度写入失败: %s", str(e))
    
    from src.services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase
    
    t0 = time.time()
    try:
        kb = ProjectKnowledgeBase(project_path, progress_callback=progress_callback)
        success = kb.build_project_knowledge_base(rebuild=rebuild)
        stats = kb.get_statistics()
        elapsed = time.time() - t0
        
        result = {
            "success": success,
            "elapsed": elapsed,
            "statistics": stats,
            "project": success,
        }
        print(json.dumps(result), flush=True)
        
        # 写入 final 信号到进度文件
        if progress_file:
            try:
                with open(progress_file, 'w', encoding='utf-8') as f:
                    f.write(json.dumps({
                        'percent': 100,
                        'message': '完成',
                        'done': True
                    }))
            except Exception as e:
                logger.debug("进度写入失败: %s", str(e))
    except Exception as e:
        import traceback
        result = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        print(json.dumps(result), flush=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
