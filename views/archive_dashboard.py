import streamlit as st
import requests
import json
import time

API_URL = "http://127.0.0.1:8888/api"


def render():
    # 🌟 初始化系统记忆库与防报错组件
    if "final_report_data" not in st.session_state:
        st.session_state.final_report_data = None
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "mode_status" not in st.session_state:
        st.session_state.mode_status = "模式一"

    st.title("⚖️ 智慧狱政 - 全量数据交叉提取与分析中心")

    # ==========================================
    # 🎯 步骤一：三模态业务场景导航
    # ==========================================
    st.markdown("### 第一步：选择业务办理模式")
    mode = st.radio(
        "👉 请指示 AI 本次执行的扫描策略：",
        [
            "📦 模式一：历史案卷初始化 (AI 盲扫全量档案，自动分类排时间线)",
            "🎯 模式二：指定类型文书精准提取 (明确告诉 AI 这是什么，防跑偏)",
            "⚡ 模式三：高频业务批量增量更新 (如：月底批量导入全监区表扬审批表)"
        ],
        index=2  # 默认推介最高频的模式三
    )

    st.divider()

    # 初始化变量防报错
    target_name = ""
    doc_category = ""
    extra_prompt = ""
    batch_name = ""
    batch_type = ""
    uploaded_files = None

    # ==========================================
    # 🎯 步骤二：动态渲染配置参数面板
    # ==========================================
    if "模式三" in mode:
        st.markdown("### 第二步：配置批量更新参数")
        col1, col2 = st.columns(2)
        with col1:
            batch_name = st.text_input("🏷️ 批次名称：", value="2026年5月份奖励件")
        with col2:
            batch_type = st.selectbox("📈 业务类型：", ["考核表扬", "物质奖励", "记功", "减刑裁定", "假释裁定"])

        st.info(
            f"⚡ **极速模式已就绪**：AI 将仅扫描每份文书的【罪犯姓名】与【落款日期】，并自动追加到各自档案的`{batch_type}`记录中，无需人工干预。")
        uploaded_files = st.file_uploader(f"📂 批量拖入【{batch_name}】的所有扫描件...", type=["jpg", "jpeg", "png"],
                                          accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")

    else:
        st.markdown("### 第二步：锁定建档目标")
        target_name = st.text_input("👤 请输入本次建档的【主犯姓名】(AI将过滤无关人员)：", placeholder="例如：张三")

        if "模式二" in mode:
            col1, col2 = st.columns(2)
            with col1:
                doc_category = st.selectbox("📄 指定文书种类：",
                                            ["一审判决书", "二审裁定书", "起诉书", "结案登记表", "其他"])
            with col2:
                extra_prompt = st.text_input("🎯 重点提取指令 (选填)：", placeholder="例：重点提取财产没收金额")

        if target_name:
            uploaded_files = st.file_uploader(f"📂 请上传关于【{target_name}】的卷宗扫描件", type=["jpg", "jpeg", "png"],
                                              accept_multiple_files=True,
                                              key=f"uploader_{st.session_state.uploader_key}")

    # ==========================================
    # 🚀 步骤三：启动引擎并传递动态参数
    # ==========================================
    if uploaded_files and (target_name or "模式三" in mode):
        col_btn1, col_btn2 = st.columns([3, 1])

        with col_btn2:
            if st.button("🗑️ 一键清空所有文件", use_container_width=True):
                st.session_state.uploader_key += 1
                st.session_state.final_report_data = None
                st.rerun()

        with col_btn1:
            if st.button("🚀 启动 AI 联合办案 (开启流式追踪)", type="primary", use_container_width=True):
                st.session_state.final_report_data = None
                start_time = time.time()
                total_files = len(uploaded_files)
                current_file_idx = 0

                st.divider()
                col_v, col_l = st.columns(2)
                with col_v:
                    vision_expander = st.expander("👁️ 视觉提取原始证据链 (点击展开)", expanded=False)
                    vision_box = vision_expander.empty()
                    vision_log = ""
                with col_l:
                    logic_expander = st.expander("🧠 逻辑法理推演实况 (点击展开)", expanded=False)
                    logic_box = logic_expander.empty()
                    logic_log = ""
                st.divider()

                with st.status("📡 正在连接本地数字底座...", expanded=True) as status:
                    progress_bar = st.progress(0, text="🚀 正在启动 AI 引擎...")
                    time_placeholder = st.empty()

                    files_payload = []
                    for file in uploaded_files:
                        files_payload.append(("files", (file.name, file.getvalue(), file.type)))

                    # 🌟 核心：将动态参数全部打包装进 payload
                    data_payload = {
                        "target_name": target_name,
                        "mode": mode[:3],  # 截取 "模式一", "模式二", "模式三"
                        "doc_category": doc_category,
                        "extra_prompt": extra_prompt,
                        "batch_name": batch_name,
                        "batch_type": batch_type
                    }

                    try:
                        response = requests.post(
                            f"{API_URL}/upload_archive_batch".strip(),
                            files=files_payload,
                            data=data_payload,
                            timeout=1800,
                            stream=True
                        )

                        if response.status_code == 200:
                            for line in response.iter_lines():
                                if line:
                                    chunk = json.loads(line.decode('utf-8'))
                                    msg = chunk.get("msg", "")
                                    step = chunk.get("step", "")

                                    current_elapsed = int(time.time() - start_time)

                                    if step == "init":
                                        progress_bar.progress(5, text="📥 正在接收并预处理卷宗影像...")

                                    elif step == "vision":
                                        if "vision_detail" not in chunk:
                                            current_file_idx += 1

                                        avg_vision_time = current_elapsed / max(1, current_file_idx)
                                        eta = int((total_files - current_file_idx) * avg_vision_time + 15)
                                        time_placeholder.markdown(
                                            f"**⏱️ 已分析时间:** `{current_elapsed} 秒` | **⏳ 预计剩余:** `约 {eta} 秒`")

                                        percent = min(95, int(5 + (current_file_idx / max(1, total_files)) * 75))
                                        progress_bar.progress(percent,
                                                              text=f"👁️ 引擎逐图穿透扫描中 ({current_file_idx}/{total_files})...")

                                        if "vision_detail" in chunk:
                                            vision_log += f"**📄 {chunk.get('file', '扫描件')}**\n```json\n{chunk['vision_detail']}\n```\n---\n"
                                            vision_box.markdown(vision_log)

                                    elif step == "logic":
                                        time_placeholder.markdown(
                                            f"**⏱️ 已分析时间:** `{current_elapsed} 秒` | **🧠 逻辑大脑全速运转中...**")
                                        progress_bar.progress(90, text="🧠 正在进行跨文件法理交叉研判与冲突侦测...")

                                    elif step == "logic_stream":
                                        logic_log += chunk.get("chunk", "")
                                        if len(logic_log) % 15 == 0:
                                            logic_box.markdown(logic_log + " ▌")

                                    if msg and step != "logic_stream":
                                        st.write(msg)

                                    if "data" in chunk:
                                        logic_box.markdown(logic_log)
                                        st.session_state.final_report_data = chunk["data"]
                                        st.session_state.mode_status = mode[:3]  # 记录本次成功的模式
                                        total_time = int(time.time() - start_time)
                                        progress_bar.progress(100, text="✅ 研判彻底完成！")
                                        status.update(label=f"✅ 联合办案完成！总耗时: {total_time} 秒", state="complete",
                                                      expanded=False)
                        else:
                            st.error(f"❌ 后端接口瞬间崩溃 (HTTP {response.status_code})")
                            st.code(response.text, language="text")
                            status.update(label="启动失败", state="error", expanded=True)
                            st.stop()
                    except requests.exceptions.RequestException as e:
                        st.error(f"❌ 前后端连接物理断开: {str(e)}")
                        status.update(label="网络断开", state="error", expanded=True)

    # ==========================================
    # 📊 步骤四：展示分析结果与人工确认
    # ==========================================
    if st.session_state.final_report_data:
        report_data = st.session_state.final_report_data
        saved_mode = st.session_state.get("mode_status", "模式一")

        st.divider()

        # 🌟 针对模式三的特殊渲染：不展示人工确认框，因为后端已经自动 Append 入库了
        if saved_mode == "模式三":
            st.success("🎉 **批量增量入库完成！**")
            st.info("💡 模式三已由系统在后端自动完成追加写入。以上为处理详情，您可直接切换至【文书生成模块】查阅最新文书。")

        else:
            # 模式一和模式二的常规表格确认渲染
            st.markdown("### 📊 AI 提取结果与法理分析")
            st.info(
                "💡 提示：下方表格支持类似 Excel 的操作。双击单元格可修改内容；点击表格底部灰色区域可添加新记录；选中行按键盘 Delete 键可删除。")

            col1, col2 = st.columns([1, 1.2])

            with col1:
                st.subheader("📂 卷宗归档物理分类核查")
                st.info(
                    "💡 提示：下方是 AI 拟定的分类。如果是连续多页的二审判决，你可以直接在此将错误的类别修改为'二审判决'。点击入库后，文件将按此表格最终移动。")

                archive_list = report_data.get("archive_mapping", [])
                edited_archive = st.data_editor(
                    archive_list,
                    use_container_width=True,
                    hide_index=True,
                    disabled=["文件名", "临时路径"],
                    key="editor_archive"
                )

                final_data_to_save = {
                    "archive_mapping": edited_archive,
                    "confirmed_data": {}
                }

                st.subheader("🟢 无争议确认数据 (可修改)")
                confirmed = report_data.get("confirmed_data", {})

                if confirmed:
                    with st.form("final_confirm_form"):
                        for k, v in confirmed.items():
                            if isinstance(v, list):
                                st.markdown(f"**📚 {k}**")
                                edited_list = st.data_editor(v, num_rows="dynamic", use_container_width=True,
                                                             key=f"editor_{k}")
                                final_data_to_save["confirmed_data"][k] = edited_list
                            else:
                                final_data_to_save["confirmed_data"][k] = st.text_input(f"✅ {k}", value=str(v))

                        submitted = st.form_submit_button("💾 将以上全量数据永久入库")
                        if submitted:
                            with st.spinner("正在写入底层数据库并移动物理文件..."):
                                try:
                                    save_res = requests.post(f"{API_URL}/confirm_and_save".strip(),
                                                             json=final_data_to_save)
                                    if save_res.status_code == 200:
                                        st.success(save_res.json().get("message",
                                                                       "🎉 入库成功！你可以去 SQLite 数据库里查看了！"))
                                    else:
                                        st.error(f"❌ 入库失败: {save_res.text}")
                                except Exception as e:
                                    st.error(f"❌ 连接数据库接口失败: {e}")
                else:
                    st.info("未提取到无争议数据。")

            with col2:
                st.subheader("🔴 悬疑冲突与 AI 分析过程")
                conflicts = report_data.get("conflicts", [])

                if not conflicts:
                    st.info("🎉 完美！核心数据高度一致，未侦测到矛盾。")
                else:
                    for i, conflict in enumerate(conflicts):
                        if isinstance(conflict, str):
                            field_name = "未分类逻辑矛盾"
                            conflict_detail = conflict
                            suggestion = "⚠️ 大模型未按标准格式输出，请干警根据上方原话进行人工核查。"
                        elif isinstance(conflict, dict):
                            field_name = conflict.get('字段') or conflict.get('field', '未知字段')
                            suggestion = conflict.get('研判意见') or conflict.get('研判结论') or conflict.get(
                                'ai_suggestion', '无')
                            conflict_detail = ""
                            if '矛盾数据' in conflict and isinstance(conflict['矛盾数据'], str):
                                conflict_detail = conflict['矛盾数据']
                            else:
                                exclude_keys = ['字段', 'field', '研判意见', '研判结论', 'ai_suggestion', '矛盾数据']
                                for k, v in conflict.items():
                                    if k not in exclude_keys:
                                        conflict_detail += f"- **{k}**: `{v}`\n"
                            if not conflict_detail.strip():
                                conflict_detail = "未提取到具体的对比数据。"
                        else:
                            continue

                        with st.expander(f"⚠️ 矛盾点：【{field_name}】", expanded=True):
                            st.markdown("**🔍 冲突详情：**")
                            st.markdown(conflict_detail)
                            st.info(f"**💡 AI 研判结论：**\n\n{suggestion}")

    elif not target_name and "模式三" not in mode:
        st.info("👈 请先在上方输入【主犯姓名】，再进行上传操作。")