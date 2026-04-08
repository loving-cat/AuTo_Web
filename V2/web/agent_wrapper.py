"""
V2 Agent工具包装器 - 用于Web界面调用MCP_Server
"""
import sys
import os
import importlib.util
import types

# V2根目录（web的父目录）
v2_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 项目根目录（共享原版数据和.env）
project_root = os.path.dirname(v2_root)

# 加载.env
try:
    from dotenv import load_dotenv
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"[V2 Agent] 已加载环境变量: {env_path}")
except ImportError:
    pass

def load_module(name, path, package=None):
    """加载模块，支持设置包上下文"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {path}")
    module = importlib.util.module_from_spec(spec)
    if package:
        module.__package__ = package
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# 1. 创建 MCP_Server 包
mcp_server_dir = os.path.join(v2_root, 'MCP_Server')
if 'MCP_Server' not in sys.modules:
    mcp_package = types.ModuleType('MCP_Server')
    mcp_package.__path__ = [mcp_server_dir]
    mcp_package.__file__ = os.path.join(mcp_server_dir, '__init__.py')
    mcp_package.__package__ = None
    sys.modules['MCP_Server'] = mcp_package

# 2. 加载 MCP_Server/config.py
config_path = os.path.join(mcp_server_dir, 'config.py')
mcp_config = load_module('MCP_Server.config', config_path, package='MCP_Server')

# 3. 加载 MCP_Server/tools_api.py
tools_api_path = os.path.join(mcp_server_dir, 'tools_api.py')
tools_api = load_module('MCP_Server.tools_api', tools_api_path, package='MCP_Server')

# 导出 - 创建一个适配类供Web界面使用
class ToolRegistry:
    """V2工具注册表适配类"""
    
    # 存储会话配置
    _session_configs = {}  # session_id -> {url, username, password, bot_name, questions}
    
    @staticmethod
    def generate_questions(content: str, count: int = 20, **kwargs):
        """生成测试问题"""
        questions, error = tools_api.generate_questions_concurrent(
            content=content, count=count, **kwargs
        )
        if error:
            return f"生成失败: {error}"
        return f"已生成 {len(questions)} 个问题"
    
    @staticmethod
    def run_debug_test(knowledge_content: str = "", questions: list = None, **kwargs):
        """执行调试测试"""
        if not questions:
            return "请先提供测试问题"
        result = tools_api.run_debug_test(
            questions=questions,
            knowledge_content=knowledge_content,
            **kwargs
        )
        if result.get("success"):
            return f"测试完成: {result.get('report', '无报告')}"
        return f"测试失败: {result.get('message', '未知错误')}"
    
    @staticmethod
    def run_concurrent_test(knowledge_content: str = "", questions: list = None, **kwargs):
        """执行并发测试"""
        if not questions:
            return "请先提供测试问题"
        result = tools_api.run_concurrent_test(
            questions=questions,
            knowledge_content=knowledge_content,
            **kwargs
        )
        if result.get("success"):
            return f"并发测试完成"
        return f"并发测试失败: {result.get('message', '未知错误')}"
    
    @staticmethod
    def update_user_credentials(username, password, login_url=None):
        """更新用户凭证（存储到会话配置）"""
        # V2版本通过环境变量传递给测试脚本
        return True
    
    @staticmethod
    def update_bot_config(bot_name):
        """更新机器人配置"""
        return True
    
    @staticmethod
    def update_test_questions(questions):
        """更新测试问题"""
        # 问题通过 run_debug_test 参数传递
        return True


class TestAgent:
    """V2 Agent适配类 - 模拟原版TestAgent接口"""
    
    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self.pending_questions = []
        self.knowledge_content = ""
        self.pending_knowledge_content = ""  # 知识库内容缓存
        self.pending_product_content = ""     # 商品库内容缓存
        self.selected_persona_config = None   # 人设配置
        self.selected_knowledge_base = None   # 选择的知识库
        self.pending_multi_turn = 1           # 多轮对话轮数
        self.status_callback = None           # 状态回调函数
        self.tools = ToolRegistry  # 添加tools属性，指向ToolRegistry类
    
    def set_status_callback(self, callback):
        """设置状态回调函数"""
        self.status_callback = callback
    
    def set_knowledge_base(self, doc_name, content=None):
        """设置预选的知识库"""
        self.selected_knowledge_base = doc_name
        if content:
            self.pending_knowledge_content = content
    
    def chat(self, message: str) -> str:
        """处理聊天消息"""
        # 简化实现：根据消息内容调用相应工具
        if "生成" in message and "问题" in message:
            return ToolRegistry.generate_questions(self.knowledge_content)
        elif "测试" in message or "执行" in message:
            return ToolRegistry.run_debug_test(self.knowledge_content, self.pending_questions)
        return "收到消息: " + message
    
    def set_knowledge(self, content: str):
        """设置知识库内容"""
        self.knowledge_content = content
        self.pending_knowledge_content = content
    
    def set_questions(self, questions: list):
        """设置测试问题"""
        self.pending_questions = questions
    
    def _generate_questions_from_doc(self, doc_name, count=10, multi_turn=1, language_requirements=None, product_catalog=None):
        """基于文档生成问题（V2简化版 - 直接调用MCP_Server）"""
        # V2版本：使用已加载的知识库内容
        content = self.pending_knowledge_content
        
        if not content:
            return None, "请先上传知识库文件"
        
        # 调用 MCP_Server 生成问题
        questions, error = tools_api.generate_questions_concurrent(
            content=content,
            count=count,
            multi_turn=multi_turn,
            session_id=self.session_id,
            product_content=product_catalog
        )
        
        if error:
            return None, error
        
        return questions, None


# 导出
__all__ = ['ToolRegistry', 'TestAgent', 'mcp_config', 'tools_api']
