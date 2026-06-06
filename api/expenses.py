import os
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from openpyxl.styles import Font, Alignment, Border, Side

# 创建一个路由器实例，取代原来 app 的位置
router = APIRouter()

# 注意这里：新增了 code 参数，使用 Form(...) 接收文本
@router.post("/generate_excel", summary="生成月消费明细表")
async def generate_excel(
        file: UploadFile = File(...),
        code: str = Form(...)
):
    base_dir = r"D:\减刑文书自动化"
    input_dir = os.path.join(base_dir, "原始账单输入")
    output_dir = os.path.join(base_dir, "最终表格输出")
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    input_path = os.path.join(input_dir, file.filename)
    with open(input_path, "wb") as f:
        f.write(await file.read())

    output_filename = file.filename.replace("个人账务明细表", "月消费明细")
    if not output_filename.endswith('.xlsx'):
        output_filename += '.xlsx'
    output_path = os.path.join(output_dir, output_filename)

    try:
        # 1. 读取原始数据
        df_raw = pd.read_excel(input_path, header=1)
        df_raw['时间'] = pd.to_datetime(df_raw['时间'])
        df_raw['支出'] = pd.to_numeric(df_raw['支出'], errors='coerce').fillna(0)

        # 【终极修复：强制时间轴】
        # 获取账单中最新的一个月作为结束点。如果账单全是空的，就默认用到当前真实月份
        if df_raw.empty or pd.isna(df_raw['时间'].max()):
            end_month = pd.Timestamp.now().strftime('%Y-%m')
        else:
            end_month = df_raw['时间'].max().strftime('%Y-%m')

        # 使用 pandas 的 period_range 强行拉出一条从 '2025-08' 到结束月份的绝对连续列表
        # 哪怕中间几个月在 Excel 里根本不存在，这条时间轴也会把它们全补齐
        all_months = pd.period_range(start='2025-08', end=end_month, freq='M').astype(str).tolist()

        # 2. 过滤数据（只保留超市购物）
        df = df_raw[df_raw['款项类型'].str.contains('超市|购物', na=False, regex=True)].copy()
        df = df.sort_values('时间').reset_index(drop=True)

        df['原始月份'] = df['时间'].dt.strftime('%Y-%m')
        df['归属月份'] = df['原始月份']

        # 3. 跨月平摊逻辑
        # 这里必须用我们强制生成的 all_months 来遍历，确保没有月份断档
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

        # 4. 汇总求和
        summary = df.groupby('归属月份')['支出'].sum().reset_index()

        # 【关键合成】：用强制生成的全量日历底表，去和求和结果拼接。没有数据的月份全部填 0
        summary_all = pd.DataFrame({'归属月份': all_months})
        summary = pd.merge(summary_all, summary, on='归属月份', how='left').fillna(0)
        summary['支出'] = summary['支出'].round(2)

        # 5. 处遇配置表
        standards = {
            '2025-08': ('360元（216元）', ''),
            '2025-09': ('360元（216元）', ''),
            '2025-10': ('432元（259.2元）', '中秋消费提额20％'),
            '2025-11': ('450元（270元）', ''),
            '2025-12': ('450元（270元）', ''),
            '2026-01': ('540元（324元）', '春节消费提额20%'),  # 修改了1月份备注
            '2026-04': ('540元（324元）', '劳动节消费提额20%')  # 新增了4月份标准和备注
        }

        # 6. 整理数据并格式化月份
        result_data = []
        for idx, row in summary.iterrows():
            month_str = row['归属月份']
            amount = row['支出']
            std_str, remark = standards.get(month_str, ('450元(270元)', ''))

            y, m = month_str.split('-')
            formatted_month = f"{y}年{int(m)}月"

            # 【关键变动3】：如果金额为0，直接显示 "0元"
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
        name_extract = file.filename.split("个人")[0] if "个人" in file.filename else "未知姓名"

        # ============ 7. 写入 Excel 并进行严谨的像素级排版 ============
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df_res.to_excel(writer, index=False, startrow=2, sheet_name='Sheet1')
            ws = writer.sheets['Sheet1']

            # ================= 1. 顶部大表头 (第 1 行) =================
            ws.merge_cells('A1:F1')
            ws.row_dimensions[1].height = 36
            cell_a1 = ws['A1']
            cell_a1.value = "罪犯个人消费明细表"
            cell_a1.font = Font(name='方正小标宋简体', size=20)
            cell_a1.alignment = Alignment(horizontal='center', vertical='center')

            # ================= 2. 姓名及编号信息 (第 2 行) =================
            ws.merge_cells('A2:F2')
            # 【变动点2】：第 2 行行高设置为 22
            ws.row_dimensions[2].height = 22
            cell_a2 = ws['A2']
            # 【变动点3】：删除了11个空格，让“编号：”向左移动了11个字符的距离
            cell_a2.value = f"罪犯姓名：{name_extract}     编号：{code}"
            cell_a2.font = Font(name='宋体', size=11, bold=True)
            cell_a2.alignment = Alignment(horizontal='left', vertical='center')

            # ================= 3. 数据表格全外边框和内边框 =================
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

            # ================= 4. 固定签字与公章区域 (第 42-45 行) =================
            bottom_font = Font(name='宋体', size=11)

            # 【变动点4】：前面加了2个“全角空格(　)”，精准实现向右缩进2个中文字符
            date_text_left = "　　调取日期：　　年　　月　　日"
            date_text_right = "出具日期：　　年　　月　　日"
            seal_text = "　　　　　　（部门公章）"

            # ---- 第 42 行 ----
            ws.merge_cells('A42:C42')
            # 【变动点4】：前面加了2个全角空格
            ws['A42'] = "　　监区干警签字："
            ws['A42'].alignment = Alignment(horizontal='left', vertical='center')
            ws['A42'].font = bottom_font

            ws.merge_cells('E42:F42')
            ws['E42'] = "监狱生活部门干警签字："
            ws['E42'].alignment = Alignment(horizontal='left', vertical='center')
            ws['E42'].font = bottom_font

            # ---- 第 44 行 ----
            ws['A44'] = date_text_left
            ws['A44'].alignment = Alignment(horizontal='left', vertical='center')
            ws['A44'].font = bottom_font

            ws.merge_cells('E44:F44')
            ws['E44'] = date_text_right
            ws['E44'].alignment = Alignment(horizontal='left', vertical='center')
            ws['E44'].font = bottom_font

            # ---- 第 45 行 ----
            ws.merge_cells('A45:C45')
            ws.merge_cells('D45:F45')
            ws.row_dimensions[45].height = 34
            ws['D45'] = seal_text
            ws['D45'].alignment = Alignment(horizontal='left', vertical='bottom')
            ws['D45'].font = bottom_font

            # ================= 5. 列宽微调 =================
            ws.column_dimensions['A'].width = 6
            ws.column_dimensions['B'].width = 12
            ws.column_dimensions['C'].width = 12
            ws.column_dimensions['D'].width = 18
            ws.column_dimensions['E'].width = 14
            ws.column_dimensions['F'].width = 25

    except Exception as e:
        return {"status": "error", "message": f"处理失败，原因: {str(e)}"}

    return {
        "status": "success",
        "message": f"计算成功！请前往文件夹查看：{output_path}",
        "file_path": output_path
    }