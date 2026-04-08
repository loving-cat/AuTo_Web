# -*- coding: utf-8 -*-
"""聊天路由"""

import os
import json
import re
import queue
import threading
from flask import request, jsonify, Response

from routes import chat_bp
from services import (
    get_session_status, get_session_logs, agent_status, log_message,
    load_multiple_knowledge, load_saved_questions, load_knowledge_content,
    execute_test, load_multiple_catalogs, format_product_for_prompt
)
from config import PLAYWRIGHT_DIR

# Agent引用（多用户会话隔离）
_get_agent_func = None

def set_get_agent(get_agent_func):
    """设置获取 Agent 实例的函数"""
    global _get_agent_func
    _get_agent_func = get_agent_func

def get_agent_for_session(session_id: str = ""):
    """获取会话对应的 Agent 实例"""
    if _get_agent_func:
        return _get_agent_func(session_id)
    return None

# 兼容旧代码
agent = None
def set_agent(agent_instance):
    """设置Agent实例（已废弃）"""
    global agent
    agent = agent_instance


@chat_bp.route("/chat", methods=["POST"])
def chat():
    """聊天接口"""
    data = request.json or {}
    message = data.get("message", "")
    knowledge = data.get("knowledge", "")
    products = data.get("products", [])  # 商品库文件列表
    url = data.get("url", "")
    username = data.get("username", "")
    password = data.get("password", "")
    bot_name = data.get("bot_name", "Auto_Test_ONE")
    multi_turn_param = int(data.get("multi_turn", 1))
    session_id = data.get("session_id", "")
    
    if not message:
        return jsonify({"success": False, "error": "消息不能为空"})
    
    # 获取会话专属的 Agent 实例
    agent = get_agent_for_session(session_id)
    if not agent:
        return jsonify({
            "success": False, 
            "error": "Agent未初始化，请检查：1) .env文件是否存在 2) LLM_API_KEY是否配置 3) 查看服务器日志获取详细错误"
        })
    
    # 获取session状态
    status = get_session_status(session_id) if session_id else agent_status
    
    # 记住用户选择的知识库（支持多选）
    if knowledge:
        status["last_knowledge"] = knowledge
    
    try:
        if url:
            agent.tools.update_user_credentials(username or "auto", password or "auto", url)
        if bot_name:
            agent.tools.update_bot_config(bot_name)
        
        # 生成问题 - 使用前端选择的知识库或session记住的知识库
        effective_knowledge = knowledge or status.get("last_knowledge", "")
        
        # 检查是否要生成问题但没有知识库
        if "生成" in message and any(w in message for w in ["题", "问", "道", "个"]):
            if not effective_knowledge:
                return jsonify({
                    "success": False, 
                    "error": "请先从左上角选择知识库文件，然后再生成测试题。"
                })
            
            count_match = re.search(r"(\d+)", message)
            count = int(count_match.group(1)) if count_match else 20
            multi_turn = multi_turn_param
            
            turn_match = re.search(r"(\d+)\s*轮", message)
            if turn_match:
                multi_turn = int(turn_match.group(1))
            
            # 检测多语言要求
            language_requirements = []
            
            # 检测"多语言"关键词，自动包含繁中、简中、英文
            if "多语言" in message:
                language_requirements = ["简体中文", "繁体中文", "英文"]
            else:
                # 单独检测各语言
                if "简体中文" in message or "简体" in message:
                    language_requirements.append("简体中文")
                if "繁体中文" in message or "繁体" in message:
                    language_requirements.append("繁体中文")
                if "英文" in message or "英语" in message or "English" in message.lower():
                    language_requirements.append("英文")
                if "日文" in message or "日语" in message:
                    language_requirements.append("日文")
                if "韩文" in message or "韩语" in message:
                    language_requirements.append("韩文")
            
            # 加载并合并多个知识库内容
            agent.pending_knowledge_content = load_multiple_knowledge(effective_knowledge)
            
            # 加载商品库内容（如果选择了商品库文件）
            product_catalog_content = ""
            if products:
                product_items = load_multiple_catalogs(products)
                if product_items:
                    product_catalog_content = format_product_for_prompt(product_items)
                    log_message(f"[Product] 已加载商品库: {len(product_items)}条商品", "INFO", session_id=session_id)
            
            # 保存商品库内容到 agent，供后续使用
            agent.pending_product_content = product_catalog_content
            
            # 获取当前选中的人设（用于生成符合人设风格的问题）
            persona_config = None
            selected_persona = status.get("selected_persona")
            if selected_persona and selected_persona.get("id"):
                try:
                    import importlib.util
                    prompt_manager_path = os.path.join(PLAYWRIGHT_DIR, "prompt_manager.py")
                    spec = importlib.util.spec_from_file_location("prompt_manager", prompt_manager_path)
                    if spec and spec.loader:
                        pm = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(pm)
                        persona = pm.get_persona_by_id(selected_persona["id"])
                        if persona:
                            from dataclasses import asdict
                            persona_config = asdict(persona)
                            log_message(f"[Persona] 使用人设: {persona_config.get('name')} 生成问题", "INFO", session_id=session_id)
                except Exception as e:
                    log_message(f"[Persona] 加载人设失败: {e}", "WARN", session_id=session_id)
            
            # 同步人设到 agent
            if persona_config:
                agent.selected_persona_config = persona_config
            
            questions, error = agent._generate_questions_from_doc(
                effective_knowledge, count, multi_turn, 
                language_requirements=language_requirements if language_requirements else None,
                product_catalog=product_catalog_content if product_catalog_content else None
            )
            
            if error:
                return jsonify({"success": False, "error": error})
            
            agent.pending_questions = questions
            agent.pending_multi_turn = multi_turn
            
            # 计算总问题数
            if questions and isinstance(questions[0], list):
                total_count = sum(len(group) for group in questions)
                group_count = len(questions)
            else:
                total_count = len(questions or [])
                group_count = 0
            
            preview = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions or []))
            return jsonify({
                "success": True, "response": f"生成{total_count}个问题:\n{preview}",
                "action": "questions_generated", "count": total_count, "questions": questions,
                "multi_turn": multi_turn, "group_count": group_count
            })
        
        # 确认测试
        if "确认" in message or ("开始" in message and "测试" in message):
            questions = getattr(agent, "pending_questions", []) or []
            if not questions:
                questions = load_saved_questions(session_id, target="solo")
            if not questions:
                return jsonify({"success": False, "error": "请先生成问题"})
            
            if agent and hasattr(agent, "pending_questions"):
                agent.pending_questions = None
            
            # 保存登录凭据到session状态
            if username:
                status["username"] = username
            if password:
                status["password"] = password
            if url:
                status["test_url"] = url
            if bot_name:
                status["bot_name"] = bot_name
            
            agent_status["is_running"] = True
            agent_status["progress"] = 0
            
            thread = threading.Thread(target=execute_test, args=(url, questions, session_id))
            thread.daemon = True
            thread.start()
            
            return jsonify({"success": True, "response": "测试已启动", "action": "test_started"})
        
        # 设置 Agent 状态回调，实时推送状态
        agent_status_updates = []
        
        def agent_callback(status_type, message):
            update = {"type": "agent_status", "status_type": status_type, "message": message, "session_id": session_id}
            agent_status_updates.append(update)
            if session_id:
                get_session_logs(session_id).put(update)
            else:
                get_session_logs("").put(update)
        
        agent.set_status_callback(agent_callback)
        
        # 如果用户选择了知识库，设置给 Agent
        if effective_knowledge:
            knowledge_content = load_knowledge_content(effective_knowledge)
            agent.set_knowledge_base(effective_knowledge, knowledge_content)
        response = agent.chat(message)
        
        # 如果有状态更新，返回带状态的响应
        if agent_status_updates:
            return jsonify({
                "success": True, 
                "response": response,
                "status_updates": agent_status_updates
            })
        
        return jsonify({"success": True, "response": response})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@chat_bp.route("/chat/stream", methods=["POST"])
def chat_stream():
    """流式聊天接口 - 实时返回 Agent 状态"""
    data = request.json or {}
    message = data.get("message", "")
    session_id = data.get("session_id", "")
    
    if not message:
        return jsonify({"success": False, "error": "消息不能为空"})
    if not agent:
        return jsonify({"success": False, "error": "Agent未初始化"})
    
    def generate():
        status_queue = queue.Queue()
        final_response = [None]
        
        def agent_callback(status_type, msg):
            status_queue.put({"type": "agent_status", "status_type": status_type, "message": msg})
        
        def run_chat():
            try:
                agent.set_status_callback(agent_callback)
                response = agent.chat(message)
                final_response[0] = response
            except Exception as e:
                final_response[0] = f"[Error] {str(e)}"
            finally:
                status_queue.put(None)  # 结束信号
        
        # 启动聊天线程
        thread = threading.Thread(target=run_chat)
        thread.daemon = True
        thread.start()
        
        # 流式输出状态
        while True:
            try:
                item = status_queue.get(timeout=30)
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
        
        # 等待线程结束
        thread.join(timeout=5)
        
        # 发送最终响应
        if final_response[0]:
            yield f"data: {json.dumps({'type': 'final', 'response': final_response[0]})}\n\n"
    
    return Response(generate(), mimetype="text/event-stream")


@chat_bp.route("/logs")
def get_logs():
    """获取日志流"""
    session_id = request.args.get("session_id", "")
    logs_queue = get_session_logs(session_id) if session_id else get_session_logs("")
    
    def generate():
        while True:
            try:
                log = logs_queue.get(timeout=1)
                yield f"data: {json.dumps(log)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
    
    return Response(generate(), mimetype="text/event-stream")


@chat_bp.route("/status")
def get_status():
    """获取测试状态"""
    session_id = request.args.get("session_id", "")
    if session_id:
        return jsonify(get_session_status(session_id))
    return jsonify(agent_status)
