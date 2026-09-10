import os
import sys

# OpenClaw 네이티브 텔레그램이 단일 진입점이다.
# 같은 봇 토큰으로 이 스크립트를 폴링하면 409 Conflict가 난다.
if __name__ == "__main__" and os.getenv("HIVE_LEGACY_TELEGRAM_BRIDGE") != "1":
    print(
        "telegram_bridge.py 는 deprecated 입니다.\n"
        "텔레그램은 OpenClaw Gateway(port 18789) 네이티브 채널이 수신합니다.\n"
        "강제 폴백이 필요하면 HIVE_LEGACY_TELEGRAM_BRIDGE=1 을 설정하세요.\n"
        "(같은 봇 토큰으로 OpenClaw와 동시 폴링하면 409가 납니다.)"
    )
    raise SystemExit(1)

import html
import asyncio
import shutil
import tempfile
import subprocess
import logging
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters

load_dotenv()

# OpenClaw 네이티브 텔레그램이 단일 진입점이다.
# 같은 봇 토큰으로 이 스크립트를 폴링하면 409 Conflict가 난다.
# 비상 폴백: HIVE_LEGACY_TELEGRAM_BRIDGE=1

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.analyzer.schemas import AnalysisReport, Severity
from services.analyzer.ulog_analyzer import ULogAnalyzer, ULogParseError

_TG_FILE_LIMIT = 20 * 1024 * 1024
_SEVERITY_EMOJI = {
    Severity.OK: "✅",
    Severity.INFO: "ℹ️",
    Severity.WARNING: "⚠️",
    Severity.CRITICAL: "🚨",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚁 **Apex HiveStrike Drone Agent (Claude Pro 연동)**\n\n"
        "• **비행 로그 진단**: `.ulg` 파일을 이 채팅에 올리면 이상 진단 + Canonical 처방 리포트를 회신합니다\n"
        "• **기술 지식 수집**: 메모나 링크를 입력하면 `03_Discovery`로 적재\n"
        "• **지식 볼트 질의**: `/ask <질문>` 입력 시 Claude Pro가 옵시디언 볼트 지식을 참조해 기술 답변 제공\n"
        "  - 예: `/ask PX4 실내 비행 시 EKF2 고도 세팅 파라미터는?`"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: `/ask <궁금한 드론 기술 질문>`", parse_mode="Markdown")
        return

    query = " ".join(context.args)
    status_msg = await update.message.reply_text("🧠 Claude Pro 에이전트가 지식 볼트를 분석 중입니다...")

    prompt = (
        f"당신은 Apex HiveStrike 드론 시스템 엔지니어링 에이전트입니다. "
        f"현재 프로젝트 지식 볼트(knowledge/02_Canonical, knowledge/03_Discovery)에 있는 문서를 우선 참조하여 질문에 답하세요.\n\n"
        f"질문: {query}"
    )

    try:
        # 로컬 Claude Code CLI를 Pro 로그인 세션으로 비동기 서브프로세스 호출
        proc = subprocess.run(
            ["/Users/drone_engineer/.local/bin/claude", "-p", prompt],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=90
        )

        output = proc.stdout.strip() if proc.stdout else proc.stderr.strip()
        if not output:
            output = "답변을 생성하지 못했습니다."

        await status_msg.delete()
        # 텔레그램 메시지 길이 제한(4096자) 대응
        for i in range(0, len(output), 4000):
            await update.message.reply_text(output[i:i+4000])

    except subprocess.TimeoutExpired:
        await status_msg.edit_text("⏳ 응답 대기 시간이 초과되었습니다 (90초).")
    except Exception as e:
        await status_msg.edit_text(f"❌ Claude 호출 오류: {str(e)}")


def _format_ulog_telegram_report(report: AnalysisReport) -> str:
    """텔레그램 HTML 리포트. 파라미터명 언더스코어가 Markdown을 깨지 않게 HTML을 쓴다."""

    emoji = _SEVERITY_EMOJI.get(report.overall_severity, "ℹ️")
    summary = report.summary
    lines = [
        f"{emoji} <b>ULog 이상 진단 리포트</b>",
        f"종합 심각도: <b>{html.escape(report.overall_severity.value.upper())}</b>",
        f"파일: <code>{html.escape(summary.filename)}</code>",
        f"비행 시간: {summary.duration_s:.1f}s",
        f"펌웨어: <code>{html.escape(summary.firmware or 'unknown')}</code>",
        f"보드: <code>{html.escape(summary.board or 'unknown')}</code>",
        "",
        "<b>탐지된 이상</b>",
    ]
    if report.findings:
        for finding in report.findings[:12]:
            mark = _SEVERITY_EMOJI.get(finding.severity, "•")
            lines.append(
                f"{mark} <b>{html.escape(finding.title)}</b>\n"
                f"    {html.escape(finding.detail)}"
            )
    else:
        lines.append("• 탐지된 이상 없음")

    lines.extend(["", "<b>Canonical 처방</b>"])
    if report.prescriptions:
        for rx in report.prescriptions[:10]:
            name = rx.param_name or rx.kind
            if rx.prescribed_value is not None:
                current = "없음" if rx.current_value is None else str(rx.current_value)
                lines.append(
                    f"• <code>{html.escape(str(name))}</code>: "
                    f"{html.escape(current)} → <b>{html.escape(str(rx.prescribed_value))}</b>"
                )
            else:
                lines.append(f"• <code>{html.escape(str(name))}</code>")
            lines.append(f"    {html.escape(rx.reason)}")
    else:
        lines.append("• Canonical 대비 추가 처방 없음")

    if report.discovery_path:
        lines.extend(["", f"저장: <code>{html.escape(report.discovery_path)}</code>"])
    return "\n".join(lines)


async def handle_ulog_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    [동작] 텔레그램으로 올린 .ulg를 받아 분석 엔진을 돌리고 채팅으로 리포트를 회신한다.
    [이유] 현장 엔지니어는 REST보다 봇 업로드가 빠르고, 기존 지식 적재 UX와 같은 창구를 유지해야 한다.
    [근거] Telegram Bot API getFile 20MB 제한, ULogAnalyzer Canonical SSOT 규칙.
    """

    message = update.message
    if message is None or message.document is None:
        return

    doc = message.document
    filename = doc.file_name or "upload.ulg"
    lowered = filename.lower()

    if lowered.endswith(".tlog") or lowered.endswith(".bin"):
        await message.reply_text(
            ".tlog/.bin 분석은 아직 지원하지 않습니다. PX4 ULog(.ulg)만 보내 주세요."
        )
        return
    if not lowered.endswith(".ulg"):
        await message.reply_text(
            "PX4 ULog(.ulg) 파일만 분석할 수 있습니다. 비행 로그를 문서로 첨부해 주세요."
        )
        return
    if doc.file_size and doc.file_size > _TG_FILE_LIMIT:
        await message.reply_text(
            "텔레그램 봇은 20MB 초과 파일을 받을 수 없습니다. "
            "짧은 구간 로그를 보내거나 REST `/logs/analyze`로 업로드해 주세요."
        )
        return

    status_msg = await message.reply_text(
        "📡 ULog 수신 완료. Canonical SSOT와 대조해 이상 진단 중입니다..."
    )
    tmp_dir = tempfile.mkdtemp(prefix="tg_ulog_")
    tmp_path = os.path.join(tmp_dir, Path(filename).name)
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(custom_path=tmp_path)

        analyzer = ULogAnalyzer(repo_root=Path(BASE_DIR))
        report = await asyncio.to_thread(analyzer.analyze, tmp_path, filename, True)
        body = _format_ulog_telegram_report(report)

        keyboard = None
        if report.discovery_path:
            keyboard = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(
                        "📄 Discovery 리포트 보기",
                        callback_data=f"view:06_Troubleshooting:{report.report_id}",
                    )
                ]]
            )

        await status_msg.delete()
        for offset in range(0, len(body), 3500):
            chunk = body[offset:offset + 3500]
            await message.reply_text(
                chunk,
                parse_mode="HTML",
                reply_markup=keyboard if offset == 0 else None,
            )
    except ULogParseError as exc:
        await status_msg.edit_text(f"❌ {exc.message}")
    except Exception as exc:
        logging.exception("ULog telegram analysis failed")
        await status_msg.edit_text(f"❌ 분석 실패: {exc}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # 만약 사용자가 물음표나 질문 어조로 보냈다면 바로 ask_command로 라우팅
    if text.endswith("?") or text.endswith("??") or any(q in text for q in ["어떻게", "알려줘", "뭐야", "요약해줘"]):
        context.args = text.split()
        await ask_command(update, context)
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    doc_id = f"TELE-{timestamp}"

    category = "03_Discovery"
    if any(k in text.lower() for k in ["px4", "ardupilot", "fc", "failsafe", "param"]):
        category = "01_Flight_Controllers"
    elif any(k in text.lower() for k in ["ros", "ros2", "dds", "jetson", "sbc", "orin"]):
        category = "02_Autonomy_ROS"
    elif any(k in text.lower() for k in ["esc", "motor", "bec", "battery", "power"]):
        category = "04_Hardware_Avionics"

    title = text.split("\n")[0][:40]

    payload = {
        "doc_id": doc_id,
        "title": f"[TG] {title}",
        "raw_content": text,
        "category": category,
        "is_human_verified": False
    }

    try:
        res = requests.post(f"{BASE_API}/knowledge/ingest", json=payload, timeout=8)
        if res.status_code == 200:
            res_data = res.json()
            routed_path = res_data.get("routed_path")

            keyboard = [
                [
                    InlineKeyboardButton("📄 문서 전문 보기", callback_data=f"view:{category}:{doc_id}"),
                    InlineKeyboardButton("🚀 Canonical 승격", callback_data=f"promote:{category}:{doc_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            preview_text = text if len(text) <= 150 else text[:150] + "..."
            reply_msg = (
                f"📥 **가설 지식 적재 완료 (검증 대기)**\n\n"
                f"• **ID**: `{doc_id}`\n"
                f"• **도메인**: `{category}`\n"
                f"• **저장 경로**: `{routed_path}`\n\n"
                f"**[수집 내용]**\n"
                f"> {preview_text}\n\n"
                f"승격 여부를 선택하세요."
            )
            await update.message.reply_text(reply_msg, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ 백엔드 오류 (HTTP {res.status_code})")
    except Exception as e:
        await update.message.reply_text(f"❌ 전송 실패: {str(e)}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    action, category, doc_id = data.split(":")

    if action == "view":
        file_path = f"knowledge/03_Discovery/{category}/{doc_id}.md"
        if not os.path.exists(file_path):
            file_path = f"knowledge/02_Canonical/{category}/{doc_id}.md"

        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                full_text = f.read()
            await query.message.reply_text(
                f"📜 **[문서 전문: {doc_id}]**\n\n```markdown\n{full_text[:3500]}\n```",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text("❌ 문서를 찾을 수 없습니다.")

    elif action == "promote":
        promote_payload = {"doc_id": doc_id, "category": category}
        try:
            res = requests.post(f"{BASE_API}/knowledge/promote", json=promote_payload, timeout=8)
            if res.status_code == 200:
                p_data = res.json()
                await query.edit_message_text(
                    f"✅ **공식 표준(Canonical) 승격 완료!**\n\n"
                    f"• **ID**: `{doc_id}`\n"
                    f"• **공식 경로**: `{p_data.get('new_path')}`\n"
                    f"• **검증 상태**: `reviewed: true`",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(f"❌ 승격 실패: {res.text}")
        except Exception as e:
            await query.edit_message_text(f"❌ 승격 요청 중 오류: {str(e)}")

if __name__ == "__main__":
    os.chdir(BASE_DIR)
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_ulog_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("[*] Claude Pro 탑재 텔레그램 에이전트 구동 중...")
    app.run_polling()
