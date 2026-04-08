# -*- coding: utf-8 -*-
"""测试执行服务"""

import os
import sys
import re
import json
import base64
import subprocess
import threading
from typing import Any

from services.session_service import (
    get_session_status,
    get_session_logs,
    log_message,
    agent_status,
)
from services.process_manager import kill_process, register_process, unregister_process
from services.knowledge_service import (
    load_multiple_knowledge,
    current_knowledge_content,
)
from services.report_service import load_latest_report_data, format_test_summary
from config import PLAYWRIGHT_DIR, SINGLE_TEST_REPORT_DIR, CONCURRENT_REPORT_DIR

# Agent引用（多用户会话隔离）
_get_agent_func = None


def set_get_agent(get_agent_func):
    """设置获取 Agent 实例的函数"""
    global _get_agent_func
    _get_agent_func = get_agent_func


def get_agent(session_id: str = ""):
    """获取会话对应的 Agent 实例"""
    if _get_agent_func:
        return _get_agent_func(session_id)
    return None


# 兼容旧代码
agent: Any = None


def set_agent(agent_instance):
    """设置Agent实例（已废弃，使用 set_get_agent）"""
    global agent
    agent = agent_instance


def execute_test(url: str, questions: list, session_id: str = ""):
    """执行单网站测试"""

    # 先终止该会话之前的单测试进程
    kill_process(session_id, "single")

    status = get_session_status(session_id) if session_id else agent_status
    logs = get_session_logs(session_id) if session_id else get_session_logs("")

    # 参数验证
    if not url:
        log_message("[ERROR] 未设置测试URL", "ERROR", session_id=session_id)
        logs.put({
            "type": "test_complete",
            "message": "测试失败: 未设置测试URL，请先在设置中配置测试网站地址",
            "session_id": session_id,
        })
        status["is_running"] = False
        return

    # 计算问题数
    total = sum(len(q) if isinstance(q, list) else 1 for q in questions)

    if total == 0:
        log_message("[ERROR] 没有测试问题", "ERROR", session_id=session_id)
        logs.put({
            "type": "test_complete",
            "message": "测试失败: 没有测试问题，请先生成问题",
            "session_id": session_id,
        })
        status["is_running"] = False
        return

    # 获取知识库内容 - 优先使用session记住的知识库
    knowledge_content = ""
    knowledge_source = ""
    # 使用会话隔离的 Agent
    session_agent = get_agent(session_id)
    if (
        session_agent
        and hasattr(session_agent, "pending_knowledge_content")
        and session_agent.pending_knowledge_content
    ):
        knowledge_content = session_agent.pending_knowledge_content
        knowledge_source = "agent.pending_knowledge_content"
    else:
        # 从session状态获取上次选择的知识库文件（支持多选）
        last_knowledge = status.get("last_knowledge", "")
        if last_knowledge:
            knowledge_content = load_multiple_knowledge(last_knowledge)
            knowledge_source = f"session.last_knowledge={last_knowledge}"
        elif current_knowledge_content:
            knowledge_content = current_knowledge_content
            knowledge_source = "global.current_knowledge_content"

    process = None
    try:
        log_message(f"[START] 开始测试 {url}", "INFO", session_id=session_id)
        log_message(f"[INFO] 测试问题数: {total}", "INFO", session_id=session_id)

        # 打印知识库加载状态
        if knowledge_content:
            log_message(
                f"[KNOWLEDGE] 已加载知识库 ({len(knowledge_content)} 字符) 来源: {knowledge_source}",
                "INFO",
                session_id=session_id,
            )
        else:
            log_message(
                "[KNOWLEDGE] 未加载知识库，裁判评估将不可用",
                "WARN",
                session_id=session_id,
            )

        if session_agent:
            session_agent.tools.update_test_questions(questions)

        logs.put(
            {"type": "test_start", "url": url, "total": total, "session_id": session_id}
        )

        # 运行测试脚本
        script_path = os.path.join(PLAYWRIGHT_DIR, "solo_worker_PlayWright", "main.py")

        if os.path.exists(script_path):
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            if session_id:
                env["SESSION_ID"] = session_id

            # 传递登录凭据
            username = status.get("username", "")
            password = status.get("password", "")
            bot_name = status.get("bot_name", "")
            if username:
                env["TEST_USERNAME"] = username
            if password:
                env["TEST_PASSWORD"] = password
            if bot_name:
                env["TEST_BOT_NAME"] = bot_name

            # 传递测试 URL
            if url:
                env["TEST_URL"] = url
                env["TEST_LOGIN_URL"] = url

            # 传递知识库内容（用于裁判评估）
            if knowledge_content:
                env["KNOWLEDGE_CONTENT_B64"] = base64.b64encode(
                    knowledge_content.encode("utf-8")
                ).decode("ascii")

            # 传递 BOT 人设
            bot_persona = status.get("bot_persona", "")
            log_message(
                f"[DEBUG] session_id={session_id}, bot_persona={bot_persona!r}, status_keys={list(status.keys())}",
                "INFO",
                session_id=session_id,
            )
            if bot_persona:
                env["BOT_PERSONA"] = bot_persona
                log_message(
                    f"[BOT_PERSONA] 已设置BOT人设: {bot_persona}",
                    "INFO",
                    session_id=session_id,
                )
            else:
                log_message(
                    f"[BOT_PERSONA] 未设置BOT人设 (session_id={session_id})",
                    "WARN",
                    session_id=session_id,
                )

            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=os.path.dirname(script_path),
                env=env,
                encoding="utf-8",
                errors="replace",
            )

            # 注册进程
            register_process(session_id, "single", process)

            question_index = 0
            current_question = ""
            stdout = process.stdout
            if stdout:
                for line in stdout:
                    line = line.strip()
                    if line:
                        log_message(line, "INFO", session_id=session_id)

                        # 检测问题行
                        q_match = re.match(r"\[(\d+)/(\d+)\]\s*问题[:：]?\s*(.+)", line)
                        if q_match:
                            question_index = int(q_match.group(1))
                            current_question = q_match.group(3)
                            progress = (
                                int((question_index / total) * 100) if total > 0 else 0
                            )
                            status["progress"] = min(progress, 95)
                            logs.put(
                                {
                                    "type": "test_progress",
                                    "progress": status["progress"],
                                    "current": question_index,
                                    "total": total,
                                    "question": current_question,
                                    "session_id": session_id,
                                }
                            )

                        # 检测回答行
                        a_match = re.match(r"回答[:：]?\s*(.+)", line)
                        if a_match and current_question:
                            logs.put(
                                {
                                    "type": "test_result",
                                    "index": question_index,
                                    "question": current_question,
                                    "answer": a_match.group(1),
                                    "response_time": 0,
                                    "success": True,
                                    "session_id": session_id,
                                }
                            )

            process.wait()
            log_message("[DONE] 测试脚本执行完成", session_id=session_id)

            # 读取报告
            report_dir = (
                os.path.join(SINGLE_TEST_REPORT_DIR, session_id)
                if session_id
                else SINGLE_TEST_REPORT_DIR
            )
            report_data = load_latest_report_data(report_dir)

            if not report_data:
                log_message("[FAILED] 测试未能完成", "ERROR", session_id=session_id)
                logs.put(
                    {
                        "type": "test_complete",
                        "message": "测试未能完成，请检查日志",
                        "session_id": session_id,
                    }
                )
                status["is_running"] = False
                return

            results = report_data.get("results", [])
            accuracy_stats = report_data.get("accuracy_stats")
            epr_stats = report_data.get("epr_stats")
            memory_recall_stats = report_data.get("memory_recall_stats")

            # 将新指标合并到 accuracy_stats 中供前端展示
            if accuracy_stats:
                if epr_stats:
                    accuracy_stats["epr_stats"] = epr_stats
                if memory_recall_stats:
                    accuracy_stats["memory_recall_stats"] = memory_recall_stats

            # 裁判评估
            if not accuracy_stats and knowledge_content and results:
                log_message("[JUDGE] 开始裁判评估...", session_id=session_id)
                try:
                    import importlib.util

                    judge_path = os.path.join(PLAYWRIGHT_DIR, "judge.py")
                    spec = importlib.util.spec_from_file_location("judge", judge_path)
                    if spec and spec.loader:
                        judge_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(judge_module)
                        results = judge_module.batch_judge(results, knowledge_content)
                        accuracy_stats = judge_module.calculate_accuracy(results)
                        log_message(
                            f"[JUDGE] 精确率: {accuracy_stats['accuracy_rate']}%",
                            session_id=session_id,
                        )
                except Exception as e:
                    log_message(
                        f"[JUDGE] 裁判评估失败: {e}", "ERROR", session_id=session_id
                    )

            # 推送结果
            if results:
                logs.put(
                    {
                        "type": "qa_pairs",
                        "results": results,
                        "accuracy_stats": accuracy_stats,
                        "session_id": session_id,
                    }
                )

            logs.put(
                {
                    "type": "test_complete",
                    "message": format_test_summary(report_data, accuracy_stats),
                    "session_id": session_id,
                }
            )
        else:
            log_message(
                f"[ERROR] 脚本不存在: {script_path}", "ERROR", session_id=session_id
            )
            logs.put(
                {
                    "type": "test_complete",
                    "message": "测试脚本不存在",
                    "session_id": session_id,
                }
            )
    except Exception as e:
        log_message(f"[ERROR] 测试失败: {e}", "ERROR", session_id=session_id)
        logs.put(
            {
                "type": "test_complete",
                "message": f"测试失败: {e}",
                "session_id": session_id,
            }
        )
    finally:
        status["progress"] = 100
        status["is_running"] = False
        unregister_process(session_id, "single")
        log_message("[DONE] 测试完成", "SUCCESS", session_id=session_id)


def execute_concurrent_test(
    session_id: str, username: str, password: str, target_sites: list = None
):
    """执行并发测试"""

    # 先终止该会话之前的并发测试进程
    kill_process(session_id, "concurrent")

    status = get_session_status(session_id)
    process = None

    # 获取用户选择的网站，如果没有则使用默认（所有网站）
    if target_sites is None:
        target_sites = status.get("target_sites", [])

    # 从 session 状态读取配置（多用户隔离）
    worker_count = status.get("worker_count", 1)
    question_count = status.get("question_count", 5)

    try:
        script_path = os.path.join(PLAYWRIGHT_DIR, "max_worker", "main.py")

        env = os.environ.copy()
        if username:
            env["TEST_USERNAME"] = username
        if password:
            env["TEST_PASSWORD"] = password
        env["SESSION_ID"] = session_id

        # 传递配置参数（多用户隔离，通过环境变量）
        env["WORKERS_PER_SITE"] = str(worker_count)
        env["TEST_QUESTION_COUNT"] = str(question_count)

        # 传递用户选择的网站索引
        if target_sites:
            env["TARGET_SITES"] = ",".join(map(str, target_sites))
            log_message(
                f"[CONCURRENT] 已设置 TARGET_SITES={env['TARGET_SITES']}",
                "INFO",
                session_id=session_id,
            )

        # 传递知识库 - 优先使用session记住的知识库
        knowledge_content = ""
        knowledge_source = ""
        # 使用会话隔离的 Agent
        session_agent = get_agent(session_id) if _get_agent_func else None
        if (
            session_agent
            and hasattr(session_agent, "pending_knowledge_content")
            and session_agent.pending_knowledge_content
        ):
            knowledge_content = session_agent.pending_knowledge_content
            knowledge_source = "agent.pending_knowledge_content"
        else:
            # 从session状态获取上次选择的知识库文件（支持多选）
            last_knowledge = status.get("last_knowledge", "")
            if last_knowledge:
                knowledge_content = load_multiple_knowledge(last_knowledge)
                knowledge_source = f"session.last_knowledge={last_knowledge}"
            elif current_knowledge_content:
                knowledge_content = current_knowledge_content
                knowledge_source = "global.current_knowledge_content"

        # 打印知识库加载状态
        if knowledge_content:
            log_message(
                f"[KNOWLEDGE] 已加载知识库 ({len(knowledge_content)} 字符) 来源: {knowledge_source}",
                "INFO",
                session_id=session_id,
            )
            env["KNOWLEDGE_CONTENT_B64"] = base64.b64encode(
                knowledge_content.encode("utf-8")
            ).decode("ascii")
        else:
            log_message(
                "[KNOWLEDGE] 未加载知识库，裁判评估将不可用",
                "WARN",
                session_id=session_id,
            )

        # 传递 BOT 人设
        bot_persona = status.get("bot_persona", "")
        log_message(
            f"[DEBUG] 并发测试 session_id={session_id}, bot_persona={bot_persona!r}",
            "INFO",
            session_id=session_id,
        )
        if bot_persona:
            env["BOT_PERSONA"] = bot_persona
            log_message(
                f"[BOT_PERSONA] BOT人设: {bot_persona}", "INFO", session_id=session_id
            )
        else:
            log_message(
                f"[BOT_PERSONA] 并发测试未设置BOT人设", "WARN", session_id=session_id
            )

        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=os.path.dirname(script_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        # 注册进程
        register_process(session_id, "concurrent", process)

        if process.stdout:
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    log_message(line.strip(), session_id=session_id)

        log_message("并发测试完成", session_id=session_id)
    except Exception as e:
        log_message(f"并发测试出错: {e}", "ERROR", session_id=session_id)
    finally:
        status["is_running"] = False
        unregister_process(session_id, "concurrent")
