import streamlit as st
from views import archive_dashboard, screening_hub, review_center, doc_generator

# 1. 初始化全局业务上下文（确保跨区块数据联动）
if "current_target_id" not in st.session_state:
    st.session_state.current_target_id = None  # 当前锁定的办案对象罪犯编号
if "current_target_name" not in st.session_state:
    st.session_state.current_target_name = None

st.set_page_config(page_title="保定监狱办公流程自动化智慧化一体平台", layout="wide", initial_sidebar_state="expanded")

# 2. 全局大区块一级路由配置
st.sidebar.title("⚖️ "
                 "保定监狱办公流程AI自动化一体平台")

st.sidebar.markdown("---")

main_block = st.sidebar.radio(
    "📂 请选择业务大区块：",
    [
        "1️⃣ 罪犯档案扫描及智能入库",
        "2️⃣ 减刑/假释/暂外资格筛查",
        "3️⃣ 录入数据审查中心",
        "4️⃣ 刑罚执行文书一键生成"
    ]
)

st.sidebar.markdown("---")
# 侧边栏常驻显示当前正在办理的人员信息，实现跨模块穿透
if st.session_state.current_target_name:
    st.sidebar.success(f"📌 当前办案中：{st.session_state.current_target_name} ({st.session_state.current_target_id})")

# 3. 动态路由分发逻辑
if main_block == "1️⃣ 罪犯档案扫描及智能入库":
    archive_dashboard.render()

elif main_block == "2️⃣ 减刑/假释/暂外资格筛查":
    screening_hub.render()

elif main_block == "3️⃣ 录入数据审查中心":
    review_center.render()

elif main_block == "4️⃣ 刑罚执行文书一键生成":
    doc_generator.render()