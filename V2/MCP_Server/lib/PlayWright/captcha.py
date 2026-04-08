"""验证码识别模块 - API配置从config参数读取"""

import os
import base64
import requests
from datetime import datetime


def recognize_captcha(image_bytes, config):
    """使用ModelScope千问视觉模型识别验证码"""
    print("识别验证码...")
    
    # 保存验证码图片用于调试
    os.makedirs("reports", exist_ok=True)
    debug_file = f"reports/captcha_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    with open(debug_file, 'wb') as f:
        f.write(image_bytes)
    print(f"  验证码图片已保存: {debug_file}")
    
    # 转换为base64
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    # 构建请求
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": config['model'],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请识别这个验证码图片中的数字，只返回数字，不要任何其他文字。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]
            }
        ],
        "max_tokens": 50,
        "temperature": 0.1
    }
    
    # 发送请求
    # 确保 API URL 指向完整的 chat/completions 端点
    api_url = config['api_url']
    if not api_url.endswith("/chat/completions"):
        api_url = api_url.rstrip("/") + "/chat/completions"
        
    print(f"  正在调用API: {api_url}")
    print(f"  使用模型: {config['model']}")
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].strip()
                import re
                numbers = re.findall(r'\d+', content)
                if numbers:
                    code = numbers[0]
                    print(f"  [OK] 识别结果: {code}")
                    return code
                print(f"  [WARN] 未提取到数字: {content}")
            else:
                print(f"  [X] API响应格式异常: {result}")
        else:
            print(f"  [X] API请求失败: {response.status_code}")
            print(f"  错误: {response.text}")
    except Exception as e:
        print(f"  [X] API请求异常: {str(e)}")
        
    return None
