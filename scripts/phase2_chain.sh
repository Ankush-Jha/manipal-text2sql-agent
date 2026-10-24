#!/bin/zsh
# Phase 2 live chain: waits for the current Phase 1 eval.run_agent jobs to finish (so it never competes with
# them for the writer/judge servers), then runs a small live slice of Phase 2 tests. Safe to leave running.
cd ~/College/hackathons/manipal
LOG=logs/phase2_chain.log
echo "$(date) waiting for Phase 1 eval.run_agent jobs to finish" | tee -a $LOG
while pgrep -f "eval.run_agent --split" >/dev/null; do sleep 30; done
echo "$(date) Phase 1 jobs done, waiting for free memory >= 15%" | tee -a $LOG
for i in {1..40}; do
  free=$(memory_pressure | grep "free percentage" | grep -o '[0-9]*')
  [ "${free:-0}" -ge 15 ] && break
  sleep 30
done
echo "$(date) starting Phase 2 offline tests (no model load)" | tee -a $LOG
.venv/bin/python -m eval.run_rbac >> $LOG 2>&1
.venv/bin/python -m eval.run_injection >> $LOG 2>&1
.venv/bin/python -m eval.run_map california_schools >> $LOG 2>&1
echo "$(date) starting Phase 2 live drift eval (5 kinds, A+D, 3 questions each)" | tee -a $LOG
for k in t_ren c_abbr t_vsplit t_hsplit combo; do
  .venv/bin/python -m eval.run_drift --db california_schools --kind $k --cond A,D --n 5 --limit 3 >> $LOG 2>&1
done
echo "$(date) starting Phase 2 live follow-up conversations (dev 20)" | tee -a $LOG
.venv/bin/python -m eval.run_conversations eval/sets/conversations_dev_20.json --n 5 >> $LOG 2>&1
echo "$(date) Phase 2 chain done" | tee -a $LOG
