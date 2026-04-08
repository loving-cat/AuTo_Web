# -*- coding: utf-8 -*-
"""人设管理路由"""

import os
from flask import request, jsonify

from routes import persona_bp
from services import get_session_status, log_message
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


@persona_bp.route("/personas")
def api_list_personas():
    """列出所有可用的人设配置"""
    try:
        # 导入 prompt_manager
        prompt_manager_path = os.path.join(PLAYWRIGHT_DIR, "prompt_manager.py")
        if not os.path.exists(prompt_manager_path):
            return jsonify({
                "success": False, 
                "error": "人设管理模块不存在",
                "personas": [],
                "has_external_prompts": False
            })
        
        import importlib.util
        spec = importlib.util.spec_from_file_location("prompt_manager", prompt_manager_path)
        if spec and spec.loader:
            pm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pm)
            
            personas = pm.list_available_personas()
            has_external = pm.get_prompt_manager().has_external_prompts()
            
            return jsonify({
                "success": True,
                "personas": personas,
                "has_external_prompts": has_external,
                "total_count": len(personas)
            })
        else:
            return jsonify({
                "success": False, 
                "error": "无法加载人设管理模块",
                "personas": []
            })
    except Exception as e:
        log_message(f"获取人设列表失败: {e}", "ERROR")
        return jsonify({"success": False, "error": str(e), "personas": []})


@persona_bp.route("/personas/<persona_id>")
def api_get_persona(persona_id):
    """获取指定人设的详细配置"""
    try:
        import importlib.util
        prompt_manager_path = os.path.join(PLAYWRIGHT_DIR, "prompt_manager.py")
        spec = importlib.util.spec_from_file_location("prompt_manager", prompt_manager_path)
        if spec and spec.loader:
            pm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pm)

            persona = pm.get_persona_by_id(persona_id)
            if persona:
                from dataclasses import asdict
                return jsonify({
                    "success": True,
                    "persona": asdict(persona)
                })
            else:
                return jsonify({
                    "success": False,
                    "error": f"找不到人设: {persona_id}"
                })
        else:
            return jsonify({
                "success": False,
                "error": "无法加载人设管理模块"
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@persona_bp.route("/personas/create", methods=["POST"])
def api_create_persona():
    """创建自定义人设并保存到 prompt.py"""
    data = request.json or {}
    direction = data.get("direction", "")
    persona_description = data.get("persona_description", "")
    additional_requirements = data.get("additional_requirements", "")
    save_to_file = data.get("save_to_file", True)

    if not direction or not persona_description:
        return jsonify({
            "success": False,
            "error": "请填写测试方向和人设描述"
        })

    try:
        import importlib.util
        prompt_manager_path = os.path.join(PLAYWRIGHT_DIR, "prompt_manager.py")
        spec = importlib.util.spec_from_file_location("prompt_manager", prompt_manager_path)
        if spec and spec.loader:
            pm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pm)

            persona = pm.create_custom_persona(
                direction=direction,
                persona_description=persona_description,
                additional_requirements=additional_requirements,
                save_to_file=save_to_file
            )

            from dataclasses import asdict
            log_message(f"创建人设成功: {persona.name}", session_id=data.get("session_id", ""))

            return jsonify({
                "success": True,
                "persona": asdict(persona),
                "message": f"人设 '{persona.name}' 创建成功"
            })
        else:
            return jsonify({
                "success": False,
                "error": "无法加载人设管理模块"
            })
    except Exception as e:
        log_message(f"创建人设失败: {e}", "ERROR")
        return jsonify({"success": False, "error": str(e)})


@persona_bp.route("/personas/save", methods=["POST"])
def api_save_persona():
    """保存人设到 prompt.py（直接保存完整配置）"""
    data = request.json or {}
    persona_id = data.get("id", "")
    name = data.get("name", "")
    description = data.get("description", "")
    persona_text = data.get("persona", "")
    scenario = data.get("scenario", "咨询")
    goal = data.get("goal", "")
    triggers = data.get("triggers", [])
    difficulty = data.get("difficulty", "medium")
    tags = data.get("tags", [])
    session_id = data.get("session_id", "")

    if not persona_id or not persona_text:
        return jsonify({
            "success": False,
            "error": "人设ID和内容不能为空"
        })

    try:
        import importlib.util
        prompt_manager_path = os.path.join(PLAYWRIGHT_DIR, "prompt_manager.py")
        spec = importlib.util.spec_from_file_location("prompt_manager", prompt_manager_path)
        if spec and spec.loader:
            pm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pm)

            manager = pm.get_prompt_manager()
            file_path = manager.generate_prompt_file(
                persona_id=persona_id,
                name=name or persona_id,
                description=description or "",
                persona_text=persona_text,
                scenario=scenario,
                goal=goal or "",
                triggers=triggers or [],
                difficulty=difficulty,
                tags=tags or []
            )

            log_message(f"人设已保存到: {file_path}", session_id=session_id)

            # 同步到 agent 状态（用于问题生成时使用人设）
            if agent:
                persona_config = {
                    "id": persona_id,
                    "name": name or persona_id,
                    "description": description or "",
                    "persona": persona_text,
                    "scenario": scenario,
                    "goal": goal or "",
                    "triggers": triggers or [],
                    "difficulty": difficulty,
                    "tags": tags or []
                }
                agent.selected_persona_config = persona_config
                log_message(f"已同步人设到Agent: {name}", session_id=session_id)

            # 同步到 session 状态
            if session_id:
                s = get_session_status(session_id)
                s["selected_persona"] = {
                    "id": persona_id,
                    "name": name,
                    "scenario": scenario
                }

            return jsonify({
                "success": True,
                "message": f"人设已保存",
                "file_path": file_path,
                "persona": {
                    "id": persona_id,
                    "name": name,
                    "scenario": scenario
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "无法加载人设管理模块"
            })
    except Exception as e:
        log_message(f"保存人设失败: {e}", "ERROR")
        return jsonify({"success": False, "error": str(e)})


@persona_bp.route("/personas/clear", methods=["POST"])
def api_clear_persona():
    """清除当前会话的人设选择"""
    data = request.json or {}
    session_id = data.get("session_id", "")
    
    # 清除 session 状态中的人设
    if session_id:
        s = get_session_status(session_id)
        s["selected_persona"] = {}
    
    # 清除 agent 中的人设
    if agent and hasattr(agent, "selected_persona_config"):
        agent.selected_persona_config = None
    
    log_message("已清除人设选择", session_id=session_id)
    
    return jsonify({
        "success": True,
        "message": "人设已清除"
    })


@persona_bp.route("/bot-persona", methods=["POST"])
def api_set_bot_persona():
    """设置BOT的人设（如"二次元"、"专业客服"等）"""
    data = request.json or {}
    session_id = data.get("session_id", "")
    bot_persona = data.get("bot_persona", "")
    
    print(f"[DEBUG] api_set_bot_persona: session_id={session_id!r}, bot_persona={bot_persona!r}")
    
    if not session_id:
        return jsonify({"success": False, "error": "缺少session_id"}), 400
    
    # 更新 session 状态
    status = get_session_status(session_id)
    status["bot_persona"] = bot_persona
    
    print(f"[DEBUG] 已保存 bot_persona 到 session_status[{session_id}]: {bot_persona!r}")
    print(f"[DEBUG] 当前 status 内容: {status}")
    
    log_message(f"已设置BOT人设: {bot_persona or '未设置'}", session_id=session_id)
    
    return jsonify({
        "success": True,
        "bot_persona": bot_persona,
        "message": f"BOT人设已设置为: {bot_persona}" if bot_persona else "BOT人设已清除"
    })


@persona_bp.route("/bot-persona", methods=["GET"])
def api_get_bot_persona():
    """获取BOT的人设"""
    session_id = request.args.get("session_id", "")
    
    if not session_id:
        return jsonify({"success": False, "error": "缺少session_id"}), 400
    
    status = get_session_status(session_id)
    
    return jsonify({
        "success": True,
        "bot_persona": status.get("bot_persona", "")
    })
