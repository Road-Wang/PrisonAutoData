import io
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl.styles import Font, Alignment, Border, Side
from urllib.parse import quote
import traceback
router = APIRouter()


@router.post("/generate_excel", summary="生成月消费明细表")
async def generate_excel(
        file: UploadFile = File(...),
        code: str = Form(...),
        target_name: str = Form("")  # 新增：接收前端传来的罪犯姓名
):
    try:
        # 直接从内存中读取上传的文件内容
        contents = await file.read()
        df_raw = pd.read_excel(io.BytesIO(contents), header=1)

        df_raw['时间'] = pd.to_datetime(df_raw['时间'])
        df_raw['支出'] = pd.to_numeric(df_raw['支出'], errors='coerce').fillna(0)

        if df_raw.empty or pd.isna(df_raw['时间'].max()):
            end_month = pd.Timestamp.now().strftime('%Y-%m')
        else:
            end_month = df_raw['时间'].max().strftime('%Y-%m')

        all_months = pd.period_range(start='2025-08', end=end_month, freq='M').astype(str).tolist()

        df = df_raw[df_raw['款项类型'].str.contains('超市|购物', na=False, regex=True)].copy()
        df = df.sort_values('时间').reset_index(drop=True)
        df['原始月份'] = df['时间'].dt.strftime('%Y-%m')
        df['归属月份'] = df['原始月份']

        for i in range(len(all_months) - 1):
            curr_m = all_months[i]
            next_m = all_months[i + 1]
            curr_shopping = df[df['归属月份'] == curr_m]

            if curr_shopping.empty:
                next_shopping = df[df['归属月份'] == next_m]
                if not next_shopping.empty:
                    earliest_date = next_shopping['时间'].min()
                    if earliest_date.day <= 10:
                        idx_to_move = next_shopping[next_shopping['时间'].dt.date == earliest_date.date()].index
                        df.loc[idx_to_move, '归属月份'] = curr_m

        summary = df.groupby('归属月份')['支出'].sum().reset_index()
        summary_all = pd.DataFrame({'归属月份': all_months})
        summary = pd.merge(summary_all, summary, on='归属月份', how='left').fillna(0)
        summary['支出'] = summary['支出'].round(2)

        standards = {
            '2025-08': ('360元（216元）', ''),
            '2025-09': ('360元（216元）', ''),
            '2025-10': ('432元（259.2元）', '中秋消费提额20％'),
            '2025-11': ('450元（270元）', ''),
            '2025-12': ('450元（270元）', ''),
            '2026-01': ('540元（324元）', '春节消费提额20%'),
            '2026-04': ('540元（324元）', '劳动节消费提额20%')
        }

        result_data = []
        for idx, row in summary.iterrows():
            month_str = row['归属月份']
            amount = row['支出']
            std_str, remark = standards.get(month_str, ('450元(270元)', ''))
            y, m = month_str.split('-')
            formatted_month = f"{y}年{int(m)}月"
            formatted_amount = "0元" if amount == 0 else f"{amount:.2f}".rstrip('0').rstrip('.') + "元"

            result_data.append({
                '序号': idx + 1,
                '月度': formatted_month,
                '分级处遇': '普管级',
                '消费标准（60%）': std_str,
                '本月消费': formatted_amount,
                '备注': remark if remark else ""
            })

        df_res = pd.DataFrame(result_data)
        name_extract = target_name if target_name else (
            file.filename.split("个人")[0] if "个人" in file.filename else "未知姓名")

        # ============ 7. 写入内存流 并进行严谨的像素级排版 ============
        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_res.to_excel(writer, index=False, startrow=2, sheet_name='Sheet1')
            ws = writer.sheets['Sheet1']

            ws.merge_cells('A1:F1')
            ws.row_dimensions[1].height = 36
            cell_a1 = ws['A1']
            cell_a1.value = "罪犯个人消费明细表"
            cell_a1.font = Font(name='方正小标宋简体', size=20)
            cell_a1.alignment = Alignment(horizontal='center', vertical='center')

            ws.merge_cells('A2:F2')
            ws.row_dimensions[2].height = 22
            cell_a2 = ws['A2']
            cell_a2.value = f"罪犯姓名：{name_extract}     编号：{code}"
            cell_a2.font = Font(name='宋体', size=11, bold=True)
            cell_a2.alignment = Alignment(horizontal='left', vertical='center')

            thin = Side(border_style="thin", color="000000")
            last_data_row = 2 + len(df_res) + 1

            for r in range(3, last_data_row + 1):
                for c in range(1, 7):
                    cell = ws.cell(row=r, column=c)
                    cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    if r == 3:
                        cell.font = Font(name='宋体', size=11, bold=True)
                    else:
                        cell.font = Font(name='宋体', size=11)

            bottom_font = Font(name='宋体', size=11)
            date_text_left = "  调取日期：  年  月  日"
            date_text_right = "出具日期：  年  月  日"
            seal_text = "      （部门公章）"

            ws.merge_cells('A42:C42')
            ws['A42'] = "  监区干警签字："
            ws['A42'].alignment = Alignment(horizontal='left', vertical='center')
            ws['A42'].font = bottom_font

            ws.merge_cells('E42:F42')
            ws['E42'] = "监狱生活部门干警签字："
            ws['E42'].alignment = Alignment(horizontal='left', vertical='center')
            ws['E42'].font = bottom_font

            ws['A44'] = date_text_left
            ws['A44'].alignment = Alignment(horizontal='left', vertical='center')
            ws['A44'].font = bottom_font

            ws.merge_cells('E44:F44')
            ws['E44'] = date_text_right
            ws['E44'].alignment = Alignment(horizontal='left', vertical='center')
            ws['E44'].font = bottom_font

            ws.merge_cells('A45:C45')
            ws.merge_cells('D45:F45')
            ws.row_dimensions[45].height = 34
            ws['D45'] = seal_text
            ws['D45'].alignment = Alignment(horizontal='left', vertical='bottom')
            ws['D45'].font = bottom_font

            ws.column_dimensions['A'].width = 6
            ws.column_dimensions['B'].width = 12
            ws.column_dimensions['C'].width = 12
            ws.column_dimensions['D'].width = 18
            ws.column_dimensions['E'].width = 14
            ws.column_dimensions['F'].width = 25

        # 将游标复位
        output_buffer.seek(0)

        # 将文件作为流返回给前端
        filename = f"月消费明细_{name_extract}.xlsx"
        encoded_filename = quote(filename)
        headers = {'Content-Disposition': f"attachment; filename*=utf-8''{encoded_filename}"}

        return StreamingResponse(
            output_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )

    except Exception as e:
        # 🔍 强化后端报错打印，在控制台强制输出红字堆栈
        print("\n" + "=" * 50)
        print("❌ [消费明细生成报错]")
        traceback.print_exc()
        print("=" * 50 + "\n")

        raise HTTPException(status_code=500, detail=f"消费明细处理失败: {str(e)}")