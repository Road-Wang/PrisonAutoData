import pandas as pd
import json
import requests
import re
from typing import List, Dict, Any

# ---------------------------------------------------------
# 1. 升级版：系统标准数据字典 (贴合真实监区数据)
# ---------------------------------------------------------
STANDARD_SCHEMA = {
    "criminal_name": "罪犯姓名",
    "crime_type": "所有罪名（一个或数罪并罚的多个罪名）",
    "first_instance_court": "一审机关",
    "first_instance_date": "一审判决日期",
    "first_instance_sentence": "一审刑期",
    "second_instance_court": "二审机关",
    "second_instance_date": "二审日期",
    "second_instance_result": "二审刑期或二审结果",
    "retrial_or_additional_info": "再审、发回重审或加刑判决信息",
    "term_start_date": "刑期起日",
    "term_end_date": "当前刑期止日",

    # 财产性判项（分拆明确，防止模型合并）
    "fine_amount": "罚金（万元）等金额列",
    "fine_execution": "罚金的缴纳/履行情况列",
    "civil_compensation": "民赔（万元）/ 民事赔偿金额列",
    "civil_execution": "民赔的履行情况列",
    "confiscation_of_property": "没收财产情况",
    "restitution_amount": "责令退赔或追缴的金额列",
    "restitution_execution": "责令退赔或追缴的履行/执行情况列",

    "criminal_type": "未成年犯、主从犯、累犯、三类、三涉等定性标签（可多对一）",
    # 减刑历史（不再让模型去猜哪次是最后一次，我们把这七次的日期和止日全部拉下来，用 Python 去算）
    "commutation_history_dates": "所有的第一到第七次减刑日期（多对一映射）",
    "commutation_history_ends": "所有的第一到第七次减刑刑期止日（多对一映射）",
    "current_points_summary": "当前最新的计分考核奖惩情况汇总"
}


def extract_json_from_text(text: str) -> dict:
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {}
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
        return {}


def get_smart_column_mapping(raw_columns: List[str]) -> Dict[str, str]:
    prompt = f"""
你是一名严谨的中国监狱刑罚执行文书审查专家。
请根据语义，将以下“Excel 原始列名”映射到我的“系统标准变量”上。

【系统标准变量及其含义】
{json.dumps(STANDARD_SCHEMA, ensure_ascii=False, indent=2)}

【Excel 原始列名】
{raw_columns}

【映射原则】
1. 财产性判项必须严格拆分！金额列映射为 _amount，其紧跟的履行情况列映射为 _execution。千万不要把金额和执行情况映射成同一个变量。
2. 表格中出现的七次减刑日期，请全部映射为 "commutation_history_dates"；对应的七次减刑止日，请全部映射为 "commutation_history_ends"。
3. 冗余信息全部映射为 "IGNORE"。
4. 必须只输出 JSON。
"""

    api_url = "http://127.0.0.1:11434/v1/chat/completions"
    payload = {
        "model": "qwen3.6:latest",
        "messages": [
            {"role": "system", "content": "你是一个只输出 JSON 的数据转换引擎。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }

    # 屏蔽代理，直连本地
    proxies = {"http": None, "https": None}

    try:
        response = requests.post(api_url, json=payload, proxies=proxies, timeout=180)
        response.raise_for_status()

        result_text = response.json()['choices'][0]['message']['content']
        match = re.search(r'\{.*\}', result_text, re.DOTALL)

        if match:
            return json.loads(match.group(0))
        return {}
    except Exception as e:
        print(f"映射失败：{e}")
        return {}


def parse_excel_smart(file_stream: Any) -> List[Dict[str, Any]]:
    # 读取所有列，强制按字符串读取，防止日期或长数字（如身份证）变成科学计数法
    df = pd.read_excel(file_stream, dtype=str)

    # 清洗原始表头（去除换行、空格）
    raw_columns = [str(col).replace('\n', '').strip() for col in df.columns.tolist()]
    df.columns = raw_columns

    print("正在呼叫 qwen3.6:latest 进行智能表头推演...")
    mapping_dict = get_smart_column_mapping(raw_columns)

    if not mapping_dict:
        raise ValueError("模型未返回有效的映射字典，请检查服务状态。")

    print(f"推演完成！有效的映射规则: { {k: v for k, v in mapping_dict.items() if v != 'IGNORE'} }")

    df.rename(columns=mapping_dict, inplace=True)

    # 丢弃 IGNORE 和未在标准库中的列
    valid_columns = [col for col in df.columns if col in STANDARD_SCHEMA.keys()]
    df_filtered = df[valid_columns]

    # 处理空值
    df_filtered = df_filtered.fillna("无")

    return df_filtered.to_dict(orient='records')