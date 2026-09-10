import os
import sys
import yaml
import subprocess
import requests
from datetime import datetime
from dotenv import load_dotenv

if __name__ == "__main__" and os.getenv("HIVE_LEGACY_CRON_COLLECTOR") != "1":
    print(
        "cron_collector.py 는 deprecated 입니다.\n"
        "OpenClaw cron 잡 hive-source-watch 가 hive_vault.py watch 를 실행합니다.\n"
        "강제 실행: HIVE_LEGACY_CRON_COLLECTOR=1"
    )
    raise SystemExit(1)

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
CONFIG_PATH = os.path.join(BASE_DIR, "config/targets.yaml")
API_URL = "http://127.0.0.1:8000/knowledge/ingest"
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_push(doc_id: str, title: str, category: str, snippet: str):
    """수집 완료 문서를 텔레그램으로 전송 (인라인 승격 버튼 포함)"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    text = (
        f"🤖 **[자동 수집 완료] {title}**\n\n"
        f"• **ID**: `{doc_id}`\n"
        f"• **도메인**: `{category}`\n\n"
        f"**[에이전트 요약 미리보기]**\n"
        f"> {snippet[:200]}...\n\n"
        f"OpenClaw 텔레그램에서 `승격 {category} {doc_id}` 라고 보내면 "
        f"hive-second-brain이 Canonical로 올립니다."
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(tg_url, json=payload, timeout=6)
    except Exception as e:
        print(f"텔레그램 푸시 실패: {e}")

def analyze_with_openclaw(target_name: str, target_url: str) -> str:
    prompt = (
        f"당신은 드론 엔지니어링 지식 수집 에이전트입니다. "
        f"대상: '{target_name}' ({target_url})\n"
        f"핵심 드론 기술 이슈, PX4/ROS 파라미터 변경 사항, 주의점을 "
        f"엔지니어링 표준 마크다운 형식(개요, 핵심 파라미터, 분석 결론)으로 상세히 정리해줘."
    )
    cmd = [OPENCLAW_BIN, "agent", "--agent", "drone-rnd", "--message", prompt]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = res.stdout.strip()
        lines = [l for l in output.split("\n") if not l.startswith("🦞 OpenClaw") and not l.startswith("o")]
        cleaned = "\n".join(lines).strip()
        return cleaned if cleaned else output
    except Exception as e:
        return f"OpenClaw 분석 실패: {str(e)}"

def run_collection():
    if not os.path.exists(CONFIG_PATH):
        print(f"[Error] 설정 파일 누락: {CONFIG_PATH}")
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    targets = config.get("targets", [])
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === OpenClaw drone-rnd 수집 파이프라인 가동 ===")

    for target in targets:
        if not target.get("enabled", False):
            continue

        t_id = target["id"]
        t_name = target["name"]
        url = target["url"]
        category = target["category"]

        print(f"[*] OpenClaw drone-rnd 분석 중 : {t_name}")
        summary_content = analyze_with_openclaw(t_name, url)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_id = f"CLAW-{t_id}-{timestamp}"

        # 1. 01_Evidence 적재
        evidence_dir = os.path.join(BASE_DIR, f"knowledge/01_Evidence/{category}")
        os.makedirs(evidence_dir, exist_ok=True)
        with open(os.path.join(evidence_dir, f"{doc_id}.md"), "w", encoding="utf-8") as f:
            f.write(f"---\nid: {doc_id}\nsource: {url}\ncollector: openclaw-drone-rnd\ningested_at: {timestamp}\n---\n\n{summary_content}")

        # 2. 03_Discovery 라우팅
        payload = {
            "doc_id": doc_id,
            "title": f"[OpenClaw] {t_name}",
            "raw_content": f"출처: {url}\n\n" + summary_content,
            "category": category,
            "is_human_verified": False
        }

        try:
            res = requests.post(API_URL, json=payload, timeout=10)
            if res.status_code == 200:
                print(f" -> 성공: {doc_id} 적재 완료")
                send_telegram_push(doc_id, f"[OpenClaw] {t_name}", category, summary_content)
            else:
                print(f" -> 실패: 백엔드 오류 ({res.status_code})")
        except Exception as e:
            print(f" -> 백엔드 전송 오류: {e}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === 수집 완료 ===\n")

if __name__ == "__main__":
    run_collection()
