import requests
import json
from typing import Dict, Any

# ==========================================
# ⚠️ 请在这里填入你本地 Dify 的配置
# ==========================================
# 你的 Dify 工作流 API Key（在 Dify 工作室 -> 对应应用 -> 访问 API 中获取）
DIFY_API_KEY = "app-YjjKHElOoGx6u0Nwzj6hSeMV"
# 你的本地 Dify 接口地址（注意后缀通常是 /v1/workflows/run）
DIFY_WORKFLOW_URL = "http://127.0.0.1/v1/workflows/run"


def run_screening_workflow(criminal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将单个罪犯的标准化数据发送给 Dify 工作流进行研判。
    """
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }

    # 构造发给 Dify 的核心请求体
    # 注意：这里的 inputs 字典的键，必须和你 Dify 里【开始节点】设置的变量名一模一样！
    # 得益于我们之前的大模型智能对齐，criminal_data 里的键已经是标准英文变量了。
    payload = {
        "inputs": criminal_data,
        "response_mode": "blocking",  # 使用阻塞模式，让 Dify 算完之后一次性把结果吐给我们
        "user": "local_automation_system"
    }

    try:
        # 发送请求，这里设置较长的超时时间，因为大模型推理法条需要时间
        response = requests.post(DIFY_WORKFLOW_URL, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        # 解析 Dify 返回的结果
        dify_result = response.json()

        # Dify blocking 模式下，工作流最终节点的输出保存在 data -> outputs 里
        if "data" in dify_result and "outputs" in dify_result["data"]:
            outputs = dify_result["data"]["outputs"]
            # 假设你的 Dify 结束节点输出的是一个 JSON 文本，名为 result_json
            # 如果你 Dify 直接输出的是文本字段，直接提取即可
            return outputs
        else:
            print(f"Dify 返回格式异常: {dify_result}")
            return {"error": "未获取到有效输出"}

    except Exception as e:
        print(f"调用 Dify 工作流失败，罪犯：{criminal_data.get('criminal_name')}, 错误：{e}")
        return {"error": str(e)}


# ====== 在文件最下方追加以下代码 ======
import re


def run_text_llm(prompt: str) -> Dict[str, Any]:
    """
    越过 Dify，直接呼叫本地 Ollama 进行纯文本推理（专用于交叉校验和挑错）
    """
    print("🧠 正在呼叫本地文本大模型进行深度逻辑比对...")

    # 你的本地 Ollama 接口地址
    ollama_url = "http://127.0.0.1:11434/api/generate"

    payload = {
        "model": "qwen3.6:latest",  # 🚨 这里必须填你本地实际运行的模型名字，比如 qwen2.5:72b
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1  # 温度设低，要求它像法官一样严谨，绝不胡编乱造
        }
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=180)
        response.raise_for_status()

        # 提取模型返回的纯文本
        raw_text = response.json().get("response", "{}")

        # 强力清洗：只提取 { } 之间的 JSON 内容，防止模型带上 markdown 标签
        clean_str_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        clean_str = clean_str_match.group(0) if clean_str_match else "{}"

        # 将清理干净的字符串转为 Python 字典
        return json.loads(clean_str)

    except json.JSONDecodeError:
        print("❌ 模型输出了非法的 JSON 格式")
        return {"error": "解析失败", "raw_output": raw_text}
    except Exception as e:
        print(f"❌ 呼叫本地大模型失败: {e}")
        return {"error": "模型连接失败", "details": str(e)}