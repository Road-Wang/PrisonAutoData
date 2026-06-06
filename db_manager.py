import sqlite3
import json
import os
import shutil

DB_PATH = "prison_archive.db"


# ==========================================
# 🌟 核心防错引擎：多锚点拾取器
# ==========================================
def safe_get(data_dict, possible_keys, default_val="无"):
    if not isinstance(data_dict, dict):
        return default_val
    for key in possible_keys:
        if key in data_dict and data_dict[key] is not None:
            val = str(data_dict[key]).strip()
            if val not in ["", "无", "None", "[]", "{}"]:
                return data_dict[key]
    return default_val


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS criminals_v5
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       criminal_number
                       TEXT
                       UNIQUE,
                       id_card
                       TEXT,
                       criminal_name
                       TEXT,
                       alias
                       TEXT,
                       gender
                       TEXT,
                       birth_date
                       TEXT,
                       origin
                       TEXT,
                       pre_arrest_address
                       TEXT,
                       detention_date
                       TEXT,
                       arrest_date
                       TEXT,
                       detention_agency
                       TEXT,
                       arrest_agency
                       TEXT,
                       pros_agency
                       TEXT,
                       pros_case_no
                       TEXT,
                       pros_date
                       TEXT,
                       t1_court
                       TEXT,
                       t1_case_no
                       TEXT,
                       t1_date
                       TEXT,
                       t1_crime
                       TEXT,
                       t1_sentence_type
                       TEXT,
                       t1_add_sentence
                       TEXT,
                       t1_prop_sentence
                       TEXT,
                       t1_term_start
                       TEXT,
                       t1_term_end
                       TEXT,
                       t2_court
                       TEXT,
                       t2_case_no
                       TEXT,
                       t2_date
                       TEXT,
                       t2_crime
                       TEXT,
                       t2_sentence_type
                       TEXT,
                       t2_add_sentence
                       TEXT,
                       t2_prop_sentence
                       TEXT,
                       t2_term_start
                       TEXT,
                       t2_term_end
                       TEXT,
                       is_principal
                       TEXT,
                       is_recidivist
                       TEXT,
                       is_underworld
                       TEXT,
                       is_financial
                       TEXT,
                       is_duty
                       TEXT,
                       is_evil
                       TEXT,
                       is_drugs
                       TEXT,
                       is_guns
                       TEXT,
                       prior_record
                       TEXT,
                       main_facts
                       TEXT,
                       prop_execution
                       TEXT,
                       dynamic_data
                       TEXT,
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')
    conn.commit()
    conn.close()


def save_criminal_to_db(data: dict):
    """模式一/模式二的智能存储逻辑：防重复、防覆盖双重校验"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    confirmed_data = data.get("confirmed_data", {})

    name = safe_get(confirmed_data, ["姓名", "罪犯姓名"], "未知")
    criminal_num_raw = safe_get(confirmed_data, ["罪犯编号", "档案号", "编号"], "")

    if not criminal_num_raw or str(criminal_num_raw).strip() in ["", "无", "None", "未知"]:
        criminal_number = None
    else:
        criminal_number = str(criminal_num_raw).strip()

    id_card = safe_get(confirmed_data, ["身份证号", "身份证件号", "身份证"], "无")
    alias = safe_get(confirmed_data, ["别化名", "曾用名", "化名", "别名"], "无")
    gender = safe_get(confirmed_data, ["性别"], "无")
    birth_date = safe_get(confirmed_data, ["出生日期", "出生年月"], "无")
    origin = safe_get(confirmed_data, ["籍贯", "户籍所在地", "原籍"], "无")
    pre_arrest_address = safe_get(confirmed_data, ["捕前住址", "家庭住址", "住址"], "无")

    detention_date = safe_get(confirmed_data, ["拘留日期", "拘留时间", "刑拘日期"], "无")
    arrest_date = safe_get(confirmed_data, ["逮捕日期", "逮捕时间"], "无")
    detention_agency = safe_get(confirmed_data, ["拘留机关", "拘留单位"], "无")
    arrest_agency = safe_get(confirmed_data, ["逮捕机关", "逮捕单位"], "无")

    pros_agency = safe_get(confirmed_data, ["起诉机关", "公诉机关", "人民检察院"], "无")
    pros_case_no = safe_get(confirmed_data, ["起诉案号", "起诉书号", "公诉案号"], "无")
    pros_date = safe_get(confirmed_data, ["起诉日期", "起诉时间", "公诉日期"], "无")

    t1_court = safe_get(confirmed_data, ["一审法院", "一审判决法院", "一审判决机关", "原判法院"], "无")
    t1_case_no = safe_get(confirmed_data, ["一审案号", "一审判决案号", "原判案号"], "无")
    t1_date = safe_get(confirmed_data, ["一审裁判日期", "一审判决日期", "一审判决时间", "原判日期", "原判时间"], "无")
    t1_crime_raw = safe_get(confirmed_data,
                            ["一审判决罪名", "一审罪名", "罪名", "原判罪名", "一审罪名列表", "罪名列表"], "无")
    t1_crime = "、".join(t1_crime_raw) if isinstance(t1_crime_raw, list) else str(t1_crime_raw)
    t1_sentence_type = safe_get(confirmed_data, ["一审判决刑种", "一审刑种", "原判刑种", "刑期"], "无")
    t1_add_sentence = safe_get(confirmed_data, ["一审判决附加刑", "一审附加刑", "附加刑", "剥夺政治权利", "剥权"], "无")
    t1_prop_sentence = safe_get(confirmed_data,
                                ["一审财产性判项", "一审判决财产性判项", "原判财产判项", "罚金", "没收财产"], "无")
    t1_term_start = safe_get(confirmed_data,
                             ["一审判决刑期起日", "一审刑期起日", "原判或现刑期起日", "现刑期起日", "刑期起日"], "无")
    t1_term_end = safe_get(confirmed_data,
                           ["一审判决刑期止日", "一审刑期止日", "原判刑期止日", "现刑期止日", "刑期止日"], "无")

    t2_court = safe_get(confirmed_data, ["二审法院", "二审判决法院", "二审机关", "终审法院"], "无")
    t2_case_no = safe_get(confirmed_data, ["二审案号", "二审判决案号", "终审案号"], "无")
    t2_date = safe_get(confirmed_data, ["二审裁判日期", "二审判决日期", "二审时间", "终审日期"], "无")
    t2_crime_raw = safe_get(confirmed_data, ["二审判决罪名", "二审罪名", "终审罪名", "一审罪名列表", "罪名列表"], "无")
    t2_crime = "、".join(t2_crime_raw) if isinstance(t2_crime_raw, list) else str(t2_crime_raw)
    t2_sentence_type = safe_get(confirmed_data, ["二审判决刑种", "二审刑种", "终审刑种"], "无")
    t2_add_sentence = safe_get(confirmed_data, ["二审判决附加刑", "二审附加刑", "二审附加险"], "无")
    t2_prop_sentence = safe_get(confirmed_data, ["二审财产性判项", "二审判决财产性判项"], "无")
    t2_term_start = safe_get(confirmed_data, ["二审判决刑期起日", "二审起日", "二审刑期起日"], "无")
    t2_term_end = safe_get(confirmed_data, ["二审判决刑期止日", "二审止日", "二审刑期止日"], "无")

    is_principal = safe_get(confirmed_data, ["是否主犯", "主犯"], "无")
    is_recidivist = safe_get(confirmed_data, ["累犯", "是否累犯"], "无")
    is_underworld = safe_get(confirmed_data, ["涉黑", "黑社会性质"], "无")
    is_financial = safe_get(confirmed_data, ["涉金融", "破坏金融管理秩序", "金融犯罪"], "无")
    is_duty = safe_get(confirmed_data, ["职务犯罪", "职务", "涉职务"], "无")
    is_evil = safe_get(confirmed_data, ["涉恶", "恶势力"], "无")
    is_drugs = safe_get(confirmed_data, ["涉毒", "毒品犯罪"], "无")
    is_guns = safe_get(confirmed_data, ["涉枪", "枪支犯罪"], "无")

    prior_record = safe_get(confirmed_data, ["前科及劣迹", "前科", "劣迹"], "无")
    main_facts = safe_get(confirmed_data, ["主要犯罪事实", "犯罪事实", "事实概括"], "无")
    prop_execution = safe_get(confirmed_data, ["财产性判项履行情况简述", "财产履行情况", "履行情况", "财产执行"], "无")

    dynamic_data_str = json.dumps(confirmed_data, ensure_ascii=False)

    try:
        existing_id = None
        if criminal_number:
            cursor.execute("SELECT id FROM criminals_v5 WHERE criminal_number = ?", (criminal_number,))
            row = cursor.fetchone()
            if row: existing_id = row[0]

        if not existing_id and name and name != "未知":
            cursor.execute("SELECT id FROM criminals_v5 WHERE criminal_name = ? ORDER BY id DESC LIMIT 1", (name,))
            row = cursor.fetchone()
            if row: existing_id = row[0]

        if existing_id:
            cursor.execute('''
                           UPDATE criminals_v5
                           SET criminal_number    = COALESCE(?, criminal_number),
                               id_card            = ?,
                               criminal_name      = ?,
                               alias              = ?,
                               gender             = ?,
                               birth_date         = ?,
                               origin             = ?,
                               pre_arrest_address = ?,
                               detention_date     = ?,
                               arrest_date        = ?,
                               detention_agency   = ?,
                               arrest_agency      = ?,
                               pros_agency        = ?,
                               pros_case_no       = ?,
                               pros_date          = ?,
                               t1_court           = ?,
                               t1_case_no         = ?,
                               t1_date            = ?,
                               t1_crime           = ?,
                               t1_sentence_type   = ?,
                               t1_add_sentence    = ?,
                               t1_prop_sentence   = ?,
                               t1_term_start      = ?,
                               t1_term_end        = ?,
                               t2_court           = ?,
                               t2_case_no         = ?,
                               t2_date            = ?,
                               t2_crime           = ?,
                               t2_sentence_type   = ?,
                               t2_add_sentence    = ?,
                               t2_prop_sentence   = ?,
                               t2_term_start      = ?,
                               t2_term_end        = ?,
                               is_principal       = ?,
                               is_recidivist      = ?,
                               is_underworld      = ?,
                               is_financial       = ?,
                               is_duty            = ?,
                               is_evil            = ?,
                               is_drugs           = ?,
                               is_guns            = ?,
                               prior_record       = ?,
                               main_facts         = ?,
                               prop_execution     = ?,
                               dynamic_data       = ?
                           WHERE id = ?
                           ''', (
                               criminal_number, id_card, name, alias, gender, birth_date, origin, pre_arrest_address,
                               detention_date, arrest_date, detention_agency, arrest_agency, pros_agency, pros_case_no,
                               pros_date,
                               t1_court, t1_case_no, t1_date, t1_crime, t1_sentence_type, t1_add_sentence,
                               t1_prop_sentence, t1_term_start, t1_term_end,
                               t2_court, t2_case_no, t2_date, t2_crime, t2_sentence_type, t2_add_sentence,
                               t2_prop_sentence, t2_term_start, t2_term_end,
                               is_principal, is_recidivist, is_underworld, is_financial, is_duty, is_evil, is_drugs,
                               is_guns,
                               prior_record, main_facts, prop_execution, dynamic_data_str, existing_id
                           ))
            print(f"💾 匹配到历史档案 (ID: {existing_id})，成功覆盖更新【{name}】的数据！")
        else:
            cursor.execute('''
                           INSERT INTO criminals_v5 (criminal_number, id_card, criminal_name, alias, gender, birth_date,
                                                     origin, pre_arrest_address,
                                                     detention_date, arrest_date, detention_agency, arrest_agency,
                                                     pros_agency, pros_case_no, pros_date,
                                                     t1_court, t1_case_no, t1_date, t1_crime, t1_sentence_type,
                                                     t1_add_sentence, t1_prop_sentence, t1_term_start, t1_term_end,
                                                     t2_court, t2_case_no, t2_date, t2_crime, t2_sentence_type,
                                                     t2_add_sentence, t2_prop_sentence, t2_term_start, t2_term_end,
                                                     is_principal, is_recidivist, is_underworld, is_financial, is_duty,
                                                     is_evil, is_drugs, is_guns,
                                                     prior_record, main_facts, prop_execution, dynamic_data)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ''', (
                               criminal_number, id_card, name, alias, gender, birth_date, origin, pre_arrest_address,
                               detention_date, arrest_date, detention_agency, arrest_agency, pros_agency, pros_case_no,
                               pros_date,
                               t1_court, t1_case_no, t1_date, t1_crime, t1_sentence_type, t1_add_sentence,
                               t1_prop_sentence, t1_term_start, t1_term_end,
                               t2_court, t2_case_no, t2_date, t2_crime, t2_sentence_type, t2_add_sentence,
                               t2_prop_sentence, t2_term_start, t2_term_end,
                               is_principal, is_recidivist, is_underworld, is_financial, is_duty, is_evil, is_drugs,
                               is_guns,
                               prior_record, main_facts, prop_execution, dynamic_data_str
                           ))
            print(f"💾 数据库未找到此人，成功为【{name}】建立全新档案！")
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ 数据库写入失败: {e}")
        return False
    finally:
        conn.close()


def get_criminal_dynamic_data(name: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT dynamic_data FROM criminals_v5 WHERE criminal_name = ? ORDER BY id DESC LIMIT 1",
                       (name,))
        row = cursor.fetchone()
        if row and row[0]: return json.loads(row[0])
    except Exception as e:
        print(f"⚠️ 历史提档失败: {e}")
    finally:
        conn.close()
    return None


# ==========================================
# ⚡ 新增：模式三专属，批量极速增量入库
# ==========================================
def process_batch_update(criminal_name: str, batch_type: str, action_date: str, source_image_path: str, extra_info: dict = None):
    """
        业务分流器：根据业务类型，执行完全不同的逻辑入库
        """
    if not criminal_name or criminal_name in ["未知", "无"]:
        print("⚠️ 无法识别罪犯姓名，跳过入库。")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id, dynamic_data FROM criminals_v5 WHERE criminal_name = ? ORDER BY id DESC LIMIT 1",
                       (criminal_name,))
        row = cursor.fetchone()

        if not row:
            print(f"⚠️ 警告：底座中未查到【{criminal_name}】的档案，请先走模式一为其建档！该页文件已跳过。")
            return False

        db_id, dynamic_data = row[0], json.loads(row[1])

        # --- 业务 1: 每月奖励件 ---
        if batch_type in ["考核表扬", "物质奖励"]:
            rewards = dynamic_data.get("日常改造奖惩", [])
            rewards.append({"获得时间": action_date, "项目名称": batch_type, "事由": extra_info.get("事由", "")})
            dynamic_data["日常改造奖惩"] = rewards

        # --- 业务 2: 分级处遇表 ---
        elif batch_type == "分级处遇":
            # 存储当前的处遇，方便后续打印文书时直接调用
            dynamic_data["当前处遇"] = extra_info.get("处遇等级", "普管")
            dynamic_data["处遇变动记录"] = dynamic_data.get("处遇变动记录", [])
            dynamic_data["处遇变动记录"].append({"时间": action_date, "等级": extra_info.get("处遇等级")})

        # --- 业务 3: 减刑裁定书 ---
        elif batch_type == "减刑裁定":
            changes = dynamic_data.get("历次刑罚变动", [])
            changes.append(
                {"变动时间": action_date, "裁定结果": extra_info.get("减刑幅度"), "案号": extra_info.get("案号")})
            dynamic_data["历次刑罚变动"] = changes
            dynamic_data["现刑期止日"] = extra_info.get("新刑期止日")

        # --- 业务 4: 惩处表 (随机上传) ---
        elif batch_type == "惩处":
            penalties = dynamic_data.get("日常改造奖惩", [])
            penalties.append({"获得时间": action_date, "类型": "日常惩处", "项目名称": extra_info.get("处罚类别"),
                              "原因": extra_info.get("惩处原因")})
            dynamic_data["日常改造奖惩"] = penalties

        new_json_str = json.dumps(dynamic_data, ensure_ascii=False)
        cursor.execute("UPDATE criminals_v5 SET dynamic_data = ? WHERE id = ?", (json.dumps(dynamic_data, ensure_ascii=False), db_id))
        conn.commit()

        # 物理归档整理：将临时图片移动至永久目录
        archive_dir = f"Prison_Archives/{criminal_name}"
        os.makedirs(archive_dir, exist_ok=True)

        safe_date = action_date.replace("-", "").replace("年", "").replace("月", "")
        new_filename = f"{safe_date}_{batch_type}.jpg"
        target_path = os.path.join(archive_dir, new_filename)

        shutil.copy(source_image_path, target_path)
        print(f"✅ 【{criminal_name}】{batch_type} 更新成功！扫描件已安全归档至: {target_path}")
        return True

    except Exception as e:
        print(f"❌ 批量更新报错: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()