# -*- coding: utf-8 -*-
"""
用户画像接口客户端

调用 /stream_response_procedure/test/user_profile 接口获取真实画像数据
用于评估 Bot 构建画像的准确率
"""

import os
import json
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class UserProfileConfig:
    """画像接口配置"""
    base_url: str = ""
    api_key: str = ""
    timeout: int = 30
    
    def __post_init__(self):
        # [CLEARED] 从环境变量读取
        if not self.base_url:
            self.base_url = os.getenv("USER_PROFILE_API_BASE_URL", "")
        if not self.api_key:
            self.api_key = os.getenv("USER_PROFILE_API_KEY", "")


class UserProfileClient:
    """
    用户画像接口客户端
    
    用于获取买家的完整画像数据，包括：
    - core_memory: 核心画像（姓名、偏好、购物任务等）
    - leads_memory: 客户留资（联系方式）
    - latest_state: 当前意向状态
    """
    
    def __init__(self, config: Optional[UserProfileConfig] = None):
        """
        初始化客户端
        
        Args:
            config: 接口配置，为空时使用默认配置
        """
        self.config = config or UserProfileConfig()
    
    def get_user_profile(
        self,
        user_id: str,
        tenant_outer_id: str
    ) -> Dict[str, Any]:
        """
        获取用户画像
        
        Args:
            user_id: 卖家/商家 ID (Seller ID)
            tenant_outer_id: 买家/客户 ID (Buyer ID)
        
        Returns:
            画像数据字典，包含:
            - success: 是否成功
            - core_memory: 核心画像
            - leads_memory: 客户留资
            - latest_state: 当前意向状态
            - error: 错误信息（如果失败）
        """
        url = f"{self.config.base_url}/stream_response_procedure/test/user_profile"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        payload = {
            "user_id": user_id,
            "tenant_outer_id": tenant_outer_id
        }
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("message") == "success":
                    data = result.get("data", {})
                    
                    # 检查是否有错误
                    if "error" in data:
                        return {
                            "success": False,
                            "error": data["error"],
                            "core_memory": {},
                            "leads_memory": {},
                            "latest_state": {}
                        }
                    
                    return {
                        "success": True,
                        "core_memory": data.get("core_memory", {}),
                        "leads_memory": data.get("leads_memory", {}),
                        "latest_state": data.get("latest_state", {}),
                        "raw_response": result
                    }
                else:
                    return {
                        "success": False,
                        "error": f"API返回错误: {result.get('message', 'unknown')}",
                        "core_memory": {},
                        "leads_memory": {},
                        "latest_state": {}
                    }
            else:
                return {
                    "success": False,
                    "error": f"HTTP错误: {response.status_code} - {response.text[:200]}",
                    "core_memory": {},
                    "leads_memory": {},
                    "latest_state": {}
                }
                
        except requests.Timeout:
            return {
                "success": False,
                "error": f"请求超时 ({self.config.timeout}秒)",
                "core_memory": {},
                "leads_memory": {},
                "latest_state": {}
            }
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"请求异常: {str(e)}",
                "core_memory": {},
                "leads_memory": {},
                "latest_state": {}
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"未知错误: {str(e)}",
                "core_memory": {},
                "leads_memory": {},
                "latest_state": {}
            }
    
    def extract_expected_profile(
        self,
        profile_data: Dict[str, Any],
        fields_to_extract: Optional[list[str]] = None
    ) -> Dict[str, Any]:
        """
        从接口返回数据中提取期望画像（用于对比评估）
        
        Args:
            profile_data: 接口返回的画像数据
            fields_to_extract: 要提取的字段列表，为空时提取所有
        
        Returns:
            扁平化的期望画像字典
        """
        if not profile_data.get("success"):
            return {}
        
        expected: Dict[str, Any] = {}
        
        core_memory = profile_data.get("core_memory", {})
        leads_memory = profile_data.get("leads_memory", {})
        latest_state = profile_data.get("latest_state", {})
        
        # 提取核心画像字段
        core_fields = ["name", "gender", "size", "age", "birthday", "address", "preferences"]
        for field in core_fields:
            if field in core_memory:
                expected[field] = core_memory[field]
        
        # 提取活跃购物任务
        active_tasks = core_memory.get("active_shopping_tasks", [])
        if active_tasks:
            # 取第一个活跃任务
            task = active_tasks[0]
            task_fields = ["item", "target", "budget", "focus", "objections", 
                          "need_specificity", "transaction_signal", "purchase_stage", "intent_score"]
            for field in task_fields:
                if field in task:
                    expected[f"task_{field}"] = task[field]
        
        # 提取留资信息
        leads_fields = ["phone", "wechat", "email", "address"]
        for field in leads_fields:
            if field in leads_memory:
                expected[field] = leads_memory[field]
        
        # 提取意向状态
        state_fields = ["current_sub_stage", "intent_score"]
        for field in state_fields:
            if field in latest_state:
                expected[field] = latest_state[field]
        
        # 如果指定了字段列表，只保留指定的
        if fields_to_extract:
            expected = {k: v for k, v in expected.items() if k in fields_to_extract}
        
        return expected


def get_user_profile_for_test(
    user_id: str,
    tenant_outer_id: str,
    config: Optional[UserProfileConfig] = None
) -> Dict[str, Any]:
    """
    便捷函数：获取用户画像用于测试
    
    Args:
        user_id: 卖家 ID
        tenant_outer_id: 买家 ID
        config: 接口配置
    
    Returns:
        画像数据
    """
    client = UserProfileClient(config)
    return client.get_user_profile(user_id, tenant_outer_id)


def extract_profile_for_comparison(
    user_id: str,
    tenant_outer_id: str,
    config: Optional[UserProfileConfig] = None
) -> tuple[bool, Dict[str, Any], str]:
    """
    获取并提取画像用于对比评估
    
    Args:
        user_id: 卖家 ID
        tenant_outer_id: 买家 ID
        config: 接口配置
    
    Returns:
        (success, expected_profile, error_message)
    """
    profile_data = get_user_profile_for_test(user_id, tenant_outer_id, config)
    
    if not profile_data.get("success"):
        return False, {}, profile_data.get("error", "未知错误")
    
    expected = UserProfileClient(config).extract_expected_profile(profile_data)
    return True, expected, ""


# 导出
__all__ = [
    "UserProfileConfig",
    "UserProfileClient",
    "get_user_profile_for_test",
    "extract_profile_for_comparison"
]
