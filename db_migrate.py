import sqlite3

DB_PATH = "prison_archive.db"


def promote_json_field_to_column(json_key: str, new_column_name: str):
    """
    将 dynamic_data (JSON) 中的某个键，提取出来成为一个独立的数据库列。
    :param json_key: JSON 字典里的键名，比如 "籍贯"
    :param new_column_name: 新建的固定列名，比如 "native_place"
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print(f"🚀 开始执行字段晋升：将 JSON 中的【{json_key}】提拔为独立列【{new_column_name}】...")

        # 步骤 1：在表结构中新增这一列 (如果列已经存在会报错，我们在 except 里捕获)
        cursor.execute(f"ALTER TABLE criminals_v2 ADD COLUMN {new_column_name} TEXT")
        print(f"✅ 第一步：成功在数据库中新增了固定列 '{new_column_name}'。")

        # 步骤 2：核心魔法！使用 SQLite 原生的 json_extract 函数，
        # 直接把 dynamic_data 里的对应值抠出来，填进新列里！
        # 这里的 '$.籍贯' 是 SQLite 提取 JSON 的标准语法
        sql_update = f"""
            UPDATE criminals_v2 
            SET {new_column_name} = json_extract(dynamic_data, '$.{json_key}')
            WHERE json_extract(dynamic_data, '$.{json_key}') IS NOT NULL
        """
        cursor.execute(sql_update)
        conn.commit()

        # 统计影响了多少行数据
        rows_updated = cursor.rowcount
        print(f"✅ 第二步：数据迁移完成！共将 {rows_updated} 名罪犯的【{json_key}】数据清洗至新列。")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"⚠️ 警告：列名 '{new_column_name}' 已经存在，无需重复添加。")
        else:
            print(f"❌ 数据库操作失败: {e}")
    except Exception as e:
        print(f"❌ 发生未知错误: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    # 【实战演示】：假设我们要把 JSON 里的 "籍贯" 提取出来，变成独立的 native_place 列
    promote_json_field_to_column(json_key="籍贯", new_column_name="native_place")