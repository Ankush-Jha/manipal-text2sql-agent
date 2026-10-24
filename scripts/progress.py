#!/usr/bin/env python3
"""Live download/install progress. Run: python3 scripts/progress.py   (Ctrl-C to quit; --once for one shot)"""
import os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def remote_size(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        return int(urllib.request.urlopen(req, timeout=10).headers.get("Content-Length", 0))
    except Exception:
        return 0

def hf_size(repo, fname):
    try:
        req = urllib.request.Request(f"https://huggingface.co/{repo}/resolve/main/{fname}", method="HEAD")
        class NoRedir(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k): return None
        op = urllib.request.build_opener(NoRedir)
        try: r = op.open(req, timeout=10)
        except urllib.error.HTTPError as e: r = e
        return int(r.headers.get("X-Linked-Size") or r.headers.get("Content-Length") or 0)
    except Exception:
        return 0

def local_size(path_glob_dir, name):
    best = 0
    for p in Path(path_glob_dir).rglob("*"):
        if p.is_file() and name in p.name:
            best = max(best, p.stat().st_size)
    return best

ITEMS = [
    ("Mini-Dev DBs (zip)", ROOT/"data/raw", "minidev.zip", remote_size("https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip")),
    ("Arctic-R1-7B Q4_K_M", ROOT/"models", "Arctic-Text2SQL-R1-7B.Q4_K_M", hf_size("mradermacher/Arctic-Text2SQL-R1-7B-GGUF", "Arctic-Text2SQL-R1-7B.Q4_K_M.gguf")),
    ("Qwen3-8B Q4_K_M", ROOT/"models", "Qwen3-8B-Q4_K_M", hf_size("Qwen/Qwen3-8B-GGUF", "Qwen3-8B-Q4_K_M.gguf")),
]

def fmt(n): return f"{n/1e9:6.2f} GB" if n > 1e9 else f"{n/1e6:6.1f} MB"

def bar(frac, w=30):
    k = int(frac*w); return "█"*k + "░"*(w-k)

prev, t0 = {}, time.time()
once = "--once" in sys.argv
while True:
    now, lines = time.time(), []
    for name, d, key, total in ITEMS:
        cur = local_size(d, key)
        rate = (cur - prev.get(name, (cur, now))[0]) / max(now - prev.get(name, (cur, now))[1], 1e-9)
        prev[name] = (cur, now)
        frac = cur/total if total else 0
        eta = f"ETA {int((total-cur)/rate/60)}m" if rate > 1e4 and total > cur else ("done" if total and cur >= total else "")
        lines.append(f"{name:22} {bar(frac)} {frac*100:5.1f}%  {fmt(cur)}/{fmt(total) if total else '?'}  {rate/1e6:5.1f} MB/s {eta}")
    venv = "ready" if (ROOT/".venv/bin/python").exists() else "installing…"
    llama = "ready" if shutil.which("llama-server") else "installing…"
    lines += [f"{'Python venv':22} {venv}", f"{'llama.cpp (brew)':22} {llama}"]
    if not once: print("\033[2J\033[H", end="")
    print(f"Download progress  {time.strftime('%H:%M:%S')}\n" + "\n".join(lines), flush=True)
    if once: break
    time.sleep(2)
