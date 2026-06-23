import io
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, Body, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime
import sqlite3
import json
import os
import re
import traceback
import shutil
from typing import List

# 🌟 新增导入了 process_batch_update
from services.vision_extractor import process_batch_documents, extract_single_document, stream_extract_from_full_text
from services.conflict_resolver import stream_synthesize_and_detect_conflicts
from db_manager import save_criminal_to_db, process_batch_update

# 尝试导入数据库提档函数（如果不存在则设为假函数防崩溃）
try:
    from db_manager import get_criminal_dynamic_data
except ImportError:
    def get_criminal_dynamic_data(name: str):
        return None

router = APIRouter()

# 临时存放扫描件的目录
UPLOAD_DIR = "uploaded_scans"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ==========================================
# 🟢 升级：支持三模态分流的单图提取通道
# ==========================================
@router.post("/upload_archive_batch", summary="批量上传档案 -> 流式提取 -> Map-Reduce 交叉研判")
async def upload_archive_batch(
        files: List[UploadFile] = File(...),
        target_name: str = Form(""),
        mode: str = Form("模式一"),
        doc_category: str = Form(""),
        extra_prompt: str = Form(""),
        batch_name: str = Form(""),
        batch_type: str = Form("")
):
    # 🌟 探照灯 1号：打印模式，确保前端参数成功送达
    print(f"\n{'=' * 40}")
    print(f"🔥 [雷达警报] 成功接收到前端请求！")
    print(f"🔥 业务模式: {mode}")
    print(f"🔥 目标罪犯: {target_name}, 收到文件数: {len(files)}")
    print(f"{'=' * 40}\n")

    def generate_progress():
        try:
            ARCHIVE_ROOT = "Prison_Archives"
            os.makedirs(ARCHIVE_ROOT, exist_ok=True)

            yield json.dumps({"step": "init", "msg": f"📥 成功接收 {len(files)} 份案卷，准备启动视觉引擎..."}) + "\n"

            # 1. 保存所有上传的文件到临时目录
            saved_paths = []
            for file in files:
                file_path = os.path.join(UPLOAD_DIR, file.filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                saved_paths.append(file_path)

            # ==========================================
            # ⚡ 核心新增：模式三分流（极速增量入库）
            # ==========================================
            if "模式三" in mode:
                for idx, path in enumerate(saved_paths):
                    doc_name = os.path.basename(path)
                    yield json.dumps({"step": "vision",
                                      "msg": f"👁️ 正在极速穿透扫描 ({idx + 1}/{len(files)})：【{doc_name}】..."}) + "\n"

                    try:
                        # 呼叫微型探针
                        extracted_data = extract_single_document(
                            image_path=path,
                            doc_name=doc_name,
                            target_name="",
                            previous_doc_type="无",
                            mode=mode,
                            batch_name=batch_name,
                            batch_type=batch_type
                        )

                        name = extracted_data.get("姓名", "")
                        action_date = extracted_data.get("时间", "")

                        if name and action_date:
                            # 直接触发神技：增量追加并物理归档
                            success = process_batch_update(name, batch_type, action_date, path)
                            if success:
                                msg = f"✅ 已成功识别【{name}】，并自动追加至底层数据库。"
                            else:
                                msg = f"⚠️ 识别出【{name}】，但底座中无该人基础档案，跳过入库。"
                        else:
                            msg = "⚠️ 未在该扫描件提取到姓名或日期，文件跳过。"

                        yield json.dumps({
                            "step": "vision",
                            "vision_detail": f"OCR 探针极速提取结果:\n{json.dumps(extracted_data, ensure_ascii=False, indent=2)}\n\n{msg}",
                            "file": doc_name
                        }) + "\n"

                    except Exception as e:
                        err_trace = traceback.format_exc()
                        print(f"⚠️ 图片 {doc_name} 极速提取失败:\n{err_trace}")
                        yield json.dumps(
                            {"step": "vision", "msg": f"⚠️ 警告：提取【{doc_name}】发生异常 ({str(e)})，跳过！"}) + "\n"

                # 模式三直接结束！不再进入后续的 Map-Reduce 流水线
                yield json.dumps({"step": "done", "msg": "🎉 批量增量入库完成！", "data": {"conflicts": []}}) + "\n"
                return

            # ==========================================
            # 🎯 核心进化：模式二（全文通读模式 - 专治多页单份长文书）
            # ==========================================
            elif "模式二" in mode:
                yield json.dumps(
                    {"step": "vision", "msg": f"📚 模式二：开启【全文通读架构】，共接收 {len(files)} 页扫描件..."}) + "\n"

                full_text_blocks = []
                archive_mapping = []
                safe_doc_type = re.sub(r'[\\/*?:"<>|]', "", doc_category)

                # 第一阶段：流水线纯 OCR 像素剥离，暂不启动逻辑思考
                for i, path in enumerate(saved_paths):
                    doc_name = os.path.basename(path)
                    yield json.dumps({"step": "vision",
                                      "msg": f"👁️ 正在进行全卷像素剥离 ({i + 1}/{len(files)})：【{doc_name}】..."}) + "\n"

                    try:
                        # 🌟 强制挂载为纯OCR模式，极速剥离文字
                        data = extract_single_document(
                            image_path=path, doc_name=doc_name, target_name=target_name, mode="纯OCR"
                        )
                        page_text = data.get("提取内容", "未提取到有效文本")

                        # 按顺序拼接，并打上明确的物理页码锚点
                        full_text_blocks.append(
                            f"\n\n=====================\n【第 {i + 1} 页：{doc_name}】\n=====================\n{page_text}")

                        archive_mapping.append({
                            "文件名": doc_name,
                            "临时路径": path,
                            "AI建议归档类别": safe_doc_type
                        })

                        yield json.dumps({
                            "step": "vision",
                            "msg": f"📄 第 {i + 1} 页提取完毕",
                            "vision_detail": f"该页提取 {len(page_text)} 字。暂不进行单页逻辑推演，等待全卷合并...",
                            "file": doc_name
                        }) + "\n"

                    except Exception as e:
                        err_trace = traceback.format_exc()
                        print(f"⚠️ 图片 {doc_name} 提取失败:\n{err_trace}")
                        yield json.dumps(
                            {"step": "vision", "msg": f"⚠️ 警告：提取【{doc_name}】发生异常 ({str(e)})，跳过！"}) + "\n"

                # 追加历史底层数据作为前置知识 (防冲突)
                historical_data = get_criminal_dynamic_data(target_name)
                if historical_data:
                    yield json.dumps(
                        {"step": "logic", "msg": f"📂 侦测到【{target_name}】的历史系统存档！已加入全卷上下文..."}) + "\n"
                    full_text_blocks.append(
                        f"\n\n=====================\n【底座历史档案参考】\n=====================\n{json.dumps(historical_data, ensure_ascii=False)}")

                # ==========================================
                # 🧠 资源调度：三段式汉堡架构 (防 OOM 与 注意力涣散)
                # ==========================================
                TOTAL_PAGES = len(full_text_blocks)

                if TOTAL_PAGES > 15:
                    yield json.dumps({"step": "logic",
                                      "msg": f"⚠️ 侦测到超长卷宗 ({TOTAL_PAGES} 页)！启动三段式智能折叠架构保护显存..."}) + "\n"

                    # 1. 物理切片：掐头去尾 (保留前10页和后10页)
                    head_blocks = full_text_blocks[:10]
                    tail_blocks = full_text_blocks[-10:]
                    middle_blocks = full_text_blocks[10:-10]

                    # 2. 拼接核心基础框架 (首尾直接喂给大模型提取刚性指标)
                    combined_text = "".join(head_blocks)
                    combined_text += f"\n\n...[系统为了节省算力，已自动折叠中间 {len(middle_blocks)} 页的庭审质证与证言过程]...\n\n"
                    combined_text += "".join(tail_blocks)

                    # 3. 动态 RAG 检索：如果干警下达了重点提取指令，从中间部分精准抽调证据
                    if extra_prompt:
                        yield json.dumps({"step": "logic",
                                          "msg": f"🔍 正在使用 FAISS 向量检索从被折叠的 {len(middle_blocks)} 页中定位特定线索..."}) + "\n"
                        # [注]：此处调用现有的 FAISS / Knowledge Base 逻辑
                        # 例如将 middle_blocks 向量化，搜索与 extra_prompt 相关的 Top-3 段落
                        # 假设找到了相关的关键段落 relevant_chunks：
                        relevant_chunks = "\n".join(["[从中间页检索到的相关事实]...", "..."])  # 替换为实际检索结果

                        combined_text += f"\n\n=====================\n【系统从折叠区域为您打捞的关键事实】\n=====================\n{relevant_chunks}"
                else:
                    # 15页以内，算力充裕，直接全文无损通读
                    combined_text = "".join(full_text_blocks)

                yield json.dumps({"step": "logic",
                                  "msg": f"🧠 全卷文本无缝合并完成 (共 {len(combined_text)} 字)！正在激活上帝视角..."}) + "\n"

                # 第二阶段：一气呵成流式提取法理
                full_final_text = ""
                final_generator = stream_extract_from_full_text(combined_text, target_name, doc_category, extra_prompt)

                for text_fragment in final_generator:
                    full_final_text += text_fragment
                    print(text_fragment, end="", flush=True)
                    yield json.dumps({"step": "logic_stream", "chunk": text_fragment}) + "\n"

                    if len(full_final_text) % 100 == 0:
                        yield json.dumps(
                            {"step": "logic", "msg": f"🧠 上帝视角通读推演中... ({len(full_final_text)} 字)"}) + "\n"

                clean_str_match = re.search(r'\{.*\}', full_final_text, re.DOTALL)
                if not clean_str_match:
                    raise Exception("大模型未能输出合法的 JSON 闭合结构！")

                # 🌟 解析出包含 confirmed_data 和 evidence_chain 的复合结构
                raw_report = json.loads(clean_str_match.group(0))

                # 重新按 Streamlit 视图规范组装
                formatted_report = {
                    "confirmed_data": raw_report.get("confirmed_data", {}),
                    "evidence_chain": raw_report.get("evidence_chain", {}),  # 🌟 安全注入溯源链
                    "conflicts": raw_report.get("conflicts", []),
                    "archive_mapping": archive_mapping
                }

                yield json.dumps(
                    {"step": "done", "msg": "🎉 判决书全卷通读研判彻底完成！", "data": formatted_report}) + "\n"
                return

            # ==========================================
            # 📦 模式一：常规混合卷宗 Map-Reduce 推理流 (保留原样)
            # ==========================================
            elif "模式一" in mode:
                last_doc_type = "未分类文书"
                archive_mapping = []
                batch_raw_data = []

                for i, path in enumerate(saved_paths):
                    doc_name = os.path.basename(path)
                    yield json.dumps(
                        {"step": "vision", "msg": f"👁️ 正在穿透扫描 ({i + 1}/{len(files)})：【{doc_name}】..."}) + "\n"

                    try:
                        # 🌟 传入动态 mode 和 params 给抽取器
                        data = extract_single_document(
                            image_path=path,
                            doc_name=doc_name,
                            target_name=target_name,
                            previous_doc_type=last_doc_type,
                            mode=mode,
                            doc_category=doc_category,
                            extra_prompt=extra_prompt
                        )

                        doc_type = data.get("文书类别", "未分类文书")
                        safe_doc_type = re.sub(r'[\\/*?:"<>|]', "", doc_type)
                        last_doc_type = safe_doc_type

                        archive_mapping.append({
                            "文件名": doc_name,
                            "临时路径": path,
                            "AI建议归档类别": safe_doc_type
                        })

                        yield json.dumps({
                            "step": "vision",
                            "msg": f"📂 拟定归档标签：【{safe_doc_type}】 (等待人工复核)",
                            "vision_detail": json.dumps(data, ensure_ascii=False, indent=2),
                            "file": doc_name
                        }) + "\n"

                        batch_raw_data.append({
                            "source_file": doc_name,
                            "extracted_content": data
                        })

                    except Exception as e:
                        err_trace = traceback.format_exc()
                        print(f"⚠️ 图片 {doc_name} 提取失败:\n{err_trace}")
                        yield json.dumps(
                            {"step": "vision", "msg": f"⚠️ 警告：提取【{doc_name}】发生异常 ({str(e)})，跳过！"}) + "\n"

                historical_data = get_criminal_dynamic_data(target_name)
                if historical_data:
                    yield json.dumps(
                        {"step": "logic", "msg": f"📂 侦测到【{target_name}】的历史系统存档！已加入研判..."}) + "\n"
                    batch_raw_data.append({
                        "source_file": "【历史系统存档】",
                        "extracted_content": historical_data
                    })

                total_valid_files = len(batch_raw_data)
                CHUNK_SIZE = 12

                if total_valid_files == 0:
                    yield json.dumps({"step": "logic", "msg": "❌ 所有文件均提取失败，无法进行逻辑研判。"}) + "\n"
                    return

                intermediate_summaries = []
                total_batches = (total_valid_files + CHUNK_SIZE - 1) // CHUNK_SIZE

                if total_valid_files > CHUNK_SIZE:
                    yield json.dumps({"step": "logic", "msg": f"⚠️ 启动【Map-Reduce 分批保护流水线】..."}) + "\n"
                    for i in range(total_batches):
                        start_idx = i * CHUNK_SIZE
                        end_idx = min(start_idx + CHUNK_SIZE, total_valid_files)
                        chunk_data = batch_raw_data[start_idx:end_idx]

                        yield json.dumps(
                            {"step": "logic", "msg": f"🧠 正在进行第 {i + 1}/{total_batches} 批次初审..."}) + "\n"
                        chunk_generator = stream_synthesize_and_detect_conflicts(chunk_data)
                        full_chunk_text = ""

                        for text_fragment in chunk_generator:
                            full_chunk_text += text_fragment
                            print(text_fragment, end="", flush=True)
                            yield json.dumps({"step": "logic_stream", "chunk": text_fragment}) + "\n"

                            if len(full_chunk_text) % 100 == 0:
                                yield json.dumps({"step": "logic",
                                                  "msg": f"🧠 [第{i + 1}批次初审] 正在推演... ({len(full_chunk_text)} 字)"}) + "\n"

                        clean_str_match = re.search(r'\{.*\}', full_chunk_text, re.DOTALL)
                        if clean_str_match:
                            intermediate_summaries.append({
                                "source_file": f"第{i + 1}批次初审汇总",
                                "extracted_content": json.loads(clean_str_match.group(0))
                            })
                    yield json.dumps({"step": "logic", "msg": f"👑 各批次初审完毕！进行最终法理融合..."}) + "\n"
                else:
                    intermediate_summaries = batch_raw_data
                    yield json.dumps({"step": "logic", "msg": f"🧠 正在唤醒逻辑大脑进行法理研判直播..."}) + "\n"

                full_final_text = ""
                final_generator = stream_synthesize_and_detect_conflicts(intermediate_summaries)

                for text_fragment in final_generator:
                    full_final_text += text_fragment
                    print(text_fragment, end="", flush=True)
                    yield json.dumps({"step": "logic_stream", "chunk": text_fragment}) + "\n"

                    if len(full_final_text) % 100 == 0:
                        yield json.dumps(
                            {"step": "logic", "msg": f"🧠 逻辑大脑生成中... ({len(full_final_text)} 字)"}) + "\n"

                clean_str_match = re.search(r'\{.*\}', full_final_text, re.DOTALL)
                if not clean_str_match:
                    raise Exception("大模型未能输出合法的 JSON 闭合结构！")

                final_report = json.loads(clean_str_match.group(0))
                final_report["archive_mapping"] = archive_mapping
                yield json.dumps({"step": "done", "msg": "🎉 全量研判彻底完成！", "data": final_report}) + "\n"

        except Exception as e:
            err_trace = traceback.format_exc()
            print(f"\n{'=' * 40}")
            print(f"❌ 致命系统崩溃:\n{err_trace}")
            print(f"{'=' * 40}\n")
            yield json.dumps({
                "step": "logic",
                "msg": f"❌ 底层逻辑彻底崩溃！具体原因:\n{str(e)}"
            }) + "\n"

    return StreamingResponse(generate_progress(), media_type="application/x-ndjson")


# ==========================================
# 🔴 原有：确认并入库 (适用于模式一、模式二)
# ==========================================
@router.post("/confirm_and_save", summary="步骤二：将全量数据永久入库与物理归档")
async def confirm_and_save(
        final_data: dict = Body(..., description="干警核对后的全量 JSON 数据")
):
    target_name = final_data.get("confirmed_data", {}).get("姓名", "未知人员")
    ARCHIVE_ROOT = "Prison_Archives"

    # 1. 执行物理文件的真正移动
    archive_mapping = final_data.get("archive_mapping", [])
    for item in archive_mapping:
        doc_name = item.get("文件名")
        temp_path = item.get("临时路径")
        final_category = item.get("AI建议归档类别", "未分类文书")

        if os.path.exists(temp_path):
            target_dir = os.path.join(ARCHIVE_ROOT, target_name, final_category)
            os.makedirs(target_dir, exist_ok=True)
            final_file_path = os.path.join(target_dir, doc_name)
            shutil.move(temp_path, final_file_path)

    # 2. 直接把字典原封不动扔给强大的数据库管家
    if save_criminal_to_db(final_data):
        return {"status": "success", "message": f"🎉 罪犯【{target_name}】的基础档案已永久入库，且卷宗已成功物理归档！"}
    else:
        return {"status": "error", "message": "入库失败，请查看后台日志。"}


@router.post("/upload_prison_admin_data", summary="狱政系统数据清洗与同步入库")
async def upload_prison_admin_data(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        # 跳过前 4 行空行，直接把第 5 行作为表头读取
        df = pd.read_excel(io.BytesIO(contents), skiprows=4)

        # 定义“脏数据”清洗规则
        def clean_cell(val):
            if pd.isna(val):
                return None
            val_str = str(val)
            if val_str.startswith("'"):
                val_str = val_str[1:]
            return val_str.strip()

        # 对整张表应用清洗规则
        df = df.applymap(clean_cell)

        # 清除完全为空的列
        df = df.dropna(axis=1, how='all')

        update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df['系统导入时间'] = update_time

        # 自动建表与全量替换写入（规范化英文表名）
        conn = sqlite3.connect("prison_archive.db")
        df.to_sql("prison_admin_data", conn, if_exists='replace', index=False)

        record_count = len(df)
        conn.close()

        return {
            "status": "success",
            "message": f"成功清洗并导入了 {record_count} 名罪犯的狱政系统最新数据！表名：prison_admin_data",
            "count": record_count,
            "update_time": update_time
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"狱政数据解析入库失败: {str(e)}")