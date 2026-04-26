# 工具模块导出
from .compile_project import compile_project, set_compiler_service
from .compile_file import compile_file
from .get_args import get_compiler_args
from .config import set_config_manager, search_compilers
from .environment import check_environment
from .coding_rules import get_coding_rules
from .knowledge_base import (
    set_delphi_kb_service,
    set_project_kb_service,
    set_thirdparty_kb_service,
    set_help_kb_service,
    search_knowledge,
    build_unified_knowledge_base,
    get_unified_knowledge_stats
)
from .project_knowledge_base import (
    init_project_knowledge_base,
    get_thirdparty_paths
)
from .help_knowledge_base import (
    build_help_knowledge_base,
    extract_help_chm,
    scan_help_html,
    build_help_kb_index,
    search_help,
    get_help_kb_stats,
    cancel_task
)
from .thirdparty_knowledge_base import (
    build_thirdparty_knowledge_base,
    set_thirdparty_knowledge_base_service
)
from .read_source_file import (
    read_source_file,
    search_and_read_file,
    set_knowledge_base_services
)
from .async_tasks import (
    start_async_task,
    get_task_status,
    get_task_result,
    list_tasks
)
from .pasfmt import (
    format_file,
    format_code,
    set_pasfmt_path,
    get_pasfmt_path,
    download_and_install_pasfmt,
    download_and_install_pasfmt_rad,
    check_pasfmt_installation,
    check_pasfmt_rad_installation,
    compile_from_source
)

__all__ = [
    # 编译工具
    'compile_project',
    'compile_file',
    'get_compiler_args',
    'set_compiler_service',
    # 配置工具
    'set_config_manager',
    'search_compilers',
    'check_environment',
    'get_coding_rules',
    # 知识库工具
    'set_delphi_kb_service',
    'set_project_kb_service',
    'set_thirdparty_kb_service',
    'set_help_kb_service',
    'search_knowledge',
    'build_unified_knowledge_base',
    'get_unified_knowledge_stats',
    # 项目知识库工具
    'init_project_knowledge_base',
    'get_thirdparty_paths',
    # 第三方库知识库工具
    'build_thirdparty_knowledge_base',
    'set_thirdparty_knowledge_base_service',
    # 帮助文档知识库工具
    'build_help_knowledge_base',
    'extract_help_chm',
    'scan_help_html',
    'build_help_kb_index',
    'search_help',
    'get_help_kb_stats',
    'cancel_task',
    # 源码文件读取工具
    'read_source_file',
    'search_and_read_file',
    'set_knowledge_base_services',
    # 异步任务工具
    'start_async_task',
    'get_task_status',
    'get_task_result',
    'list_tasks',
    # pasfmt 代码格式化工具
    'format_file',
    'format_code',
    'set_pasfmt_path',
    'get_pasfmt_path',
    'download_and_install_pasfmt',
    'download_and_install_pasfmt_rad',
    'check_pasfmt_installation',
    'check_pasfmt_rad_installation',
    'compile_from_source'
]
