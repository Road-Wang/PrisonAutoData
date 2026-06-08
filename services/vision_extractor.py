import base64
import requests
import json
import re
import os
import time
from PIL import Image
import io
import traceback

OLLAMA_VISION_URL = "http://127.0.0.1:11434/api/generate"


def encode_image_to_base64(image_path: str, max_size=1600):
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"⚠️ 图片 {image_path} 预处理失败: {e}")
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')



def extract_single_document(image_path: str, doc_name: str, target_name: str, previous_doc_type: str = "无",
                            mode: str = "模式一", doc_category: str = "", extra_prompt: str = "", batch_name: str = "",
                            batch_type: str = ""):
    # ====== 🌟 核心升级 1：旁路缓存拦截机制 ======
    # 只要这个图片按这个模式被处理过，直接秒速读取，拒绝重复劳动！
    cache_file = f"{image_path}.{mode}.cache.json"
    if os.path.exists(cache_file):
        print(f"⚡ [Cache Hit] 命中本地缓存，跳过全部大模型推理，瞬间加载: {doc_name}")
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 缓存损坏，系统将重新解析: {e}")
    # ============================================

    print(f"\n" + "=" * 50)
    print(f"🎬 开始处理卷宗: 【{doc_name}】 (业务模式: {mode})")
    print(f"=" * 50)

    try:
        print(f"[{doc_name}] ⏳ [1/4] 正在读取本地图片并转码 Base64...")
        base64_image = encode_image_to_base64(image_path)
    except Exception as e:
        print(f"[{doc_name}] ❌ 崩溃：图片读取失败！\n报错详情: {e}")
        return {"文书类别": "系统错误", "其他信息": "图片读取或转码失败"}

    print(f"👁️ 正在启动 DeepSeek-OCR 像素剥离: {doc_name}...")
    ocr_start_time = time.time()

    try:
        ocr_payload = {
            "model": "deepseek-ocr:latest",
            "prompt": "请仔细提取图片中的所有文字内容，不要输出废话和坐标格式。",
            "images": [base64_image],
            "stream": False,
            "keep_alive": 0,
            "options": {"temperature": 0.1, "top_p": 0.5}
        }
        ocr_response = requests.post(OLLAMA_VISION_URL, json=ocr_payload, timeout=120)
        if ocr_response.status_code == 200:
            raw_ocr_text = ocr_response.json().get("response", "").strip()
            ocr_cost = time.time() - ocr_start_time
            print(f"[{doc_name}] ⚡ [3/4] 接口响应成功！网络耗时: {ocr_cost:.1f} 秒。")

            clean_text = re.sub(r'<\|.*?\|>', '', raw_ocr_text)
            clean_text = re.sub(r'\[\[.*?\]\]', '', clean_text)
            fluff_patterns = [r"^好的[，。！,!\s]*", r"^以下是.*?[:：\n]", r"以上内容[为是已].*?[。！!]",
                              r"按照您?[的]?要求.*?[。！!]", r"没有包含任何.*?[。！!]", r"这是图片中.*?[。！!]"]
            for pattern in fluff_patterns:
                clean_text = re.sub(pattern, '', clean_text, flags=re.MULTILINE)
            clean_text = clean_text.strip()
            print(f"[{doc_name}] ✅ OCR 成功！提取 {len(clean_text)} 个字符。")

        else:
            return {"文书类别": "OCR_引擎报错", "其他信息": f"状态码: {ocr_response.status_code}"}
    except Exception as e:
        return {"文书类别": "OCR_请求异常", "其他信息": str(e)}

    # ====== 🌟 核心升级 2：纯OCR直通车 ======
    # 如果指定了纯OCR模式，提取完文字直接跑路，彻底封杀耗时的逻辑大脑！
    if mode == "纯OCR":
        print(f"🚀 [提速直通车] 已跳过逻辑大脑解析，直接交付纯净文本。")
        result = {"文书类别": "原始扫描文本", "提取内容": clean_text}

        # 存入缓存
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return result

    # ==========================================
    # 🧠 第二步：呼叫 Qwen 主审大脑 (动态分流 Prompt)
    # ==========================================
    print(f"🧠 逻辑大脑正在解析案卷法理格式...")
    llm_start_time = time.time()

    if mode == "模式三":
        # ⚡ 根据细分的四种业务类型，进行靶向数据提取
        if batch_type in ["考核表扬", "物质奖励", "记功"]:
            prompt = f"""
                你是一个极速数据提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                请严格从下方文本中提取对应信息。
                💡 业务常识规则：如果是月度常规奖励，落款日期通常为当月的14日。
                必须严格输出合法的 JSON 格式，绝不要包含 Markdown 标识符(如```json)或多余文字：
                {{
                    "姓名": "提取出的名字",
                    "时间": "YYYY-MM-DD",
                    "事由": "简述因何获得奖励"
                }}

                【原始文本】
                {clean_text}
                """

        elif batch_type == "分级处遇":
            prompt = f"""
                你是一个极速数据提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                请严格从下方文本中提取对应信息。
                💡 业务常识规则：评测日期通常为1月7日、4月7日、7月7日或10月7日。处遇等级必须是“宽管”、“普管”、“考察”、“严管”之一的绝对标准词。
                必须严格输出合法的 JSON 格式，绝不要包含 Markdown 标识符(如```json)或多余文字：
                {{
                    "姓名": "提取出的名字",
                    "时间": "YYYY-MM-DD",
                    "处遇等级": "宽管/普管/考察/严管"
                }}

                【原始文本】
                {clean_text}
                """

        elif batch_type in ["减刑裁定", "假释裁定"]:
            prompt = f"""
                你是一个极速数据提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                请严格从下方文本中提取对应信息。
                必须严格输出合法的 JSON 格式，绝不要包含 Markdown 标识符(如```json)或多余文字：
                {{
                    "姓名": "提取出的名字",
                    "时间": "YYYY-MM-DD (裁定落款日期)",
                    "案号": "如(2026)冀XX刑更XX号",
                    "减刑幅度": "如减去有期徒刑五个月",
                    "新刑期止日": "YYYY-MM-DD"
                }}

                【原始文本】
                {clean_text}
                """

        elif batch_type == "惩处":
            prompt = f"""
                你是一个极速数据提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                请严格从下方文本中提取对应信息。
                💡 业务常识规则：处罚类别通常为“单独严管”、“警告”、“记过”、“禁闭”等。
                必须严格输出合法的 JSON 格式，绝不要包含 Markdown 标识符(如```json)或多余文字：
                {{
                    "姓名": "提取出的名字",
                    "时间": "YYYY-MM-DD (惩处日期)",
                    "处罚类别": "提取准确的处罚类别",
                    "惩处原因": "简述违反了什么纪律"
                }}

                【原始文本】
                {clean_text}
                """

        else:
            # 模式三的默认兜底（防止出现未知选项）
            prompt = f"""
                你是一个极速提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                请只从下方文本中提取【罪犯姓名】和【落款时间/裁判日期】。
                必须严格输出合法的 JSON 格式，不要包含任何其他文字或 markdown 标识。
                {{
                    "姓名": "提取出的名字",
                    "时间": "YYYY-MM-DD"
                }}

                【原始文本】
                {clean_text}
                """
    elif mode == "模式二":
        prompt = f"""
        你是一个专业的司法档案提取AI。
        【先验知识注入】明确告诉你，这是一份【{doc_category}】。请只按照该文书的结构提取【{target_name}】的信息。
        【用户特别指令】：{extra_prompt if extra_prompt else "无"}

        必须输出合法的 JSON 格式，绝不要包含 Markdown 标识符(如```json)或多余文字。
        {{
            "文书类别": "{doc_category}",
            "作出机关": "...", "案号": "...", "姓名": "...", "别化名": "...", "性别": "...", "出生日期": "...",
            "籍贯": "...", "捕前住址": "...", "起诉机关": "...", "起诉案号": "...", "起诉时间": "...",
            "拘留日期": "...", "逮捕日期": "...", "逮捕机关": "...", "前科及劣迹": "...", "主犯": "...", "累犯": "...",
            "涉黑恶职务金融": "...", "一审判决机关": "...", "一审判决案号": "...", "罪名": "...", "一审刑期": "...",
            "原判或现刑期起日": "...", "原判或现刑期止日": "...", "附加刑": "...", "财产性判项": "...", "犯罪事实": "...",
            "一审判决时间": "...", "二审判决机关": "...", "二审判决案号": "...", "二审判决时间": "...", "二审判决罪名": "...",
            "入监日期": "...", "奖惩情况": "...", "本文件记载的减刑历史": "...", "其他信息": "...", "本文件记载的日常奖惩": "..."
        }}
        【原始文本】
        {clean_text}
        """
    else:
        # 模式一原版
        prompt = f"""
        你是一个专业的司法档案提取AI。
        【核心任务】请提取与目标罪犯【{target_name}】相关的法理数据，忽略同案犯。
        上一张分类为【{previous_doc_type}】，中间页请优先继承。
        从白名单选择文书类别：["起诉书", "一审判决", "二审判决", "发回重审", "一审再审", "二审再审", "漏罪加刑", "狱内再犯罪", "执行通知书", "结案登记表", "入监登记表", "入监体检表", "历次减刑裁定", "年终鉴定表", "分级处遇表", "奖惩审批表", "财产性判项证据材料文书", "未分类文书"]
        必须输出合法 JSON。
        {{
            "文书类别": "...", "作出机关": "...", "案号": "...", "姓名": "...", "别化名": "...", "性别": "...", "出生日期": "...",
            "籍贯": "...", "捕前住址": "...", "起诉机关": "...", "起诉案号": "...", "起诉时间": "...", "拘留日期": "...", "逮捕日期": "...", "逮捕机关": "...",
            "前科及劣迹": "...", "主犯": "...", "累犯": "...", "涉黑恶职务金融": "...", "一审判决机关": "...", "一审判决案号": "...", "罪名": "...", "一审刑期": "...",
            "原判或现刑期起日": "...", "原判或现刑期止日": "...", "附加刑": "...", "财产性判项": "...", "犯罪事实": "...", "一审判决时间": "...",
            "二审判决机关": "...", "二审判决案号": "...", "二审判决时间": "...", "二审判决罪名": "...", "入监日期": "...", "奖惩情况": "...",
            "本文件记载的减刑历史": "...", "其他信息": "...", "本文件记载的日常奖惩": "..."
        }}
        【原始文本】
        {clean_text}
        """

    payload = {"model": "qwen3.6:27b", "prompt": prompt, "stream": False, "keep_alive": 0,
               "options": {"temperature": 0.1}}

    try:
        response = requests.post(OLLAMA_VISION_URL, json=payload, timeout=180)
        if response.status_code == 200:
            raw_text = response.json().get("response", "{}")
            clean_str_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            clean_str = clean_str_match.group(0) if clean_str_match else "{}"
            try:
                result_json = json.loads(clean_str)
                # ====== 🌟 核心升级 3：存入缓存 ======
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(result_json, f, ensure_ascii=False, indent=2)
                except Exception as ce:
                    print(f"⚠️ 缓存写入失败: {ce}")
                # ====================================
                return result_json
            except json.JSONDecodeError:
                print(f"⚠️ {doc_name} JSON格式崩溃！")
                return {"文书类别": "格式崩溃_需人工核查", "系统提示": "模型JSON崩溃，提取原文本：",
                        "抢救出的原始文本": raw_text}
        else:
            return {"error": "逻辑大脑调用失败"}
    except requests.exceptions.Timeout:
        return {"文书类别": "识别超时_需人工复核", "姓名": target_name, "其他信息": "严重超时跳过"}
    except Exception as e:
        return {"文书类别": "逻辑大脑_请求异常", "其他信息": str(e)}


def process_batch_documents(image_paths: list, target_name: str):
    all_extracted_data = []
    for path in image_paths:
        doc_name = os.path.basename(path)
        data = extract_single_document(path, doc_name, target_name)
        all_extracted_data.append({"source_file": doc_name, "extracted_content": data})
    return all_extracted_data