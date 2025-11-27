import re
from typing import List, Dict, Any

# 结构化知识点数据
# 返回：List[Dict]，每个dict包含分层归属、知识点名称、描述

def parse_md_structure(md_path: str) -> List[Dict[str, Any]]:
    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()

    # 从文件名提取卷编号（例如：第二卷.md -> "2"）
    import os
    filename = os.path.basename(md_path)
    volume_match = re.match(r'第([一二三四五六七八九十\d]+)卷', filename)
    
    # 中文数字转阿拉伯数字
    chinese_to_arabic = {
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
        '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'
    }
    
    volume_num = "1"  # 默认值
    volume_name = "未知卷"
    if volume_match:
        vol_str = volume_match.group(1)
        # 如果是中文则转换，否则直接使用（支持阿拉伯数字）
        volume_num = chinese_to_arabic.get(vol_str, vol_str)
        
    # 从第一行提取完整的卷名
    first_line = lines[0].strip() if lines else ""
    volume_name_match = re.match(r'第[一二三四五六七八九十\d]+卷[：:]\s*(.+)', first_line)
    if volume_name_match:
        # 提取卷名，去掉括号中的英文部分
        full_name = volume_name_match.group(1)
        volume_name = re.sub(r'\s*\([^)]+\)\s*', '', full_name).strip()
    
    results = []
    current = {
        "卷编号": volume_num,
        "卷名": volume_name,
        "章编号": None,
        "章名": None,
        "单元编号": None,
        "单元名": None,
        "小节编号": None,
        "小节名": None
    }
    
    # 例如：第1章 物理化学基础
    chapter_pat = re.compile(r'^第(\d+)章(?:\s+(.+))?')
    # 例如：单元 1.1 热力学与状态方程
    unit_pat = re.compile(r'^单元\s*(\d+\.\d+)(?:\s+(.+))?')
    # 例如：1.1.1 基础热力学势
    section_pat = re.compile(r'^(\d+\.\d+\.\d+)(?:\s+(.+))?')
    kp_pat = re.compile(r'^-\s*(.+?)：\s*(.+)')

    for line in lines:
        line = line.strip()
        m_chap = chapter_pat.match(line)
        m_unit = unit_pat.match(line)
        m_sec = section_pat.match(line)
        if m_chap:
            current["章编号"] = m_chap.group(1)
            current["章名"] = m_chap.group(2) if m_chap and m_chap.group(2) else None
            current["单元编号"] = None
            current["单元名"] = None
            current["小节编号"] = None
            current["小节名"] = None
        elif m_unit:
            current["单元编号"] = m_unit.group(1)
            current["单元名"] = m_unit.group(2) if m_unit and m_unit.group(2) else None
            current["小节编号"] = None
            current["小节名"] = None
        elif m_sec:
            current["小节编号"] = m_sec.group(1)
            current["小节名"] = m_sec.group(2) if m_sec and m_sec.group(2) else None
        else:
            kp_match = kp_pat.match(line)
            if kp_match:
                kp_name = kp_match.group(1)
                kp_desc = kp_match.group(2)
                results.append({
                    "卷编号": current["卷编号"],
                    "卷名": current["卷名"],
                    "章编号": current["章编号"],
                    "章名": current["章名"],
                    "单元编号": current["单元编号"],
                    "单元名": current["单元名"],
                    "小节编号": current["小节编号"],
                    "小节名": current["小节名"],
                    "知识点": kp_name,
                    "描述": kp_desc
                })
    return results

if __name__ == "__main__":
    from pprint import pprint
    md_path = "第一卷.md"
    result = parse_md_structure(md_path)
    pprint(result[:5])
    print(f"总计知识点：{len(result)}")
