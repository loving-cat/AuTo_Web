# -*- coding: utf-8 -*-
"""问题管理路由"""

import os
import json
from flask import request, jsonify

from routes import question_bp
from services import load_saved_questions
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


@question_bp.route("/questions")
def get_questions():
    """获取问题列表"""
    session_id = request.args.get("session_id", "")
    target = request.args.get("target", "")  # 获取目标类型
    
    # 获取会话专属的 Agent 实例
    agent = get_agent_for_session(session_id)
    if agent and hasattr(agent, "pending_questions") and agent.pending_questions:
        return jsonify({"success": True, "questions": agent.pending_questions})
    
    saved = load_saved_questions(session_id, target=target)
    if saved:
        return jsonify({"success": True, "questions": saved, "from_file": True})
    
    return jsonify({"success": True, "questions": []})


@question_bp.route("/questions/save", methods=["POST"])
def save_questions():
    """保存问题，支持多轮对话格式和问题类型"""
    data = request.json or {}
    questions = data.get("questions", [])
    target = data.get("target", "single")
    session_id = data.get("session_id", "")
    multi_turn = data.get("multi_turn", 1)

    if not questions:
        return jsonify({"success": False, "error": "问题列表不能为空"})

    # 检查是否是多轮对话格式
    is_multi_turn = questions and isinstance(questions[0], list)

    # 提取问题文本用于保存（同时保留完整对象用于JSON）
    def extract_question_text(q):
        """提取问题文本"""
        if isinstance(q, dict):
            return q.get('question', str(q))
        return str(q)

    # 构建文本内容：多轮对话用空行分隔组
    if is_multi_turn:
        content = "\n\n".join(["\n".join([extract_question_text(q) for q in group]) for group in questions])
    else:
        content = "\n".join([extract_question_text(q) for q in questions])

    # 计算总问题数
    if is_multi_turn:
        total_count = sum(len(group) for group in questions)
    else:
        total_count = len(questions)

    # 构建元数据（扁平列表格式，每个元素包含问题文本和类型）
    typed_questions_meta = []
    
    def extract_meta(q, group_idx=0):
        """提取问题元数据"""
        if isinstance(q, dict):
            meta = {
                'question': q.get('question', str(q)),
                'question_type': q.get('question_type', 'normal'),
                'group_index': q.get('group_index', group_idx)
            }
            # 保存画像测试的期望画像
            expected_profile = q.get('expected_profile')
            if expected_profile:
                meta['expected_profile'] = expected_profile
            return meta
        return {
            'question': str(q),
            'question_type': 'normal',
            'group_index': group_idx
        }
    
    if is_multi_turn:
        for group_idx, group in enumerate(questions):
            for q in group:
                typed_questions_meta.append(extract_meta(q, group_idx))
    else:
        for q in questions:
            typed_questions_meta.append(extract_meta(q, 0))
    
    meta_data = typed_questions_meta

    saved_files = []

    # simuser 也需要保存到并发测试目录
    effective_target = target
    if target == "simuser":
        effective_target = "concurrent"

    try:
        if effective_target in ("single", "all"):
            if session_id:
                path = os.path.join(PLAYWRIGHT_DIR, "solo_worker_PlayWright", "questions", session_id, "test_questions.txt")
                meta_path = os.path.join(PLAYWRIGHT_DIR, "solo_worker_PlayWright", "questions", session_id, "questions_meta.json")
                os.makedirs(os.path.dirname(path), exist_ok=True)
            else:
                path = os.path.join(PLAYWRIGHT_DIR, "solo_worker_PlayWright", "test_questions.txt")
                meta_path = os.path.join(PLAYWRIGHT_DIR, "solo_worker_PlayWright", "questions_meta.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            # 保存元数据（包含问题类型）
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            saved_files.append("调试测试")

        if effective_target in ("concurrent", "all"):
            if session_id:
                path = os.path.join(PLAYWRIGHT_DIR, "max_worker", "questions", session_id, "test_questions.txt")
                meta_path = os.path.join(PLAYWRIGHT_DIR, "max_worker", "questions", session_id, "questions_meta.json")
                os.makedirs(os.path.dirname(path), exist_ok=True)
            else:
                path = os.path.join(PLAYWRIGHT_DIR, "max_worker", "test_questions.txt")
                meta_path = os.path.join(PLAYWRIGHT_DIR, "max_worker", "questions_meta.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            # 保存元数据（包含问题类型）
            os.makedirs(os.path.dirname(meta_path), exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            saved_files.append("并发测试" if target != "simuser" else "SimUser测试")

        return jsonify({"success": True, "message": f"已保存{total_count}个问题到: {', '.join(saved_files)}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@question_bp.route("/questions/count")
def get_questions_count():
    """获取问题数量"""
    session_id = request.args.get("session_id", "")
    target = request.args.get("target", "concurrent")  # 默认查询渠道Web测试的问题
    
    # 优先检查待确认的问题
    if agent and hasattr(agent, "pending_questions") and agent.pending_questions:
        questions = agent.pending_questions
        # 检查是否是多轮对话格式（二维数组）
        if questions and isinstance(questions[0], list):
            total_count = sum(len(group) for group in questions)
            group_count = len(questions)
            return jsonify({"success": True, "count": total_count, "group_count": group_count, "is_multi_turn": True})
        else:
            return jsonify({"success": True, "count": len(questions), "is_multi_turn": False})
    
    # 检查已保存的问题文件
    questions = load_saved_questions(session_id, target)
    if questions and isinstance(questions[0], list):
        total_count = sum(len(group) for group in questions)
        group_count = len(questions)
        return jsonify({"success": True, "count": total_count, "group_count": group_count, "is_multi_turn": True})
    return jsonify({"success": True, "count": len(questions), "is_multi_turn": False})


@question_bp.route("/generate_persona_questions", methods=["POST"])
def generate_persona_questions():
    """生成画像测试问题"""
    data = request.json or {}
    count = data.get("count", 20)
    complexity = data.get("complexity", "medium")
    knowledge_content = data.get("knowledge_content", "")
    session_id = data.get("session_id", "")
    
    try:
        # 导入画像问题生成器
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
        from MCP_Server.tools_api import generate_persona_questions
        
        # 生成画像问题
        result = generate_persona_questions(
            count=count,
            complexity=complexity,
            knowledge_content=knowledge_content,
            session_id=session_id,
            worker_type="solo"
        )
        
        if result.get("success"):
            # 获取生成的问题
            questions = result.get("questions", [])
            
            # 保存到 agent 的 pending_questions 中
            agent = get_agent_for_session(session_id)
            if agent:
                agent.pending_questions = questions
            
            return jsonify({
                "success": True,
                "questions": questions,
                "count": len(questions),
                "message": f"成功生成 {len(questions)} 道画像测试问题"
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("message", "生成失败")
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
