"""
API 认证中间件
支持基于 Token 的 API 保护机制
"""
import os
import functools
from flask import request, jsonify

# 从环境变量读取认证 Token
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "")

# 是否启用认证（Token 为空时禁用）
AUTH_ENABLED = bool(API_AUTH_TOKEN)


def require_auth(f):
    """
    API 认证装饰器
    如果设置了 API_AUTH_TOKEN，则要求请求头中包含有效的 Authorization: Bearer <token>
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not AUTH_ENABLED:
            # 未配置 Token，跳过认证
            return f(*args, **kwargs)
        
        # 获取 Authorization 头
        auth_header = request.headers.get("Authorization", "")
        
        if not auth_header:
            return jsonify({
                "success": False,
                "error": "缺少认证信息",
                "message": "请在请求头中添加 Authorization: Bearer <token>"
            }), 401
        
        # 验证 Bearer Token 格式
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({
                "success": False,
                "error": "认证格式错误",
                "message": "Authorization 头格式应为: Bearer <token>"
            }), 401
        
        token = parts[1]
        
        if token != API_AUTH_TOKEN:
            return jsonify({
                "success": False,
                "error": "认证失败",
                "message": "无效的 API Token"
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def check_auth_status():
    """返回认证状态信息"""
    return {
        "enabled": AUTH_ENABLED,
        "message": "API 认证已启用" if AUTH_ENABLED else "API 认证未启用（未配置 API_AUTH_TOKEN）"
    }
