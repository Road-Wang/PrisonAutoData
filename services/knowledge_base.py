import os
import pandas as pd
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from rapidocr_onnxruntime import RapidOCR

# ==========================================
# 🌟 核心升级：获取项目绝对根目录，彻底解决路径漂移问题
# __file__ 指向 services/knowledge_base.py，它的上一级就是 PrisonAutoData 根目录
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledgebase")
VECTOR_DB_PATH = os.path.join(BASE_DIR, "faiss_index")


def build_vector_db():
    print(f"📚 正在启动全模态本地法理知识库构建引擎...")
    print(f"🎯 锁定知识库源目录: {KNOWLEDGE_DIR}")
    print(f"🎯 锁定索引输出目录: {VECTOR_DB_PATH}")

    if not os.path.exists(KNOWLEDGE_DIR):
        print(f"❌ 找不到 {KNOWLEDGE_DIR} 文件夹，请先创建并放入文档！")
        return

    documents = []
    ocr_engine = RapidOCR()  # 初始化本地 OCR 引擎

    # 🌟 核心升级：使用 os.walk 递归遍历所有子文件夹
    file_count = 0
    for root, dirs, files in os.walk(KNOWLEDGE_DIR):
        for filename in files:
            file_path = os.path.join(root, filename)

            # 为了让日志更清晰，这里截取相对路径用于显示
            relative_path = os.path.relpath(file_path, KNOWLEDGE_DIR)

            try:
                # 👉 处理标准 PDF
                if filename.endswith(".pdf"):
                    print(f"  📄 加载 PDF: {relative_path}")
                    loader = PyPDFLoader(file_path)
                    documents.extend(loader.load())
                    file_count += 1

                # 👉 处理 Word 文档
                elif filename.endswith(('.docx', '.doc')):
                    print(f"  📝 加载 Word: {relative_path}")
                    loader = Docx2txtLoader(file_path)
                    documents.extend(loader.load())
                    file_count += 1

                # 👉 处理 Excel 表格台账
                elif filename.endswith(('.xlsx', '.xls')):
                    print(f"  📊 加载 Excel: {relative_path}")
                    df = pd.read_excel(file_path)
                    # 将表格每一行转化为一段自然语言文本
                    for index, row in df.iterrows():
                        row_text = "；".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                        # 在 metadata 中保留它的来源路径，方便后续排查溯源
                        documents.append(
                            Document(page_content=row_text, metadata={"source": relative_path, "row": index}))
                    file_count += 1

                # 👉 处理图片扫描件 (红头文件/政策影印版)
                elif filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    print(f"  👁️ 启动 OCR 提取扫描件: {relative_path}")
                    result, _ = ocr_engine(file_path)
                    if result:
                        # 将提取出的文字块拼装成完整段落
                        text = "\n".join([line[1] for line in result])
                        documents.append(Document(page_content=text, metadata={"source": relative_path}))
                    else:
                        print(f"    ⚠️ OCR 未在 {relative_path} 中检测到有效文字。")
                    file_count += 1

            except Exception as e:
                print(f"  ⚠️ 加载 {relative_path} 失败: {e}")

    if not documents:
        print("❌ 知识库文件夹为空，或者没有找到支持格式的文件。")
        return

    print(f"📂 扫描完毕！共成功读取 {file_count} 份文件（包含各级子目录）。")

    # 2. 文本切块（司法级粒度）
    print(f"✂️ 正在对提取的卷宗和政策进行智能法理切块...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "第", "条", "。", "；"]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"✅ 共切分出 {len(chunks)} 个法理知识块。")

    # 3. 连接本地 Ollama 向量模型
    print("🧠 正在连接本地 qwen3-embedding:8b 向量引擎...")
    embeddings = OllamaEmbeddings(
        model="qwen3-embedding:8b",
        base_url="http://127.0.0.1:11434"
    )

    # 4. 构建并保存本地 FAISS 向量库
    print("💾 正在构建底层向量数据库，请稍候...")
    vector_db = FAISS.from_documents(chunks, embeddings)
    vector_db.save_local(VECTOR_DB_PATH)
    print(f"🎉 全模态知识库构建彻底完成！索引已保存至 {VECTOR_DB_PATH}。")


if __name__ == "__main__":
    build_vector_db()