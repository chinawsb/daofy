#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild All Knowledge Bases Script - with real-time progress report

Reports progress every 30 seconds

Usage: PYTHONIOENCODING=utf-8 python rebuild_all_kbs_with_progress.py
"""

import sys
import os
import time
import threading
import locale
from pathlib import Path

# Set environment variables
if 'PYTHONIOENCODING' not in os.environ:
    os.environ['PYTHONIOENCODING'] = 'utf-8'
if 'PYTHONUTF8' not in os.environ:
    os.environ['PYTHONUTF8'] = '1'

# Set locale
try:
    locale.setlocale(locale.LC_ALL, '')
except Exception:
    pass

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.logger import init_default_logger, get_logger

init_default_logger()
logger = get_logger(__name__)


class ProgressReporter:
    """Progress reporter - reports every N seconds"""
    
    def __init__(self, interval: int = 30):
        self.interval = interval
        self.running = True
        self.current_task = "Initializing..."
        self.start_time = time.time()
        self.last_report_time = self.start_time
        self.thread = None
        
    def start(self):
        """Start progress reporter thread"""
        self.running = True
        self.thread = threading.Thread(target=self._report_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop progress reporter"""
        self.running = False
        
    def update(self, task: str):
        """Update current task description"""
        self.current_task = task
        self.last_report_time = time.time()
        
    def _report_loop(self):
        """Report loop"""
        while self.running:
            elapsed = time.time() - self.start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            
            print(f"\n{'='*60}")
            print(f"Progress Report (Running {minutes}m {seconds}s)")
            print(f"   Current Task: {self.current_task}")
            print(f"{'='*60}\n")
            
            time.sleep(self.interval)
            
    def report(self, message: str):
        """Immediate report"""
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        print(f"\n[{minutes}m {seconds}s] {message}")


def get_kb_directories() -> dict:
    """Get all knowledge base directories"""
    data_dir = project_root / "data"
    
    kb_dirs = {
        "delphi-source": data_dir / "delphi-knowledge-base",
        "thirdparty": data_dir / "thirdparty-knowledge-base",
        "help": data_dir / "help-knowledge-base",
    }
    
    return kb_dirs


def check_kb_exists(kb_dir) -> bool:
    """Check if knowledge base exists"""
    if not kb_dir.exists():
        return False
    
    # Check for SQLite database
    db_file = kb_dir / "index" / "knowledge_base_vector.sqlite"
    if db_file.exists():
        return True
    
    # Check for source_index.json
    index_file = kb_dir / "index" / "source_index.json"
    return index_file.exists()


def rebuild_delphi_source_kb(reporter: ProgressReporter) -> bool:
    """Rebuild Delphi official source knowledge base"""
    reporter.update("Delphi Source KB")
    reporter.report("Starting rebuild Delphi source KB...")
    
    try:
        from src.services.knowledge_base.service import DelphiKnowledgeBaseService
        from src.utils.progress_tracker import ProgressInfo
        
        def progress_callback(progress_info: ProgressInfo):
            msg = f"Processing: {progress_info.current}/{progress_info.total} - {progress_info.message}"
            reporter.report(msg)
        
        kb_service = DelphiKnowledgeBaseService(progress_callback=progress_callback)
        kb_dir = kb_service.kb_dir
        
        if not check_kb_exists(kb_dir):
            reporter.report("KB not exists, skip")
            return True
        
        reporter.report(f"KB location: {kb_dir}")
        
        # Delete old database
        db_file = kb_dir / "index" / "knowledge_base_vector.sqlite"
        if db_file.exists():
            reporter.report(f"Deleting old DB: {db_file}")
            db_file.unlink()
        
        # Rebuild
        reporter.report("Starting scan and rebuild...")
        success = kb_service.build_knowledge_base(force_rebuild=True)
        
        if success:
            reporter.report("[OK] Delphi Source KB rebuild completed")
            return True
        else:
            reporter.report("[FAILED] Delphi Source KB rebuild failed")
            return False
            
    except Exception as e:
        reporter.report(f"[ERROR] Rebuild failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def rebuild_thirdparty_kb(reporter: ProgressReporter) -> bool:
    """Rebuild third-party library knowledge base"""
    reporter.update("Thirdparty KB")
    reporter.report("Starting rebuild thirdparty KB...")
    
    try:
        from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
        
        kb = ThirdPartyKnowledgeBase()
        kb_dir = kb.kb_dir
        
        if not check_kb_exists(kb_dir):
            reporter.report("KB not exists, skip")
            return True
        
        reporter.report(f"KB location: {kb_dir}")
        
        # Delete old database
        db_file = kb_dir / "index" / "knowledge_base_vector.sqlite"
        if db_file.exists():
            reporter.report(f"Deleting old DB: {db_file}")
            db_file.unlink()
        
        # Rebuild
        reporter.report("Starting scan and rebuild...")
        success = kb.build_thirdparty_knowledge_base(force_rebuild=True)
        
        if success:
            reporter.report("[OK] Thirdparty KB rebuild completed")
            return True
        else:
            reporter.report("[FAILED] Thirdparty KB rebuild failed")
            return False
            
    except Exception as e:
        reporter.report(f"[ERROR] Rebuild failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def rebuild_help_kb(reporter: ProgressReporter) -> bool:
    """Rebuild help documentation knowledge base"""
    reporter.update("Help Docs KB")
    reporter.report("Starting rebuild help docs KB...")
    
    try:
        from src.services.knowledge_base.help_knowledge_base import DelphiHelpKnowledgeBase
        
        def stage_progress_callback(stage: str, current: int, total: int, message: str):
            reporter.report(f"[{stage}] {message}")
        
        kb = DelphiHelpKnowledgeBase()
        kb_dir = kb.kb_dir
        
        if not check_kb_exists(kb_dir):
            reporter.report("KB not exists, skip")
            return True
        
        reporter.report(f"KB location: {kb_dir}")
        
        # Use files directory (extracted HTML files)
        files_dir = kb_dir / "files"
        
        if not files_dir.exists():
            reporter.report("files directory not exists, need to extract CHM first")
            return False
        
        # Delete old database
        db_file = kb_dir / "index" / "knowledge_base_vector.sqlite"
        if db_file.exists():
            reporter.report(f"Deleting old DB: {db_file}")
            db_file.unlink()
        
        reporter.report(f"Using directory: {files_dir}")
        
        # Rebuild (incremental build, using files directory)
        # Limit file count to avoid timeout
        reporter.report("Starting scan and rebuild (limit 2000 files/help)...")
        success = kb.build_knowledge_base_incremental(
            source_dir=str(files_dir),
            max_files_per_help=2000,
            progress_callback=stage_progress_callback
        )
        
        if success:
            reporter.report("[OK] Help Docs KB rebuild completed")
            return True
        else:
            reporter.report("[FAILED] Help Docs KB rebuild failed")
            return False
            
    except Exception as e:
        reporter.report(f"[ERROR] Rebuild failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function"""
    print("=" * 60)
    print("Rebuild All Knowledge Bases")
    print("=" * 60)
    print()
    print("Will rebuild the following knowledge bases:")
    print("  1. Delphi Official Source KB")
    print("  2. Third-party Library KB")
    print("  3. Help Documentation KB")
    print()
    print("Progress will be reported every 30 seconds...")
    print()
    print("NOTE: Run with PYTHONIOENCODING=utf-8 for proper Chinese output")
    print()
    
    # Show current knowledge base status
    print("Current knowledge base status:")
    kb_dirs = get_kb_directories()
    for name, kb_dir in kb_dirs.items():
        exists = check_kb_exists(kb_dir)
        status = "[OK]" if exists else "[MISSING]"
        print(f"  - {name}: {status}")
    print()
    
    # Start progress reporter
    reporter = ProgressReporter(interval=30)
    reporter.start()
    
    results = {}
    
    try:
        # Rebuild each knowledge base
        reporter.report("Starting rebuild task...")
        
        results["Delphi Source"] = rebuild_delphi_source_kb(reporter)
        results["Thirdparty"] = rebuild_thirdparty_kb(reporter)
        results["Help Docs"] = rebuild_help_kb(reporter)
        
    finally:
        # Stop progress reporter
        reporter.stop()
    
    # Show results
    print("\n" + "=" * 60)
    print("Rebuild Results Summary")
    print("=" * 60)
    for name, success in results.items():
        status = "[OK]" if success else "[FAILED]"
        print(f"  {name}: {status}")
    
    total_success = sum(1 for v in results.values() if v)
    total = len(results)
    print()
    print(f"Total: {total_success}/{total} succeeded")


if __name__ == "__main__":
    main()
