import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime

API_URL = "http://127.0.0.1:8888/api/v1/screening"


def render():
    st.title("🔍 减刑、假释资格智能筛查中心")
    st.info("💡 依托本地法理知识库与大宽表数据，支持单人深度推演与全监区一键摸底。")

    tab_single, tab_batch = st.tabs(["🎯 单人深度法理研判", "📊 全监区批量资格摸底"])

    # ==========================================
    # 选项卡 1：单人深度研判 (带干预微调与复杂规则推演)
    # ==========================================
    with tab_single:
        col1, col2 = st.columns([2, 1])
        with col1:
            target_name = st.text_input("👤 请输入审查对象姓名：", key="single_target",
                                        placeholder="输入数据库中已有的姓名")
        with col2:
            cutoff_date = st.date_input("📅 本次考核止日设定：", datetime.now(), key="single_date")

        if st.button("📥 从本地底座提取档案数据", type="secondary"):
            if target_name:
                with st.spinner(f"正在穿透数据库提取 {target_name} 的最新卷宗..."):
                    res = requests.get(f"{API_URL}/fetch_criminal?name={target_name}")
                    if res.status_code == 200 and res.json().get("status") == "success":
                        st.session_state.screening_data = res.json().get("data")
                        st.success("✅ 数据提取成功！请在下方核对与补充。")
                    else:
                        st.error(res.json().get("message", "提档失败，请确认该犯档案是否入库"))
            else:
                st.warning("请先输入姓名。")

        st.divider()
        st.subheader("📝 核心考核数据矩阵 (支持人工二次修正)")

        with st.form("screening_form"):
            st.markdown("### 📋 减刑假释十步审查工作台")

            # 步骤 1-4
            st.markdown("#### 【步骤 1-4】：基础身份与罪名")
            c1, c2, c3 = st.columns(3)
            with c1:
                sentence_type = st.selectbox("1. 原判刑种", ["有期徒刑", "无期徒刑", "死缓", "死缓限制减刑"])
                crime_count = st.number_input("3. 判决罪名数量", min_value=1, value=1,
                                              help="输入2个及以上且为无期，将自动触发【数罪并罚】从严逻辑")
            with c2:
                # 🌟 修复点一：智能隐藏原判输入，且改为年月分别输入后台自动换算
                if sentence_type == "有期徒刑":
                    col_y, col_m = st.columns(2)
                    with col_y:
                        term_years = st.number_input("2. 原判(年)", min_value=0, value=10)
                    with col_m:
                        term_months = st.number_input("原判(月)", min_value=0, max_value=11, value=0)
                    original_months = term_years * 12 + term_months
                else:
                    original_months = 0
                    st.info("⚠️ 无期/死缓无需填写原判刑期")

                is_first = st.radio("4. 减刑阶段", ["首次减刑", "再次减刑"]) == "首次减刑"
            with c3:
                CRIME_LIST = [
                    "职务犯罪", "破坏金融", "涉黑", "涉恶", "危害国家安全", "恐怖活动",
                    "毒品首要分子", "毒品再犯", "故意杀人", "强奸", "抢劫", "绑架",
                    "放火", "爆炸", "投放危险物质", "有组织的暴力性犯罪",
                    "贪污贿赂国家工作人员", "危害公共安全"
                ]
                crime_tags = st.multiselect("5. 特殊与核心暴力罪名", CRIME_LIST)

            # 步骤 5-6
            st.markdown("#### 【步骤 5-6】：时间起点与表现")
            c4, c5 = st.columns(2)
            with c4:
                ref_date = st.date_input("5. 起算/上次裁定日期", datetime.now())
            with c5:
                reward_count = st.number_input("6. 累计有效奖励件数", min_value=0, value=2)

            # 步骤 7-8
            st.markdown("#### 【步骤 7-8】：违规处遇阻断")
            c6, c7, c8 = st.columns(3)
            with c6:
                warn_count = st.number_input("7. [警告] 次数", min_value=0, value=0)
                demerit_count = st.number_input("7. [记过] 次数", min_value=0, value=0)
            with c7:
                confinement_count = st.number_input("7. [禁闭] 次数", min_value=0, value=0)
                contraband_count = st.number_input("7. [私藏违禁品] 次数", min_value=0, value=0)
            with c8:
                # 🌟 修复点二：无处分时不显示恢复日期
                if warn_count > 0 or demerit_count > 0 or confinement_count > 0 or contraband_count > 0:
                    upgrade_date = st.date_input("8. 恢复考察级日期", datetime.now(),
                                                 help="因受处分降级，需填写恢复日期")
                else:
                    upgrade_date = None
                    st.write("8. 恢复考察级日期")
                    st.caption("✅ 无违规处分，无需填写")

            # 步骤 9-10
            st.markdown("#### 【步骤 9-10】：动态从严项与财产履行")
            c9, c10 = st.columns(2)
            with c9:
                # 🌟 修复点四：全量动态从严项映射
                normal_strict_tags = st.multiselect(
                    "9. 常规从严项 (多选, 每项扣减 1 个月)",
                    [
                        "危害国家安全罪", "恐怖活动犯罪", "毒品犯罪集团首要分子", "毒品再犯",
                        "职务犯罪", "破坏金融", "涉黑", "涉恶", "危害公共安全罪",
                        "10年以上含10年八项暴力性犯罪", "数罪并罚且两罪均10年以上或原判无期死缓",
                        "单独主犯", "限制减刑", "被害人涉未成年人", "受过劳教或行政处罚", "二次犯罪",
                        "涉众型经济犯罪", "电信网络犯罪", "邪教组织犯罪", "有重大社会影响的犯罪"
                    ]
                )
                super_strict_tags = st.multiselect(
                    "双倍从严项 (多选, 先从严1再扣1，等效扣减 2 个月)",
                    ["累犯", "假释期间又犯罪", "服刑期间犯罪", "缓刑期间犯罪"]
                )
            with c10:
                property_unfulfilled = st.checkbox("10. ❌ 财产性判项【未】履行完毕")
                st.caption("💡 勾选后系统将自动推迟间隔期 3 个月，有期再扣 1 个月，无期增加 1 个奖励件。")
                st.write("特殊叠加次数设置 (无则填0)：")
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    strict_record = st.number_input("【前科】次数", min_value=0, value=0)
                with col_r2:
                    strict_strict = st.number_input("【单独严管集训】次数", min_value=0, value=0)

            submitted = st.form_submit_button("🚀 启动底层硬逻辑测算", type="primary", use_container_width=True)

            if submitted:
                if not target_name:
                    st.error("❌ 拦截操作：必须在上方输入审查对象姓名。")
                else:
                    # 动态组装所有从严项，传给后端统一算子
                    assembled_strict_items = {}
                    for tag in normal_strict_tags: assembled_strict_items[tag] = 1
                    for tag in super_strict_tags: assembled_strict_items[tag] = 1
                    if strict_record > 0: assembled_strict_items["前科"] = strict_record
                    if strict_strict > 0: assembled_strict_items["单独严管集训"] = strict_strict

                    payload = {
                        "name": target_name,
                        "sentence_type": sentence_type,
                        "original_term_months": original_months,
                        "crime_count": crime_count,
                        "crime_tags": crime_tags,
                        "is_first": is_first,
                        "reference_date": ref_date.strftime("%Y-%m-%d"),
                        "reward_count": reward_count,
                        "punishments": {
                            "警告": warn_count,
                            "记过": demerit_count,
                            "禁闭": confinement_count,
                            "私藏违禁品": contraband_count
                        },
                        "upgrade_date": upgrade_date.strftime("%Y-%m-%d") if upgrade_date else None,
                        "strict_items": assembled_strict_items,
                        "property_unfulfilled": property_unfulfilled
                    }

                    with st.spinner("🧠 引擎启动！正在穿透本地法理规则树进行交叉推演..."):
                        try:
                            res = requests.post(f"{API_URL}/run_screening", json=payload)
                            if res.status_code == 200:
                                result = res.json()
                                st.divider()
                                if result.get("is_qualified"):
                                    st.success("✅ **初步审查通过**：该犯当前客观条件符合提请要求。")
                                    st.info(f"**🎯 系统测算呈报幅度**：{result.get('recommended_reduction')}")
                                else:
                                    st.error("❌ **触发负面拦截**：暂不符合提请条件。")

                                st.markdown("**🔍 AI 法理推演链路日志：**")
                                st.code(result.get("legal_reasoning", "无日志输出"), language="text")
                            else:
                                st.error(f"❌ 后端接口异常 (HTTP {res.status_code}): {res.text}")
                        except Exception as e:
                            st.error(f"❌ 网络请求失败: {str(e)}")

    # ==========================================
    # 选项卡 2：全监区批量筛查 (流式数据台账) —— 保持原样不动
    # ==========================================
    with tab_batch:
        st.subheader("📋 数据库全案卷遍历与硬逻辑初筛")
        batch_cutoff_date = st.date_input("📅 设定全监区统一考核止日：", datetime.now(), key="batch_date")

        if st.button("🚀 一键生成《全监区减刑资格摸底花名册》", type="primary"):

            progress_bar = st.progress(0, text="📡 正在唤醒数据库引擎...")
            table_placeholder = st.empty()
            batch_results = []

            try:
                # 开启超长超时限制，以防数据库过大
                with requests.get(
                        f"{API_URL}/batch_screening_stream?cutoff_date={batch_cutoff_date.strftime('%Y-%m-%d')}",
                        stream=True, timeout=300) as r:
                    total_records = 1
                    for line in r.iter_lines():
                        if line:
                            chunk = json.loads(line.decode('utf-8'))
                            step = chunk.get("step")

                            if step == "init":
                                total_records = max(1, chunk.get("total", 1))
                                progress_bar.progress(5, text=f"📥 成功锁定 {total_records} 份罪犯档案，开始极速演算...")

                            elif step == "processing":
                                current = chunk.get("current", 1)
                                batch_results.append(chunk.get("data"))

                                # 实时更新进度条与展示表格
                                percent = min(100, int((current / total_records) * 100))
                                progress_bar.progress(percent, text=f"⚙️ 正在排查 ({current}/{total_records})...")

                                # 每 5 条刷新一次前端表格，防卡顿
                                if current % 5 == 0 or current == total_records:
                                    df = pd.DataFrame(batch_results)
                                    table_placeholder.dataframe(df, use_container_width=True, hide_index=True)

                            elif step == "done":
                                progress_bar.progress(100, text="🎉 全监区摸底彻底完成！")

                                # 提供 Excel 下载按钮
                                df = pd.DataFrame(batch_results)
                                table_placeholder.dataframe(df, use_container_width=True, hide_index=True)

                                # 生成下载流
                                # 将 DataFrame 转换为 CSV 以供下载 (Streamlit 原生支持极佳)
                                csv = df.to_csv(index=False).encode('utf-8-sig')  # utf-8-sig 防止 Excel 乱码
                                st.download_button(
                                    label="💾 导出摸底花名册 (CSV/Excel)",
                                    data=csv,
                                    file_name=f"减刑摸底花名册_{datetime.now().strftime('%Y%m%d')}.csv",
                                    mime="text/csv",
                                    type="primary"
                                )

            except Exception as e:
                st.error(f"❌ 批量提取发生网络断连或崩溃: {e}")