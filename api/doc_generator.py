from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from docxtpl import DocxTemplate
from typing import List
import sqlite3
import json
import os
import re
from io import BytesIO
from datetime import datetime
from urllib.parse import quote

import io
import zipfile
import pandas as pd
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml.ns import qn
router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "prison_archive.db")
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "提请减刑建议书模板.docx")


def safe_get(data_dict, possible_keys, default_val=""):
    if not isinstance(data_dict, dict): return default_val
    for key in possible_keys:
        if key in data_dict and data_dict[key] is not None:
            val = str(data_dict[key]).strip()
            if val not in ["", "无", "None", "[]", "{}"]: return data_dict[key]
    return default_val


def build_commutation_doc_context(data: dict) -> dict:
    name = safe_get(data, ["姓名", "name"], "未知")

    # 🌟 修复 1：强制匹配人工习惯的“性别男”
    gender = safe_get(data, ["性别", "gender"], "男").strip()
    if not gender.startswith("性别"):
        gender = f"性别{gender}"

    birth_date = safe_get(data, ["出生日期", "birth"], "XXXX年X月X日")
    birth_date = birth_date.replace("-", "年").replace(" ", "").replace("月日", "月")
    if len(birth_date) == 10 and birth_date[4] == '年' and birth_date[7] == '月':
        birth_date += "日"

    ethnicity = safe_get(data, ["民族", "nation"], "汉")
    if ethnicity.endswith("族"): ethnicity = ethnicity[:-1]

    origin = safe_get(data, ["籍贯", "origin"], "某省某市某县")
    if "区" in origin and "镇" in origin:
        origin = origin.split("区")[0] + "区"
    elif "县" in origin and "乡" in origin:
        origin = origin.split("县")[0] + "县"

    raw_crimes = safe_get(data, ["罪名列表", "一审判决罪名", "罪名", "t1_crime"], [])
    crimes = [c.strip() for c in str(raw_crimes).replace("、", ",").replace("，", ",").split(",")] if isinstance(
        raw_crimes, str) else raw_crimes
    crime_str = "、".join(crimes) if crimes and crimes[0] not in ["无", ""] else "未知罪名"

    t1_court = safe_get(data, ["一审法院", "原判法院"], "某某人民法院")
    t1_date = safe_get(data, ["一审裁判日期", "t1_date"], "XXXX年X月X日")
    t1_case_no = safe_get(data, ["一审案号", "t1_case_no"], "某刑初字第XX号")
    term = safe_get(data, ["刑期", "一审判决刑种"], "有期徒刑X年")
    bq = safe_get(data, ["剥权", "一审判决附加刑"], "剥夺政治权利X年")

    t1_prop = safe_get(data, ["一审财产判项", "一审判决财产性判项"], "")
    t1_prop_str = "" if "剥夺" in t1_prop or not t1_prop or t1_prop == "无" else f"，并处{t1_prop}"

    t1_info = f"因{crime_str}，经{t1_court}于{t1_date}作出{t1_case_no}判决书，判处{term}，{bq}{t1_prop_str}。"

    t2_court = safe_get(data, ["二审法院", "终审法院", "复核法院"])
    trial_and_sentence_summary = t1_info

    if t2_court and t2_court != "无":
        t2_case_no = safe_get(data, ["二审案号", "复核案号"], "")
        t2_date = safe_get(data, ["二审裁判日期", "复核日期"], "XXXX年X月X日")

        if "复" in t2_case_no or "复核" in t2_court or "核准" in safe_get(data, ["二审裁定结果"]):
            trial_and_sentence_summary = f"{t1_info}经{t2_court}于{t2_date}作出{t2_case_no}复核书，予以核准，刑期自XXXX年X月X日起。"
        else:
            appeal_reason = safe_get(data, ["上诉或抗诉情况"], "被告人不服提出上诉")
            t2_result = safe_get(data, ["二审裁定结果"], "驳回上诉，维持原判")
            trial_and_sentence_summary = f"{t1_info}{appeal_reason}。{t2_court}于{t2_date}作出{t2_case_no}刑事裁定，裁定：{t2_result}。"

    # 🌟 修复 2：彻底拦截“于由送押”这种空缺病句
    transfer_date = str(safe_get(data, ["入监时间", "送押时间"], "")).strip()
    transfer_from = str(safe_get(data, ["送押机关", "看守所"], "")).strip()
    if transfer_date and transfer_from and transfer_date not in ["无", "未知", ""] and transfer_from not in ["无",
                                                                                                             "未知",
                                                                                                             ""]:
        transfer_info = f"于{transfer_date}由{transfer_from}送押我狱服刑改造。"
    else:
        # 如果大模型没抓到时间，提供占位符供干警修改，绝不能拼出病句
        transfer_info = "于XXXX年X月X日由某某看守所送押我狱服刑改造。"

    changes = safe_get(data, ["历次刑罚变动", "减刑假释记录"], [])
    changes_str = ""
    for change in changes:
        c_date_raw = safe_get(change, ["变动时间", "裁定时间"], "XXXX-X-X")
        try:
            if "-" in c_date_raw:
                dt = datetime.strptime(c_date_raw, "%Y-%m-%d")
                c_date = f"{dt.year}年{dt.month}月{dt.day}日"
            else:
                c_date = c_date_raw
        except:
            c_date = c_date_raw

        c_court = safe_get(change, ["裁定法院", "法院"], "")
        c_content = safe_get(change, ["变动内容", "裁定内容"], "减去有期徒刑X个月")
        if not c_court or c_court == "无":
            c_court = "河北省高级人民法院" if "无期" in c_content or "有期" in c_content else "河北省保定市中级人民法院"

        c_content = c_content.replace("不变", "").replace("改为", "")
        changes_str += f"{c_date}经{c_court}裁定，{c_content}；"

    changes_str = changes_str.rstrip("；。") + "。" if changes_str else "无刑罚变动记录。"

    # 🌟 修复 3：强制转换大模型带的“一次”为干警习惯的“1次”
    rewards_detail_list = ""
    raw_score = 0.0
    rewards = safe_get(data, ["日常改造奖惩", "历次奖惩"], [])
    cutoff_date = datetime(2017, 10, 1)

    for reward in rewards:
        r_date_str = safe_get(reward, ["获得时间", "时间"], "1970-01-01")
        r_type = safe_get(reward, ["项目名称", "奖励类型"], "表扬")

        # 强制洗掉大模型自己带的后缀，防止变成“表扬一次1次”
        r_type = r_type.replace("一次", "").replace("1次", "").replace("次", "").strip()

        match = re.search(r'(\d{4})[-年/](\d{1,2})', r_date_str)
        if match:
            r_year, r_month = int(match.group(1)), int(match.group(2))
            ym_str = f"{r_year}年{r_month}月"
            r_date_obj = datetime(r_year, r_month, 1)
        else:
            ym_str = r_date_str
            r_date_obj = datetime(1970, 1, 1)

        rewards_detail_list += f"该犯{ym_str}获得{r_type}1次；"

        if r_date_obj < cutoff_date:
            if "积极分子" in r_type:
                raw_score += 0.75
            elif "表扬" in r_type:
                raw_score += 0.5
            elif "记功" in r_type:
                raw_score += 0.75
        else:
            if "表扬" in r_type:
                raw_score += 1.0
            elif "记功" in r_type:
                raw_score += 1.0

    rewards_detail_list = rewards_detail_list.rstrip("；。")

    prop_status = safe_get(data, ["财产性判项履行情况简述", "履行情况"], "无")
    if prop_status in ["无", "已全部履行", "履行完毕"]:
        property_execution_status = "该犯已履行生效裁判中的财产性判项。"
    else:
        property_execution_status = f"该犯财产性判项履行情况：{prop_status}。"

    prior_record = safe_get(data, ["前科及劣迹", "前科"], "无")
    prior_criminal_record = f"另查明，{prior_record}。" if prior_record and prior_record != "无" else ""

    context = {
        "name": name,
        "gender": gender,
        "birth_date": birth_date,
        "ethnicity": ethnicity,
        "origin": origin,
        "trial_and_sentence_summary": trial_and_sentence_summary,
        "transfer_info": transfer_info,
        "prison_changes_and_reductions": changes_str,
        "rewards_detail_list": rewards_detail_list,
        "total_rewards": int(raw_score + 0.5),
        "property_execution_status": property_execution_status,
        "prior_criminal_record": prior_criminal_record,
        "recommended_reduction": "减去有期徒刑X个月，剥夺政治权利X年不变",
        "current_year": str(datetime.now().year)
    }

    # 🌟 修复 4：终极标点净化器 (抹杀一切连打的句号)
    for key, value in context.items():
        if isinstance(value, str):
            # 将两个或两个以上的句号替换为一个句号
            cleaned_value = re.sub(r'。{2,}', '。', value)
            context[key] = cleaned_value

    return context


# ==========================================
# 🚀 接口1：获取文书预览内容 (带有记忆读取机制)
# ==========================================
# ==========================================
# 🚀 接口1：获取文书预览内容 (带有智能融合机制)
# ==========================================
@router.get("/preview_doc")
async def preview_doc(name: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT dynamic_data FROM criminals_v5 WHERE criminal_name = ? ORDER BY id DESC LIMIT 1",
                       (name,))
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="未在底座中查到档案")

        data = json.loads(row[0])

        # 1. 无论如何，先生成一份包含【最新动态信息】的初稿
        fresh_context = build_commutation_doc_context(data)

        # 2. 🌟 智能融合：如果库里已经保存过“人工定稿”，进行字段级混编
        if "reviewed_commutation_doc" in data:
            reviewed = data["reviewed_commutation_doc"]
            merged_context = fresh_context.copy()

            # 【锁定静态字段】：继承上次人工润色的心血
            merged_context["origin"] = reviewed.get("origin", fresh_context["origin"])
            merged_context["ethnicity"] = reviewed.get("ethnicity", fresh_context["ethnicity"])
            merged_context["trial_and_sentence_summary"] = reviewed.get("trial_and_sentence_summary",
                                                                        fresh_context["trial_and_sentence_summary"])
            merged_context["transfer_info"] = reviewed.get("transfer_info", fresh_context["transfer_info"])
            merged_context["property_execution_status"] = reviewed.get("property_execution_status",
                                                                       fresh_context["property_execution_status"])
            merged_context["prior_criminal_record"] = reviewed.get("prior_criminal_record",
                                                                   fresh_context["prior_criminal_record"])
            merged_context["recommended_reduction"] = reviewed.get("recommended_reduction",
                                                                   fresh_context["recommended_reduction"])

            # ⚠️ 注意：这里故意不去覆盖 prison_changes_and_reductions, rewards_detail_list, total_rewards
            # 让它们保持 fresh_context 的最新状态，从而实现“随时间动态变化”的需求！

            return {"status": "reviewed_and_merged", "context": merged_context}

        # 如果没有定稿记录，直接返回初稿
        return {"status": "generated", "context": fresh_context}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览提取失败: {str(e)}")


# ==========================================
# 🚀 接口2：保存定稿并渲染下载 Word
# ==========================================
class SaveDocPayload(BaseModel):
    name: str
    edited_context: dict


@router.post("/generate_and_save_doc")
async def generate_and_save_doc(payload: SaveDocPayload):
    # 1. 保存人工定稿入库
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, dynamic_data FROM criminals_v5 WHERE criminal_name = ? ORDER BY id DESC LIMIT 1",
                       (payload.name,))
        row = cursor.fetchone()

        if row:
            db_id = row[0]
            data = json.loads(row[1])
            # 将干警改好的字典，嵌套存在 JSON 黑洞里
            data["reviewed_commutation_doc"] = payload.edited_context
            cursor.execute("UPDATE criminals_v5 SET dynamic_data = ? WHERE id = ?",
                           (json.dumps(data, ensure_ascii=False), db_id))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"定稿保存警告: {e}")  # 容错，不阻断下载

    # 2. 将修改后的定稿渲染为 Word
    try:
        doc = DocxTemplate(TEMPLATE_PATH)
        doc.render(payload.edited_context)

        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        filename = f"提请减刑建议书_{payload.name}.docx"
        encoded_filename = quote(filename)
        headers = {'Content-Disposition': f"attachment; filename*=utf-8''{encoded_filename}"}

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文书模板渲染异常: {str(e)}")


# ==========================================
# 🚀 接口3：快捷获取罪犯编号 (新增)
# ==========================================
@router.get("/get_criminal_info")
async def get_criminal_info(name: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # 提取 criminal_number 字段
        cursor.execute("SELECT criminal_number FROM criminals_v5 WHERE criminal_name = ? ORDER BY id DESC LIMIT 1", (name,))
        row = cursor.fetchone()
        conn.close()
        return {"criminal_number": row[0] if row and row[0] else ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询档案编号失败: {str(e)}")


# ==========================================
# 🚀 1. 监舍点名册解析接口 (处理特殊的左右双栏排版)
# ==========================================
@router.post("/upload_rollcall")
async def upload_rollcall(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        # 跳过前两行表头，读取数据
        df = pd.read_excel(io.BytesIO(contents), skiprows=2)

        mappings = []

        # 提取左半区 (C区) 和 右半区 (D区) 的数据
        def extract_area(sub_df):
            current_officer = None
            current_room = None
            for _, row in sub_df.iterrows():
                officer_val = str(row.iloc[0]).strip()
                room_val = str(row.iloc[1]).strip()

                if officer_val and officer_val != 'nan':
                    current_officer = officer_val
                if room_val and room_val != 'nan':
                    current_room = room_val.replace('\n', '')

                # 遍历后面的成员列
                for col_idx in range(2, len(row)):
                    inmate_name = str(row.iloc[col_idx]).strip()
                    if inmate_name and inmate_name != 'nan' and not inmate_name.isdigit():
                        if current_officer:
                            mappings.append((inmate_name, current_officer, current_room))

        # 拆分左右栏 (假设左栏索引0-8，右栏索引10-18)
        left_df = df.iloc[:, 0:9]
        right_df = df.iloc[:, 10:19]

        extract_area(left_df)
        extract_area(right_df)

        # 写入数据库
        conn = sqlite3.connect("prison_archive.db")
        c = conn.cursor()
        c.execute("DELETE FROM inmate_officer_map")  # 清空旧数据
        c.executemany("""
                      INSERT INTO inmate_officer_map (inmate_name, officer_name, room_number)
                      VALUES (?, ?, ?)
                      """, mappings)
        conn.commit()
        conn.close()

        return {"status": "success", "message": f"成功更新 {len(mappings)} 名罪犯的包组归属信息！"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"点名册解析失败: {str(e)}")
# ==========================================
# 🚀 2. 三级会议纪要生成核心引擎
# ==========================================
def create_meeting_doc(meeting_type, month_str, inmates_list, personnel_dict):
    doc = Document()

    # 基础样式设置
    doc.styles['Normal'].font.name = u'仿宋'
    doc.styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'), u'仿宋')
    doc.styles['Normal'].font.size = Pt(16)  # 三号字

    # 动态辅助函数：添加带高亮的段落
    def add_run(p, text, is_dynamic=False, bold=False):
        run = p.add_run(text)
        if bold: run.bold = True
        if is_dynamic:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW

    # 计算日期 (默认25、27、29日)
    year, month = month_str.split('-')
    day = "25" if meeting_type == "提名" else ("27" if meeting_type == "评议" else "29")
    target_reduction_month = f"{year}年{int(month) + 1}月"  # 议题月份推后一月

    # 1. 标题
    titles = {
        "提名": "关于罪犯减刑假释案件提名评议记录",
        "评议": "关于罪犯减刑假释案件集体评议记录",
        "办公会": "关于罪犯减刑假释案件监区长办公会\n评议记录"
    }
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run(f"河北省保定监狱十五监区\n{titles[meeting_type]}")
    run_title.font.name = '黑体'
    run_title._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    run_title.font.size = Pt(22)
    run_title.bold = True

    # 2. 会议基本信息
    doc.add_paragraph(f"时间：{year}年{month}月{day}日")
    doc.add_paragraph("地点：监区会议室")

    p_host = doc.add_paragraph("主持人：")
    add_run(p_host, personnel_dict.get("监区长", "未设置"), is_dynamic=True)
    add_run(p_host, "（监区长）")

    p_attend = doc.add_paragraph("参加人员（姓名、职务）：")
    attend_str = "、".join([f"{name}({role})" for role, name in personnel_dict.items()])
    add_run(p_attend, attend_str, is_dynamic=True)

    doc.add_paragraph("列席人员（姓名、职务）：无")
    doc.add_paragraph("缺席人员（姓名、职务）：无")

    p_recorder = doc.add_paragraph("记录人（姓名、职务）：")
    add_run(p_recorder, personnel_dict.get("内勤", "未设置"), is_dynamic=True)

    p_topic = doc.add_paragraph("会议议题：")
    add_run(p_topic, f"{target_reduction_month}有、无期减刑", is_dynamic=True)

    # 3. 按包组干警分组罪犯数据
    grouped_inmates = {}
    for inmate in inmates_list:
        officer = inmate.get("officer_name", "未分配干警")
        if officer not in grouped_inmates:
            grouped_inmates[officer] = []
        grouped_inmates[officer].append(inmate)

    # 前置会议文案 (评议和办公会特有)
    if meeting_type == "评议":
        doc.add_paragraph("评议内容（记录评议详情及评议结果）：\n一、刑罚执行专职干警通报本次办案工作开展情况...")
    elif meeting_type == "办公会":
        doc.add_paragraph("评议内容（记录评议详情及评议结果）：\n一、刑罚执行专职干警汇报本次办案工作开展情况...")

    # 4. 核心罪犯遍历逻辑
    counter = 1
    for officer, inmates in grouped_inmates.items():
        if meeting_type == "提名":
            p_officer = doc.add_paragraph()
            add_run(p_officer, f"包组干警{officer}：", bold=True)

        for idx, inv in enumerate(inmates):
            p = doc.add_paragraph()

            # 如果是后两个会议，需要在段首加上包组干警汇报的话术
            if meeting_type != "提名" and idx == 0:
                add_run(p, f"包组干警{officer}汇报：\n", bold=True)

            # 基本情况拼接
            add_run(p, f"{counter}、罪犯")
            add_run(p, inv['name'], is_dynamic=True)
            add_run(p, f"因犯{inv.get('crime', '')}罪，判处{inv.get('sentence', '')}。")
            add_run(p, inv.get('entry_date', ''), is_dynamic=True)
            add_run(p, f"送押监狱服刑改造，服刑期间获得")
            add_run(p, str(inv.get('prev_reductions', 0)), is_dynamic=True)
            add_run(p, "次减刑。")

            # 奖励情况
            add_run(p, "该犯现奖励情况：")
            add_run(p, inv.get('rewards_str', '无'), is_dynamic=True)
            add_run(p, "。")

            # 扣分/推迟情况
            punishments = inv.get('punishments_str', '')
            if punishments:
                add_run(p, "该犯")
                add_run(p, punishments, is_dynamic=True)
                add_run(p, f"。自")
                add_run(p, inv.get('eligible_date', ''), is_dynamic=True)
                add_run(p, "符合呈报减刑条件，已按规定进行推迟。")

            # 财产情况
            add_run(p, "该犯")
            add_run(p, inv.get('property_status', '财产性判项已履行完毕'), is_dynamic=True)
            add_run(p, "。")

            # 减刑建议
            add_run(p, "监区对该犯建议提请")
            add_run(p, inv.get('proposed_reduction', '减去有期徒刑X个月'), is_dynamic=True)
            add_run(p, "。")

            counter += 1

    # 5. 结尾决议
    doc.add_paragraph("")
    p_dec = doc.add_paragraph("会议决议：\n    同意")
    names_str = "、".join([i['name'] for i in inmates_list])
    add_run(p_dec, names_str, is_dynamic=True)
    add_run(p_dec, f"等共 ")
    add_run(p_dec, str(len(inmates_list)), is_dynamic=True)
    add_run(p_dec, " 名罪犯提请减刑。")

    doc.add_paragraph("\n参加人员签名：\n\n\n\n\n\n")
    return doc


# ==========================================
# 🚀 接口：大模型会议纪要专用提取引擎 (新增)
# ==========================================
@router.post("/extract_meeting_archives")
async def extract_meeting_archives(files: List[UploadFile] = File(...)):
    try:
        # 这里模拟您调用大模型视觉提取服务 (vision_extractor.py 或 dify_client.py)
        # 💡 在实际生产代码中，您需要将 `files` 送入多模态大模型（如 GPT-4o 或 讯飞/智谱视觉模型）

        # 🌟 核心：给大模型的极度定制化 Prompt 指令如下：
        """
        你是一个专业的中国监狱刑罚执行业务 AI 助理。请阅读以下一系列档案扫描件，从中提取会议纪要所需的关键数据，并严格按照以下 JSON 格式返回。
        如果档案中涉及多名罪犯，请返回一个列表。
        提取规则：
        1. "inmate_name": 识别罪犯姓名。
        2. "crime": 从判决书/执行通知书中提取罪名（如：贩卖毒品罪）。
        3. "sentence": 提取原判刑期（如：无期徒刑，或有期徒刑十五年）。
        4. "entry_date": 从执行通知书/入监表提取送押入监日期（格式：XXXX年X月X日）。
        5. "prev_reductions": 阅读历次减刑裁定，统计已减刑的【次数】（纯数字）。
        6. "rewards_str": 汇总所有《奖励审批表》，输出高度浓缩的话术，格式必须为："该犯XXXX年X月、XXXX年X月...获得考核表扬X次"。
        7. "punishments_str": 汇总《惩处表》，格式为："XXXX年X月受到警告X次"（无惩处则留空字符串）。
        8. "property_status": 综合罚金、没收财产收据或终结执行裁定，用一句话总结（如：被判处没收个人全部财产，被保定市中院裁定终结本次执行程序）。
        """

        # ----------- 模拟大模型返回解析结果 -----------
        # 实际代码中，此处 result_json 应为大模型调用的返回结果
        extracted_data_from_llm = [
            {
                "inmate_name": "匡凤禹",
                "crime": "贩卖毒品罪",
                "sentence": "无期徒刑",
                "entry_date": "2015年11月16日",
                "prev_reductions": 2,
                "rewards_str": "2023年9月、2024年3月、2024年9月、2025年9月、2026年3月获得考核表扬5次",
                "punishments_str": "",
                "eligible_date": "2026年4月7日",  # 可结合大模型或后端逻辑计算
                "property_status": "被判处没收个人全部财产，被保定市中级人民法院裁定终结本次执行程序",
                "proposed_reduction": "减去有期徒刑六个月，剥夺政治权利十年不变"  # 可从业务系统算，或大模型抓取本次填报表
            }
        ]
        # ----------------------------------------------

        # 将大模型吐出的规范化 JSON 写入我们刚建好的 meeting_inmate_data 表
        conn = sqlite3.connect("prison_archive.db")
        c = conn.cursor()

        saved_names = []
        for data in extracted_data_from_llm:
            name = data.get("inmate_name")
            if not name: continue

            # 使用 REPLACE INTO，如果名字存在则更新，不存在则插入
            c.execute("""
                      REPLACE
                      INTO meeting_inmate_data 
                (inmate_name, crime, sentence, entry_date, prev_reductions, rewards_str, punishments_str, eligible_date, property_status, proposed_reduction)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                      """, (
                          name, data.get('crime'), data.get('sentence'), data.get('entry_date'),
                          data.get('prev_reductions', 0), data.get('rewards_str'), data.get('punishments_str'),
                          data.get('eligible_date'), data.get('property_status'), data.get('proposed_reduction')
                      ))
            saved_names.append(name)

        conn.commit()
        conn.close()

        return {"status": "success", "extracted_names": saved_names}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能档案解析失败: {str(e)}")

# ==========================================
# 🚀 接口升级：让纪要生成器真正读取数据库
# ==========================================
# 在您的 generate_meeting_docs 函数内部，修改遍历提取数据的部分：
@router.post("/generate_meeting_docs")
async def generate_meeting_docs(payload: dict):
    target_month = payload.get("month", "2026-06")
    inmate_names = payload.get("inmates", [])

    if not inmate_names:
        raise HTTPException(status_code=400, detail="请至少输入一名罪犯姓名")

    conn = sqlite3.connect("prison_archive.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 获取人员名单
    c.execute("SELECT role, name FROM ward_personnel WHERE is_active=1")
    personnel = {row['role']: row['name'] for row in c.fetchall()}

    # 提取罪犯信息及包组干警信息
    inmates_data = []
    for name in inmate_names:
        name = name.strip()
        # 1. 查询归属干警
        c.execute("SELECT officer_name FROM inmate_officer_map WHERE inmate_name=?", (name,))
        officer_row = c.fetchone()
        officer = officer_row['officer_name'] if officer_row else "待核实干警"

        # 🌟 3. 核心升级：从我们刚建好的大模型提取表 (meeting_inmate_data) 中抓取真实数据！
        c.execute("SELECT * FROM meeting_inmate_data WHERE inmate_name=?", (name,))
        db_row = c.fetchone()

        if db_row:
            # 数据库里有真实提炼的数据，直接组装
            inmate_info = {
                "name": name,
                "officer_name": officer,
                "crime": db_row['crime'] or "【罪名缺失】",
                "sentence": db_row['sentence'] or "【刑期缺失】",
                "entry_date": db_row['entry_date'] or "【入监日期缺失】",
                "prev_reductions": db_row['prev_reductions'] or 0,
                "rewards_str": db_row['rewards_str'] or "无奖励记录",
                "punishments_str": db_row['punishments_str'] or "",
                "eligible_date": db_row['eligible_date'] or "【起算日期缺失】",
                "property_status": db_row['property_status'] or "【财产履行情况缺失】",
                "proposed_reduction": db_row['proposed_reduction'] or "【拟减幅度缺失】"
            }
        else:
            # 🚨 如果该犯人没有通过 Tab3 上传过档案，提供醒目的标黄占位符
            inmate_info = {
                "name": name,
                "officer_name": officer,
                "crime": "【未解析档案，请补充】",
                "sentence": "【未解析档案】",
                "entry_date": "【XXXX年X月X日】",
                "prev_reductions": 0,
                "rewards_str": "【未提取到表扬数据】",
                "punishments_str": "【未提取到处分数据】",
                "eligible_date": "【未计算】",
                "property_status": "【未提取到财产信息】",
                "proposed_reduction": "【拟减刑幅度未填报】"
            }

        inmates_data.append(inmate_info)
    conn.close()
    # 批量生成三份文档
    doc1 = create_meeting_doc("提名", target_month, inmates_data, personnel)
    doc2 = create_meeting_doc("评议", target_month, inmates_data, personnel)
    doc3 = create_meeting_doc("办公会", target_month, inmates_data, personnel)

    # 打包为 ZIP 内存流下发
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for name, doc in [("包组干警提名会议.docx", doc1), ("集体评议记录.docx", doc2), ("监区长办公会.docx", doc3)]:
            doc_buffer = io.BytesIO()
            doc.save(doc_buffer)
            zip_file.writestr(name, doc_buffer.getvalue())

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={'Content-Disposition': 'attachment; filename="三级会议纪要_批量生成.zip"'}
    )

