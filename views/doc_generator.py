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
        doc_type = st.selectbox("📄 文书类别：", ["《提请减刑建议书》",
                                                "罪犯个人消费明细表",
                                                "罪犯收入和消费情况统计表",
                                                "三级会议纪要生成",
                                                "狱情分析会议纪要生成",
                                                "释放四表 (出监鉴定评估)",])

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
            # 🌟 修改 1：现在只强制要求必须传新文件
            if not new_file:
                st.warning("⚠️ 【新系统】账务汇总表为必传项！如果该犯有旧系统记录，请一并上传以便合并。")
            else:
                with st.spinner("正在跨系统融合账单数据并渲染红头文书..."):
                    # 🌟 修改 2：动态拼装文件流，有旧文件才加进去
                    files = [
                        ("new_file", (new_file.name, new_file.getvalue(), new_file.type))
                    ]
                    if old_file:
                        files.append(("old_file", (old_file.name, old_file.getvalue(), old_file.type)))

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
                                file_name=f"{target_name}罪犯收入和消费情况统计表.docx" if target_name else "罪犯收入和消费情况统计表.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                type="secondary"
                            )
                        else:
                            st.error(f"❌ 生成失败 | HTTP {res.status_code} | {res.text}")
                    except Exception as e:
                        st.error(f"调用失败: {e}")

    elif doc_type == "三级会议纪要生成":
        st.divider()
        # 🌟 升级为 4 个步骤
        tab1, tab2, tab3, tab4 = st.tabs([
            "📝 1.点名册同步",
            "👮 2.监区人员管理",
            "🗂️ 3.本批次档案智能解析",
            "🚀 4.纪要一键生成"
        ])

        # --- TAB 1: 点名册更新 ---
        with tab1:
            st.info("上传最新的《监舍点名册.xlsx》，系统将自动读取包组干警与罪犯的对应关系并永久保存。")
            rollcall_file = st.file_uploader("📁 上传监舍点名册", type=["xlsx", "xls"])
            if st.button("🔄 同步包组关系", use_container_width=True):
                if rollcall_file:
                    with st.spinner("正在智能拆解双栏表格..."):
                        files = {"file": (rollcall_file.name, rollcall_file.getvalue())}
                        res = requests.post(f"{API_URL}/upload_rollcall", files=files)
                        if res.status_code == 200:
                            st.success(res.json().get("message", "更新成功！"))
                        else:
                            st.error("更新失败，请检查文件格式。")
                else:
                    st.warning("请先上传文件")

        # --- TAB 2: 人员名单管理 (此处可扩展完整的增删改查) ---
        with tab2:
            st.info("💡 录入参加会议的监区干警名单，数据将长久保存，直接用于纪要抬头。")
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("监区长姓名：", key="warden")
                st.text_input("教导员姓名：", key="instructor")
            with col2:
                st.text_input("分管刑罚副监区长：", key="deputy1")
                st.text_input("刑罚专职/内勤：", key="clerk")
            st.text_area("其他包组干警（用逗号分隔）：", key="officers")
            if st.button("💾 保存/更新干警名单"):
                st.success(
                    "（此功能需绑定您的本地 SQLite 写入接口，为节省篇幅，建议复用您的基础 DB 接口写入 `ward_personnel` 表）")

        # --- TAB 3: 本批次档案上传与大模型解析 (全新逻辑) ---
        with tab3:
            st.subheader("🗂️ 减刑核心档案大模型视觉提取")
            st.info(
                "💡 请上传本批次罪犯的【一二审判决书、入监登记表、历次减刑裁定、奖惩审批表、财产履行材料】。系统将自动阅读并提炼会议纪要专用的高度浓缩话术，并永久入库。")

            archive_files = st.file_uploader(
                "📂 批量上传档案扫描件 (支持 PDF/JPG/PNG，建议以罪犯姓名命名文件或文件夹)",
                type=["pdf", "png", "jpg", "jpeg"],
                accept_multiple_files=True
            )

            if st.button("🧠 开始视觉阅卷与智能入库", type="primary", use_container_width=True):
                if not archive_files:
                    st.warning("⚠️ 请先上传档案文件！")
                else:
                    with st.spinner(
                            "🤖 AI 正在交叉阅读判决书、裁定书与奖惩表，提炼会议核心数据... (这可能需要几分钟)"):
                        # 构造 multipart form-data 传给后端
                        files_payload = [
                            ("files", (file.name, file.getvalue(), file.type)) for file in archive_files
                        ]
                        res = requests.post(f"{API_URL}/extract_meeting_archives", files=files_payload)

                        if res.status_code == 200:
                            result = res.json()
                            st.success(
                                f"🎉 档案解析完毕！成功提取并更新了 {len(result['extracted_names'])} 名罪犯的会议档案：")
                            st.write("、".join(result['extracted_names']))
                        else:
                            st.error(f"解析失败: {res.text}")

        # --- TAB 4: 生成纪要 ---
        with tab4:
            st.subheader("🎯 选定本批次减刑人员并生成")
            meeting_month = st.date_input("📅 会议发生年月：")
            inmates_input = st.text_area("👥 参与本次评议的罪犯姓名（使用逗号或空格分隔）：",
                                         placeholder="例如：吕中亮, 杨毅, 匡凤禹...")

            if st.button("🚀 自动抽取数据并生成三份纪要", type="primary", use_container_width=True):
                if not inmates_input.strip():
                    st.error("⚠️ 请至少输入一名罪犯姓名！")
                else:
                    with st.spinner("正在从数据底座交叉比对刑期、处分、包组归属，并排版红头文件..."):
                        # 处理输入的姓名
                        names = [n.strip() for n in inmates_input.replace('，', ',').split(',')]
                        names = [n for n in names if n]

                        payload = {
                            "month": meeting_month.strftime("%Y-%m"),
                            "inmates": names
                        }
                        res = requests.post(f"{API_URL}/generate_meeting_docs", json=payload)

                        if res.status_code == 200:
                            st.success("🎉 三级纪要生成完毕！非固定数据已全部标黄。")
                            st.download_button(
                                label="⬇️ 点击下载完整纪要压缩包 (ZIP)",
                                data=res.content,
                                file_name=f"减刑会议纪要_{meeting_month.strftime('%Y%m')}.zip",
                                mime="application/zip",
                                type="secondary"
                            )
                        else:
                            st.error(f"生成失败：{res.text}")

    # =============== 分支 4：狱情分析会议纪要生成 (全链路流式打字机终极版) ===============
    elif doc_type == "狱情分析会议纪要生成":
        import os
        import json

        st.divider()
        st.subheader("📊 狱情分析会议纪要智能生成台")

        # ⚠️ 隐藏知识库文件，避免 FastAPI 触发热重启
        KB_FILE_PATH = ".kb_standard_process.txt"

        # --- 1. 知识库区域 ---
        st.markdown("#### 1. 规则底座 (知识库)")
        has_kb = os.path.exists(KB_FILE_PATH)

        if has_kb:
            st.success("✅ 已检测到《狱情分析会议标准化流程》知识库，无需重复上传。")
            with st.expander("👀 查看当前生效的流程规则 (可手动更新)"):
                with open(KB_FILE_PATH, "r", encoding="utf-8") as f:
                    st.text(f.read())
                if st.button("🗑️ 清除当前规则并重新上传"):
                    os.remove(KB_FILE_PATH)
                    st.rerun()
            standard_process_files = []
        else:
            st.warning("⚠️ 首次使用，请上传《标准化流程》打印版扫描件。系统将使用 DeepSeek-OCR 流式提取并入库。")
            standard_process_files = st.file_uploader(
                "📄 上传标准化流程扫描件 (支持多图多页)",
                type=["jpg", "png", "jpeg"],
                accept_multiple_files=True
            )

        # --- 2. 数据与设定区域 ---
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("#### 2. 会议日期设定")
            default_dates = "2026年5月26日, 2026年6月2日, 2026年6月9日, 2026年6月16日, 2026年6月23日"
            dates_input = st.text_area(
                "📅 批量会议日期 (逗号分隔)：",
                value=default_dates
            )

        with col_d2:
            st.markdown("#### 3. 动态手写记录上传")
            handwritten_files = st.file_uploader(
                "📝 批量上传本周期所有的手写记录扫描件 (页数不限)",
                type=["jpg", "png", "jpeg"],
                accept_multiple_files=True
            )

        # --- 3. 执行引擎与流式输出 ---
        if st.button("🚀 开始流水线处理与流式生成", type="primary", use_container_width=True):
            if not has_kb and not standard_process_files:
                st.error("❌ 缺少规则底座！请先上传流程扫描件存入知识库。")
            elif not handwritten_files:
                st.error("❌ 请至少上传一份手写记录扫描件！")
            else:
                date_list = [d.strip() for d in dates_input.split(",") if d.strip()]

                st.markdown("### ⚙️ 核心引擎流式执行日志")
                main_status = st.empty()
                log_container = st.container()

                try:
                    # ==========================================
                    # [步骤一]：多页打印体规则入库 (流式打字机)
                    # ==========================================
                    main_status.info("🧠 视觉解析与大模型组稿正在初始化...")
                    if not has_kb:
                        main_status.warning("⏳ **[1/3] 正在启动 DeepSeek-OCR 实时剥离多页流程规则...**")
                        standard_text = ""
                        for idx, std_file in enumerate(standard_process_files):
                            with log_container:
                                with st.expander(f"👁️ 正在实时剥离第 {idx + 1} 页流程规范...", expanded=True):
                                    ocr_box = st.empty()
                                    current_page_text = ""

                                    # 🌟 强制调用新的 stream 接口
                                    with requests.post(
                                            f"{API_URL}/extract_image_text_stream",
                                            files={"file": (std_file.name, std_file.getvalue(), std_file.type)},
                                            data={"mode": "standard"},
                                            stream=True
                                    ) as res_ocr:
                                        for line in res_ocr.iter_lines():
                                            if line:
                                                decoded_line = line.decode('utf-8')
                                                if decoded_line.startswith("data: "):
                                                    data = json.loads(decoded_line[6:])
                                                    if data['type'] == 'token':
                                                        current_page_text += data['text']
                                                        ocr_box.info(current_page_text + " ▌")
                                                    elif data['type'] == 'done':
                                                        ocr_box.info(current_page_text)
                                                        standard_text += f"\n【制度第{idx + 1}页】:\n" + current_page_text
                                                    elif data['type'] == 'error':
                                                        ocr_box.error(f"识读出错: {data['text']}")

                        with open(KB_FILE_PATH, "w", encoding="utf-8") as f:
                            f.write(standard_text)
                        with log_container:
                            st.success("💾 **流程规则提取完毕，已永久存入知识库。**")
                    else:
                        with open(KB_FILE_PATH, "r", encoding="utf-8") as f:
                            standard_text = f.read()
                        with log_container:
                            st.success("✔️ **已直接加载本地流程知识库。**")

                    with log_container:
                        st.divider()

                        # ==========================================
                    # [步骤二]：多页手写记录识别 (流式打字机)
                    # ==========================================
                    main_status.warning("⏳ **[2/3] 正在启动 Qwen3.6 视觉大脑【逐字推演】手写流水账...**")
                    hw_text_combined = ""
                    for idx, hw_file in enumerate(handwritten_files):
                        with log_container:
                            with st.expander(f"👁️ 正在实时识读第 {idx + 1} 页手写记录...", expanded=True):
                                ocr_box = st.empty()
                                current_page_text = ""

                                # 🌟 强制调用新的 stream 接口
                                with requests.post(
                                        f"{API_URL}/extract_image_text_stream",
                                        files={"file": (hw_file.name, hw_file.getvalue(), hw_file.type)},
                                        data={"mode": "handwritten"},
                                        stream=True
                                ) as res_ocr:
                                    for line in res_ocr.iter_lines():
                                        if line:
                                            decoded_line = line.decode('utf-8')
                                            if decoded_line.startswith("data: "):
                                                data = json.loads(decoded_line[6:])
                                                if data['type'] == 'token':
                                                    current_page_text += data['text']
                                                    ocr_box.info(current_page_text + " ▌")
                                                elif data['type'] == 'done':
                                                    ocr_box.info(current_page_text)
                                                    hw_text_combined += f"\n--- 手写记录第 {idx + 1} 页 ---\n" + current_page_text
                                                elif data['type'] == 'error':
                                                    ocr_box.error(f"识读出错: {data['text']}")

                    with log_container:
                        st.divider()

                    # ==========================================
                    # [步骤三]：打字机流式生成、实时可见、安全下载
                    # ==========================================
                    main_status.warning("⏳ **[3/3] 正在让 Qwen3.6 研读所有线索，按日期【逐个推演】并排版...**")

                    with log_container:
                        st.markdown("### 📝 智能纪要打字机实况")
                        st.info("💡 你现在可以完全实时看到大模型的思考过程！待单篇完成，专属下载按钮会自动就绪。")

                    result_container = st.container()

                    for meeting_date in date_list:
                        main_status.warning(f"⏳ **[3/3] 正在流式生成 {meeting_date} 的会议纪要...**")

                        with result_container:
                            st.markdown(f"#### 📅 {meeting_date} 会议纪要")
                            text_box = st.empty()
                            full_text = ""

                            # 🌟 调用生成的 stream 接口
                            with requests.post(
                                    f"{API_URL}/build_single_meeting_stream",
                                    data={
                                        "standard_text": standard_text,
                                        "handwritten_text": hw_text_combined,
                                        "meeting_date": meeting_date
                                    },
                                    stream=True
                            ) as res_meeting:
                                for line in res_meeting.iter_lines():
                                    if line:
                                        decoded_line = line.decode('utf-8')
                                        if decoded_line.startswith("data: "):
                                            data = json.loads(decoded_line[6:])

                                            if data['type'] == 'token':
                                                full_text += data['text']
                                                text_box.info(full_text + " ▌")

                                            elif data['type'] == 'done':
                                                text_box.info(full_text)
                                                st.success(
                                                    f"🎉 **{meeting_date} 纪要正文与 Word 文档已生成就绪！**")

                                                docx_b64 = data['docx_base64']
                                                safe_date = meeting_date.replace('年', '-').replace('月',
                                                                                                    '-').replace(
                                                    '日', '')
                                                filename = f"狱情分析会纪要_{safe_date}.docx"

                                                download_html = f'''
                                                <a href="data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{docx_b64}" 
                                                   download="{filename}" 
                                                   style="display: inline-block; padding: 0.6em 1.2em; color: white; background-color: #FF4B4B; 
                                                          text-decoration: none; border-radius: 6px; font-weight: bold; font-family: sans-serif;
                                                          box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px;">
                                                   📥 点击立即下载《{filename}》
                                                </a>
                                                '''
                                                st.markdown(download_html, unsafe_allow_html=True)
                                                st.divider()

                                            elif data['type'] == 'error':
                                                text_box.error(f"❌ 生成中断：{data['text']}")
                                                break

                    main_status.success("🎉 全部任务流水线执行完毕！")

                except Exception as e:
                    main_status.error("❌ 引擎运行崩溃")
                    st.error(f"运行过程中发生异常: {e}")

    elif doc_type == "释放四表 (出监鉴定评估)":
        st.divider()
        st.subheader("📝 释放前四表一键自动化组装 (共6页)")
        st.info(
            "💡 提示：系统会自动从狱政数据库读取信息，并自动将报表日期逆推至【释放前2个月】。您只需提供罪犯姓名和心理测试答案即可。")

        col1, col2 = st.columns([1, 1])

        with col1:
            target_name = st.text_input("👤 请输入待释放罪犯姓名：", placeholder="例如：鹿付山")

        with col2:
            st.markdown("🧠 **出监心理测评结果录入**")
            input_method = st.radio("录入方式：", ["直接粘贴答案", "上传答题卡AI识别"], horizontal=True)

            psycho_answers = ""
            if input_method == "直接粘贴答案":
                psycho_answers = st.text_area("✍️ 粘贴选项序列 (如: AABBCC...)：", height=100)
            else:
                st.caption("支持上传手写打勾的答题卡图片，AI将自动识别并转为选项。")
                ans_file = st.file_uploader("📎 上传答题卡图片/PDF", type=["jpg", "png", "jpeg", "pdf"])
                if ans_file and st.button("👁️ AI视觉识别"):
                    with st.spinner("大模型正在分析答题卡..."):
                        files = {"file": (ans_file.name, ans_file.getvalue(), ans_file.type)}
                        res = requests.post(f"{API_URL}/extract_psycho_answers", files=files)
                        if res.status_code == 200:
                            psycho_answers = res.json().get("answers")
                            st.success("识别成功！选项结果如下：")
                            st.code(psycho_answers)
                        else:
                            st.error("识别失败")

        st.markdown("---")
        if st.button("🚀 根据狱政数据全自动生成《释放四表》", type="primary", use_container_width=True):
            if not target_name:
                st.error("⚠️ 请输入姓名！")
            else:
                with st.spinner(f"正在抓取 {target_name} 的狱政数据，推算日期与评估分数，组装 6 页 Word..."):
                    payload = {
                        "inmate_name": target_name,
                        "psycho_answers": psycho_answers
                    }
                    res = requests.post(f"{API_URL}/generate_release_forms", json=payload)

                    if res.status_code == 200:
                        st.success("🎉 生成完毕！请点击下方按钮下载。")
                        st.download_button(
                            label="⬇️ 下载《释放四表》.docx",
                            data=res.content,
                            file_name=f"{target_name}_释放四表.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            type="secondary"
                        )
                    else:
                        st.error(f"生成失败：{res.json().get('detail', res.text)}")