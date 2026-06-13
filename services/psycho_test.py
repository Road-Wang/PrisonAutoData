# -*- coding: utf-8 -*-
import os
import sys
import csv
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime

# ==================== 1. 艾森克 88 题标准计分键与常模 ====================
EPQ_KEY = {
    "P": {
        "是": [26, 30, 34, 46, 50, 66, 68, 75, 76, 81, 85],
        "否": [2, 6, 9, 11, 18, 22, 38, 42, 56, 62, 72, 88]
    },
    "E": {
        "是": [1, 5, 10, 13, 14, 17, 25, 33, 37, 41, 49, 53, 55, 61, 65, 71, 80, 84],
        "否": [21, 29, 45]
    },
    "N": {
        "是": [3, 7, 12, 15, 19, 23, 27, 31, 35, 39, 43, 47, 51, 57, 59, 63, 67, 69, 73, 74, 77, 78, 82, 86],
        "否": []
    },
    "L": {
        "是": [20, 32, 36, 58, 72, 87],
        "否": [4, 8, 16, 24, 28, 40, 44, 48, 52, 54, 60, 64, 70, 79, 83]
    }
}

NORM_DATA = {
    "男": {"P": {"mean": 5.92, "sd": 3.09}, "E": {"mean": 10.74, "sd": 4.31}, "N": {"mean": 10.94, "sd": 4.81},
           "L": {"mean": 12.18, "sd": 3.84}},
    "女": {"P": {"mean": 5.21, "sd": 2.87}, "E": {"mean": 10.14, "sd": 4.14}, "N": {"mean": 11.52, "sd": 4.85},
           "L": {"mean": 12.63, "sd": 3.65}}
}

TEXT_BANK = {
    "P_HIGH": "【风险提示】此人可能是孤独，不关心他人，难以适应外部环境，社会适应不良，常有麻烦，不近人情，甚至出现反社会行为，喜欢寻衅滋扰，也可能是酗酒者。\n\n",
    "N_EXTREME_HIGH": "此人焦虑、紧张、易怒，往往又有抑郁，睡眠不好，患有各种身心障碍。情绪过分，对各种刺激的反映都十分强烈，情绪激发后很难平复下来，因而影响了正常的社会适应，适应环境能力较差，常有偏见，有时让人觉得不可理喻，甚至可能走上危险道路。兼有外向特点时，更容易发火，以致激动、进攻。概括地说，是一个很紧张的人，抱有偏见，容易犯错误。",
    "N_HIGH": "此人情绪不够稳定，焦虑、紧张、易怒，睡眠不好，对各种刺激的反映都十分强烈，情绪激发后很难平复下来，因而影响了正常的社会适应，适应环境能力较差，常有偏见，有时让人觉得不可理喻，甚至可能走上危险道路。",
    "N_HIGH_SHORT": "此人情绪不稳定，可能是焦虑，常常郁郁不乐，忧心忡忡,有强烈的情绪反应，有时会出现不够理智的行为。焦虑、紧张、易怒，往往又有抑郁，睡眠不好，患有各种身心障碍。",
    "N_LOW": "此人情绪反应缓慢且弱、轻微，即使情绪有所波动也能很快平复，恢复平静。通常是稳定的，性情温和，善于自我控制，表现出平静的心态，即使生点气行为也有节制，并且不紧张。",
    "E_HIGH_PURE": "此人爱交际，朋友多，喜参加各种聚会和联谊活动，需要有人同他谈话，不爱一个人阅读和做研究，渴望兴奋的事，喜冒险和向外发展。",
    "E_HIGH_EXTENDED": "此人性格外向，渴望刺激和冒险，较少受外界环境影响和制约，喜参加各种聚会和联谊活动，需要有人同他谈话，不爱一个人阅读和做研究，渴望兴奋的事，喜冒险和向外发展。喜欢干点实际事，与人交往随和、乐观，喜欢谈笑，愿动不愿静，生活中不是一个踏实、细心的人。",
    "MIX_N_LOW_E_LOW": "此人可能性情温和，情绪稳定而成熟，为人处世小心翼翼，着重客观现实，冷寂理智，条理性强，很少患得患失，能前途充满信心，富有安全感。",
    "MIX_E_HIGH_N_LOW": "此人性格外向，爱交际，朋友多，喜参加各种聚会和联谊活动，需要有人同他谈话，不爱一个人阅读和做研究，渴望兴奋的事，喜冒险和向外发展，行为受一时冲动影响。情绪反应缓慢且弱、轻微，即使情绪有所波动也能很快平复，恢复平静。",
    "PURE_NORMAL_MIDDLE": "此人可能情绪比较稳定，性格内外向倾向不明显，属于心理中间型。日常情绪基本稳定，心理耐受力良好，对外界刺激反应适度。在人际交往中表现得随和、好通融，既能享受独处的独立思考，也能较好地融入集体共事。生活中做事较为稳妥、有条理，能保持平静、理智的心态，社会适应能力良好。",
    "PURE_NORMAL_E_HIGH": "此人性格较为外向，开朗健谈，喜欢参与集体活动和与人共事。日常情绪保持在基本稳定的范围内，很少出现情绪的大起大落。生活中愿动不愿静，喜欢谈笑，为人随和乐观，对前途富有信心，喜欢干点实际事，但在处理长周期细腻事务时可能略显不够踏实和细心。",
    "PURE_NORMAL_E_LOW": "此人性格较为内向、沉静，为人处世小心翼翼，着重客观现实，倾向于独立思考和安静的环境。日常情绪基本稳定而温和，很少患得患失，遇事能够保持冷静和冷寂理智。做事条理性较强，富有安全感，在人际交往中较为被动，但社会适应状态良好。"
}


# ==================== 2. GUI 交互式程序架构 ====================
class EPQApplication:
    def __init__(self, root):
        self.root = root
        self.root.title("释放心理测评高频录入系统")
        self.root.geometry("750x630")
        self.root.resizable(False, False)

        self.init_test_data()
        self.create_welcome_frame()

    def init_test_data(self):
        self.current_q = 1
        self.answers = {i: "未答" for i in range(1, 89)}
        self.review_buttons = {}

    def create_welcome_frame(self):
        self.welcome_frame = ttk.Frame(self.root, padding="30")
        self.welcome_frame.pack(expand=True, fill="both")

        ttk.Label(self.welcome_frame, text="艾森克 88 题极速录入工具", font=("微软雅黑", 20, "bold")).pack(pady=15)

        input_frame = ttk.Frame(self.welcome_frame)
        input_frame.pack(pady=15)

        ttk.Label(input_frame, text="受测姓名:", font=("微软雅黑", 12)).grid(row=0, column=0, padx=10, pady=10,
                                                                             sticky="e")
        self.name_entry = ttk.Entry(input_frame, font=("微软雅黑", 12), width=20)
        self.name_entry.grid(row=0, column=1, padx=10, pady=10)
        self.name_entry.focus()

        ttk.Label(input_frame, text="受测性别:", font=("微软雅黑", 12)).grid(row=1, column=0, padx=10, pady=10,
                                                                             sticky="e")
        self.gender_combo = ttk.Combobox(input_frame, values=["男", "女"], font=("微软雅黑", 11), state="readonly",
                                         width=18)
        self.gender_combo.set("男")
        self.gender_combo.grid(row=1, column=1, padx=10, pady=10)

        btn_frame = ttk.Frame(self.welcome_frame)
        btn_frame.pack(pady=15)

        btn_start = ttk.Button(btn_frame, text="开始全新录入 (Enter)", command=self.start_testing, width=25)
        btn_start.pack(pady=5)

        btn_import = ttk.Button(btn_frame, text="📥 导入历史元数据一键生成", command=self.import_history_metadata,
                                width=25)
        btn_import.pack(pady=5)

        # ====== 【核心新功能】：优雅地在首页底部挂载版本迭代与说明信息 ======
        version_frame = ttk.LabelFrame(self.welcome_frame, text=" 系统版本与日志说明 ")
        version_frame.pack(side="bottom", fill="x", pady=(20, 0), ipady=5, ipadx=10)

        v02_text = "当前版本：快速心理测试版本V0.2  |  更新时间：2026.6.12\n更新内容：增加简易使用说明，优化操作体验，优化部分输出结果"
        ttk.Label(version_frame, text=v02_text, font=("微软雅黑", 9), foreground="#333333", justify="left").pack(
            anchor="w", pady=3, padx=10)

        v01_text = "历史版本：快速心理测试版本V0.1  |  更新时间：2026.6.10\n历史用途：用于出监心理测试20快速输出结果"
        ttk.Label(version_frame, text=v01_text, font=("微软雅黑", 9), foreground="#777777", justify="left").pack(
            anchor="w", pady=3, padx=10)

        self.root.bind("<Return>", lambda event: self.start_testing())

    def start_testing(self):
        self.username = self.name_entry.get().strip()
        self.gender = self.gender_combo.get()
        if not self.username:
            messagebox.showwarning("提示", "请输入受测人员姓名！")
            return

        self.welcome_frame.destroy()
        self.create_testing_frame()

    def import_history_metadata(self):
        self.username = self.name_entry.get().strip()
        self.gender = self.gender_combo.get()
        if not self.username:
            messagebox.showwarning("提示", "请先在上方输入受测人员姓名！")
            return

        metadata_str = simpledialog.askstring("导入历史元数据", f"请输入【{self.username}】的88位答题元数据:")
        if not metadata_str: return

        metadata_str = metadata_str.strip()
        if len(metadata_str) != 88 or not all(ch in ["是", "否"] for ch in metadata_str):
            messagebox.showerror("错误", "元数据不合法！必须是精确的88位字符。")
            return

        self.answers = {i: metadata_str[i - 1] for i in range(1, 89)}
        self.welcome_frame.destroy()
        self.generate_and_save_final_report(from_import=True)

    def create_testing_frame(self):
        self.test_frame = ttk.Frame(self.root, padding="30")
        self.test_frame.pack(expand=True, fill="both")

        tip_text = "操作说明：按 1 键选择是，2 键选择否，← 键后退，按 Enter 展示整体作答状况"
        ttk.Label(self.test_frame, text=tip_text, font=("微软雅黑", 11, "bold"), foreground="#D83B01").pack(anchor="w",
                                                                                                            pady=(0,
                                                                                                                  10))

        self.q_label = ttk.Label(self.test_frame, text=f"第 {self.current_q} / 88 题", font=("微软雅黑", 36, "bold"))
        self.q_label.pack(pady=80)

        self.status_label = ttk.Label(self.test_frame, text="等待输入...", font=("微软雅黑", 14), foreground="#0078D7")
        self.status_label.pack(pady=20)

        self.root.bind("1", lambda e: self.save_answer("是"))
        self.root.bind("2", lambda e: self.save_answer("否"))
        self.root.bind("<Left>", lambda e: self.go_back())
        self.root.bind("<Return>", lambda e: self.skip_to_review_frame())

        self.refresh_q_ui()

    def save_answer(self, value):
        if self.current_q <= 88:
            self.answers[self.current_q] = value
            if self.current_q < 88:
                self.current_q += 1
                self.refresh_q_ui()
            else:
                self.q_label.config(text="全部题目已答完！")
                self.status_label.config(text="请按 Enter 键展示全部选项进行核对", foreground="green")

    def go_back(self):
        if self.current_q > 1:
            self.current_q -= 1
            self.refresh_q_ui()

    def refresh_q_ui(self):
        self.q_label.config(text=f"第 {self.current_q} / 88 题")
        prev_ans = self.answers[self.current_q]
        self.status_label.config(text=f"当前选择：{prev_ans}", foreground="#0078D7" if prev_ans != "未答" else "gray")

    def skip_to_review_frame(self):
        self.test_frame.destroy()
        self.create_review_frame()

    def create_review_frame(self):
        self.review_frame = ttk.Frame(self.root, padding="15")
        self.review_frame.pack(expand=True, fill="both")

        ttk.Label(self.review_frame, text="整体作答状况（红色块为未答，鼠标点击任意项可直接补全/修改，确认无误按 Enter）",
                  font=("微软雅黑", 11, "bold"), foreground="#D83B01").pack(pady=5)

        grid_frame = ttk.Frame(self.review_frame)
        grid_frame.pack(pady=10, fill="both", expand=True)

        for i in range(1, 89):
            row = (i - 1) // 8
            col = (i - 1) % 8
            val = self.answers[i]

            if val == "是":
                bg_color = "#CCE4F7"
            elif val == "否":
                bg_color = "#E1DFDD"
            else:
                bg_color = "#FFD2D2"

            btn = tk.Button(grid_frame, text=f"{i:02d}:{val}", font=("Consolas", 10), width=8,
                            bg=bg_color, relief="groove",
                            command=lambda q_num=i: self.toggle_review_answer(q_num))
            btn.grid(row=row, column=col, padx=2, pady=2)
            self.review_buttons[i] = btn

        self.root.bind("<Return>", lambda e: self.generate_and_save_final_report(from_import=False))

    def toggle_review_answer(self, q_num):
        current_val = self.answers[q_num]
        new_val = "否" if current_val == "是" else "是"
        self.answers[q_num] = new_val
        bg_color = "#CCE4F7" if new_val == "是" else "#E1DFDD"
        self.review_buttons[q_num].config(text=f"{q_num:02d}:{new_val}", bg=bg_color)

    def generate_and_save_final_report(self, from_import=False):
        if "未答" in self.answers.values():
            unanswered = [k for k, v in self.answers.items() if v == "未答"]
            messagebox.showinfo("提示",
                                f"检测到仍有 {len(unanswered)} 道题未作答！\n系统将自动返回答题界面，优先补全第 {unanswered[0]} 题。")
            if hasattr(self, 'review_frame'): self.review_frame.destroy()
            self.current_q = unanswered[0]
            self.create_testing_frame()
            return

        raw_scores = {"P": 0, "E": 0, "N": 0, "L": 0}
        for dimension, rules in EPQ_KEY.items():
            for q_num in rules["是"]:
                if self.answers.get(q_num) == "是": raw_scores[dimension] += 1
            for q_num in rules["否"]:
                if self.answers.get(q_num) == "否": raw_scores[dimension] += 1

        t_scores = {}
        norms = NORM_DATA[self.gender]
        for dim, score in raw_scores.items():
            t_scores[dim] = 50 + 10 * ((score - norms[dim]["mean"]) / norms[dim]["sd"])

        e_t, n_t, p_t = t_scores["E"], t_scores["N"], t_scores["P"]

        report_text = ""
        if p_t >= 65.0: report_text += TEXT_BANK["P_HIGH"]

        if n_t >= 66.5:
            report_text += TEXT_BANK["N_EXTREME_HIGH"]
        elif 55.0 <= n_t < 66.5:
            report_text += TEXT_BANK["N_HIGH_SHORT"] if e_t < 50 else TEXT_BANK["N_HIGH"]
        elif e_t <= 43.3 and n_t <= 43.3:
            report_text += TEXT_BANK["MIX_N_LOW_E_LOW"]
        elif e_t >= 61.5 and n_t <= 40.0:
            report_text += TEXT_BANK["MIX_E_HIGH_N_LOW"]
        elif e_t >= 62.0:
            report_text += TEXT_BANK["E_HIGH_EXTENDED"]
        elif 55.0 <= e_t < 62.0:
            report_text += TEXT_BANK["E_HIGH_PURE"]
        elif n_t <= 38.5:
            report_text += TEXT_BANK["N_LOW"]
        elif e_t >= 55.0:
            report_text += TEXT_BANK["PURE_NORMAL_E_HIGH"]
        elif e_t <= 43.3:
            report_text += TEXT_BANK["PURE_NORMAL_E_LOW"]
        else:
            report_text += TEXT_BANK["PURE_NORMAL_MIDDLE"]

        metadata_str = "".join([self.answers[i] for i in range(1, 89)])

        if getattr(sys, 'frozen', False):
            current_dir = os.path.dirname(sys.executable)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))

        filename = os.path.join(current_dir, "测试结果本地备份.csv")
        file_exists = os.path.exists(filename)

        with open(filename, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["姓名", "性别", "测试时间", "P_T分", "E_T分", "N_T分", "性格总述", "答题元数据"])
            writer.writerow(
                [self.username, self.gender, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{p_t:.1f}", f"{e_t:.1f}",
                 f"{n_t:.1f}", report_text.replace('\n', ' '), metadata_str])

        self.root.unbind("1")
        self.root.unbind("2")
        self.root.unbind("<Left>")
        self.root.unbind("<Return>")
        if not from_import and hasattr(self, 'review_frame'): self.review_frame.destroy()

        self.create_result_frame(report_text)

    def create_result_frame(self, report_text):
        self.result_frame = ttk.Frame(self.root, padding="30")
        self.result_frame.pack(expand=True, fill="both")

        ttk.Label(self.result_frame, text="🎉 测评分析报告生成成功", font=("微软雅黑", 16, "bold"),
                  foreground="green").pack(pady=10)

        btn_frame = ttk.Frame(self.result_frame)
        btn_frame.pack(side="bottom", pady=10)

        def copy_text():
            self.root.clipboard_clear()
            self.root.clipboard_append(report_text)
            messagebox.showinfo("提示", "结果已成功复制到剪贴板！")

        ttk.Button(btn_frame, text="📋 一键复制结果", command=copy_text).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="🔄 返回重新录入", command=self.reset_and_go_home).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="退出程序", command=self.root.quit).pack(side="left", padx=10)

        text_area = tk.Text(self.result_frame, font=("微软雅黑", 11), wrap="word", bg="#F3F2F1", relief="flat", padx=15,
                            pady=15)
        text_area.insert("1.0", f"【性格总述结果】\n\n{report_text}")
        text_area.config(state="disabled")
        text_area.pack(fill="both", expand=True, pady=10)

    def reset_and_go_home(self):
        self.result_frame.destroy()
        self.init_test_data()
        self.create_welcome_frame()


if __name__ == "__main__":
    root = tk.Tk()
    app = EPQApplication(root)
    root.mainloop()