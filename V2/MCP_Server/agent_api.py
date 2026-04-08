# -*- coding: utf-8 -*-
"""
Agent API 模块 - 自然对话调用测试工具
集成到MCP_Server，提供Function Calling格式的Agent能力
"""
import os
import json
import requests
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

# 导入tools_api中的功能
from .tools_api import (
    run_debug_test,
    run_concurrent_test,
    generate_questions,
    generate_questions_concurrent,
    generate_persona_questions,
    get_test_report,
    list_personas,
    get_persona,
    create_persona,
    run_human_like_eval,
)


@dataclass
class AgentMessage:
    """Agent消息"""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None


# 工具定义 - Function Calling格式
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "run_debug_test",
            "description": "执行单网站调试测试。用于测试单个网站的AI对话功能。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_site": {"type": "integer", "description": "目标站点ID，默认1", "default": 1},
                    "session_id": {"type": "string", "description": "会话ID"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_concurrent_test",
            "description": "执行多渠道并发测试。同时对多个网站渠道进行并发测试。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_sites": {"type": "array", "items": {"type": "integer"}, "description": "目标站点ID列表"},
                    "workers_per_site": {"type": "integer", "description": "每站点worker数", "default": 1},
                    "session_id": {"type": "string", "description": "会话ID"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_questions",
            "description": "基于知识库内容生成测试问题。支持混沌矩阵规则。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "知识库内容"},
                    "count": {"type": "integer", "description": "生成数量", "default": 10},
                    "multi_turn": {"type": "integer", "description": "多轮对话轮数", "default": 1},
                    "use_chaos_matrix": {"type": "boolean", "description": "使用混沌矩阵", "default": True}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_persona_questions",
            "description": "生成画像测试问题。用于测试BOT的用户画像提取能力。",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "生成数量", "default": 10},
                    "complexity": {"type": "string", "description": "复杂度:simple/medium/complex", "default": "medium"},
                    "knowledge_content": {"type": "string", "description": "知识库内容"},
                    "session_id": {"type": "string", "description": "会话ID"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_personas",
            "description": "列出所有可用的测试人设。",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_test_report",
            "description": "获取测试报告和统计信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "会话ID"},
                    "report_type": {"type": "string", "description": "报告类型:solo/max/all", "default": "all"}
                },
                "required": []
            }
        }
    }
]


class AgentAPI:
    """Agent API 类 - 自然对话调用测试工具"""
    
    def __init__(self, api_key: str | None = None, api_base: str | None = None, model: str | None = None):
        """
        初始化Agent API
        
        Args:
            api_key: LLM API密钥
            api_base: LLM API基础URL
            model: 模型名称
        """
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.api_base = api_base or os.getenv("LLM_API_BASE_URL", "")
        self.model = model or os.getenv("LLM_MODEL", "qwen-plus")
        self.messages: List[AgentMessage] = []
        
        # 工具映射
        self.tools: Dict[str, Callable] = {
            "run_debug_test": self._run_debug_test,
            "run_concurrent_test": self._run_concurrent_test,
            "generate_questions": self._generate_questions,
            "generate_persona_questions": self._generate_persona_questions,
            "list_personas": self._list_personas,
            "get_test_report": self._get_test_report,
        }
    
    def chat(self, user_input: str, session_id: str = "") -> Dict[str, Any]:
        """
        自然对话接口 - 核心入口
        
        Args:
            user_input: 用户输入
            session_id: 会话ID
            
        Returns:
            {"reply": str, "tool_calls": list, "result": any}
        """
        # 添加用户消息
        self.messages.append(AgentMessage(role="user", content=user_input))
        
        # 调用LLM进行意图识别和工具选择
        response = self._call_llm_with_tools(session_id)
        
        # 处理响应
        if response.get("tool_calls"):
            # 需要调用工具
            tool_results = self._execute_tools(response["tool_calls"], session_id)
            return {
                "reply": response.get("content", ""),
                "tool_calls": response["tool_calls"],
                "results": tool_results
            }
        else:
            # 普通对话回复
            return {
                "reply": response.get("content", ""),
                "tool_calls": [],
                "results": None
            }
    
    def _call_llm_with_tools(self, session_id: str) -> Dict:
        """调用LLM，支持Function Calling"""
        if not self.api_key:
            return {"content": "请先配置LLM API密钥"}
        
        # 构建消息历史
        messages = []
        for msg in self.messages[-10:]:  # 保留最近10轮
            messages.append({"role": msg.role, "content": msg.content})
        
        # 添加系统提示
        system_prompt = self._get_system_prompt(session_id)
        messages.insert(0, {"role": "system", "content": system_prompt})
        
        try:
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "tools": TOOLS_SCHEMA,
                    "tool_choice": "auto",
                    "temperature": 0.7
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            choice = result["choices"][0]
            message = choice["message"]
            
            # 处理工具调用
            if message.get("tool_calls"):
                return {
                    "content": message.get("content", ""),
                    "tool_calls": message["tool_calls"]
                }
            else:
                return {"content": message.get("content", "")}
                
        except Exception as e:
            return {"content": f"调用LLM失败: {str(e)}"}
    
    def _get_system_prompt(self, session_id: str) -> str:
        """获取系统提示"""
        return f"""你是一个AI测试助手，帮助用户执行自动化测试任务。

当前会话ID: {session_id}

你可以使用以下工具：
1. run_debug_test - 单网站调试测试
2. run_concurrent_test - 多渠道并发测试
3. generate_questions - 生成测试问题
4. generate_persona_questions - 生成画像测试问题
5. list_personas - 列出测试人设
6. get_test_report - 获取测试报告

请根据用户的自然语言描述，选择合适的工具执行。
"""
    
    def _execute_tools(self, tool_calls: List[Dict], session_id: str) -> List[Dict]:
        """执行工具调用"""
        results = []
        for call in tool_calls:
            function_name = call["function"]["name"]
            arguments = json.loads(call["function"]["arguments"])
            
            if function_name in self.tools:
                try:
                    result = self.tools[function_name](**arguments, session_id=session_id)
                    results.append({
                        "tool": function_name,
                        "success": True,
                        "result": result
                    })
                except Exception as e:
                    results.append({
                        "tool": function_name,
                        "success": False,
                        "error": str(e)
                    })
            else:
                results.append({
                    "tool": function_name,
                    "success": False,
                    "error": "未知工具"
                })
        
        return results
    
    # ===== 工具实现包装 =====
    
    def _run_debug_test(self, session_id: str = "", target_site: int = 1, **kwargs):
        """包装run_debug_test"""
        # 需要先加载问题
        from .lib.PlayWright.questions import load_questions
        questions = load_questions(session_id=session_id)
        
        if not questions:
            return {"error": "没有测试问题，请先生成问题"}
        
        result = run_debug_test(
            questions=questions,
            target_site=target_site,
            session_id=session_id
        )
        return result
    
    def _run_concurrent_test(self, session_id: str = "", target_sites: List[int] = None, workers_per_site: int = 1, **kwargs):
        """包装run_concurrent_test"""
        from .lib.PlayWright.questions import load_questions
        questions = load_questions(session_id=session_id, target="concurrent")
        
        if not questions:
            return {"error": "没有测试问题，请先生成问题"}
        
        result = run_concurrent_test(
            questions=questions,
            target_sites=target_sites or [1],
            workers_per_site=workers_per_site,
            session_id=session_id
        )
        return result
    
    def _generate_questions(self, content: str, count: int = 10, multi_turn: int = 1, use_chaos_matrix: bool = True, **kwargs):
        """包装generate_questions"""
        questions, error = generate_questions(
            content=content,
            count=count,
            multi_turn=multi_turn,
            use_chaos_matrix=use_chaos_matrix
        )
        if error:
            return {"error": error}
        return {"questions": questions, "count": len(questions)}
    
    def _generate_persona_questions(self, count: int = 10, complexity: str = "medium", knowledge_content: str = "", session_id: str = "", **kwargs):
        """包装generate_persona_questions"""
        result = generate_persona_questions(
            count=count,
            complexity=complexity,
            knowledge_content=knowledge_content,
            session_id=session_id
        )
        return result
    
    def _list_personas(self, **kwargs):
        """包装list_personas"""
        return list_personas()
    
    def _get_test_report(self, session_id: str = "", report_type: str = "all", **kwargs):
        """包装get_test_report"""
        return get_test_report(session_id=session_id, report_type=report_type)


# ===== 便捷函数 =====

def agent_chat(user_input: str, session_id: str = "", api_key: str = None) -> Dict[str, Any]:
    """
    Agent对话便捷函数
    
    Args:
        user_input: 用户输入
        session_id: 会话ID
        api_key: LLM API密钥
        
    Returns:
        {"reply": str, "tool_calls": list, "results": list}
        
    示例:
        >>> result = agent_chat("帮我生成10个测试问题")
        >>> print(result["reply"])
    """
    agent = AgentAPI(api_key=api_key)
    return agent.chat(user_input, session_id)


# ===== Flask API路由（如果使用Flask）=====

def register_agent_api(app):
    """
    注册Agent API到Flask应用
    
    Args:
        app: Flask应用实例
    """
    @app.route("/api/agent/chat", methods=["POST"])
    def agent_chat_endpoint():
        """Agent对话API端点"""
        data = request.json or {}
        user_input = data.get("message", "")
        session_id = data.get("session_id", "")
        
        if not user_input:
            return jsonify({"error": "消息不能为空"}), 400
        
        result = agent_chat(user_input, session_id)
        return jsonify(result)
    
    @app.route("/api/agent/tools", methods=["GET"])
    def list_tools():
        """获取可用工具列表"""
        return jsonify({"tools": TOOLS_SCHEMA})


# 导出
__all__ = [
    "AgentAPI",
    "agent_chat",
    "register_agent_api",
    "TOOLS_SCHEMA"
]