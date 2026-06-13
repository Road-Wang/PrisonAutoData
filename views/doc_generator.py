import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import datetime

# 根据您的 FastAPI 路由配置。假设 expenses 在 api/v1/expenses 路由下注册
API_URL = "http://127.0.0.1:8888/api/v1/doc_gen"
EXPENSE_API_URL = "http://127.0.0.1:8888/api/v1/expenses"


def render():
    st.title("🖨️ 刑罚执行文书智能校对与套打中心")
    st.info("💡 系统将自动草拟或生成格式化文书。您可以自由编辑或生成后直接下载最终版。")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col2:
        # 🌟 1. 新增“罪犯收入和消费情况统计表”选项
        doc_type = st.selectbox("📄 文书类别：", ["《提请减刑建议书》", "罪犯个人消费明细表", "罪犯收入和消费情况统计表"])

    with col1:
        target_name = st.text_input("👤 罪犯姓名：", value=st.session_state.get("current_target_name", ""))

    auto_code = ""
    if target_name and doc_type == "罪犯个人消费明细表":
        try:
            res = requests.get(f"{API_URL}/get_criminal_info?name={target_name}")
            if res.status_code == 200:
                auto_code = res.json().get("criminal_number", "")
        except Exception:
            pass

    # =============== 分支 1：提请减刑建议书的逻辑 ===============
    if doc_type == "《提请减刑建议书》":
        with col3:
            st.write("")
            st.write("")
            load_btn = st.button("🔍 提取文书草稿", use_container_width=True)

        st.divider()

        # 状态管理
        if "doc_context" not in st.session_state:
            st.session_state.doc_context = None
        if "doc_status" not in st.session_state:
            st.session_state.doc_status = None

        if load_btn and target_name:
            with st.spinner("正在从数据底座提取并拼装文书..."):
                res = requests.get(f"{API_URL}/preview_doc?name={target_name}")
                if res.status_code == 200:
                    res_data = res.json()
                    st.session_state.doc_context = res_data.get("context", {})
                    st.session_state.doc_status = res_data.get("status")
                else:
                    st.error("❌ 提取失败，请确认罪犯档案是否已入库。")
                    st.session_state.doc_context = None

        if st.session_state.doc_context:
            ctx = st.session_state.doc_context

            if st.session_state.doc_status == "reviewed_and_merged":
                st.success("✅ 检测到该犯已有【历史人工定稿】记录！")
                st.info(
                    "💡 **智能融合完毕**：系统已提取您上次润色的【原判案情】与【财产情况】，并 **自动刷新** 了最新的【奖惩明细】。")
            else:
                st.warning("🤖 以下为系统智能拼装的初稿，请进行法理复核与润色修改。")

            with st.form("doc_edit_form"):
                st.subheader("📝 核心段落校对台")
                st.error("🚨 核心规范：只要修改了下方任何文本，必须先点击最底部的【💾 确认/更新定稿】按钮！")

                col_t1, col_t2 = st.columns(2)
                with col_t1: edited_origin = st.text_input("籍贯", value=ctx.get("origin", ""))
                with col_t2: edited_nation = st.text_input("民族", value=ctx.get("ethnicity", ""))

                edited_trial = st.text_area("原判及上诉复核情况 (历史沉淀)",
                                            value=ctx.get("trial_and_sentence_summary", ""), height=100)
                edited_transfer = st.text_input("送押收监情况", value=ctx.get("transfer_info", ""))

                st.markdown("---")
                edited_changes = st.text_area("🔄 历次减刑/假释情况 (已自动更新至最新)",
                                              value=ctx.get("prison_changes_and_reductions", ""), height=100)
                edited_rewards = st.text_area("🔄 日常考核奖惩明细 (已自动更新至最新)",
                                              value=ctx.get("rewards_detail_list", ""), height=100)

                col_r1, col_r2 = st.columns(2)
                with col_r1: edited_total_rewards = st.number_input("折合奖励次数",
                                                                    value=int(ctx.get("total_rewards", 0)))

                st.markdown("---")
                edited_prop = st.text_area("财产性判项执行情况 (历史沉淀)",
                                           value=ctx.get("property_execution_status", ""), height=80)
                edited_recommendation = st.text_input("最终减刑建议幅度", value=ctx.get("recommended_reduction", ""))

                st.markdown("<br>", unsafe_allow_html=True)
                submit_edit = st.form_submit_button("💾 确认/更新定稿 并生成 Word 文件", type="primary",
                                                    use_container_width=True)

            if submit_edit:
                final_context = ctx.copy()
                final_context.update({
                    "origin": edited_origin, "ethnicity": edited_nation,
                    "trial_and_sentence_summary": edited_trial, "transfer_info": edited_transfer,
                    "prison_changes_and_reductions": edited_changes, "rewards_detail_list": edited_rewards,
                    "total_rewards": edited_total_rewards, "property_execution_status": edited_prop,
                    "recommended_reduction": edited_recommendation
                })

                with st.spinner("正在将最新定稿写入数据底座并渲染红头文件..."):
                    payload = {"name": target_name, "edited_context": final_context}
                    res = requests.post(f"{API_URL}/generate_and_save_doc", json=payload)

                    if res.status_code == 200:
                        st.success("🎉 定稿入库成功！Word 文书已生成完毕。")
                        st.download_button(
                            label=f"⬇️ 点击下载《提请减刑建议书_{target_name}》",
                            data=res.content,
                            file_name=f"提请减刑建议书_{target_name}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            type="secondary"
                        )
                    else:
                        st.error("生成失败请重试。")

    # =============== 分支 2：罪犯个人消费明细表的逻辑 ===============
    elif doc_type == "罪犯个人消费明细表":
        with col3:
            code_input = st.text_input("🔢 罪犯编号：", value=auto_code)

        st.divider()
        st.subheader("🛒 消费明细表生成台")

        # ================== 🌟 新增：日期联动逻辑 ==================

        # 🌟 计算本月26日的具体日期
        today = datetime.date.today()
        default_date = datetime.date(today.year, today.month, 26)

        # 初始化 session_state 中的日期（默认为本月26日）
        if "expense_date1" not in st.session_state:
            st.session_state.expense_date1 = default_date
        if "expense_date2" not in st.session_state:
            st.session_state.expense_date2 = default_date

        # 定义回调函数：当修改调取日期时，出具日期自动同步
        def sync_d1_to_d2():
            st.session_state.expense_date2 = st.session_state.expense_date1

        # 定义回调函数：当修改出具日期时，调取日期自动同步
        def sync_d2_to_d1():
            st.session_state.expense_date1 = st.session_state.expense_date2

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.date_input("📅 调取日期", key="expense_date1", on_change=sync_d1_to_d2)
        with col_d2:
            st.date_input("📅 出具日期", key="expense_date2", on_change=sync_d2_to_d1)
        # =========================================================

        st.info("请从监管系统中导出该犯的《个人帐务明细表》(.xls / .xlsx)，系统将自动跨月轧平并排版。")

        uploaded_file = st.file_uploader("📂 上传【个人帐务明细表】Excel", type=["xlsx", "xls"])

        if st.button("🚀 生成预览并获取文件", use_container_width=True, type="primary"):
            if not target_name or not code_input or not uploaded_file:
                st.warning("⚠️ 请先完整填写【姓名】、【编号】并【上传文件】！")
            else:
                with st.spinner("正在智能清洗消费数据并绘制标准排版表格..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}

                    # 🌟 提取并格式化日期为“XXXX年XX月XX日”
                    d1_str = f"{st.session_state.expense_date1.year}年{st.session_state.expense_date1.month}月{st.session_state.expense_date1.day}日"
                    d2_str = f"{st.session_state.expense_date2.year}年{st.session_state.expense_date2.month}月{st.session_state.expense_date2.day}日"

                    # 将日期加入向后端发送的数据包中
                    data = {
                        "code": code_input,
                        "target_name": target_name,
                        "fetch_date": d1_str,  # 👈 新增
                        "issue_date": d2_str  # 👈 新增
                    }

                    try:
                        res = requests.post(f"{EXPENSE_API_URL}/generate_excel", files=files, data=data)

                        if res.status_code == 200:
                            # ...(后面成功的预览与下载逻辑保持不变)...
                            st.success("✅ 消费明细清洗与排版成功！")
                            excel_bytes = res.content

                            st.markdown("### 📊 结构化数据预览")
                            try:
                                preview_df = pd.read_excel(BytesIO(excel_bytes), skiprows=2)
                                st.dataframe(preview_df, use_container_width=True)
                            except Exception as e:
                                st.warning(f"由于单元格合并，预览数据无法完美呈现，但不影响最终 Excel，报错信息: {e}")

                            st.download_button(
                                label=f"⬇️ 点击下载最终成片《罪犯个人消费明细表_{target_name}》",
                                data=excel_bytes,
                                file_name=f"月消费明细_{target_name}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="secondary"
                            )
                        else:
                            st.error(f"❌ 生成失败 | 状态码: HTTP {res.status_code} | 返回信息: {res.text}")
                    except Exception as e:
                        st.error(f"后台接口调用失败，请检查 API 服务是否启动: {e}")

    # =============== 🌟 分支 3：罪犯收入和消费情况统计表 (全新逻辑) ===============
    elif doc_type == "罪犯收入和消费情况统计表":
        st.divider()
        st.subheader("💰 跨系统收入和消费表生成台")

        # 🌟 锁定默认日期为本月26日
        today = datetime.date.today()
        default_date = datetime.date(today.year, today.month, 26)

        if "exp_stat_d1" not in st.session_state:
            st.session_state.exp_stat_d1 = default_date
        if "exp_stat_d2" not in st.session_state:
            st.session_state.exp_stat_d2 = default_date

        def sync_stat_d1_to_d2():
            st.session_state.exp_stat_d2 = st.session_state.exp_stat_d1

        def sync_stat_d2_to_d1():
            st.session_state.exp_stat_d1 = st.session_state.exp_stat_d2

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.date_input("📅 调取日期", key="exp_stat_d1", on_change=sync_stat_d1_to_d2)
        with col_d2:
            st.date_input("📅 出具日期", key="exp_stat_d2", on_change=sync_stat_d2_to_d1)

        st.info("请分别上传该犯的【旧系统账务明细表】与【新系统账务汇总表】，系统将自动进行双轨汇算。")

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            old_file = st.file_uploader("📂 1. 上传【旧系统】账务明细 (.frp/csv/xls)",
                                        type=["frp", "csv", "xls", "xlsx"])
        with col_f2:
            new_file = st.file_uploader("📂 2. 上传【新系统】账务汇总 (.xls/csv)", type=["csv", "xls", "xlsx"])

        if st.button("🚀 智能汇算并生成 Word 统计表", use_container_width=True, type="primary"):
            if not old_file or not new_file:
                st.warning("⚠️ 必须同时上传【旧系统】和【新系统】两份账单文件，才能进行跨月轧平与累计！")
            else:
                with st.spinner("正在跨系统融合账单数据并渲染红头文书..."):
                    files = [
                        ("old_file", (old_file.name, old_file.getvalue(), old_file.type)),
                        ("new_file", (new_file.name, new_file.getvalue(), new_file.type))
                    ]

                    d1_str = f"{st.session_state.exp_stat_d1.year}年{st.session_state.exp_stat_d1.month}月{st.session_state.exp_stat_d1.day}日"
                    d2_str = f"{st.session_state.exp_stat_d2.year}年{st.session_state.exp_stat_d2.month}月{st.session_state.exp_stat_d2.day}日"
                    data = {"fetch_date": d1_str, "issue_date": d2_str}

                    try:
                        res = requests.post(f"{EXPENSE_API_URL}/generate_income_expense_doc", files=files,
                                            data=data)
                        if res.status_code == 200:
                            st.success("✅ 账单跨系统汇算完毕，排版生成成功！")
                            st.download_button(
                                label=f"⬇️ 点击下载《{target_name} 收入和消费情况统计表》.docx",
                                data=res.content,
                                file_name=f"{target_name}消费.docx" if target_name else "收入和消费情况统计表.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                type="secondary"
                            )
                        else:
                            st.error(f"❌ 生成失败 | HTTP {res.status_code} | {res.text}")
                    except Exception as e:
                        st.error(f"调用失败: {e}")