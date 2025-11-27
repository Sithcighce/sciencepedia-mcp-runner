#!/usr/bin/env python3
"""
extract_verified.py

扫描工作区 MD 文件与对应目录，提取通过交叉验证（cross_check_status True）的生成题目（generator）与解答（solver），
将符合条件的数据合并为 JSON 文件并输出到卷级目录，例如：`第1卷总输出/知识点名_0.json`。

注: 输出中的 `ground_truth_answer` 字段将从 `log.json` 中获取（若无则回退到 `log.json` 的 `answer`，再回退到 solver 的 `answer`）。

用法:
    python extract_verified.py -d . -p "第*卷*.md" --outdir outputs --verbose

"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

from count_knowledge_points import scan, build_fs_index, find_matching_dir, chinese_to_int


def sanitize_filename(s: str, max_len: int = 180) -> str:
    # Remove path separators and illegal chars
    banned = '<>:"/\\|?*'
    out = ''.join('_' if c in banned or ord(c) < 32 else c for c in s)
    out = out.strip()
    if len(out) > max_len:
        out = out[:max_len]
    return out


def read_json_safe(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        try:
            return json.loads(path.read_text(encoding='gbk', errors='ignore'))
        except Exception:
            return None


def find_file_in_subtree(index: dict, start_dir: Path, filename: str):
    # BFS through index child map
    stack = [start_dir]
    seen = set()
    while stack:
        cur = stack.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        if filename in index['files_map'].get(cur, []):
            return cur / filename
        # push children
        for child_name in index['child_dirs_map'].get(cur, []):
            stack.append(cur / child_name)
    return None


def is_cross_check_true_from_log(path: Path) -> bool:
    j = read_json_safe(path)
    if not isinstance(j, dict):
        return False
    vs = j.get('verify_status')
    if not isinstance(vs, list):
        return False
    for entry in vs:
        if isinstance(entry, dict) and 'cross_check_status' in entry:
            inner = entry['cross_check_status']
            # iterate through nested values
            def contains_true(obj):
                if isinstance(obj, bool):
                    return obj is True
                if isinstance(obj, dict):
                    for v in obj.values():
                        if contains_true(v):
                            return True
                if isinstance(obj, list):
                    for v in obj:
                        if contains_true(v):
                            return True
                return False

            if contains_true(inner):
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract verified and completed problems to JSON files")
    parser.add_argument('-d', '--dir', default='.', help='Root directory')
    parser.add_argument('-p', '--pattern', default='第*卷*.md', help='Glob pattern for markdown files')
    parser.add_argument('--outdir', default='.', help='Output base directory')
    parser.add_argument('--verbose', action='store_true', help='Verbose')
    args = parser.parse_args()

    root = Path(args.dir)
    outdir = Path(args.outdir)
    verbose = args.verbose

    if verbose:
        print('Building filesystem index...')
    index = build_fs_index(root)
    if verbose:
        print('Index built: total dirs=', len(index['dirs']))

    if verbose:
        print('Scanning markdown files...')
    result = scan(root, args.pattern, unique=False, verbose=False)
    count_written = 0
    # track counts of verified outputs per volume
    per_vol_written = {}

    for md_path, info in result.items():
        vol = None
        # parse volume number
        m = Path(md_path).name
        mv = Path(md_path).name
        m2 = __import__('re').search(r"第\s*([0-9]+|[一二三四五六七八九十百千]+)\s*卷", mv)
        if m2:
            val = m2.group(1)
            vol = str(int(val)) if val.isdigit() else str(chinese_to_int(val))
        for itm in info['items']:
            match_dir = itm.get('match_dir')
            if not match_dir:
                continue
            match_path = Path(match_dir)
            # find numeric children list
            for child_name in index['child_dirs_map'].get(match_path, []):
                if not child_name.isdigit():
                    continue
                child_dir = match_path / child_name
                # quick pre-check: need generator and solver and log
                # generator path
                gen = find_file_in_subtree(index, child_dir, 'generator_output.json')
                solver = find_file_in_subtree(index, child_dir, 'solver_output-1.json')
                if not gen or not solver:
                    continue
                # check log for cross_check True
                logf = find_file_in_subtree(index, child_dir, 'log.json')
                if not logf:
                    continue
                if not is_cross_check_true_from_log(logf):
                    continue
                # read generator and solver
                gjson = read_json_safe(gen) or {}
                sjson = read_json_safe(solver) or {}
                logjson = read_json_safe(logf) or {}

                # compute ground truth answer value
                gt_answer = None
                if isinstance(logjson, dict):
                    # prefer top-level ground_truth_answer if present
                    gt_answer = logjson.get('ground_truth_answer') or logjson.get('answer')
                    # otherwise, search inside verify_status entries; prefer entry with cross_check_status True
                    if not gt_answer and isinstance(logjson.get('verify_status'), list):
                        for entry in logjson.get('verify_status'):
                            if isinstance(entry, dict):
                                # prefer entry with cross_check_status True
                                if 'ground_truth_answer' in entry:
                                    gt_answer = entry.get('ground_truth_answer')
                                    # If entry also has cross_check_status, we can break early
                                    if 'cross_check_status' in entry:
                                        break
                if not gt_answer:
                    gt_answer = sjson.get('answer')

                out = {
                    'field': logjson.get('field') or gjson.get('field') or itm.get('item'),
                    'thumbnail': logjson.get('thumbnail') or gjson.get('thumbnail'),
                    'difficulty': logjson.get('difficulty') or gjson.get('difficulty'),
                    'answer_type': logjson.get('answer_type') or gjson.get('answer_type'),
                    'problem': gjson.get('problem') or gjson.get('task') or gjson.get('prompt') or gjson.get('data'),
                    'solution': gjson.get('solution') or gjson.get('answer') or None,
                    # solver fields
                    'answer': sjson.get('answer') or None,
                    'solution2': sjson.get('solution') or sjson.get('result') or None,
                    # generator's optional answer as answer2
                    'answer2': gjson.get('answer') or None,
                    # ground truth answer - prefer log.json fields, fallback to solver 'answer'
                    'ground_truth_answer': gt_answer,
                    # extract cross_check_status from log.json if present
                    'cross_check_status': None,
                }
                cross_check = None
                if isinstance(logjson, dict) and 'verify_status' in logjson and isinstance(logjson['verify_status'], list):
                    for entry in logjson['verify_status']:
                        if isinstance(entry, dict) and 'cross_check_status' in entry:
                            cross_check = entry['cross_check_status']
                            break
                out['cross_check_status'] = cross_check

                # create volume dir
                if vol:
                    vdir = outdir / f"第{vol}卷总输出"
                else:
                    vdir = outdir / "第x卷总输出"
                vdir.mkdir(parents=True, exist_ok=True)

                fname = f"{sanitize_filename(itm.get('item') or '知识点')}_{child_name}.json"
                fpath = vdir / fname
                fpath.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
                count_written += 1
                # increment per volume count
                vkey = vol if vol else 'x'
                per_vol_written[vkey] = per_vol_written.get(vkey, 0) + 1
                if verbose:
                    print(f"Wrote: {fpath}")

    if verbose:
        print('Done. total written:', count_written)
    # write summary markdown with per-volume counts (verified outputs only)
    try:
        vol_counts: dict[str, int] = {}
        # use the per_vol_written counts which represent verified JSON outputs
        for v, cnt in per_vol_written.items():
            vol_counts[v] = cnt

        # sort volumes numerically when possible
        def vol_key(v: str):
            try:
                return (int(v), v)
            except Exception:
                return (9999, v)

        lines = ["# 有效题目统计", ""]
        total = 0
        for v in sorted(vol_counts.keys(), key=vol_key):
            c = vol_counts[v]
            total += c
            # represent numeric vol as 第x卷
            if v.isdigit():
                lines.append(f"第{v}卷：{c}题")
            else:
                lines.append(f"{v}：{c}题")
        lines.append("")
        lines.append(f"合计：{total}题")
        stats_path = outdir / '有效题目统计.md'
        stats_path.write_text('\n'.join(lines), encoding='utf-8')
        if verbose:
            print(f"Wrote stats markdown: {stats_path}")
    except Exception:
        # don't crash if summary cannot be written
        import traceback
        if verbose:
            traceback.print_exc()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
