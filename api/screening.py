from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import os
import sqlite3
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict

# 引入我们手写的完美法理引擎
from services.screening_engine import ScreeningEngine, CriminalProfile

# 如果其他地方不需要大模型算减刑，这里连 requests 和 langchain 都可以省去很多
# 但为了兼容你可能在别的模块用到，予以保留
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS

router = APIRouter()

# ==========================================
# 🌟 环境与路径配置
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAISS_PATH = os.path.join(BASE_DIR, "faiss_index")
DB_PATH = os.path.join(BASE_DIR, "prison_archive.db")

# 预加载知识库 (保留你的原有设计)
print("🚀 正在加载减刑法理知识库...")
try:
    embeddings = OllamaEmbeddings(model="qwen3-embedding:8b", base_url="http://127.0.0.1:11434")
    vector_db = FAISS.load_local(FAISS_PATH, embeddings, allow_dangerous_deserialization=True)
    print("✅ 知识库加载成功！")
except Exception as e:
    print(f"⚠️ 知识库加载失败，系统将降级为无 RAG 模式: {e}")
    vector_db = None


# ==========================================
# 🎯 核心修复：10步工作台的数据拦截模型 (必须与前端 100% 一致)
# ==========================================
class ScreeningRequest(BaseModel):
    name: str
    sentence_type: str
    original_term_months: int
    crime_count: int
    crime_tags: List[str]
    is_first: bool
    reference_date: str  # 前端传来的 YYYY-MM-DD
    reward_count: int
    punishments: Dict[str, int]
    upgrade_date: Optional[str] = None
    strict_items: Dict[str, int]
    property_unfulfilled: bool


# ==========================================
# 🚀 接口1：单人深度法理筛查 (完全接管为硬核 Python 引擎计算)
# ==========================================
@router.post("/run_screening", summary="执行单人深度减刑法理筛查")
async def run_screening(payload: ScreeningRequest):
    # 1. 安全转换时间格式
    ref_date = datetime.strptime(payload.reference_date, "%Y-%m-%d")
    upg_date = datetime.strptime(payload.upgrade_date, "%Y-%m-%d") if payload.upgrade_date else None

    # 2. 组装送入引擎的档案实体
    profile = CriminalProfile(
        sentence_type=payload.sentence_type,
        original_term_months=payload.original_term_months,
        crime_count=payload.crime_count,
        crime_tags=payload.crime_tags,
        is_first=payload.is_first,
        reference_date=ref_date,
        reward_count=payload.reward_count,
        punishments=payload.punishments,
        upgrade_date=upg_date,
        strict_items=payload.strict_items,
        property_unfulfilled=payload.property_unfulfilled
    )

    # 3. 运行毫秒级精确算子，直接返回结果给前端
    engine = ScreeningEngine(profile)
    return engine.run_screening()


# ==========================================
# 🌟 接口2：单人提档引擎 (保留你的原有逻辑)
# ==========================================
@router.get("/fetch_criminal")
async def fetch_criminal(name: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT dynamic_data FROM criminals_v5 WHERE criminal_name = ? ORDER BY id DESC LIMIT 1",
                       (name,))
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            data = json.loads(row[0])
            rewards = data.get("日常改造奖惩", [])
            praise_count = sum(1 for r in rewards if "表扬" in str(r.get("项目名称", "")))

            return {
                "status": "success",
                "data": {
                    "crime_type": data.get("一审罪名列表", ["未知罪名"])[0] if isinstance(data.get("一审罪名列表"),
                                                                                          list) else data.get(
                        "一审罪名列表", "未知罪名"),
                    "praise_count": praise_count,
                    "last_change_date": data.get("现刑期起日", "1970-01-01"),
                    "property_status": "未履行" if data.get("财产性判项履行情况简述") == "无" else "已全部履行",
                    "is_heie": "普通罪犯"  # 简化处理，由前端十步工作台点选即可
                }
            }
        return {"status": "error", "message": "未在数据库中找到该罪犯"}
    except Exception as e:
        return {"status": "error", "message": f"数据库连接异常: {str(e)}"}


# ==========================================
# 🌟 接口3：全监批量筛查引擎 (保留你的原有逻辑)
# ==========================================
@router.get("/batch_screening_stream")
async def batch_screening_stream(cutoff_date: str):
    def generate():
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT criminal_name, dynamic_data FROM criminals_v5 WHERE dynamic_data IS NOT NULL")
            rows = cursor.fetchall()
            conn.close()

            total = len(rows)
            yield json.dumps({"step": "init", "total": total}) + "\n"

            for i, row in enumerate(rows):
                name, dynamic_data_str = row
                data = json.loads(dynamic_data_str)

                crime_type = data.get("一审罪名列表", ["未知"])[0] if isinstance(data.get("一审罪名列表"),
                                                                                 list) else data.get("一审罪名列表",
                                                                                                     "未知")
                last_change_date = data.get("现刑期起日", "1970-01-01")

                rewards = data.get("日常改造奖惩", [])
                praise_count = sum(1 for r in rewards if "表扬" in str(r.get("项目名称", "")))

                try:
                    start_date = datetime.strptime(last_change_date, "%Y-%m-%d")
                    end_date = datetime.strptime(cutoff_date, "%Y-%m-%d")
                    delta = relativedelta(end_date, start_date)
                    interval_months = delta.years * 12 + delta.months
                except:
                    interval_months = 0

                is_qualified = False
                reason = "间隔期或表扬数不足"

                if interval_months >= 18 and praise_count >= 3:
                    is_qualified = True
                    reason = f"已满 {interval_months} 个月，累计表扬 {praise_count} 次，基本达标。"
                elif interval_months >= 24:
                    is_qualified = True
                    reason = f"间隔期充裕 ({interval_months}个月)，需核查积分细节。"

                result_data = {
                    "姓名": name,
                    "罪名": crime_type,
                    "间隔期(月)": interval_months,
                    "表扬次数": praise_count,
                    "筛查结论": "✅ 拟符合" if is_qualified else "❌ 不符合",
                    "系统判定依据": reason
                }

                yield json.dumps({"step": "processing", "current": i + 1, "data": result_data}) + "\n"

            yield json.dumps({"step": "done", "msg": "全监区摸底完成！"}) + "\n"

        except Exception as e:
            yield json.dumps({"step": "error", "msg": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")