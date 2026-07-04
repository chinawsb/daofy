"""Shared constants for Daofy runtime modules."""

from typing import Final


DEFAULT_ENCODING: Final[str] = "utf-8"
DEFAULT_ENCODING_SIG: Final[str] = "utf-8-sig"

TIMEOUT_DELPHI_COMPILE: Final[int] = 60
TIMEOUT_DELPHI_PROJECT_COMPILE: Final[int] = 300
TIMEOUT_GIT_QUICK: Final[int] = 30
TIMEOUT_GIT_REV_PARSE: Final[int] = 10
TIMEOUT_GIT_REMOTE_SYNC: Final[int] = 45
TIMEOUT_GIT_LOCAL_SLOW: Final[int] = 60
TIMEOUT_GIT_PUSH: Final[int] = 300
TIMEOUT_GIT_FETCH_PULL: Final[int] = 120
TIMEOUT_NETWORK_REQUEST: Final[int] = 30
TIMEOUT_NETWORK_DOWNLOAD: Final[int] = 120
TIMEOUT_NETWORK_DOWNLOAD_LARGE: Final[int] = 300
TIMEOUT_PASFMT: Final[int] = 30
TIMEOUT_AUDIT: Final[int] = 300
TIMEOUT_SUBPROCESS_SHORT: Final[int] = 5
TIMEOUT_PROCESS_TERMINATE: Final[int] = 5
TIMEOUT_WAITFOR_PIPE: Final[int] = 10
TIMEOUT_PROCESS_QUERY: Final[int] = 10
TIMEOUT_MSBUILD_DISCOVERY: Final[int] = 15
TIMEOUT_BROWSER_PDF_RENDER: Final[int] = 60
TIMEOUT_BROWSER_DOM_RENDER: Final[int] = 30
TIMEOUT_BROWSER_VIRTUAL_TIME_BUDGET_MS: Final[int] = 5000
TIMEOUT_ARCHIVE_7Z: Final[int] = 120
TIMEOUT_DFM_COMPILER_DISCOVERY: Final[int] = 5
TIMEOUT_DFM_COMPILE: Final[int] = 30
TIMEOUT_DFM_CONVERT: Final[int] = 15
TIMEOUT_DELPHI_COMPONENT_COMPILE: Final[int] = 60
TIMEOUT_COMPONENT_CREATION_EXEC: Final[int] = 15
TIMEOUT_DOCUMENT_CONVERT: Final[int] = 30
TIMEOUT_DOCUMENT_ARCHIVE_EXTRACT: Final[int] = 600
TIMEOUT_DOCUMENT_ARCHIVE_LIST: Final[int] = 60
TIMEOUT_DOCUMENT_WORKER_RESULT: Final[float] = 5.0
TIMEOUT_DOCUMENT_WORKER_JOIN: Final[int] = 30
TIMEOUT_PASFMT_GIT_CLONE: Final[int] = 300
TIMEOUT_PASFMT_BUILD: Final[int] = 600
TIMEOUT_UPDATER_GIT_PULL: Final[int] = 60
TIMEOUT_EXPERIENCE_TOOL: Final[int] = 30
TIMEOUT_GENERATE_COPYRIGHT: Final[int] = 300
TIMEOUT_AUTOMATION_GUI: Final[int] = 300

RETRY_INTERVAL_DAOFY_UPDATE: Final[int] = 60
MAX_RETRIES_DAOFY_UPDATE: Final[int] = 10
RETRY_INTERVAL_GIT_PUSH: Final[int] = 300
MAX_RETRIES_GIT_PUSH: Final[int] = 12
RETRY_INTERVAL_VERSION_CHECK: Final[int] = 300
MAX_RETRIES_VERSION_CHECK: Final[int] = 12

BUFFER_SIZE_1MB: Final[int] = 1048576
CHUNK_SIZE_DOWNLOAD: Final[int] = 8192
CHUNK_SIZE_DOCUMENT_LINES: Final[int] = 5000

DEFAULT_TOP_K: Final[int] = 200
DEFAULT_MAX_LINES: Final[int] = 500
MAX_LINES_LIMIT: Final[int] = 1000
DEFAULT_MAX_PAGES: Final[int] = 100
DEFAULT_MAX_ENTRIES: Final[int] = 100

POLL_INTERVAL_AUTOMATION: Final[float] = 0.3
POLL_INTERVAL_PIPE_MS: Final[int] = 50
TIMEOUT_AUTOMATION_PIPE_MS: Final[int] = 5000
SQLITE_BUSY_TIMEOUT_MS: Final[int] = 5000

OCR_MAX_LONG_EDGE: Final[int] = 2560
OCR_MAX_SHORT_EDGE: Final[int] = 640

REG_KEY_EMBARCADERO_BDS: Final[str] = r"SOFTWARE\Embarcadero\BDS"
REG_KEY_EMBARCADERO_STUDIO: Final[str] = r"SOFTWARE\Embarcadero\Studio"

DIR_HISTORY: Final[str] = "__history"
DIR_DELPHI_KB: Final[str] = ".delphi-kb"
DIR_RECOVERY: Final[str] = "__recovery"
CONFIG_COMPILERS: Final[str] = "config/compilers.json"
CONFIG_LOGGING: Final[str] = "config/logging_config.json"
CONFIG_COPYRIGHT: Final[str] = "docs/copyright/copyright.json"

SOURCE_SCAN_EXCLUDED_DIRS: Final[frozenset[str]] = frozenset(
    {
        DIR_DELPHI_KB,
        "thirdpart",
        "vendor",
        "lib",
        "packages",
        "__pycache__",
        ".git",
        ".svn",
        "node_modules",
        "dist",
        "bin",
        "obj",
        "win32",
        "win64",
        DIR_HISTORY,
        DIR_RECOVERY,
        "backup",
        "logs",
    }
)
EXCLUDED_DIRS: Final[frozenset[str]] = SOURCE_SCAN_EXCLUDED_DIRS

DEPENDENCY_SCAN_EXCLUDED_DIRS: Final[frozenset[str]] = frozenset(
    {
        DIR_RECOVERY,
        DIR_HISTORY,
        "backup",
        ".git",
        ".svn",
        "win32",
        "win64",
        "debug",
        "release",
    }
)

EXAMPLE_SCAN_EXCLUDED_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        "__pycache__",
        "win32",
        "win64",
        DIR_HISTORY,
        DIR_RECOVERY,
        "backup",
        ".svn",
        "node_modules",
    }
)
