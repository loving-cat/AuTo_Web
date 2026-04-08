# -*- coding: utf-8 -*-
"""V2路由模块"""

from flask import Blueprint

# 创建蓝图
test_bp = Blueprint('test', __name__, url_prefix='/api')
chat_bp = Blueprint('chat', __name__, url_prefix='/api')
question_bp = Blueprint('question', __name__, url_prefix='/api')
file_bp = Blueprint('file', __name__, url_prefix='/api')
report_bp = Blueprint('report', __name__, url_prefix='/api')
site_bp = Blueprint('site', __name__, url_prefix='/api')
task_bp = Blueprint('task', __name__, url_prefix='/api')
check_bp = Blueprint('check', __name__, url_prefix='/api')
persona_bp = Blueprint('persona', __name__, url_prefix='/api')
product_bp = Blueprint('product', __name__, url_prefix='/api')

__all__ = [
    "test_bp", "chat_bp", "question_bp", "file_bp",
    "report_bp", "site_bp", "task_bp", "check_bp", "persona_bp",
    "product_bp"
]
