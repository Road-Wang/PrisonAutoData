import json
from datetime import datetime
from typing import Dict, Any, List
# 引入已有的视觉提取和文本大模型接口
from services.vision_extractor import extract_single_document
from services.dify_client import run_text_llm
# 引入模块2的减刑引擎（用于交叉验证减刑幅度）
from services.screening_engine import ScreeningEngine, CriminalProfile


class ReviewEngine:
    def __init__(self, criminal_name: str, db_manager=None):
        self.criminal_name = criminal_name
        self.db_manager = db_manager  # 预留数据库接口用于拉取原始档案

    def _fetch_archive_data(self) -> Dict[str, Any]:
        """
        [预留接口] 从 Prison_Archives 中提取该罪犯的原始档案结构化数据。
        通常你需要从数据库或本地 JSON 缓存中读取模块1提取的法理数据。
        """
        # 伪代码：这里应返回模块1提取好的起诉书、判决书、奖惩记录等结构化JSON
        return {
            "name": self.criminal_name,
            "crimes": ["故意伤害罪", "寻衅滋事罪"],
            "is_ringleader": True,  # 是否主犯/首要分子
            "is_recidivist": True,  # 是否累犯
            "previous_crimes": "2018年因盗窃被判处有期徒刑一年，2019年5月1日刑满释放。",
            "property_penalties": "罚金两万元，没收个人全部财产",
            "property_execution_status": "终结本次执行程序",
            "rewards": {"表扬": 5, "物质奖励": 2},
            "punishments": {"警告": 0},
            # 此处应包含更多模块1清洗出的字段...
        }

    def _get_expected_reduction(self, archive_data: Dict) -> str:
        """
        调用模块2的代码，获取系统建议的减刑幅度，用于核对监区意见。
        """
        # 注意：你需要根据真实的数据库记录来构造 CriminalProfile
        # 下面为对接示例演示
        try:
            profile = CriminalProfile(
                sentence_type="有期徒刑",
                original_term_months=120,
                crime_count=len(archive_data.get("crimes", [])),
                crime_tags=archive_data.get("crimes", []),
                is_first=True,
                reference_date=datetime(2026, 1, 1),
                reward_count=archive_data.get("rewards", {}).get("表扬", 0),
                punishments=archive_data.get("punishments", {}),
                upgrade_date=None,
                strict_items={"累犯": 1} if archive_data.get("is_recidivist") else {},
                property_unfulfilled=False
            )
            engine = ScreeningEngine(profile)
            result = engine.run_screening()
            return result.get("recommended_reduction", "未知")
        except Exception as e:
            return f"模块2计算异常: {e}"

    def run_review(self, approval_img_paths: List[str], eval_img_paths: List[str]) -> Dict[str, Any]:
        """
        执行完整的审查流
        """
        # 1. 获取系统底层档案（Ground Truth）
        archive_data = self._fetch_archive_data()
        expected_reduction = self._get_expected_reduction(archive_data)

        # 2. OCR 提取上传的审批表和评议表
        # 借用 vision_extractor 的能力将表单转为文本
        approval_texts = []
        for path in approval_img_paths:
            res = extract_single_document(path, "审批表", self.criminal_name, mode="模式一")
            approval_texts.append(str(res))

        eval_texts = []
        for path in eval_img_paths:
            res = extract_single_document(path, "评议表", self.criminal_name, mode="模式一")
            eval_texts.append(str(res))

        # 3. 组装终极审查 Prompt
        # 预留高频易错点扩展空间，可随时在 prompt 中追加规则
        review_prompt = f"""
        你是一个严苛的监狱刑罚执行数据审查专家。
        现在你需要对比【系统原始档案】与刚提交的【审批表】和【评议表】，找出表单填写的错误并给出修改建议。

        【系统原始档案（绝对正确的基础事实）】
        {json.dumps(archive_data, ensure_ascii=False, indent=2)}
        【系统计算出的应减刑幅度】
        {expected_reduction}

        【提交的审批表 OCR 文本】
        {approval_texts}

        【提交的评议表 OCR 文本】
        {eval_texts}

        🚨 必须严格执行以下审查规则（高频易错点）：
        1. **主要犯罪事实**：必须囊括该犯所有罪名！如果档案显示其系“主犯”或“首要分子”，表单中必须出现对应字眼，绝不可遗漏。
        2. **其他犯罪史（前科劣迹）**：必须与档案完全一致。必须写明“刑满释放日期”或附加刑。如果档案标注为“累犯”，此处必须写明该犯系累犯！且审批表与评议表的该栏位内容必须一字不差。
        3. **奖励/处罚核对**：审批表第二页的奖励统计中，绝对不能出现“物质奖励”的数量！请核对表扬等其他奖励次数是否与档案一致。
        4. **减刑幅度意见**：核查监区意见中的减刑幅度，是否与系统计算的【{expected_reduction}】一致。
        5. **历次改判/减刑/加刑情况**：必须逐字核对！极易遗漏“没收个人全部财产”等财产刑变更情况，如发现档案有而表单没有，坚决报错。
        6. **狱级改造积极分子年度**：如果在评议表中出现“XX年度狱级改造积极分子”，这个XX必须是评选获得的**前一年**（例如2025年评上的，必须写为“2024年度”）。
        7. **财产性判项执行情况**：严格区分“履行完毕”、“终结执行”、“终结本次执行程序”，必须与档案原汁原味对照，不可混用。

        请输出严格合法的 JSON，不要输出任何 Markdown 标记，格式如下：
        {{
            "基础信息及犯罪事实": {{"status": "通过/异常", "error": "如有错误写这里", "suggestion": "..."}},
            "前科与劣迹": {{"status": "通过/异常", "error": "...", "suggestion": "..."}},
            "奖励与处分核对": {{"status": "通过/异常", "error": "...", "suggestion": "..."}},
            "历次刑罚变更": {{"status": "通过/异常", "error": "...", "suggestion": "..."}},
            "财产性判项": {{"status": "通过/异常", "error": "...", "suggestion": "..."}},
            "监区减刑幅度": {{"status": "通过/异常", "error": "...", "suggestion": "..."}},
            "综合评价": "对整个卷宗录入质量的总结语"
        }}
        """

        # 4. 调用大模型纯文本能力进行强逻辑比对
        review_result = run_text_llm(review_prompt)
        return review_result