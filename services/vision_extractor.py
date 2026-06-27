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


# ==========================================
# 📚 全局动态文书骨架注册表 (Schema Registry)
# ==========================================
DOCUMENT_FIELD_REGISTRY = {
    "判决书": ["判决机关", "案号", "姓名", "别化名", "性别", "出生日期", "文化程度",  "籍贯", "捕前住址", "起诉机关", "起诉时间", "拘留日期", "逮捕日期", "拘留机关", "逮捕机关", "前科及劣迹", "主犯", "累犯", "涉黑恶职务金融", "罪名", "刑期", "刑期起日", "刑期止日", "附加刑", "财产性判项", "犯罪事实", "判决日期"],
    "减刑裁定书": ["裁定机关", "案号", "姓名", "别化名", "原判信息", "本次减刑所获得奖惩", "前科及劣迹", "财产性判项执行履行情况", "原判刑期", "现刑期起日", "现刑期止日", "减刑或假释幅度", "新刑期", "新刑期起日", "新刑期止日",  "裁定日期"],
    "执行通知书": ["执行机关", "案号", "姓名", "原判刑期起日", "原判刑期止日", "执行日期"],
    "结案登记表": ["结案日期", "姓名", "曾用名", "性别", "年龄", "民族", "出身", "成份", "文化程度", "特长", "籍贯", "捕前住址", "捕前职业、政治面目", "逮捕机关", "案件类别", "刑期", "过去违法、犯罪及处理情况", "是否剥夺政治权利",  "简历", "犯罪事实", "实际执行刑期", "释放类型"],
    "入监登记表": ["单位", "入监日期", "姓名", "别化名", "民族", "出生日期", "文化程度", "捕前职业", "原政治面貌", "特长", "身份证号", "籍贯", "原户籍所在地", "家庭住址", "婚姻状况", "拘留日期", "逮捕机关" , "逮捕日期", "判决书号", "判决机关", "判决日期", "罪名", "刑种",  "刑期", "刑期起止", "附加刑", "曾受何种惩处", "身体状况", "本人简历", "主要犯罪事实", "家庭成员及主要社会关系", "同案犯"],
    "入监体检表": ["姓名", "基础信息", "体检日期", "身高", "体重", "体貌特征", "既往病史", "检查项目", "主检医师意见"],
    "奖惩审批表": ["姓名", "奖惩日期", "奖惩类别", "奖惩事由"],
    "年终鉴定表": ["姓名", "鉴定年度", "基本信息",  "主要犯罪事实", "本年度奖罚情况", "个人鉴定", "包组干警意见", "鉴定落款时间"],
    "分级处遇": ["姓名", "审批日期", "原处遇等级", "新处遇等级", "调整原因"],
    "财产性判项材料": ["姓名", "出具机关", "执行案号", "财产性判项执行情况描述", "落款日期"],
    "起诉书": ["起诉机关", "起诉案号", "姓名", "指控犯罪事实", "指控罪名", "起诉日期"],
    # 🎯 默认兜底：如果干警选择了字典外的新文书，默认提取这几项基础信息防崩溃
    "通用默认兜底": ["姓名", "文书时间", "核心业务内容", "作出机关", "备注"]
}

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


def stream_extract_from_full_text(combined_text: str, target_name: str, doc_category: str, extra_prompt: str, last_page_b64: str = None):
    """
    🌟 专为模式二设计的：全文通读 + 双驱溯源 + 红章透视提取流
    """
    safe_target = target_name.strip() if target_name else "通用"

    # ==========================================
    # 🌟 核心升级：智能感知并拼装 JSON 骨架
    # ==========================================
    # 1. 自动匹配注册表中的文书类型
    matched_fields = DOCUMENT_FIELD_REGISTRY.get("通用默认兜底")
    for key, fields in DOCUMENT_FIELD_REGISTRY.items():
        if key in doc_category:
            matched_fields = fields
            break

    # 2. 自动生成 confirmed_data 和 evidence_chain 模板
    confirmed_data_template = {"文书类别": doc_category}
    evidence_chain_template = {}

    for field in matched_fields:
        confirmed_data_template[field] = "..."
        # 针对落款日期的智能挂载视觉指令
        if "时间" in field or "日期" in field:
            evidence_chain_template[field] = "尾页图片视觉透视：'...' (如果文本中找不到，请看原图)"
        else:
            evidence_chain_template[field] = "第X页原文：'...'"

    # 3. 转化为大模型认识的字符串模板
    dynamic_schema = json.dumps({
        "confirmed_data": confirmed_data_template,
        "evidence_chain": evidence_chain_template
    }, ensure_ascii=False, indent=4)

    prompt = f"""
    你是一个拥有超大上下文窗口且极其严谨的司法档案审计AI。
    【核心任务】
    请通读下方包含物理页码标记的【{doc_category}】全卷文本，精准提取罪犯【{safe_target}】的法理数据（必须忽略同案犯）。

    ⚠️【防崩溃核心指令】
    1. 短文书容错：如果 JSON 模板中的某些字段在原文中完全找不到，请直接填入 ""（空字符串），并在 evidence_chain 中填 "全卷未提及"。**绝对不允许因为找不到字段而中断输出或输出空字符！**
    2. 双驱溯源：必须在 evidence_chain 中提供原话出处。
    3. 红章透视：如果文本中找不到落款时间，务必启动视觉神经审视附带的图片，看穿公章提取年月日。

    【用户特别指令】：{extra_prompt if extra_prompt else "无"}

    必须严格输出合法的 JSON 格式，保持与下方结构完全一致，绝不要包含多余文字：
    {dynamic_schema}

    【多页全卷原始文本 (已包含页面物理标记)】
    {combined_text}
    """

    payload = {
        "model": "qwen3.6:27b",
        "prompt": prompt,
        "stream": True,
        "keep_alive": 0,
        "options": {
            "temperature": 0.1, # 🌟 【修复 2】：切勿设为 0.0，避开量化模型的 NaN 崩溃死穴
            "top_p": 0.5, # 适度调高 top_p 增加流畅度
            "num_ctx": 32768
        }
    }

    # 🌟 核心破局点：如果传来了最后一页的图片，直接挂载到视觉输入中！
    if last_page_b64:
        payload["images"] = [last_page_b64]

    has_meaningful_output = False

    try:
        response = requests.post(OLLAMA_VISION_URL, json=payload, stream=True, timeout=180)
        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    # 🚨 核心防线 1：拦截大模型底层的致命报错 (如 RTX 5090 显存溢出 OOM、上下文超限)
                    if "error" in chunk:
                        yield f'{{"error": "Ollama引擎底层报错: {chunk["error"]}"}}'
                        break
                    token = chunk.get("response", "")
                    if token:
                        if token.strip():
                            has_meaningful_output = True
                        yield token

        else:
            yield f'{{"error": "后端接口异常, 状态码: {response.status_code}"}}'
    except Exception as e:
        yield f'{{"error": "流式提取异常: {str(e)}"}}'

    # ==========================================
    # 🚨 绝对防御：静默崩溃拦截与降级抢救
    # ==========================================
    if not has_meaningful_output:
        warning_msg = "\n\n⚠️【系统警报：侦测到大模型由于篇幅冲突发生静默崩溃！正在自动剥离图片、压缩模板，启动降级抢救模式...】\n\n"
        yield warning_msg
        print(warning_msg)

        if "images" in payload:
            del payload["images"]
        payload["options"]["num_ctx"] = 4096
        payload["prompt"] = prompt.replace("审视附带的图片", "仅从OCR文本中尽力")

        try:
            response = requests.post(OLLAMA_VISION_URL, json=payload, stream=True, timeout=180)
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line.decode('utf-8'))
                        token = chunk.get("response", "")
                        if token:
                            yield token
            else:
                yield f'{{"error": "降级模式失败, HTTP {response.status_code}"}}'
        except Exception as e:
            yield f'{{"error": "降级模式彻底崩溃: {str(e)}"}}'