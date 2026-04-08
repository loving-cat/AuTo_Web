# -*- coding: utf-8 -*-
"""服务层模块"""

from services.session_service import (
    get_session_status, get_session_logs, session_status, session_logs,
    agent_status, log_message, get_log_files, read_log_file
)
from services.process_manager import kill_process, register_process, unregister_process, session_processes
from services.knowledge_service import load_knowledge_content, load_multiple_knowledge, load_saved_questions
from services.report_service import load_latest_report_data, format_test_summary
from services.test_executor import execute_test, execute_concurrent_test
from services.product_service import (
    load_product_catalog, load_multiple_catalogs, format_product_for_prompt
)

__all__ = [
    # Session
    "get_session_status",
    "get_session_logs",
    "session_status",
    "session_logs",
    "agent_status",
    "log_message",
    # Log persistence
    "get_log_files",
    "read_log_file",
    # Process
    "kill_process",
    "register_process",
    "unregister_process",
    "session_processes",
    # Knowledge
    "load_knowledge_content",
    "load_multiple_knowledge",
    "load_saved_questions",
    # Report
    "load_latest_report_data",
    "format_test_summary",
    # Test
    "execute_test",
    "execute_concurrent_test",
    # Product
    "load_product_catalog",
    "load_multiple_catalogs",
    "format_product_for_prompt",
]
