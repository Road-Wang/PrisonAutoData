import streamlit as st
import os
import tempfile
# 假设你已经将上述引擎保存在 services/review_engine.py
from services.review_engine import ReviewEngine
from db_manager import get_criminal_dynamic_data, update_criminal_data # 确保引入了你的 db_manager

def render():

    st.title("🛡️ 录入数据审查中心")
    st.markdown("上传《减刑审批表》及《审核评议表》，系统将自动调取底层电子档案进行逐字级比对与逻辑纠错。")

    # 1. 顶部查询区域
    with st.container():
        st.subheader("🔍 基础检索与标准库配置")
        col1, col2 = st.columns([1, 3])
        with col1:
            criminal_name = st.text_input("👤 罪犯姓名", placeholder="输入待审核罪犯姓名...")
        with col2:
            # 动态加载数据库中的标准财产叙述
            standard_prop_text = ""
            if criminal_name:
                db_data = get_criminal_dynamic_data(criminal_name)
                if db_data:
                    standard_prop_text = db_data.get("财产性判项标准叙述", "")

            prop_input = st.text_area(
                "💰 财产性判项执行情况 (标准叙述库)",
                value=standard_prop_text,
                height=100,
                help="此处内容将保存至数据库。本批次减刑生成其他文书时将直接复用此段叙述。大模型也将以此为绝对基准核对评议表。"
            )

            if st.button("💾 更新该犯财产标准叙述至数据库", type="secondary"):
                if criminal_name and prop_input:
                    try:
                        # 调用 db_manager 的更新方法，将其写入档案字典
                        update_criminal_data(criminal_name, {"财产性判项标准叙述": prop_input})
                        st.success("标准叙述已入库！后续文书可直接调取。")
                    except Exception as e:
                        st.error(f"入库失败，请检查数据库连接: {e}")
    st.divider()

    # 2. 文件上传区域
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("📄 审批表上传")
        approval_files = st.file_uploader(
            "请上传《提请减刑审批表》（支持多张，请按顺序上传）",
            type=['jpg', 'jpeg', 'png'],
            accept_multiple_files=True,
            key="approval_upload"
        )

    with col4:
        st.subheader("📝 评议表上传")
        eval_files = st.file_uploader(
            "请上传《减刑审核评议表》（支持多张，请按顺序上传）",
            type=['jpg', 'jpeg', 'png'],
            accept_multiple_files=True,
            key="eval_upload"
        )

    # 3. 审查执行区
    if st.button("🚀 开始智能审查", type="primary", use_container_width=True):
        if not criminal_name:
            st.error("请先输入罪犯姓名！")
            return
        if not approval_files or not eval_files:
            st.warning("请确保审批表和评议表均已上传图片！")
            return

        # 临时保存上传的图片供 OCR 读取
        temp_dir = tempfile.mkdtemp()
        app_paths, eval_paths = [], []

        try:
            for f in approval_files:
                path = os.path.join(temp_dir, f"app_{f.name}")
                with open(path, "wb") as out: out.write(f.read())
                app_paths.append(path)

            for f in eval_files:
                path = os.path.join(temp_dir, f"eval_{f.name}")
                with open(path, "wb") as out: out.write(f.read())
                eval_paths.append(path)

                # 使用状态容器展示进度
                status_container = st.status("🚀 正在启动多模态比对引擎...", expanded=True)

                # 你可以在 ReviewEngine 的 run_review 中加入回调函数，或者简单一点，先在前端显示节点
                status_container.write("⏳ [1/4] 正在检索底层电子档案...")
                # (假装或真实传递状态给 engine)
                status_container.write("👁️ [2/4] 正在启动防断连 OCR 读取审批表与评议表...")

                engine = ReviewEngine(criminal_name=criminal_name)
                # 🌟 注意：我们把 UI 里的标准叙述也传给引擎
                result = engine.run_review(app_paths, eval_paths, standard_prop_text=prop_input)

                status_container.write("🧠 [3/4] 正在调度 16K 超长上下文大模型进行法理逻辑碰撞...")
                status_container.write("📝 [4/4] 正在生成红绿灯审查报告...")
                status_container.update(label="✅ 审查完毕！", state="complete", expanded=False)
                # 处理异常情况
                if "error" in result:
                    st.error(f"审查过程中断: {result['error']}")
                    return

            # 4. 结果展示区
            st.success("✅ 交叉审查完毕！请关注以下异常项目：")
            with st.expander("⚖️ 展开查看系统底层法理时间轴推演过程", expanded=True):
                st.code(result.get("法定幅度推演明细", "暂无法理推演过程"), language="markdown")
            st.markdown(f"**💡 综合评价:** {result.get('综合评价', '无')}")

            st.markdown("### 📊 分项核查报告")

            # views/review_center.py 中需要对应的修改（只需修改这一个列表）：
            check_items = [
                ("基本身份信息", "基本身份信息"),
                ("强制措施与刑期起止", "强制措施与刑期起止"),
                ("犯罪事实与前科劣迹", "犯罪事实与前科劣迹"),
                ("历次裁判与附加刑变动", "历次裁判与附加刑明细"),  # 更新此项
                ("奖励与处分核对", "奖励与处分核对"),
                ("财产判项与积极分子", "财产判项与积极分子"),
                ("监区减刑幅度", "监区减刑幅度意见")
            ]

            # 使用网格系统展示卡片
            for i in range(0, len(check_items), 2):
                c1, c2 = st.columns(2)
                cols = [c1, c2]
                for j in range(2):
                    if i + j < len(check_items):
                        key, title = check_items[i + j]
                        data = result.get(key, {})
                        status = data.get("status", "未知")

                        with cols[j]:
                            if "异常" in status or "驳回" in status:
                                st.error(f"**{title}** - ❌ {status}")
                                st.write(f"**错误描述:** {data.get('error', '未提供')}")
                                st.write(f"**修改建议:** {data.get('suggestion', '未提供')}")
                            elif "通过" in status:
                                st.success(f"**{title}** - ✅ {status}")
                            else:
                                st.info(f"**{title}** - ℹ️ 未检出明显异常")

            st.markdown("---")
            st.markdown("### 🎯 AI 视觉靶点圈定分析")
            st.info("系统已自动将存在错误的表单区域进行坐标映射，红框代表致命错误或遗漏，黄框代表逻辑疑点。")

            # 提取我们在 ReviewEngine 里画好的带红圈的图片
            annotated_imgs = result.get("annotated_images", [])

            if annotated_imgs:
                # 动态分配列数来展示图片（比如一行放两张）
                cols = st.columns(2)
                for idx, img_path in enumerate(annotated_imgs):
                    with cols[idx % 2]:
                        # 使用 streamlit 展示本地图片，开启点击放大的参数
                        st.image(img_path, caption=f"AI 批注图纸 {idx + 1}", use_container_width=True)
            else:
                st.success("🎉 太棒了，当前表单未发现需要红笔圈改的错误定位点！")

        finally:
            # 修改原来的清理代码，别忘了把生成的带框图片也清理掉
            cleanup_paths = app_paths + eval_paths + result.get("annotated_images", [])
            for path in cleanup_paths:
                if os.path.exists(path):
                    os.remove(path)


if __name__ == "__main__":
    render()