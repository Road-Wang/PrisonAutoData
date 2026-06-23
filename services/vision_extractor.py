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
    # ====== 🌟 核心升级 1：旁路缓存拦截机制 (已修复 Key 碰撞) ======
    safe_target = target_name.strip() if target_name else "通用"
    safe_category = doc_category.strip() if doc_category else "通用分类"
    cache_file = f"{image_path}.{safe_target}.{safe_category}.{mode}.cache.json"

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

            # 💡 防御性编程：对于执行通知书，如果 OCR 提取出来的字数少于 20 个字，直接视为失败，拉起多模态兜底
            if len(clean_text) > 20:
                ocr_success = True
                print(f"[{doc_name}] ✅ OCR 成功！提取 {len(clean_text)} 个字符。")
            else:
                print(f"[{doc_name}] ⚠️ OCR 提取到的有效字符过少 (仅 {len(clean_text)} 字)，判定为扫描失效。")

        else:
            return {"文书类别": "OCR_引擎报错", "其他信息": f"状态码: {ocr_response.status_code}"}
    except Exception as e:
        return {"文书类别": "OCR_请求异常", "其他信息": str(e)}

    # ====== 纯OCR直通车 ======
    if mode == "纯OCR":
        if ocr_success:
            result = {"文书类别": "原始扫描文本", "提取内容": clean_text}
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return result
        else:
            return {"文书类别": "OCR严重报错", "提取内容": "纯 OCR 模式下发生底层提取失败"}

    # ==========================================
    # 🧠 第二步：生成动态 Prompt (自动适应失败状态)
    # ==========================================
    # 🌟 如果 OCR 成功，我们正常给 Qwen 喂文本。如果失败，我们给多模态大模型下达特殊的视觉指令。
    prompt_text_source = clean_text if ocr_success else "【系统指令：前期文字引擎因墨迹/排版问题扫描失效。请您作为高级视觉多模态大脑，直接审视附带的案卷原图，并完成以下数据结构的提取。】"
    print(f"🧠 逻辑大脑正在解析案卷法理格式...")

    if mode == "模式三":
        if batch_type in ["考核表扬", "物质奖励", "记功"]:
            prompt = f"""
                    你是一个极速数据提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                    请严格提取对应信息。如果是月度常规奖励，落款日期通常为当月14日。
                    必须严格输出合法的 JSON 格式：
                    {{ "姓名": "提取出的名字", "时间": "YYYY-MM-DD", "事由": "简述因何获得奖励" }}
                    【原始文本/图像指引】
                    {prompt_text_source}
                    """
        elif batch_type == "分级处遇":
            prompt = f"""
                    你是一个极速数据提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                    评测日期通常为1月/4月/7月/10月的7日。处遇等级必须是“宽管/普管/考察/严管”之一。
                    必须严格输出合法的 JSON 格式：
                    {{ "姓名": "提取出的名字", "时间": "YYYY-MM-DD", "处遇等级": "宽管/普管/考察/严管" }}
                    【原始文本/图像指引】
                    {prompt_text_source}
                    """
        elif batch_type in ["减刑裁定", "假释裁定"]:
            prompt = f"""
                    你是一个极速数据提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                    必须严格输出合法的 JSON 格式：
                    {{ "姓名": "名字", "时间": "裁定落款日期", "案号": "如(2026)冀XX刑更XX号", "减刑幅度": "如减去有期徒刑五个月", "新刑期止日": "YYYY-MM-DD" }}
                    【原始文本/图像指引】
                    {prompt_text_source}
                    """
        elif batch_type == "惩处":
            prompt = f"""
                    你是一个极速数据提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                    必须严格输出合法的 JSON 格式：
                    {{ "姓名": "名字", "时间": "惩处日期", "处罚类别": "单独严管/警告/记过/禁闭等", "惩处原因": "简述原因" }}
                    【原始文本/图像指引】
                    {prompt_text_source}
                    """
        else:
            prompt = f"""
                    你是一个极速提取API。这是一份【{batch_name}】(业务类别: {batch_type})。
                    必须严格输出合法的 JSON 格式：
                    {{ "姓名": "名字", "时间": "YYYY-MM-DD" }}
                    【原始文本/图像指引】
                    {prompt_text_source}
                    """
    elif mode == "模式二":
        prompt = f"""
                你是一个专业的司法档案提取AI。
                这是一份【{doc_category}】。请提取【{safe_target}】的信息。
                【重点指令】：{extra_prompt if extra_prompt else "无"}
                必须输出合法的 JSON 格式：
                {{
                    "文书类别": "{doc_category}", "作出机关": "...", "案号": "...", "姓名": "...", "别化名": "...", "性别": "...", "出生日期": "...",
                    "籍贯": "...", "捕前住址": "...", "起诉机关": "...", "起诉案号": "...", "起诉时间": "...", "拘留日期": "...", "逮捕日期": "...", "逮捕机关": "...",
                    "前科及劣迹": "...", "主犯": "...", "累犯": "...", "涉黑恶职务金融": "...", "一审判决机关": "...", "一审判决案号": "...", "罪名": "...", "一审刑期": "...",
                    "原判或现刑期起日": "...", "原判或现刑期止日": "...", "附加刑": "...", "财产性判项": "...", "犯罪事实": "...", "一审判决时间": "...",
                    "二审判决机关": "...", "二审判决案号": "...", "二审判决时间": "...", "二审判决罪名": "...", "入监日期": "...", "奖惩情况": "...",
                    "本文件记载的减刑历史": "...", "其他信息": "...", "本文件记载的日常奖惩": "..."
                }}
                【原始文本/图像指引】
                {prompt_text_source}
                """
    else:
        prompt = f"""
                你是一个专业的司法档案提取AI。请提取与【{safe_target}】相关的法理数据，忽略同案犯。
                上一张分类为【{previous_doc_type}】。
                必须输出合法的 JSON 格式：
                {{
                    "文书类别": "...", "作出机关": "...", "案号": "...", "姓名": "...", "别化名": "...", "性别": "...", "出生日期": "...",
                    "籍贯": "...", "捕前住址": "...", "起诉机关": "...", "起诉案号": "...", "起诉时间": "...", "拘留日期": "...", "逮捕日期": "...", "逮捕机关": "...",
                    "前科及劣迹": "...", "主犯": "...", "累犯": "...", "涉黑恶职务金融": "...", "一审判决机关": "...", "一审判决案号": "...", "罪名": "...", "一审刑期": "...",
                    "原判或现刑期起日": "...", "原判或现刑期止日": "...", "附加刑": "...", "财产性判项": "...", "犯罪事实": "...", "一审判决时间": "...",
                    "二审判决机关": "...", "二审判决案号": "...", "二审判决时间": "...", "二审判决罪名": "...", "入监日期": "...", "奖惩情况": "...",
                    "本文件记载的减刑历史": "...", "其他信息": "...", "本文件记载的日常奖惩": "..."
                }}
                【原始文本/图像指引】
                {prompt_text_source}
                """

    # ==========================================
    # 🧠 第三步：呼叫主审大脑 (分流：纯文本通道 vs 视觉兜底通道)
    # ==========================================
    llm_start_time = time.time()

    # 统一构建基础的 Qwen payload
    payload = {
        "model": "qwen3.6:27b",
        "prompt": prompt,
        "stream": False,
        "keep_alive": 0,
        "options": {"temperature": 0.1}
    }

    # 🌟 核心判断：动态追加视觉参数
    if ocr_success:
        print(f"🧠 [文本通道] OCR 成功，正在使用 Qwen 解析文字推演法理...")
    else:
        print(f"🚀 [视觉兜底通道] OCR 遇到障碍！正在激活 Qwen3.6 多模态视觉能力看图提取...")
        payload["images"] = [base64_image]  # 挂载原图 Base64

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


def stream_extract_from_full_text(combined_text: str, target_name: str, doc_category: str, extra_prompt: str):
    """
    🌟 专为模式二设计的：全文通读+双驱溯源提取流
    同时输出标准结构化数据与物理证据链，彻底封杀幻觉。
    """
    safe_target = target_name.strip() if target_name else "通用"
    prompt = f"""
    你是一个拥有超大上下文窗口且极其严谨的司法档案审计AI。
    【核心任务】
    请通读下方包含物理页码标记的【{doc_category}】全卷文本，精准提取罪犯【{safe_target}】的法理数据（必须忽略同案犯）。

    ⚠️【极端重要指令：开启双驱溯源，拒绝幻觉】
    你必须为你提取的每一个非空字段寻找铁证！你必须输出两部分内容：
    1. "confirmed_data": 用于永久入库的标准纯净键值对。
    2. "evidence_chain": 对应的证据溯源链。键名必须与 confirmed_data 完全一致，其值必须严格格式化为：“第X页原文：'包含该信息的完整句子'”。

    如果在全卷文本中没有任何一页提到该字段的内容（例如你没有看到任何关于“别化名”或“前科劣迹”的记录），该字段在 confirmed_data 中必须填空字符串 ""，在 evidence_chain 中填 "全卷未提及"。
    绝允许凭空编造、凭经验猜测或将同案犯的信息张冠李戴！

    【用户特别指令】：{extra_prompt if extra_prompt else "无"}

    必须严格输出合法的 JSON 格式，绝不要包含 Markdown 标识符(如```json)或多余文字：
    {{
        "confirmed_data": {{
            "文书类别": "{doc_category}", "作出机关": "...", "案号": "...", "姓名": "...", "别化名": "...", "性别": "...", "出生日期": "...",
            "籍贯": "...", "捕前住址": "...", "起诉机关": "...", "起诉案号": "...", "起诉时间": "...", "拘留日期": "...", "逮捕日期": "...", "逮捕机关": "...",
            "前科及劣迹": "...", "主犯": "...", "累犯": "...", "涉黑恶职务金融": "...", "一审判决机关": "...", "一审判决案号": "...", "罪名": "...", "一审刑期": "...",
            "原判或现刑期起日": "...", "原判或现刑期止日": "...", "附加刑": "...", "财产性判项": "...", "犯罪事实": "...", "一审判决时间": "...",
            "二审判决机关": "...", "二审判决案号": "...", "二审判决时间": "...", "二审判决罪名": "...", "入监日期": "...", "奖惩情况": "...",
            "本文件记载的减刑历史": "...", "其他信息": "...", "本文件记载的日常奖惩": "..."
        }},
        "evidence_chain": {{
            "作出机关": "第X页原文：'...' ",
            "案号": "第X页原文：'...' ",
            "姓名": "第X页原文：'...' ",
            "别化名": "第X页原文：'...' ",
            "一审刑期": "第X页原文：'...' "
            // ... 这里的键必须与上方 confirmed_data 每一个键保持1:1完全对应映射 ...
        }}
    }}

    【多页全卷原始文本 (已包含页面物理标记)】
    {combined_text}
    """

    payload = {
        "model": "qwen3.6:27b",
        "prompt": prompt,
        "stream": True,
        "keep_alive": 0,
        "options": {
            "temperature": 0.0,  # 🌟 强制将创造力降为0，极致追求确定性，防止胡言乱语
            "top_p": 0.1,
            "num_ctx": 32768
        }
    }

    try:
        response = requests.post(OLLAMA_VISION_URL, json=payload, stream=True, timeout=300)
        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    yield chunk.get("response", "")
        else:
            yield f'{{"error": "后端接口异常, 状态码: {response.status_code}"}}'
    except Exception as e:
        yield f'{{"error": "流式提取异常: {str(e)}"}}'