"""把程式打包成單一 JSON（雲端排程每天從報告頁面下載它來執行）。"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files = ["run.py", "config.json", "requirements.txt"] + sorted(
    os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "kkc", "*.py")))
bundle = {f: open(os.path.join(ROOT, f), encoding="utf-8").read() for f in files}
cfg = json.loads(bundle["config.json"])
cfg["telegram_bot_token"] = ""   # 不把任何金鑰放進打包檔
cfg["telegram_chat_id"] = ""
bundle["config.json"] = json.dumps(cfg, ensure_ascii=False, indent=2)
os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
with open(os.path.join(ROOT, "reports", "kkc_bundle.json"), "w", encoding="utf-8") as f:
    json.dump(bundle, f, ensure_ascii=False)
print("bundle:", len(bundle), "files")
