# Setting up another Mac (Mac 2, Mac 3) as a worker

Same code, same models. Every Mac runs its own model server and a different shard of the questions.
Mac 1 = this laptop = shard 0. Mac 2 = shard 1. Mac 3 (if used) = shard 2.

## Step 0: on Mac 1 (this one): make the bundle
```bash
cd ~/College/hackathons/manipal
zip -r ~/Desktop/manipal_bundle.zip . \
  -x ".venv/*" "logs/*" "results/*" "data/raw/*" "data/unanswerable_dbs/*" "models/*" "__pycache__/*" "*/__pycache__/*"
ls -lh ~/Desktop/manipal_bundle.zip      # about 400-500 MB (databases + cache)
```
Optional: for the unanswerable run also copy `data/unanswerable_dbs` (505 MB) to the Mac that will run it.

## Step 1: move files to Mac 2 (pick one)
- **AirDrop** (easiest): send `manipal_bundle.zip` and these two files from `~/Downloads`:
  - `Arctic-Text2SQL-R1-7B.Q4_K_M.gguf` (4.7 GB)
  - `Qwen3-8B-Q4_K_M.gguf` (5.0 GB)
- or a USB drive, or `scp` if Remote Login is on (System Settings > General > Sharing).

On Mac 2:
```bash
mkdir -p ~/College/hackathons/manipal && cd ~/College/hackathons/manipal
unzip ~/Downloads/manipal_bundle.zip
mkdir -p models && mv ~/Downloads/Arctic-Text2SQL-R1-7B.Q4_K_M.gguf ~/Downloads/Qwen3-8B-Q4_K_M.gguf models/
```

## Step 2: install tools on Mac 2
```bash
# Homebrew (skip if `brew --version` works): https://brew.sh
brew install llama.cpp uv
cd ~/College/hackathons/manipal
uv venv --python 3.11 .venv
UV_HTTP_TIMEOUT=180 uv pip install --python .venv/bin/python sqlglot pytest httpx scikit-learn fastapi uvicorn sse-starlette numpy
.venv/bin/python -m pytest -q          # expect: 37 passed
```

## Step 3: start the writer on Mac 2
```bash
cd ~/College/hackathons/manipal && mkdir -p logs
nohup llama-server -m models/Arctic-Text2SQL-R1-7B.Q4_K_M.gguf --port 8081 -c 16384 -np 2 --alias writer > logs/writer.log 2>&1 &
until curl -s localhost:8081/health | grep -q ok; do sleep 2; done; echo writer ready
```
Only start the judge (Qwen, port 8082) on a Mac when a run needs it (product mode / calibration). Never run both on a 16 GB Mac together with other heavy apps.

## Step 4: smoke test (2 questions, about 1 minute)
```bash
.venv/bin/python -m eval.run_bird --hints false --limit 2 --workers 1 --shard 1/2
```
You should see `[1/1] q... correct=... ` lines and a file `results/baseline_report_hints_false_shard1of2.jsonl`.

## Step 5: run the real shard
Baseline, no hints, 2 Macs (Mac 1 runs `--shard 0/2`, Mac 2 runs `--shard 1/2`):
```bash
nohup .venv/bin/python -m eval.run_bird --hints false --workers 2 --shard 1/2 > logs/baseline.log 2>&1 &
tail -f logs/baseline.log
```
Then the same with `--hints true`. For 3 Macs use `0/3`, `1/3`, `2/3`.
It is resumable: if it stops, run the same command again.

## Step 6: collect results back on Mac 1
Copy each worker's `results/*.jsonl` into Mac 1's `results/` (AirDrop/USB), then:
```bash
.venv/bin/python -m eval.merge_shards
.venv/bin/python -m eval.summarize
```

## Keep the Macs cool
- Plugged in, lid open, on a hard flat surface (not a bed or cushion), fan area clear.
- `--workers 2` max. Use `--workers 1` if the fan gets loud.
- Close browsers and heavy apps. Check `memory_pressure | tail -1` (want > 25% free).
- To stop everything: `pkill -f eval.run_bird; pkill -f llama-server`.
