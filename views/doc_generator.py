import streamlit as st
import requests

API_URL = "http://127.0.0.1:8888/api/v1/doc_gen"


def render():
    st.title("🖨️ 刑罚执行文书智能校对与套打中心")
    st.info("💡 系统将自动草拟文书。您可以在下方文本框中自由润色，修改后的内容将永久存入档案底座，下次提取免除二次修改。")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        target_name = st.text_input("👤 罪犯姓名：", value=st.session_state.get("current_target_name", ""))
    with col2:
        doc_type = st.selectbox("📄 文书类别：", ["《提请减刑建议书》"])
    with col3:
        st.write("")  # 占位对齐
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

    # 如果内存中有数据，渲染【人工校对工作台】
    if st.session_state.doc_context:
        ctx = st.session_state.doc_context

        # 🌟 动态友好的前台 UI 提示
        if st.session_state.doc_status == "reviewed_and_merged":
            st.success("✅ 检测到该犯已有【历史人工定稿】记录！")
            st.info(
                "💡 **智能融合完毕**：系统已提取您上次润色的【原判案情】与【财产情况】，并 **自动刷新** 了最新的【奖惩明细】。您可以直接滑至底部生成下载，或继续微调。")
        else:
            st.warning("🤖 以下为系统智能拼装的初稿，请进行法理复核与润色修改。")

        # 将字典中的关键长文本抽取为文本框供人工修改 (支持二次修改)
        with st.form("doc_edit_form"):
            st.subheader("📝 核心段落校对台")
            # 👇 加上这行醒目的警告
            st.error(
                "🚨 核心规范：只要修改了下方任何文本，必须先点击最底部的【💾 确认/更新定稿】按钮！切勿改完字直接点下载，否则下载的将是旧版！")

            # 第一段：原判及送押 (静态数据，继承历史)
            col_t1, col_t2 = st.columns(2)
            with col_t1: edited_origin = st.text_input("籍贯", value=ctx.get("origin", ""))
            with col_t2: edited_nation = st.text_input("民族", value=ctx.get("ethnicity", ""))

            edited_trial = st.text_area("原判及上诉复核情况 (历史沉淀)",
                                        value=ctx.get("trial_and_sentence_summary", ""), height=100)
            edited_transfer = st.text_input("送押收监情况", value=ctx.get("transfer_info", ""))

            # 第二段：历次变动与积分表现 (动态数据，每次刷新)
            st.markdown("---")
            edited_changes = st.text_area("🔄 历次减刑/假释情况 (已自动更新至最新)",
                                          value=ctx.get("prison_changes_and_reductions", ""), height=100)
            edited_rewards = st.text_area("🔄 日常考核奖惩明细 (已自动更新至最新)",
                                          value=ctx.get("rewards_detail_list", ""), height=100)

            col_r1, col_r2 = st.columns(2)
            with col_r1: edited_total_rewards = st.number_input("折合奖励次数", value=int(ctx.get("total_rewards", 0)))

            # 第三段：财产刑执行与减刑建议
            st.markdown("---")
            edited_prop = st.text_area("财产性判项执行情况 (历史沉淀)", value=ctx.get("property_execution_status", ""),
                                       height=80)
            edited_recommendation = st.text_input("最终减刑建议幅度", value=ctx.get("recommended_reduction", ""))

            st.markdown("<br>", unsafe_allow_html=True)
            # 即便以前定稿过，点击这个按钮依然会产生一次覆写入库操作
            submit_edit = st.form_submit_button("💾 确认/更新定稿 并生成 Word 文件", type="primary",
                                                use_container_width=True)

        # 提交处理逻辑
        if submit_edit:
            final_context = ctx.copy()
            final_context.update({
                "origin": edited_origin,
                "ethnicity": edited_nation,
                "trial_and_sentence_summary": edited_trial,
                "transfer_info": edited_transfer,
                "prison_changes_and_reductions": edited_changes,
                "rewards_detail_list": edited_rewards,
                "total_rewards": edited_total_rewards,
                "property_execution_status": edited_prop,
                "recommended_reduction": edited_recommendation
            })

            with st.spinner("正在将最新定稿写入数据底座并渲染红头文件..."):
                payload = {
                    "name": target_name,
                    "edited_context": final_context
                }
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