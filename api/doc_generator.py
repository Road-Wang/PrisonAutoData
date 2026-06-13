from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from docxtpl import DocxTemplate
import sqlite3
import json
import os
import re
from io import BytesIO
from datetime import datetime
from urllib.parse import quote

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

