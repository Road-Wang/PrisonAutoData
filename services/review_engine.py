import os
import json
import re
import traceback
from datetime import datetime
from typing import Dict, Any, List

# 引入已有的视觉提取、大模型接口和数据库组件
from services.vision_extractor import extract_single_document
from services.screening_engine import ScreeningEngine, CriminalProfile
from db_manager import get_criminal_dynamic_data
from services.ocr_locator import OCRLocator

import requests
import json
import re

from PIL import Image
import io

import base64
import requests
import json


def call_qwen_vl(image_path: str) -> str:
    """
    专门用于长图/复杂图兜底的视觉大模型 (Vision LLM) 调用函数。
    直接将图片喂给大模型，让大模型“看图说话”提取纯文本。
    """
    try:
        # 1. 读取本地图片并转换为 Base64
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        return f"兜底失败：图片文件读取异常 {e}"

    # 2. 组装发给 Ollama 的多模态请求
    ollama_url = "http://127.0.0.1:11434/api/generate"
    payload = {
        "model": "qwen3.6:27b",  # 👈 使用你指定的模型名称
        "prompt": "你是一个高精度的司法文书文字提取器。请逐字提取这张图片中的所有文字信息，保留原本的段落结构和表格信息。绝对不要解释，不要输出除了图片文字以外的任何废话。",
        "images": [base64_image],
        "stream": False,
        "options": {
            "temperature": 0.0,  # 🌟 极其重要：设为 0，防止大模型看着图片自己瞎编案情
            "num_ctx": 4096  # 给足上下文
        }
    }

    try:
        # 3. 发起请求，设置 2 分钟超时
        response = requests.post(ollama_url, json=payload, timeout=120)
        response.raise_for_status()

        # 4. 解析大模型的返回结果
        result_text = response.json().get("response", "").strip()

        # 简单清洗一下可能存在的大模型“废话”
        if result_text.startswith("好的"):
            result_text = result_text.split("\n", 1)[-1]

        print(f"✅ Qwen-VL 兜底提取成功！提取了 {len(result_text)} 个字符。")
        return result_text

    except requests.exceptions.Timeout:
        return "兜底失败：视觉大模型推理也超时了"
    except Exception as e:
        return f"兜底失败：视觉大模型调用异常 {str(e)}"



def run_review_llm(prompt: str) -> dict:
    """
    专为高强度法理比对打造的大模型调用函数。
    增加了超大上下文支持、强制JSON提取与零温度严谨模式。
    """
    print("🧠 正在呼叫本地审查大模型 (启用超长上下文与深核逻辑解析)...")

    # 请确保此处的 URL 是你实际本地 Ollama 服务的地址
    ollama_url = "http://127.0.0.1:11434/api/generate"

    payload = {
        # 🚨 强烈建议：审查任务极其吃逻辑，建议使用 qwen2.5:32b 或更大模型
        "model": "qwen3.6:27b",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,  # 🌟 绝对严谨：温度降至 0，消除一切随机性，绝不允许AI自我发挥
            "num_ctx": 16384,  # 🌟 核心修复：开辟 16K 的巨大上下文窗口，容纳所有卷宗与法理规则
            "top_p": 0.1,  # 限制词汇选择范围，增加确定性
        }
    }

    try:
        # 放宽超时时间到 5 分钟，给予模型充分的“逐字核对”思考时间
        response = requests.post(ollama_url, json=payload, timeout=300)
        response.raise_for_status()

        # 获取返回纯文本
        raw_text = response.json().get("response", "{}")

        # 🌟 强力洗脱 Markdown 外衣
        raw_text = raw_text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0]
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0]

        # 兜底：精确捕获大括号内的内容
        clean_str_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        clean_str = clean_str_match.group(0) if clean_str_match else "{}"

        # 转换为 Python 字典
        return json.loads(clean_str)

    except json.JSONDecodeError:
        print("❌ 模型输出了非法的 JSON 格式")
        return {
            "error": "大模型返回格式无法解析，请人工复核卷宗",
            "raw_output": raw_text  # 把乱码原样返回，便于排查
        }
    except requests.exceptions.Timeout:
        print("❌ 审查大模型推理超时")
        return {"error": "卷宗内容过多，大模型审查超时（超过5分钟）"}
    except Exception as e:
        print(f"❌ 呼叫本地大模型失败: {e}")
        return {"error": f"审查大模型连接/推理异常: {str(e)}"}


class ReviewEngine:
    def __init__(self, criminal_name: str, archives_base_dir: str = "Prison_Archives"):
        self.criminal_name = criminal_name
        self.archives_base_dir = archives_base_dir
        # 严格对应你要求的文件夹名称
        self.target_folders = [
            "起诉书", "一审判决", "二审判决", "执行通知书",
            "结案登记表", "入监登记表", "历次减刑裁定", "奖惩审批表"
        ]

    def _extract_long_image_safe(self, image_path: str, doc_type: str) -> str:
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                if height / width < 2.0:
                    return str(extract_single_document(image_path, doc_type, self.criminal_name, mode="纯OCR"))

                print(f"✂️ 检测到长截图，启动【重叠防断行切片】...")
                # 假设宽度为标准，高度设为宽度的 1.5 倍
                piece_height = int(width * 1.5)
                overlap = int(width * 0.15)  # 🌟 核心：15% 的像素重叠，绝对不会再把字拦腰切断！

                extracted_texts = []
                # 步长为 piece_height - overlap
                for i in range(0, height, piece_height - overlap):
                    box = (0, i, width, min(i + piece_height, height))
                    piece = img.crop(box)
                    temp_piece_path = f"{image_path}_piece_{i}.jpg"
                    piece.convert("RGB").save(temp_piece_path, "JPEG")

                    # 1. 尝试使用常规纯OCR直通车提取
                    print(f"⏳ 正在使用常规 OCR 解析切片 {i}...")
                    text = extract_single_document(temp_piece_path, doc_type, self.criminal_name, mode="纯OCR")

                    # 2. 🌟 综合判定 OCR 是否真的失败了（这三道防线缺一不可）
                    is_ocr_failed = False
                    text_str = str(text)

                    # 防线一：如果返回的是一个字典，且字典里包含了报错关键词
                    if isinstance(text, dict):
                        error_keywords = ["异常", "报错", "失败", "超时", "error", "Timeout"]
                        if any(kw in text_str for kw in error_keywords):
                            is_ocr_failed = True

                    # 防线二：如果返回内容特别短（说明提取出来的全是空白）
                    elif len(text_str.strip()) < 20:
                        is_ocr_failed = True

                    # 防线三：包含 requests 库的典型断连报错字符串
                    elif "Read timed out" in text_str or "ConnectionPool" in text_str:
                        is_ocr_failed = True

                    # 3. 🚨 触发多模态视觉大模型兜底！
                    if is_ocr_failed:
                        print(f"⚠️ 切片 {i} 常规 OCR 彻底崩溃/超时！正在呼叫 Qwen 多模态视觉大脑强行突围...")
                        # 👈 调用我们刚写的兜底函数
                        text = call_qwen_vl(temp_piece_path)

                    extracted_texts.append(str(text))

                    # 阅后即焚
                    if os.path.exists(temp_piece_path):
                        os.remove(temp_piece_path)

                    extracted_texts.append(str(text))
                    os.remove(temp_piece_path)

                return "\n---(重叠切片接缝)---\n".join(extracted_texts)
        except Exception as e:
            return f"图片解析异常: {str(e)}"

    def _fetch_raw_archives(self, force_refresh: bool = False) -> Dict[str, str]:
        """
        核心：动态遍历 Prison_Archives 目录。
        加入【持久化缓存机制】，第一次耗时提取后将永久保存，后续秒级加载。
        """
        criminal_dir = os.path.join(self.archives_base_dir, self.criminal_name)
        archive_texts = {}

        print(f"📂 [Review] 正在检索底层卷宗库: {criminal_dir}")
        if not os.path.exists(criminal_dir):
            print(f"⚠️ [Review] 警告：未找到该罪犯的实体卷宗目录。")
            return archive_texts

        # 定义缓存文件路径
        cache_file_path = os.path.join(criminal_dir, "raw_ocr_cache.json")

        # 1. 尝试秒级加载缓存（如果不强制刷新且缓存存在）
        if not force_refresh and os.path.exists(cache_file_path):
            print(f"⚡ [Cache Hit] 发现该犯的卷宗 OCR 缓存文件，直接秒级加载：{cache_file_path}")
            try:
                with open(cache_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 缓存文件损坏，将重新触发 OCR 解析: {e}")

        # 2. 如果没有缓存，则执行耗时的逐张 OCR 提取
        print(f"⏳ [OCR] 未发现缓存或触发强制更新，开始首次深度提取卷宗库 (耗时较长，请耐心等待)...")
        valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.pdf')

        for folder in self.target_folders:
            folder_path = os.path.join(criminal_dir, folder)
            if not os.path.exists(folder_path):
                continue

            folder_content = []
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith(valid_exts):
                        file_path = os.path.join(root, file)
                        print(f"👁️ [OCR] 正在溯源提取卷宗材料: {folder}/{file}")
                        try:
                            # 启用直通车模式，耗时从几分钟缩减为几秒！
                            res = extract_single_document(file_path, folder, self.criminal_name, mode="纯OCR")
                            folder_content.append(f"---【卷宗来源: {folder}/{file}】---\n{res}")
                        except Exception as e:
                            print(f"❌ 提取底层卷宗 {file_path} 失败: {e}")

            if folder_content:
                archive_texts[folder] = "\n".join(folder_content)

        # 3. 将漫长提取的结果写入缓存，造福以后
        if archive_texts:
            try:
                with open(cache_file_path, 'w', encoding='utf-8') as f:
                    json.dump(archive_texts, f, ensure_ascii=False, indent=4)
                print(f"💾 [Cache Saved] 卷宗原始 OCR 数据已永久保存至：{cache_file_path}")
            except Exception as e:
                print(f"⚠️ 缓存写入失败，但不影响本次审查: {e}")

        return archive_texts

    def _parse_term_to_months(self, term_str: str) -> int:
        """健壮的刑期解析器：将文字刑期转换为模块2所需的月数"""
        if not term_str or str(term_str) in ["无期徒刑", "死刑", "死缓"]:
            return 0
        y_match = re.search(r'(\d+|[一二三四五六七八九十]+)年', str(term_str))
        m_match = re.search(r'(\d+|[一二三四五六七八九十]+)个月', str(term_str))
        years, months = 0, 0
        chinese_num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
                           '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '二十': 20, '二十五': 25}

        if y_match:
            y_str = y_match.group(1)
            years = int(y_str) if y_str.isdigit() else chinese_num_map.get(y_str, 0)
        if m_match:
            m_str = m_match.group(1)
            months = int(m_str) if m_str.isdigit() else chinese_num_map.get(m_str, 0)

        total = years * 12 + months
        return total if total > 0 else 120  # 解析失败兜底为10年

    def _get_expected_reduction(self) -> str:
        """调用模块2的 ScreeningEngine 基于已入库的结构化数据推演法定减刑幅度"""
        print("🧮 [Review] 正在加载模块2的 screening_engine 进行法理对撞推演...")
        db_data = get_criminal_dynamic_data(self.criminal_name)
        if not db_data:
            return "无法测算（未能在结构化数据库找到该犯数据）"

        try:
            sentence_type = str(db_data.get("一审判决刑种", db_data.get("一审刑种", "有期徒刑")))
            if "无期" in sentence_type:
                sentence_type = "无期徒刑"
            elif "死缓" in sentence_type:
                sentence_type = "死缓"
            else:
                sentence_type = "有期徒刑"

            term_str = db_data.get("一审判决刑期", db_data.get("一审刑期", db_data.get("刑期", "")))
            term_months = self._parse_term_to_months(term_str)

            crimes_raw = db_data.get("一审判决罪名", db_data.get("罪名列表", db_data.get("罪名", [])))
            crime_tags = crimes_raw if isinstance(crimes_raw, list) else [crimes_raw] if crimes_raw else ["未知罪名"]

            history = db_data.get("历次刑罚变动", db_data.get("本文件记载的减刑历史", []))
            is_first = len(history) == 0 or history == "无" or not history

            rewards = db_data.get("日常改造奖惩", [])
            if isinstance(rewards, str): rewards = []
            reward_count = sum(1 for r in rewards if isinstance(r, dict) and "表扬" in str(r.get("项目名称", "")))

            punishments = {}
            for r in rewards:
                if isinstance(r, dict) and r.get("类型") == "日常惩处":
                    ptype = str(r.get("项目名称", "警告"))
                    punishments[ptype] = punishments.get(ptype, 0) + 1

            strict_items = {}
            if str(db_data.get("是否累犯", db_data.get("累犯", ""))) in ["是", "有", "True"]: strict_items["累犯"] = 1
            if str(db_data.get("是否主犯", db_data.get("主犯", ""))) in ["是", "有", "True"]: strict_items["主犯"] = 1
            if str(db_data.get("职务犯罪", "")) in ["是", "有"]: strict_items["职务犯罪"] = 1
            if str(db_data.get("涉黑恶", db_data.get("涉黑", ""))) in ["是", "有"]: strict_items["涉黑"] = 1

            prop_exec = str(
                db_data.get("财产履行情况", db_data.get("财产性判项履行情况简述", db_data.get("财产执行", ""))))
            prop_unfulfilled = "未" in prop_exec or "终结执行" in prop_exec or "终结本次执行" in prop_exec

            profile = CriminalProfile(
                sentence_type=sentence_type,
                original_term_months=term_months,
                crime_count=len(crime_tags),
                crime_tags=crime_tags,
                is_first=bool(is_first),
                reference_date=datetime.now(),
                reward_count=reward_count,
                punishments=punishments,
                upgrade_date=None,
                strict_items=strict_items,
                property_unfulfilled=prop_unfulfilled
            )

            engine = ScreeningEngine(profile)
            result = engine.run_screening()
            if result.get("is_qualified"):
                return {
                    "reduction": result.get("recommended_reduction", "系统判定符合，但未返回幅度"),
                    "reasoning": result.get("legal_reasoning", "无详细推演步骤")
                }
            else:
                return {
                    "reduction": "不符合提请条件",
                    "reasoning": result.get('legal_reasoning', "条件不符")
                }

        except Exception as e:
            traceback.print_exc()
            return {
                "reduction": "测算异常",
                "reasoning": f"减刑幅度无法自动测算（系统参数缺失或报错: {str(e)}）"
            }

    def run_review(self, approval_img_paths: List[str], eval_img_paths: List[str],
                   force_refresh_archive: bool = False) -> Dict[str, Any]:
        """执行全流审查核心方法"""

        # 1. 抓取底层原件文本 (绝对真理)，传入刷新标识
        raw_archives = self._fetch_raw_archives(force_refresh=force_refresh_archive)
        if not raw_archives:
            return {"error": f"在 Prison_Archives/{self.criminal_name} 目录下未读取到有效的卷宗扫描件。"}

        # 2. 预测幅度及获取法理推演明细 (🌟这里只调用一次)
        expected_data = self._get_expected_reduction()
        expected_reduction = expected_data.get("reduction", "未知幅度")
        legal_reasoning = expected_data.get("reasoning", "无法理推演过程")

        # 3. 提取待审表单 (🌟 这里换装搭载坐标定位雷达的 OCRLocator)
        print("👁️ [Review] 正在解析待审表单并建立空间坐标系...")
        locator = OCRLocator()
        approval_texts = []
        for path in approval_img_paths:
            # 提取文本，坐标字典我们直接画图时再提，先只拿文本送给大模型
            text, _ = locator.extract_with_boxes(path)
            approval_texts.append(text)

        eval_texts = []
        for path in eval_img_paths:
            text, _ = locator.extract_with_boxes(path)
            eval_texts.append(text)


        # ---------------- 核心业务审查规则库 ----------------
        review_prompt = f"""
        你是一个严苛的监狱刑罚执行数据审查总警长。
        你需要严格核对【底层原始档案扫描件内容(绝对真理)】与刚上传的【审批表】和【评议表】，逐字检查表单填写的错误并给出修改建议。

        【底层系统调取的卷宗原始扫描件内容（三书一表、裁定及奖惩等）】
        {json.dumps(raw_archives, ensure_ascii=False, indent=2)}

        【系统基于法理算出的应减刑建议】
        {expected_reduction}

        【新提交的审批表 OCR 内容（受检对象）】
        {approval_texts}

        【新提交的评议表 OCR 内容（受检对象）】
        {eval_texts}

        🚨 必须运用你的审查逻辑，参考原始扫描件文本，严格执行以下 13 条狱政审查红线规则：

        === 第一部分：基础信息核对 ===
        1. **别名**：只能包含起诉书、一审判决、二审判决、执行通知书、结案登记表中明确写为“别名”的名字，严禁抓取曾用名、绰号、小名等。如无，表单为空不视为错误。
        2. **文化程度**：必须以判决书为准！严格区分“毕业”与“肄业”。
        3. **籍贯**：若三书一表未明确写明，则填户籍所在地。格式必须是“省+市”或“省+县”。
        4. **捕前住址**：必须与户籍所在地区分开。
        5. **入监时间**：必须为本次服刑进入【第一个监狱】的时间，参考入监登记表。

        === 第二部分：强制措施与初次刑期 ===
        6. **拘留日期**：参考起诉/判决书。若同一个案件多次拘留，【必须以执行通知书开始折抵的日期】为准。没有拘留日期的留空算正确。
        7. **逮捕日期及机关**：逮捕日期为公安实际执行日。逮捕机关名称必须以三书一表为准，严查机构更名（如“保定市公安局北市区分局”不能漏字或写错）。
        8. **初次刑期起止**：“无期、死缓”一审判决绝对不能填写刑期起止日期！二审起日以执行通知书起日为准（无起日看落款）。“死缓减无期”的，无期起日必须为死缓届满的第二日。

        === 第三部分：犯罪事实与【历次裁判、刑罚变动明细】 ===
        9. **主要犯罪事实**：必须囊括该犯所有罪名！如果扫描件显示系“主犯”或“首要分子”，必须在栏目中原样写明。
        10. **前科劣迹（其他犯罪史）**：必须与原件一致，并写明“刑满释放日期”或“附加刑”。如果是“累犯”，必须写明该犯系累犯。且【审批表】与【评议表】的内容必须一字不差！
        11. **历次裁判及刑罚变动明细**：审查审批表“项目”栏下的“一审判决”、“二审判决”、“减刑”等条目，必须严格参照一审、二审判决书及【历次减刑裁定】进行全要素核查！重点审查：
            (1) **裁判机关**与**裁判文号**：必须一字不差；
            (2) **裁判日期**：准确无误；
            (3) **刑期**：核对本次减刑或加刑后的当前总刑期。若表单未直接写明，请根据原判刑期减去减刑幅度进行数学计算来验证！
            (4) **刑期起止**：遵循起止日期推算逻辑；
            (5) **附加刑**：极易遗漏“没收个人全部财产”，重点核对！剥政若在“无期减有期”时由终身变为某年，以裁定原文为准。

        === 第四部分：奖惩与财产性判项 ===
        12. **有效奖惩规则**：（1）奖励栏中【绝对不能】出现“物质奖励”；（2）死缓期间获得的奖励（与减为无期前的时间有重叠的）【严禁出现】在本次提请中；（3）奖励一般每6个月一次，根据本次表单提请日期推算，判断是否“漏录”了最新的奖励。
        13. **评议表与财产规定**：财产性判项严格区分“履行完毕”、“终结执行”、“终结本次执行程序”，必须与档案扫描件原汁原味对照！评议表中若写“XX年度狱级改造积极分子”，XX必须是获奖时间的【前一年】。

        【重要强制批注指令】：为了能在原图上模仿人类警官“批改卷宗”，你必须在 JSON 的每一个检查项中新增一个 "keyword_in_image" 字段。
        该字段必须【一字不差】地提取自你核对的那行 OCR 文本原文！
        - 如果该项【异常/疑点】，提取写错的那个词（如档案是四川省，表单是四川，提取“四川”）。
        - 如果该项【通过】，提取表单上该栏目最核心的那个正确对账词（例如核对财产完全正确，提取“履行完毕”；核对前科正确，提取“累犯”）。
        如果在图上找不到对应文字或留空，请填 "无"。
        
        请输出严格合法的 JSON，只输出 JSON，不要输出 Markdown 标记，确保 Python 能直接解析：
        {{
            "基本身份信息": {{"status": "通过" 或 "异常", "error": "...", "suggestion": "..."}},
            "强制措施与刑期起止": {{"status": "通过" 或 "异常", "error": "...", "suggestion": "..."}},
            "犯罪事实与前科劣迹": {{"status": "通过" 或 "异常", "error": "...", "suggestion": "..."}},
            "历次裁判与附加刑变动": {{"status": "通过" 或 "异常", "error": "...", "suggestion": "..."}},
            "奖励与处分核对": {{"status": "通过" 或 "异常", "error": "...", "suggestion": "..."}},
            "财产判项与积极分子": {{"status": "通过" 或 "异常", "error": "...", "suggestion": "..."}},
            "监区减刑幅度": {{"status": "通过" 或 "异常", "error": "...", "suggestion": "..."}},
            "综合评价": "对该卷宗录入质量的整体综合判定（简短总结）"
        }}
        """

        review_result = run_review_llm(review_prompt)
        review_result["法定幅度推演明细"] = legal_reasoning

        # 🌟 4. 新增：自动画图拦截逻辑 (支持红圈、黄三角、绿对勾) 🌟
        print("🎨 [Review] 正在将大模型批注反馈至坐标空间...")

        annotations_to_draw = []
        for key, value in review_result.items():
            if isinstance(value, dict):
                # 兼容不同命名
                keyword = value.get("keyword_in_image") or value.get("error_keyword_in_image")
                status = value.get("status")

                # 只要大模型提取了字，且字不是"无"，我们就画图批注
                if keyword and keyword != "无":
                    annotations_to_draw.append({
                        "keyword": keyword,
                        "status": status
                    })

        # 渲染批改后的图片
        annotated_image_paths = []
        for path in approval_img_paths + eval_img_paths:
            output_path = f"{path}_annotated.jpg"
            locator.draw_annotations(path, annotations_to_draw, output_path)
            annotated_image_paths.append(output_path)

        review_result["annotated_images"] = annotated_image_paths

        return review_result