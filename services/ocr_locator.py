import os
from PIL import Image, ImageDraw
from rapidocr_onnxruntime import RapidOCR


class OCRLocator:
    def __init__(self):
        self.ocr_engine = RapidOCR()

    def extract_with_boxes(self, image_path: str):
        """提取文本及四角坐标雷达"""
        result, _ = self.ocr_engine(image_path)
        full_text = ""
        box_mapping = []

        if result:
            for line in result:
                box, text, score = line
                full_text += text + "\n"
                box_mapping.append({
                    "text": text,
                    "box": box
                })

        return full_text, box_mapping

    def _find_box_by_keyword(self, keyword: str, box_mapping: list):
        """雷达追踪：在图上定位大模型指出的关键词"""
        if not keyword or keyword in ["无", "未提供", "未知"]:
            return None

        for item in box_mapping:
            if keyword in item["text"]:
                return item["box"]
        return None

    def draw_annotations(self, image_path: str, annotations: list, output_path: str):
        """
        全息批注引擎：红圈、黄三角、绿对勾
        annotations 格式: [{"keyword": "履行完毕", "status": "通过"}]
        """
        _, box_mapping = self.extract_with_boxes(image_path)

        with Image.open(image_path) as img:
            draw = ImageDraw.Draw(img)

            for ann in annotations:
                keyword = ann.get("keyword")
                status = ann.get("status", "异常")

                box = self._find_box_by_keyword(keyword, box_mapping)
                if box:
                    # 获取文本框的左上角和右下角坐标
                    top_left = tuple(box[0])
                    bottom_right = tuple(box[2])

                    # 计算文本框的宽和高
                    box_w = bottom_right[0] - top_left[0]
                    box_h = bottom_right[1] - top_left[1]

                    if status in ["异常", "驳回"]:
                        # ❌ 致命错误：画【红圈】 (包裹文字的红色椭圆)
                        expand_x, expand_y = 8, 4  # 稍微扩张一点，不挡住字
                        ellipse_box = [
                            (top_left[0] - expand_x, top_left[1] - expand_y),
                            (bottom_right[0] + expand_x, bottom_right[1] + expand_y)
                        ]
                        draw.ellipse(ellipse_box, outline="#FF0000", width=5)

                    elif status == "疑点":
                        # ⚠️ 逻辑疑点：在文字左侧画【黄三角】 (实心警告牌)
                        tri_size = 12
                        # 三角形的中心点放在文字的左边缘
                        cx = top_left[0] - tri_size - 6
                        cy = top_left[1] + box_h / 2

                        # 计算三角形的三个顶点 (上、左下、右下)
                        p1 = (cx, cy - tri_size)
                        p2 = (cx - tri_size, cy + tri_size)
                        p3 = (cx + tri_size, cy + tri_size)

                        draw.polygon([p1, p2, p3], outline="#FFA500", fill="#FFA500")

                    elif status == "通过":
                        # ✅ 完全正确：在文字右侧打【绿对勾】
                        chk_size = max(6, box_h * 0.3)
                        # 对勾的起点放在文字右边缘偏下一点
                        cx = bottom_right[0] + 10
                        cy = bottom_right[1] - chk_size

                        # 计算对勾的三个折点
                        p1 = (cx, cy)  # 起点 (左中)
                        p2 = (cx + chk_size, cy + chk_size)  # 拐点 (最底)
                        p3 = (cx + chk_size * 2.5, cy - chk_size * 1.5)  # 终点 (右上挑起)

                        # 使用 curve 曲线连接，画出粗壮的绿笔对勾
                        draw.line([p1, p2, p3], fill="#32CD32", width=5, joint="curve")

            img.save(output_path)
            return output_path