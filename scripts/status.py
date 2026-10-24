#!/usr/bin/env python3
"""Live dashboard: model servers, Phase 1 eval jobs, Phase 2 chain stage and progress, memory.
Run: .venv/bin/python scripts/status.py   (Ctrl-C to quit; --once for one shot)"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
once = "--once" in sys.argv


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def bar(frac, w=24):
    k = int(max(0, min(1, frac)) * w)
    return "█" * k + "░" * (w - k)


def mem_free_pct():
    m = re.search(r"(\d+)%", sh("memory_pressure | grep -i 'free percentage'"))
    return int(m.group(1)) if m else -1


def server_up(port):
    try:
        urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1.5)
        return True
    except Exception:
        return False


def jsonl_count(path: Path) -> int:
    return sum(1 for _ in path.open()) if path.exists() else 0


def phase1_status():
    lines = []
    ps = sh("ps -eo pid,args | grep 'eval.run_agent --split' | grep -v grep")
    jobs = [l for l in ps.splitlines() if l.strip()]
    if not jobs:
        lines.append("Phase 1: no eval.run_agent jobs running")
        return lines
    try:
        split = json.loads((ROOT / "eval/split.json").read_text())
    except Exception:
        split = {}
    for j in jobs:
        m_split = re.search(r"--split (\w+)", j)
        m_mode = re.search(r"--mode (\w+)", j)
        m_shard = re.search(r"--shard (\d+)/(\d+)", j)
        m_n = re.search(r"--n (\d+)", j)
        m_tag = re.search(r"--tag (\S+)", j)
        m_limit = re.search(r"--limit (\d+)", j)
        sname = m_split.group(1) if m_split else "?"
        total = len(split.get(sname, [])) if split else 0
        if m_shard:
            total = total // int(m_shard.group(2)) + (1 if total % int(m_shard.group(2)) else 0)
        if m_limit:
            total = min(total, int(m_limit.group(1))) if total else int(m_limit.group(1))
        sfx = f"_shard{m_shard.group(1)}of{m_shard.group(2)}" if m_shard else ""
        tag = f"_{m_tag.group(1)}" if m_tag else ""
        n = m_n.group(1) if m_n else "5"
        fname = f"agent_{sname}_{m_mode.group(1) if m_mode else '?'}_hints_false_n{n}{tag}{sfx}.jsonl"
        done = jsonl_count(ROOT / "results" / fname)
        frac = done / total if total else 0
        label = f"{sname}/{m_mode.group(1) if m_mode else '?'}{tag}{sfx}"
        lines.append(f"  {label:34} {bar(frac)} {done:>4}/{total or '?':<4}")
    return ["Phase 1 (eval.run_agent):"] + lines


def phase2_chain_status():
    log = ROOT / "logs/phase2_chain.log"
    running = bool(sh("pgrep -f phase2_chain.sh"))
    lines = [f"Phase 2 chain: {'running' if running else 'not running'}"]
    if not log.exists():
        return lines
    tail = log.read_text().splitlines()
    stage = next((l for l in reversed(tail) if l.strip()), "")
    lines.append(f"  stage: {stage[:100]}")
    kinds = ["t_ren", "c_abbr", "t_vsplit", "t_hsplit", "combo"]
    for k in kinds:
        for c in ("A", "D"):
            p = ROOT / f"results/drift_california_schools_{k}_{c}_n5.jsonl"
            if p.exists():
                lines.append(f"  drift {k:10} {c}  {bar(jsonl_count(p) / 3)} {jsonl_count(p)}/3")
    conv = ROOT / "results/conversations_conversations_dev_20_n5.jsonl"
    if conv.exists():
        lines.append(f"  conversations dev20  {bar(jsonl_count(conv) / 15)} {jsonl_count(conv)}/15")
    for f, label in (("rbac_ladder.md", "RBAC ladder"), ("injection_reach.md", "injection reach"), ("migration_map.md", "migration map")):
        lines.append(f"  {label:18} {'done' if (ROOT / 'results' / f).exists() else 'pending'}")
    return lines


def render():
    free = mem_free_pct()
    writer, judge = server_up(8081), server_up(8082)
    lines = [f"Status  {time.strftime('%H:%M:%S')}", "",
             f"Memory free: {free}%" + ("  ⚠ low" if 0 <= free < 10 else ""),
             f"writer (8081): {'up' if writer else 'down'}   judge (8082): {'up' if judge else 'down'}", "",
             *phase1_status(), "", *phase2_chain_status()]
    if not once:
        print("\033[2J\033[H", end="")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    while True:
        render()
        if once:
            break
        time.sleep(5)
