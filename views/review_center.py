import streamlit as st
import os
import tempfile
# 假设你已经将上述引擎保存在 services/review_engine.py
from services.review_engine import ReviewEngine


def render():

    st.title("🛡️ 录入数据审查中心")
    st.markdown("上传《减刑审批表》及《审核评议表》，系统将自动调取底层电子档案进行逐字级比对与逻辑纠错。")

    # 1. 顶部查询区域
    with st.container():
        col1, col2 = st.columns([1, 3])
        with col1:
            criminal_name = st.text_input("👤 罪犯姓名", placeholder="输入待审核罪犯姓名...")
        with col2:
            st.write("")  # 占位对齐
            st.info("系统会自动从 `Prison_Archives` 目录下检索该犯的起诉书、一审判决等作为比对基准源。")

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

            with st.spinner("🧠 正在启动多模态比对引擎... (提取底层档案 -> OCR文书 -> 法理推演 -> 格式纠错)"):
                engine = ReviewEngine(criminal_name=criminal_name)
                result = engine.run_review(app_paths, eval_paths)

                # 处理异常情况
                if "error" in result:
                    st.error(f"审查过程中断: {result['error']}")
                    return

            # 4. 结果展示区
            st.success("✅ 交叉审查完毕！请关注以下异常项目：")
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

        finally:
            # 清理临时文件
            for path in app_paths + eval_paths:
                if os.path.exists(path):
                    os.remove(path)


if __name__ == "__main__":
    render()