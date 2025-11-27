#!/usr/bin/env python3
"""
count_knowledge_points.py

统计 Markdown 文档中以 '-' 开头并且一直到第一个冒号为止的“知识点”。

用法示例:
  python count_knowledge_points.py -d . -p "第*卷*.md" --list

--
输出结果包含每个文件的知识点数量与可选的详细知识点列表。
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple


KNOWLEDGE_RE = re.compile(r"^\s*-\s*(.+?)(?::|：)")
CHAPTER_RE = re.compile(r"^\s*第\s*([0-9]+|[一二三四五六七八九十百千]+)\s*章")
UNIT_RE = re.compile(r"^\s*单元\s*([0-9]+(?:\.[0-9]+)+)\s*[:：]?")
SUBSECTION_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)+)\s+.+")


def extract_from_text(text: str) -> List[str]:
    """从文本中提取符合知识点定义的名称（不包含后面的冒号）。"""
    items: List[str] = []
    for line in text.splitlines():
        m = KNOWLEDGE_RE.match(line)
        if m:
            items.append(m.group(1).strip())
    return items


CHINESE_NUMERAL = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    '十': 10, '百': 100, '千': 1000
}


def chinese_to_int(s: str) -> int:
    # simplistic mapping for '一'..'十'..'百' cases; not robust for complex numerals
    total = 0
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    # handle simple patterns like 一、二、三十、二十一 not fully implemented
    cur = 0
    i = 0
    for ch in s:
        val = CHINESE_NUMERAL.get(ch)
        if val is None:
            continue
        if val >= 10:
            if cur == 0:
                cur = 1
            cur *= val
            total += cur
            cur = 0
        else:
            cur += val
    total += cur
    return total


def build_fs_index(root: Path):
    """Walk the root and build useful indices to support fast queries.

    Returns a dict with:
      - dirs: list of directory paths
      - dir_by_name: mapping name -> list of Path
      - child_dirs_map: mapping Path -> list of child dir names
      - files_map: mapping Path -> list of filenames (immediate)
      - gen_count_subtree/solver_count_subtree/verify_count_subtree (dicts mapping Path -> int)
      - verify_cross_self: mapping Path -> bool
    """
    dirs = []
    dir_by_name = {}
    child_dirs_map = {}
    files_map = {}
    file_count_self = {}
    verify_cross_self = {}
    # Walk filesystem once
    for dirpath, dirnames, filenames in os.walk(root):
        dpath = Path(dirpath)
        dirs.append(dpath)
        files_map[dpath] = list(filenames)
        child_dirs_map[dpath] = list(dirnames)
        name = dpath.name
        dir_by_name.setdefault(name, []).append(dpath)
        # file count self
        file_count_self[dpath] = {
            'gen': sum(1 for fn in filenames if fn == 'generator_output.json'),
            'solver': sum(1 for fn in filenames if fn == 'solver_output-1.json'),
        }
        # parse log.json if present to determine whether has cross_check_status
        verify_cross = False
        if 'log.json' in filenames:
            try:
                j = json.loads((dpath / 'log.json').read_text(encoding='utf-8'))
            except Exception:
                try:
                    j = json.loads((dpath / 'log.json').read_text(encoding='gbk', errors='ignore'))
                except Exception:
                    j = None
            if isinstance(j, dict) and 'verify_status' in j and isinstance(j['verify_status'], list):
                for entry in j['verify_status']:
                    if isinstance(entry, dict) and 'cross_check_status' in entry:
                        verify_cross = True
                        break
        verify_cross_self[dpath] = verify_cross

    # compute subtree counts by processing directories sorted by descending depth
    dirs_sorted = sorted(dirs, key=lambda p: len(p.parts), reverse=True)
    gen_count_subtree = {d: file_count_self.get(d, {}).get('gen', 0) for d in dirs}
    solver_count_subtree = {d: file_count_self.get(d, {}).get('solver', 0) for d in dirs}
    verify_count_subtree = {d: 1 if verify_cross_self.get(d, False) else 0 for d in dirs}
    for d in dirs_sorted:
        # add children's subtree counts
        for child_name in child_dirs_map.get(d, []):
            child = d / child_name
            if child in gen_count_subtree:
                gen_count_subtree[d] += gen_count_subtree[child]
                solver_count_subtree[d] += solver_count_subtree[child]
                verify_count_subtree[d] += verify_count_subtree[child]

    return {
        'dirs': dirs,
        'dir_by_name': dir_by_name,
        'child_dirs_map': child_dirs_map,
        'files_map': files_map,
        'gen_count_subtree': gen_count_subtree,
        'solver_count_subtree': solver_count_subtree,
        'verify_count_subtree': verify_count_subtree,
        'verify_cross_self': verify_cross_self,
    }


def find_matching_dir(root: Path, vol: str, chap: str, unit: str, sub: str, item: str, index=None) -> Path | None:
    """Try to find the corresponding directory on disk for the given path components.
    The primary attempt is an exact path: root/vol/chap/unit/sub/item. If not found,
    try to search under root for a directory named 'item' with the parent structure that matches.
    """
    # Build exact path first
    parts = [root]
    if vol:
        parts.append(Path(vol))
    if chap:
        parts.append(Path(chap))
    if unit:
        parts.append(Path(unit))
    if sub:
        parts.append(Path(sub))
    parts.append(Path(item))
    candidate = Path().joinpath(*parts)
    if candidate.exists() and candidate.is_dir():
        return candidate

    if index is None:
        index = build_fs_index(root)
    candidates = index['dir_by_name'].get(item, [])
    # prefer candidates whose ancestors contain vol/chap/unit/sub strings
    for d in candidates:
        try:
            rel = d.relative_to(root)
        except Exception:
            continue
        parts = rel.parts
        ok = True
        if vol and (vol not in parts):
            ok = False
        if chap and (chap not in parts):
            ok = False
        if unit and (unit not in parts):
            ok = False
        if sub and (sub not in parts):
            ok = False
        if ok:
            return d
    return None
    return None


def analyze_folder_counts(folder: Path) -> Tuple[int, int, int]:
    """Given a folder, return:
       - number of child numeric folders (names digits only)
       - number of files named 'generator_output.json' found recursively
       - number of files named 'solver_output-1.json' found recursively
    """
    if not folder or not folder.exists():
        return 0, 0, 0
    numeric_count = 0
    for child in folder.iterdir():
        if child.is_dir() and child.name.isdigit():
            numeric_count += 1
    gen_count = sum(1 for _ in folder.rglob('generator_output.json'))
    solver_count = sum(1 for _ in folder.rglob('solver_output-1.json'))
    return numeric_count, gen_count, solver_count


def analyze_numeric_children_details(folder: Path) -> Tuple[int, List[int], List[int], List[int]]:
    """Return:
      - numeric_count: number of numeric child directories
      - generation_no_solver_list: list of numeric names (as int) that have generator but no solver
      - generation_no_verify_list: list of numeric names that have generator but no verify_status in log
      - verify_count: number of numeric children whose log.json includes verify_status with cross_check_status
    """
    gens_no_solver = []
    gens_no_verify = []
    verify_count = 0
    numeric_count = 0
    for child in sorted(folder.iterdir(), key=lambda p: p.name if p.is_dir() else ''):
        if not child.is_dir() or not child.name.isdigit():
            continue
        numeric_count += 1
        # presence checks
        has_generator = any(True for _ in child.rglob('generator_output.json'))
        has_solver = any(True for _ in child.rglob('solver_output-1.json'))
        # examine log.json if present
        log_files = list(child.rglob('log.json'))
        has_verify = False
        has_cross_check = False
        for lf in log_files:
            try:
                j = json.loads(lf.read_text(encoding='utf-8'))
            except Exception:
                try:
                    j = json.loads(lf.read_text(encoding='gbk', errors='ignore'))
                except Exception:
                    j = None
            if not isinstance(j, dict):
                continue
            if 'verify_status' in j and isinstance(j['verify_status'], list):
                has_verify = True
                # check cross_check_status inside any element
                for entry in j['verify_status']:
                    if isinstance(entry, dict) and 'cross_check_status' in entry:
                        has_cross_check = True
                        break
            if has_cross_check:
                break
        if has_cross_check:
            verify_count += 1
        if has_generator and (not has_solver):
            gens_no_solver.append(int(child.name))
        if has_generator and (not has_verify):
            gens_no_verify.append(int(child.name))
    return numeric_count, gens_no_solver, gens_no_verify, verify_count


def process_file(path: Path, root: Path | None = None, unique: bool = False, fs_index=None, verbose: bool = False) -> Tuple[int, List[dict]]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        # 尝试自动检测其他编码（回退为 gbk）
        text = path.read_text(encoding="gbk", errors="ignore")
    items = []
    current_chapter = ''
    current_unit = ''
    current_sub = ''

    # derive volume number from filename
    filename = path.name
    vol_num = ''
    m = re.search(r"第\s*([0-9]+|[一二三四五六七八九十百千]+)\s*卷", filename)
    if m:
        vol_val = m.group(1)
        if vol_val.isdigit():
            vol_num = str(int(vol_val))
        else:
            vol_num = str(chinese_to_int(vol_val))

    for line in text.splitlines():
        # update chapter/unit/subsection if found on non-bullet lines
        mch = CHAPTER_RE.match(line)
        if mch:
            val = mch.group(1)
            current_chapter = str(int(val)) if val.isdigit() else str(chinese_to_int(val))
            # reset lower-level
            current_unit = ''
            current_sub = ''
            continue
        mun = UNIT_RE.match(line)
        if mun:
            current_unit = mun.group(1)
            current_sub = ''
            continue
        msub = SUBSECTION_RE.match(line)
        if msub:
            # ensure this is a numbered subsection with at least two dots signifying deeper level
            num = msub.group(1)
            # Only treat as sub if it has at least one dot
            if '.' in num:
                current_sub = num
                continue

        # if it's a bullet matching knowledge pattern, create path
        mk = KNOWLEDGE_RE.match(line)
        if mk:
            item = mk.group(1).strip()
            items.append({
                'vol': vol_num,
                'chapter': current_chapter,
                'unit': current_unit,
                'sub': current_sub,
                'item': item,
            })
    if unique:
        seen = set()
        uniq_items = []
        for obj in items:
            if obj['item'] not in seen:
                seen.add(obj['item'])
                uniq_items.append(obj)
        items = uniq_items

    # analyze folder counts if root provided
    results = []
    # track progress of items
    total_items = len(items)
    if verbose and total_items > 0:
        print(f"  已发现知识点数量: {total_items}", flush=True)
    item_counter = 0
    for obj in items:
        item_counter += 1
        if verbose and item_counter % 20 == 0:
            print(f"    处理知识点 {item_counter}/{total_items} -> {obj['item']}", flush=True)
        res = obj.copy()
        if root:
            matched = find_matching_dir(root, res['vol'], res['chapter'], res['unit'], res['sub'], res['item'], index=fs_index)
            res['match_dir'] = str(matched) if matched else ''
            nchild, ngen, nsolver = analyze_folder_counts(matched) if matched else (0, 0, 0)
            res['numeric_children'] = nchild
            res['generator_jsons'] = ngen
            res['solver_output1_jsons'] = nsolver
            # new detailed numeric child analysis
            if matched:
                nc_count, gens_no_solver, gens_no_verify, verify_count = analyze_numeric_children_details(matched)
            else:
                nc_count, gens_no_solver, gens_no_verify, verify_count = 0, [], [], 0
            res['verify'] = verify_count
            # store as lists of ints
            res['generation_no_solver_list'] = gens_no_solver
            res['generation_no_verify_list'] = gens_no_verify
        else:
            res['match_dir'] = ''
            res['numeric_children'] = 0
            res['generator_jsons'] = 0
            res['solver_output1_jsons'] = 0
            res['verify'] = 0
            res['generation_no_solver_list'] = []
            res['generation_no_verify_list'] = []
        results.append(res)
    return len(results), results
    if unique:
        unique_items = sorted(set(items))
        return len(unique_items), unique_items
    return len(items), items


def scan(root: Path, pattern: str, unique: bool = False, verbose: bool = False) -> Dict[str, Dict[str, object]]:
    out: Dict[str, Dict[str, object]] = {}
    # build filesystem index once for performance
    if verbose:
        print("索引构建开始...", flush=True)
    fs_index = build_fs_index(root)
    if verbose:
        print("索引构建完成: 总目录数", len(fs_index['dirs']), "总名称索引条数", len(fs_index['dir_by_name']), flush=True)
    files = list(root.glob(pattern))
    # sort by extracted volume number if present
    def file_vol_key(p: Path):
        m = re.search(r"第\s*([0-9]+|[一二三四五六七八九十百千]+)\s*卷", p.name)
        if not m:
            return (9999, p.name)
        val = m.group(1)
        if val.isdigit():
            return (int(val), p.name)
        # chinese numeric -> int
        try:
            return (chinese_to_int(val), p.name)
        except Exception:
            return (9999, p.name)
    files = sorted(files, key=file_vol_key)
    if verbose:
        print("要处理的 Markdown 文件数:", len(files))
    for i, p in enumerate(files, start=1):
        if p.is_file():
            if verbose:
                print(f"处理文件 {i}/{len(files)}: {p.name}", flush=True)
            count, items = process_file(p, root=root, unique=unique, fs_index=fs_index, verbose=verbose)
            out[str(p)] = {
                "count": count,
                "items": items,
            }
    return out


def format_summary(result: Dict[str, Dict[str, object]]) -> str:
    lines = []
    total = sum(info["count"] for info in result.values())
    maxlen = max((len(Path(p).name) for p in result.keys()), default=0)
    header = f"{'文件':<{maxlen}} | 知识点数量"
    lines.append(header)
    lines.append("-" * len(header))
    for p, info in result.items():
        lines.append(f"{Path(p).name:<{maxlen}} | {info['count']}")
    lines.append("-")
    lines.append(f"合计: {total}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="统计 Markdown 文件中的知识点（以 '-' 开头并到第一个冒号为止）")
    parser.add_argument("-d", "--dir", default=".", help="根目录（默认当前目录）")
    parser.add_argument("-p", "--pattern", default="第*卷*.md", help="Glob 模式，默认: 第*卷*.md")
    parser.add_argument("--unique", action="store_true", help="只统计不重复的知识点（去重）")
    parser.add_argument("--verbose", action="store_true", help="显示进度信息和调试输出")
    parser.add_argument("--list", action="store_true", help="打印每个文件中提取的知识点列表")
    parser.add_argument("--json", help="输出为 JSON 文件路径")
    parser.add_argument("--csv", default="knowledge_points_full_counts.csv", help="输出为 CSV 文件路径（单列，格式为 卷/章/单元/小节/知识点）；默认: knowledge_points_full_counts.csv")
    args = parser.parse_args()

    root = Path(args.dir)
    verbose = args.verbose

    def log_progress(*parts):
        if verbose:
            import time
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{ts}]", *parts, flush=True)
    log_progress("开始扫描:", root, "模式:", args.pattern)
    result = scan(root, args.pattern, unique=args.unique, verbose=verbose)
    log_progress("扫描完成，准备写入输出")

    print(format_summary(result))

    if args.list:
        print('\n详细知识点列表：')
        for p, info in result.items():
            print('\n' + Path(p).name + ':')
            for i, item in enumerate(info['items'], 1):
                print(f"  {i}. {item}")

    if args.json:
        jpath = Path(args.json)
        jpath.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 JSON: {jpath}")

    if args.csv:
        import csv
        rows = []
        for p, info in result.items():
            for it in info['items']:
                # create CSV row: path, numeric_children, generator_jsons, solver_output1_jsons, verify, generation_no_solver_list, generation_no_verify_list
                path_col = f"{it.get('vol','')}/{it.get('chapter','')}/{it.get('unit','')}/{it.get('sub','')}/{it.get('item','')}"
                nc = it.get('numeric_children', 0)
                ngen = it.get('generator_jsons', 0)
                nsolver = it.get('solver_output1_jsons', 0)
                verify = it.get('verify', 0)
                gens_no_solver = it.get('generation_no_solver_list', [])
                gens_no_verify = it.get('generation_no_verify_list', [])
                # serialize lists as bracketed strings
                rows.append((path_col, nc, ngen, nsolver, verify, gens_no_solver, gens_no_verify))
        csv_path = Path(args.csv)
        with csv_path.open('w', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(['path', 'numeric_children', 'generator_output.json', 'solver_output-1.json', 'verify', 'generation_no_solver_list', 'generation_no_verify_list'])
            for r in rows:
                # convert lists to JSON-like strings for CSV
                import json as _json
                writer.writerow([r[0], r[1], r[2], r[3], r[4], _json.dumps(r[5], ensure_ascii=False), _json.dumps(r[6], ensure_ascii=False)])
        print(f"已写入 CSV: {csv_path}")
    log_progress("完成：已写入 CSV", args.csv if args.csv else '')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
