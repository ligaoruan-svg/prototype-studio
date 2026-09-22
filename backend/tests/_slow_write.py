"""被 test_进程被杀时原文件完好 拉起来的子进程：停在 os.replace 之前等死。"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
real_replace = os.replace
os.replace = lambda src, dst: (time.sleep(30), real_replace(src, dst))
from backend.atomicio import write_atomic   # noqa: E402

write_atomic(sys.argv[1], "N" * 200000)
