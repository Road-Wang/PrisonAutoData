#main.py
import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api import expenses
from api import screening
from api import archive_maker
from api import doc_generator
from services import vision_extractor
import db_manager
app = FastAPI(
    title="减刑业务自动化中枢",
    servers=[
        {"url": "http://host.docker.internal:8000", "description": "本地宿主机"}
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 把账务模块“挂载”到主应用上，可以加一个统一的前缀，比如 /api/v1
app.include_router(expenses.router, prefix="/api/v1/expenses", tags=["账务处理模块"])
app.include_router(screening.router, prefix="/api/v1/screening", tags=["资格筛查模块"])
app.include_router(archive_maker.router, prefix="/api", tags=["智能档案提取"])
app.include_router(doc_generator.router, prefix="/api/v1/doc_gen", tags=["文书生成模块"])


if __name__ == "__main__":
        uvicorn.run("main:app", host="127.0.0.1", port=8888, reload=True)