#!/bin/zsh
# Mac1 job chain: waits for the benchmark agent run, then calibration -> product report -> unanswerable (shard 0).
cd ~/College/hackathons/manipal
while pgrep -f "eval.run_agent --split report --mode benchmark" >/dev/null; do sleep 20; done
echo "$(date) start calibration"
.venv/bin/python -m eval.run_agent --split calibration --mode product --hints false --n 5 --limit 120 --shard 0/2 > logs/agent_calib.log 2>&1
echo "$(date) start report product"
.venv/bin/python -m eval.run_agent --split report --mode product --hints false --n 5 --shard 0/2 > logs/agent_report_product.log 2>&1
echo "$(date) start unanswerable"
.venv/bin/python -m eval.run_unanswerable > logs/unanswerable.log 2>&1
echo "$(date) chain done"
