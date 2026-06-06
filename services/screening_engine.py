from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
from dateutil.relativedelta import relativedelta


class CriminalProfile(BaseModel):
    sentence_type: str
    original_term_months: int
    crime_count: int
    crime_tags: List[str]
    is_first: bool
    reference_date: datetime
    reward_count: int
    punishments: Dict[str, int]
    upgrade_date: Optional[datetime]
    strict_items: Dict[str, int]
    property_unfulfilled: bool


class ScreeningEngine:
    def __init__(self, profile: CriminalProfile):
        self.p = profile
        self.req_interval_months = 0
        self.req_rewards = 0
        self.probation_months = 0
        self.target_sentence = ""
        self.reasoning = []
        self.penalty_details = []
        self.final_eligible_date = None

    def _get_display_sentence_type(self) -> str:
        """智能化转换文书专用的基础刑种描述"""
        if self.p.sentence_type == "有期徒刑":
            if self.p.original_term_months >= 120:
                return "十年以上有期徒刑"
            elif self.p.original_term_months > 60:
                return "五年以上十年以下有期徒刑"
            else:
                return "五年以下有期徒刑"
        return self.p.sentence_type

    def run_screening(self) -> dict:
        if self.p.sentence_type == "死缓终身监禁":
            return {"is_qualified": False, "legal_reasoning": "死缓终身监禁不得再减刑或者假释。",
                    "recommended_reduction": "不予呈报"}

        # 1. 确定基础门槛
        self._determine_base_thresholds()

        original_base_interval = self.req_interval_months
        self.req_interval_months += self.probation_months

        # 2. 计算处分推迟期
        punishment_delay = (self.p.punishments.get("警告", 0) * 6 +
                            self.p.punishments.get("记过", 0) * 9 +
                            self.p.punishments.get("禁闭", 0) * 12)
        if self.p.punishments.get("私藏违禁品", 0) > 0:
            punishment_delay += 36
            self.reasoning.append("【步骤7】因私藏违禁品，法定间隔期额外延长 3 年 (36个月)。")
            self.penalty_details.append("因私藏违禁品推迟36个月")

        if punishment_delay > 0:
            self.penalty_details.append(f"处分推迟间隔{punishment_delay}个月")

        # 3. 基础时间轴推演
        base_eligible_date = self.p.reference_date + relativedelta(months=self.req_interval_months)

        # 4. 时间轴对撞
        if punishment_delay > 0:
            if not self.p.upgrade_date:
                return {"is_qualified": False, "legal_reasoning": "存在处分记录，但未录入恢复考察级的日期。",
                        "recommended_reduction": "参数不全"}
            punishment_eligible_date = self.p.upgrade_date + relativedelta(months=punishment_delay)
            self.final_eligible_date = max(base_eligible_date, punishment_eligible_date)
            self.reasoning.append(
                f"【时间轴对撞】基础日:{base_eligible_date.strftime('%Y-%m-%d')} vs 受限日:{punishment_eligible_date.strftime('%Y-%m-%d')}")
        else:
            self.final_eligible_date = base_eligible_date
            self.reasoning.append(f"【时间轴】无处分，暂时达标日为: {self.final_eligible_date.strftime('%Y-%m-%d')}")

        # 5. 最后动作：财产刑未履行平移 3 个月
        if self.p.property_unfulfilled:
            self.final_eligible_date += relativedelta(months=3)
            self.reasoning.append(
                f"【步骤10】财产刑未履行，最终达标日期硬性推迟 3 个月至: {self.final_eligible_date.strftime('%Y-%m-%d')}")
            self.penalty_details.append("财产未履行推迟间隔3个月")

        # 校验
        if datetime.now() < self.final_eligible_date:
            return {"is_qualified": False, "legal_reasoning": "\n".join(
                self.reasoning) + f"\n❌ 时间限制：法定最早呈报日期 {self.final_eligible_date.strftime('%Y-%m-%d')}，当前未到期。",
                    "recommended_reduction": "暂不符合条件"}

        if self.p.reward_count < self.req_rewards:
            return {"is_qualified": False, "legal_reasoning": "\n".join(
                self.reasoning) + f"\n❌ 奖励件限制：需 {self.req_rewards} 件，当前仅 {self.p.reward_count} 件。",
                    "recommended_reduction": "暂不符合条件"}

        self.reasoning.append("✅ 准入达标：已满足全部时间底线与奖励件要求。")

        # 6. 计算最终文书格式
        reduction_str = self._calculate_reduction_amount()
        stage_str = "首次减刑" if self.p.is_first else "再次减刑"
        display_sentence = self._get_display_sentence_type()

        def format_months(m_count):
            y, m = divmod(m_count, 12)
            s_y = f"{y}年" if y > 0 else ""
            s_m = f"{m}个月" if m > 0 else ""
            return (s_y + s_m) if (s_y + s_m) else "0个月"

        base_interval_str = format_months(original_base_interval)
        total_interval_str = format_months(self.req_interval_months)

        interval_display = f"{base_interval_str}+延迟{self.probation_months}个月（实际{total_interval_str}）"
        penalty_summary = "，".join(self.penalty_details) if self.penalty_details else "无附加推迟或扣减"
        date_str = self.final_eligible_date.strftime("%Y年%m月%d日")

        final_recommendation = (
            f"该犯自{date_str}起符合条件，共{self.p.reward_count}个奖励件（基本条件为{display_sentence}，"
            f"{stage_str}，间隔期{interval_display}，要求奖励件{self.req_rewards}个，"
            f"因涉及从严项，{penalty_summary}），建议{reduction_str}。"
        )

        return {"is_qualified": True, "legal_reasoning": "\n".join(self.reasoning),
                "recommended_reduction": final_recommendation}

    def _determine_base_thresholds(self):
        term, is_first = self.p.original_term_months, self.p.is_first
        tags = self.p.crime_tags + list(self.p.strict_items.keys())
        if self.p.property_unfulfilled: tags.append("财产未履行")

        if self.p.crime_count >= 2:
            if self.p.sentence_type == "无期徒刑":
                tags.append("数罪并罚无期")
            elif self.p.sentence_type == "有期徒刑" and term >= 120:
                tags.append("数罪并罚十年以上")

        is_corruption, is_new_crime = "贪污贿赂国家工作人员" in tags, "执行期间又犯罪(有期)" in tags

        strict_group = any(t in tags for t in
                           ["职务犯罪", "破坏金融", "涉黑", "危害国家安全", "恐怖活动", "毒品首要分子", "毒品再犯",
                            "累犯", "主犯", "前科", "限制减刑"])
        violent_group = any(t in tags for t in
                            ["故意杀人", "强奸", "抢劫", "绑架", "放火", "爆炸", "投放危险物质", "有组织的暴力性犯罪",
                             "数罪并罚十年以上", "数罪并罚无期"])

        if self.p.sentence_type == "有期徒刑":
            self.probation_months = 1
            if is_new_crime:
                self.req_interval_months, self.req_rewards = 36, 7
                self.reasoning.append("【步骤1-4】适用：执行期间又犯罪(新罪有期)")
            elif is_corruption:
                self.req_interval_months, self.req_rewards = (24, 4) if is_first else (18, 3) if term < 120 else (36,
                                                                                                                  6) if is_first else (
                    24, 4)
                self.reasoning.append("【步骤1-4】适用：贪污贿赂罪国家工作人员")
            elif strict_group or (violent_group and term >= 120):
                triggered_tags = [t for t in tags if
                                  t in ["职务犯罪", "破坏金融", "涉黑", "危害国家安全", "恐怖活动", "毒品首要分子",
                                        "毒品再犯", "累犯", "主犯", "前科", "限制减刑", "故意杀人", "强奸", "抢劫",
                                        "绑架", "放火", "爆炸", "投放危险物质", "有组织的暴力性犯罪",
                                        "数罪并罚十年以上"]]
                tag_desc = "/".join(triggered_tags[:2]) + "等" if triggered_tags else ""

                self.req_interval_months, self.req_rewards = (24, 4) if is_first else (12, 2) if term < 120 else (24,
                                                                                                                  4) if is_first else (
                    18, 3)
                self.reasoning.append(
                    f"【步骤1-4】适用：{self._get_display_sentence_type()} (因包含[{tag_desc}]触发特定要求)")
            else:
                self.req_interval_months, self.req_rewards = (12, 2) if term <= 60 else (18, 3) if term <= 120 else (24,
                                                                                                                     4) if is_first else (
                    18, 3)
                self.reasoning.append(f"【步骤1-4】适用：{self._get_display_sentence_type()} (普管)")

        elif self.p.sentence_type == "无期徒刑":
            self.probation_months = 2
            if not is_first:
                self.req_interval_months, self.req_rewards = 24, 4
                self.reasoning.append("【步骤1-4】适用：无期改有期后，再次减刑。")
            else:
                if strict_group or violent_group:
                    self.req_interval_months, self.req_rewards = 36, 6
                    self.target_sentence = "建议减为有期徒刑22年，剥权10年"
                    self.reasoning.append("【步骤1-4】适用：无期首次减刑 (因触发从严/暴力项提高门槛)")
                else:
                    self.req_interval_months, self.req_rewards = 24, 4
                    self.target_sentence = "建议减为有期徒刑22年，剥权9年"
                    self.reasoning.append("【步骤1-4】适用：无期首次减刑 (普管)")

                # 🌟 修复点1：仅在首次减刑（无期减有期）时增加奖励件，再次减刑不加件！
                if "危害公共安全" in tags or self.p.property_unfulfilled:
                    self.req_rewards += 1
                    self.reasoning.append("【附加】无期减有期，特殊项要求奖励件增加 1 个。")
                    self.penalty_details.append("首次减为有期额外增加1个奖励件")

        elif self.p.sentence_type in ["死缓", "死缓限制减刑"]:
            self.probation_months = 2
            if not is_first:
                self.req_interval_months, self.req_rewards = 24, 4
                self.reasoning.append("【步骤1-4】适用：死缓改无期后，再次减刑 (减为有期徒刑后再减刑)。")
            else:
                self.req_interval_months, self.req_rewards = (60, 10) if self.p.sentence_type == "死缓限制减刑" else (
                    36, 6)
                self.target_sentence = "建议减为有期徒刑25年，剥权10年"
                self.reasoning.append("【步骤1-4】适用：死缓改无期后，首次减为有期徒刑。")

    def _calculate_reduction_amount(self) -> str:
        # 🌟 修复点2：加上 and self.p.is_first，确保再次减刑能够滑入下方测算逻辑，而不再返回空句
        if self.p.sentence_type in ["无期徒刑", "死缓", "死缓限制减刑"] and self.p.is_first:
            return self.target_sentence

        base_reduction = 9
        if "贪污贿赂国家工作人员" in self.p.crime_tags or self.p.sentence_type == "死缓限制减刑":
            base_reduction = 6
            self.reasoning.append("【步骤9】触发贪贿或死缓限制减刑，起算顶格幅度降为 6 个月。")
        elif any(t in self.p.crime_tags for t in ["职务犯罪", "破坏金融", "涉黑", "涉恶"]):
            base_reduction = 6
            self.reasoning.append("【步骤9】触发三涉/涉恶，起算顶格幅度降为 6 个月。")

        strict_weight = 0
        for tag, count in self.p.strict_items.items():
            if tag in ["累犯", "假释期间又犯罪", "服刑期间犯罪", "缓刑期间犯罪"]:
                strict_weight += 2 * count
                self.reasoning.append(f"【步骤9】触发双倍从严项【{tag}】x{count}，计为 {2 * count} 个权重。")
            else:
                strict_weight += 1 * count
                self.reasoning.append(f"【步骤9】触发常规从严项【{tag}】x{count}，计为 {count} 个权重。")

        if sum(self.p.punishments.values()) > 0 and strict_weight == 0 and not self.p.property_unfulfilled:
            strict_weight = 1
            self.reasoning.append("【步骤9】有处分但无其他从严项，计为 1 个权重。")

        deduction = 0
        if strict_weight == 1:
            deduction = 1
        elif strict_weight == 2:
            deduction = 3
        elif strict_weight == 3:
            deduction = 4
        elif strict_weight == 4:
            deduction = 5
        elif strict_weight >= 5:
            deduction = 6

        if deduction > 0:
            self.penalty_details.append(f"从严项累计扣减幅度{deduction}个月")

        final_reduction = base_reduction - deduction

        if strict_weight >= 2 and final_reduction > 6:
            final_reduction = 6
            self.reasoning.append("【修正】具有2种以上从严情景，硬性封顶最高呈报 6 个月。")

        final_reduction = max(3, final_reduction)

        if self.p.property_unfulfilled:
            final_reduction = max(2, final_reduction - 1)
            self.penalty_details.append("财产未履行额外扣减幅度1个月")

        if final_reduction == 9: final_reduction = 8
        return f"减去有期徒刑{final_reduction}个月"