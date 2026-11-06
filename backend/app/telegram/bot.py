"""Telegram bot (aiogram 3) - Persian UI, pairing-code authorization.

The bot uses the same Python services as the Web Dashboard, so decisions made
in either interface are immediately consistent. Every action that changes
state goes through the same service layer with the same guards (no proposal
generation without project approval, no submission without final approval).
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import secrets

from sqlalchemy import select

from app.core.logging_config import get_logger, log_execution
from app.core.security import decrypt_value
from app.services.outbox import handler
from app.services.text import format_toman

log = get_logger("telegram-bot")

_pairing_adjectives = ["طلایی", "نقره‌ای", "کهربایی", "فیروزه‌ای", "یاقوتی"]
_supervisor_wakeup: asyncio.Event | None = None

def wakeup_supervisor() -> None:
    global _supervisor_wakeup
    if _supervisor_wakeup is not None:
        _supervisor_wakeup.set()

STATUS_FA = {
    "discovered": "کشف شد", "pending_analysis": "در انتظار تحلیل", "analyzing": "در حال تحلیل",
    "analyzed": "تحلیل شد", "recommended": "پیشنهاد ارسال (در انتظار تأیید شما)",
    "skipped": "صرف‌نظر شد (امتیاز پایین)", "approved_for_proposal": "تأییدشده - آماده تولید پیشنهاد",
    "rejected_by_owner": "ردشده توسط شما", "proposal_generating": "در حال تولید پیشنهاد",
    "proposal_ready": "پیشنهاد آماده بررسی", "proposal_submitted": "پیشنهاد ارسال شد",
    "analysis_failed": "تحلیل ناموفق", "unavailable": "ناموجود",
}


def new_pairing_code() -> str:
    # URL-safe alphanumeric pairing code (compatible with Telegram deep link /start parameter)
    return f"NX-{secrets.randbelow(90000) + 10000}"


def decrypt_token(setting) -> str:
    return decrypt_value(setting.bot_token_encrypted)


# --------------------------------------------------------------------------- #
# Cached Bot instance                                                         #
# --------------------------------------------------------------------------- #
_cached: dict = {"token_hash": None, "bot": None}


def _bot_for(token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if _cached["bot"] is None or _cached["token_hash"] != token_hash:
        from aiogram import Bot
        _cached["bot"] = Bot(token=token)
        _cached["token_hash"] = token_hash
    return _cached["bot"]


async def reset_bot() -> None:
    _cached["bot"] = None
    _cached["token_hash"] = None


async def test_token(token: str) -> dict:
    try:
        bot = _bot_for(token)
        me = await bot.get_me()
        return {"ok": True, "message": f"اتصال برقرار است: @{me.username}", "bot_username": me.username}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"اتصال ناموفق: {exc}", "bot_username": None}


async def send_text(token: str, chat_id: str, text: str, reply_markup=None) -> tuple[bool, str]:
    try:
        bot = _bot_for(token)
        await bot.send_message(chat_id=int(chat_id), text=text, reply_markup=reply_markup,
                               parse_mode="HTML", disable_web_page_preview=True)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# --------------------------------------------------------------------------- #
# Keyboards & Glass (Inline) Buttons                                          #
# --------------------------------------------------------------------------- #
def _kb(rows: list[list[tuple[str, str]]]):
    """Builds Telegram glass buttons (InlineKeyboardMarkup). Supports both
    callback data and external URLs (e.g. for opening projects directly)."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = []
    for row in rows:
        btn_row = []
        for t, d in row:
            if str(d).startswith("http://") or str(d).startswith("https://"):
                btn_row.append(InlineKeyboardButton(text=t, url=str(d)))
            else:
                btn_row.append(InlineKeyboardButton(text=t, callback_data=str(d)))
        if btn_row:
            keyboard.append(btn_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def main_reply_keyboard():
    """Persistent bottom reply keyboard with direct shortcuts for every panel action."""
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 پروژه‌های جدید"), KeyboardButton(text="🎯 پیشنهادهای آماده")],
            [KeyboardButton(text="⚡ اسکن آنی پلتفرم‌ها"), KeyboardButton(text="📊 وضعیت و آمار")],
            [KeyboardButton(text="⚙️ تنظیمات و فیلتر"), KeyboardButton(text="❓ راهنما")],
        ],
        resize_keyboard=True,
        persistent=True,
        input_field_placeholder="یک گزینه انتخاب کنید یا دستور بفرستید...",
    )


def project_card(project, analysis=None, platform_name: str = "") -> str:
    lines = [
        f"<b>🆕 پروژه جدید - {html.escape(platform_name or 'فریلنسری')}</b>",
        f"📌 <b>{html.escape(project.title[:120])}</b>",
        ""
    ]
    budget = format_toman(project.budget_min) if project.budget_min else "نامشخص"
    budget_max = format_toman(project.budget_max) if project.budget_max else None
    lines.append(f"💰 بودجه: <b>{budget}" + (f" تا {budget_max}</b>" if budget_max else "</b>"))
    if project.deadline:
        lines.append(f"⏳ مهلت: {project.deadline.strftime('%Y-%m-%d')}")
    if project.skills:
        lines.append("🛠 مهارت‌ها: " + html.escape("، ".join(project.skills[:6])))
    if analysis is not None:
        lines += [
            "",
            f"🎯 ارزیابی هوش مصنوعی: <b>{analysis.match_score}/100</b>",
            f"📊 تحلیل کوتاه: {html.escape((analysis.summary or '')[:350])}",
            "💵 پیشنهاد متوازن: <b>" + _bid_line(analysis.balanced_bid) + "</b>"
        ]
    return "\n".join(lines)


def _bid_line(bid: dict) -> str:
    if not bid:
        return "—"
    price = format_toman(bid.get("price"))
    days = bid.get("delivery_days")
    return f"{price} در {days} روز" if days else price


def project_keyboard(project_id: int, canonical_url: str = "") -> "InlineKeyboardMarkup":
    rows = [
        [("✅ تأیید پروژه", f"appr:{project_id}"), ("❌ رد پروژه", f"rej:{project_id}")],
        [("📝 تولید پیشنهاد هوشمند", f"gen:{project_id}"), ("🔍 تحلیل AI", f"anlz:{project_id}")],
    ]
    sub_row = [("📄 جزئیات کامل", f"viewp:{project_id}")]
    if canonical_url:
        sub_row.append(("🌐 مشاهده در سایت", canonical_url))
    rows.append(sub_row)
    return _kb(rows)


def proposal_keyboard(proposal_id: int, project_url: str = "") -> "InlineKeyboardMarkup":
    rows = [
        [("🚀 تأیید نهایی و ارسال", f"submit:{proposal_id}"), ("✍️ ویرایش متن", f"editp:{proposal_id}")],
        [("🔄 تولید مجدد", f"regen:{proposal_id}"), ("🎯 استراتژی قیمت", f"strat:{proposal_id}")],
        [("💰 تغییر قیمت و زمان", f"editbid:{proposal_id}")],
    ]
    if project_url:
        rows.append([("🌐 مشاهده پروژه در سایت", project_url)])
    return _kb(rows)


def strategy_keyboard(proposal_id: int) -> "InlineKeyboardMarkup":
    return _kb([
        [("💬 تهاجمی (قیمت رقابتی)", f"genb:{proposal_id}:aggressive"),
         ("⚖️ متوازن (پیشنهاد استاندارد)", f"genb:{proposal_id}:balanced")],
        [("💎 پرمیوم (کیفیت و ارزش بالا)", f"genb:{proposal_id}:premium")],
        [("⬅️ بازگشت به پیشنهاد", f"prop:{proposal_id}")],
    ])


async def send_project_notification(token: str, chat_id: str, project, analysis=None,
                                    platform_name: str = "") -> None:
    text = project_card(project, analysis, platform_name=platform_name)
    kb = project_keyboard(project.id, canonical_url=project.canonical_url)
    await send_text(token, chat_id, text, kb)


# --------------------------------------------------------------------------- #
# Outbox delivery handler                                                     #
# --------------------------------------------------------------------------- #
@handler("notify.telegram")
async def deliver_notification(session, payload: dict) -> None:
    from app.models import AuthorizedChatID, Notification, TelegramSetting, Project, ProjectAnalysis, Platform

    notification = (await session.execute(
        select(Notification).where(Notification.id == payload.get("notification_id"))
    )).scalar_one_or_none()
    if notification is None:
        return
    setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
    if setting is None or not setting.enabled or not setting.notify_enabled or not setting.bot_token_encrypted:
        return
    token = decrypt_token(setting)
    chats = (await session.execute(
        select(AuthorizedChatID).where(AuthorizedChatID.authorized == True)  # noqa: E712
    )).scalars().all()
    if not chats:
        return

    # 1. New Project Discovered or Analysis Completed Notification
    if notification.type in ("project.new", "analysis.done") and notification.project_id:
        p_row = (await session.execute(
            select(Project, Platform)
            .join(Platform, Project.platform_id == Platform.id)
            .where(Project.id == notification.project_id)
        )).first()
        if p_row:
            project, platform = p_row
            analysis = (await session.execute(
                select(ProjectAnalysis).where(ProjectAnalysis.project_id == project.id)
                .order_by(ProjectAnalysis.id.desc()).limit(1)
            )).scalar_one_or_none()

            # Filter by minimum score if specified in Telegram settings
            if analysis and setting.notify_min_score and (analysis.match_score or 0) < setting.notify_min_score:
                log.info("Telegram notification skipped: score %s below threshold %s",
                         analysis.match_score, setting.notify_min_score)
                return

            text = project_card(project, analysis, platform_name=platform.name)
            kb = project_keyboard(project.id, canonical_url=project.canonical_url)
            for chat in chats:
                await send_text(token, chat.chat_id, text, kb)
            return

    # 2. Proposal Ready Notification
    elif notification.type == "proposal.ready":
        prop_id = (notification.data or {}).get("proposal_id")
        if prop_id:
            from app.models import Proposal, ProposalVersion, Project
            proposal = (await session.execute(
                select(Proposal).where(Proposal.id == prop_id)
            )).scalar_one_or_none()
            if proposal and proposal.current_version_id:
                version = (await session.execute(
                    select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id)
                )).scalar_one_or_none()
                project = (await session.execute(
                    select(Project).where(Project.id == proposal.project_id)
                )).scalar_one_or_none()
                text = "🎉 <b>پیش‌نویس پیشنهاد هوشمند NEXUS آماده شد!</b>\n\n" + _proposal_text(version)
                kb = proposal_keyboard(prop_id, project_url=project.canonical_url if project else "")
                for chat in chats:
                    await send_text(token, chat.chat_id, text, kb)
                return

    # 3. Submission Assisted Confirmation
    elif notification.type == "submission.update":
        sub_id = (notification.data or {}).get("submission_id")
        status = (notification.data or {}).get("status")
        if sub_id and status == "assisted_pending":
            text = (
                f"📤 <b>{html.escape(notification.title)}</b>\n\n"
                f"{html.escape(notification.body or '')}\n\n"
                "جهت ارسال دستی، روی لینک زیر کلیک کنید و پس از ثبت در سایت مبدا دکمه تایید را بزنید:"
            )
            url = (notification.data or {}).get("url") or ""
            kb_rows = []
            if url:
                kb_rows.append([("🌐 باز کردن صفحه پروژه در سایت", url)])
            kb_rows.append([("✔️ ارسال دستی انجام شد", f"assist:{sub_id}")])
            for chat in chats:
                await send_text(token, chat.chat_id, text, _kb(kb_rows))
            return

    # 4. Fallback general notification
    text = f"🔔 <b>{html.escape(notification.title)}</b>"
    if notification.body:
        text += f"\n{html.escape(notification.body)}"
    if (notification.data or {}).get("url"):
        text += f"\n🔗 {notification.data['url']}"
    for chat in chats:
        await send_text(token, chat.chat_id, text)


# --------------------------------------------------------------------------- #
# Router (commands + callbacks)                                               #
# --------------------------------------------------------------------------- #
def build_router():
    from aiogram import F, Router
    from aiogram.filters import Command, CommandStart
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.types import CallbackQuery, Message

    from app.core.db import get_session_factory
    from app.models import AuthorizedChatID
    from app.services import submissions as submission_service
    from app.services import proposals as proposal_service

    router = Router()

    class EditProposal(StatesGroup):
        waiting_content = State()

    class EditBid(StatesGroup):
        waiting_bid = State()

    async def _authorized(chat_id: int) -> bool:
        session_factory = get_session_factory()
        async with session_factory() as session:
            row = (await session.execute(
                select(AuthorizedChatID).where(AuthorizedChatID.chat_id == str(chat_id))
            )).scalar_one_or_none()
        return row is not None and row.authorized

    async def _pair(setting_session, chat: Message, code: str) -> bool:
        from app.models import AuthorizedChatID, TelegramSetting

        setting = (await setting_session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
        if setting is None or not setting.pairing_code:
            return False

        clean_input = code.strip().replace("\u200e", "").replace("\u200f", "").upper()
        if clean_input.startswith("/START"):
            clean_input = clean_input.replace("/START", "").strip()
        clean_target = setting.pairing_code.strip().replace("\u200e", "").replace("\u200f", "").upper()

        if clean_input != clean_target:
            return False

        row = (await setting_session.execute(
            select(AuthorizedChatID).where(AuthorizedChatID.chat_id == str(chat.chat.id))
        )).scalar_one_or_none()
        if row is None:
            row = AuthorizedChatID(chat_id=str(chat.chat.id))
            setting_session.add(row)
        row.username = chat.from_user.username if chat.from_user else None
        row.display_name = (chat.from_user.full_name if chat.from_user else "") or None
        row.authorized = True
        setting.enabled = True
        setting.notify_enabled = True
        setting_session.add(row)
        await setting_session.commit()
        return True

    # --------------------------- Main Handlers --------------------------- #
    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext):
        session_factory = get_session_factory()
        async with session_factory() as session:
            args = (message.text or "").split(maxsplit=1)
            code = args[1].strip() if len(args) > 1 else ""
            paired = await _pair(session, message, code) if code else False
            if paired:
                welcome_kb = _kb([
                    [("⚡ اسکن آنی پلتفرم‌ها", "quick:scan"), ("🆕 پروژه‌های جدید", "quick:projects")],
                    [("🎯 پیشنهادهای آماده", "quick:proposals"), ("📊 وضعیت و آمار", "quick:status")],
                ])
                await message.answer(
                    "🎉 <b>اتصال با موفقیت برقرار شد!</b>\n\n"
                    "حساب کاربری تلگرام شما به سامانه هوشمند فریلنسری <b>NEXUS</b> متصل گردید.\n"
                    "از این لحظه تمام اعلان‌های پروژه‌های جدید، ارزیابی هوش مصنوعی و تایید پیشنهادها مستقیماً در این چت در دسترس شماست.\n\n"
                    "از منوی شیشه‌ای زیر یا کلیدهای پایین صفحه برای کنترل کامل سیستم استفاده کنید:",
                    reply_markup=welcome_kb,
                    parse_mode="HTML"
                )
                await message.answer("👇 منوی کنترل سریع فعال شد:", reply_markup=main_reply_keyboard())
                return

            if await _authorized(message.chat.id):
                menu_kb = _kb([
                    [("⚡ اسکن آنی پلتفرم‌ها", "quick:scan"), ("🆕 پروژه‌های اخیر", "quick:projects")],
                    [("🎯 پیشنهادهای آماده", "quick:proposals"), ("📊 آمار و وضعیت", "quick:status")],
                    [("⚙️ تنظیمات و فیلتر", "quick:settings"), ("❓ راهنما", "quick:help")],
                ])
                await message.answer(
                    "👋 <b>درود! به مرکز کنترل هوشمند NEXUS خوش آمدید.</b>\n\n"
                    "تمام عملیات داشبورد وب از طریق دکمه‌های شیشه‌ای زیر و منوی پایینی قابل انجام است:",
                    reply_markup=menu_kb,
                    parse_mode="HTML"
                )
                await message.answer("منوی دسترسی سریع:", reply_markup=main_reply_keyboard())
                return

            await message.answer(
                "🔒 <b>این چت هنوز در سامانه NEXUS تأیید نشده است.</b>\n\n"
                "برای اتصال حساب کاربری:\n"
                "1️⃣ وارد داشبورد <b>NEXUS</b> شوید.\n"
                "2️⃣ در تب «ربات تلگرام»، روی دکمه <b>اتصال مستقیم</b> کلیک کنید یا کد جفت‌سازی را کپی کنید.\n"
                "3️⃣ در صورت ارسال دستی، کد را به این شکل بفرستید:\n"
                "<code>/start کد_جفت‌سازی</code>",
                parse_mode="HTML"
            )

    @router.message(Command("help"))
    @router.message(F.text == "❓ راهنما")
    async def cmd_help(message: Message):
        if not await _authorized(message.chat.id):
            return
        text = (
            "🤖 <b>راهنمای مرکز کنترل هوشمند NEXUS</b>\n\n"
            "<b>🔹 پایش و تایید دومرحله‌ای:</b>\n"
            "۱. <b>پروژه جدید:</b> پایش خودکار مناقصات پونیشا و کارلنسر با ارسال مشخصات و بودجه به این چت.\n"
            "۲. <b>تأیید پروژه (Approve):</b> فقط اجازه تولید پیش‌نویس به هوش مصنوعی داده می‌شود.\n"
            "۳. <b>تولید پیشنهاد (Generate Proposal):</b> هوش مصنوعی با استراتژی انتخابی (تهاجمی/متوازن/پرمیوم) پروپوزال را تدوین می‌کند.\n"
            "۴. <b>تأیید و ارسال نهایی (Submit):</b> مرحله دوم برای ارسال نهایی به پلتفرم. هیچ پیشنهادی بدون تایید این مرحله ارسال نمی‌شود.\n\n"
            "<b>🔹 دستورات در دسترس:</b>\n"
            "🔹 /projects - پروژه‌های پیشنهادی اخیر\n"
            "🔹 /proposals - پیشنهادهای آماده ارسال\n"
            "🔹 /scan - اسکن زنده و آنی پلتفرم‌ها\n"
            "🔹 /status - وضعیت ایجنت، کانال‌ها و تله‌متری\n"
            "🔹 /settings - تنظیمات اعلان‌ها و فیلتر حداقل امتیاز\n"
            "🔹 /help - نمایش این راهنما"
        )
        kb = _kb([
            [("⚡ اسکن آنی", "quick:scan"), ("🆕 پروژه‌های اخیر", "quick:projects")],
            [("📊 وضعیت سیستم", "quick:status"), ("⚙️ تنظیمات", "quick:settings")],
        ])
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    # --------------------------- Projects Listing --------------------------- #
    async def _show_projects(target_chat_id: int):
        from app.models import Platform, Project, ProjectAnalysis, TelegramSetting
        session_factory = get_session_factory()
        async with session_factory() as session:
            rows = (await session.execute(
                select(Project, Platform)
                .join(Platform, Project.platform_id == Platform.id)
                .where(Project.status.in_(["recommended", "approved_for_proposal", "proposal_ready", "discovered"]))
                .order_by(Project.first_discovered_at.desc()).limit(5)
            )).all()
            if not rows:
                await send_text("", str(target_chat_id), "📌 در حال حاضر پروژه‌ای در این بخش یافت نشد.")
                return

            setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
            token = decrypt_token(setting) if setting and setting.bot_token_encrypted else ""

            for project, platform in rows:
                analysis = (await session.execute(
                    select(ProjectAnalysis).where(ProjectAnalysis.project_id == project.id)
                    .order_by(ProjectAnalysis.id.desc()).limit(1)
                )).scalar_one_or_none()
                text = project_card(project, analysis, platform_name=platform.name)
                kb = project_keyboard(project.id, canonical_url=project.canonical_url)
                await send_text(token, str(target_chat_id), text, kb)

    @router.message(Command("projects"))
    @router.message(F.text == "🆕 پروژه‌های جدید")
    async def cmd_projects(message: Message):
        if not await _authorized(message.chat.id):
            return
        await _show_projects(message.chat.id)

    # --------------------------- Proposals Listing -------------------------- #
    async def _show_proposals(target_chat_id: int):
        from app.models import Proposal, ProposalVersion, Project, Platform, TelegramSetting
        session_factory = get_session_factory()
        async with session_factory() as session:
            rows = (await session.execute(
                select(Proposal, ProposalVersion, Project, Platform)
                .join(ProposalVersion, Proposal.current_version_id == ProposalVersion.id)
                .join(Project, Proposal.project_id == Project.id)
                .join(Platform, Project.platform_id == Platform.id)
                .where(Proposal.status.in_(["draft", "ready"]))
                .order_by(Proposal.updated_at.desc()).limit(5)
            )).all()
            if not rows:
                await send_text("", str(target_chat_id), "🎯 در حال حاضر پیش‌نویس پیشنهادی آماده ارسال نیست.")
                return

            setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
            token = decrypt_token(setting) if setting and setting.bot_token_encrypted else ""

            for prop, version, project, platform in rows:
                text = (
                    f"📝 <b>پیشنهاد آماده ارسال برای {html.escape(platform.name)}</b>\n"
                    f"📌 <b>{html.escape(project.title)}</b>\n\n" +
                    _proposal_text(version)
                )
                kb = proposal_keyboard(prop.id, project_url=project.canonical_url)
                await send_text(token, str(target_chat_id), text, kb)

    @router.message(Command("proposals"))
    @router.message(F.text == "🎯 پیشنهادهای آماده")
    async def cmd_proposals(message: Message):
        if not await _authorized(message.chat.id):
            return
        await _show_proposals(message.chat.id)

    # --------------------------- Instant Scan ------------------------------- #
    async def _execute_instant_scan(target_chat_id: int, message_to_edit: Message | None = None):
        from app.services.discovery import scan_platform
        from app.models import Platform, TelegramSetting
        session_factory = get_session_factory()
        async with session_factory() as session:
            platforms = (await session.execute(
                select(Platform).where(Platform.enabled == True, Platform.slug != "demo")
            )).scalars().all()
            setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
            token = decrypt_token(setting) if setting and setting.bot_token_encrypted else ""

        results = []
        total_new = 0
        total_found = 0
        for p in platforms:
            res = await scan_platform(p.slug, trigger="telegram")
            found = res.get("found", 0)
            new = res.get("new", 0)
            total_found += found
            total_new += new
            results.append(f"🔹 <b>{p.name}</b>: {found} پروژه بررسی شد ({new} جدید)")

        summary = "\n".join(results)
        result_text = (
            f"✅ <b>اسکن آنی با موفقیت به پایان رسید!</b>\n\n"
            f"{summary}\n\n"
            f"📊 مجموع پایش‌شده: <b>{total_found}</b> | پروژه‌های جدید: <b>{total_new}</b>\n" +
            ("🔔 کارت‌های پروژه‌های جدید در صورت تطابق به زودی ارسال می‌شوند." if total_new > 0 else "")
        )
        scan_kb = _kb([
            [("🆕 مشاهده پروژه‌ها", "quick:projects"), ("🎯 پیشنهادهای آماده", "quick:proposals")],
            [("⚡ اسکن مجدد", "quick:scan"), ("📊 وضعیت و آمار", "quick:status")],
        ])

        if message_to_edit:
            try:
                await message_to_edit.edit_text(result_text, reply_markup=scan_kb, parse_mode="HTML")
                return
            except Exception:
                pass
        await send_text(token, str(target_chat_id), result_text, scan_kb)

    @router.message(Command("scan"))
    @router.message(F.text == "⚡ اسکن آنی پلتفرم‌ها")
    async def cmd_scan(message: Message):
        if not await _authorized(message.chat.id):
            return
        progress = await message.answer("⚡ <b>در حال استعلام و اسکن زنده تمام پلتفرم‌ها...</b>\nلطفاً چند ثانیه شکیبا باشید.", parse_mode="HTML")
        await _execute_instant_scan(message.chat.id, message_to_edit=progress)

    # --------------------------- Status & Telemetry ------------------------- #
    async def _show_status(target_chat_id: int):
        from sqlalchemy import func as safunc
        from app.models import Project, Proposal, ProposalSubmission, Platform, AIProvider, TelegramSetting
        session_factory = get_session_factory()
        async with session_factory() as session:
            n_projects = (await session.execute(select(safunc.count(Project.id)))).scalar() or 0
            n_recommended = (await session.execute(
                select(safunc.count(Project.id)).where(Project.status == "recommended")
            )).scalar() or 0
            n_approved = (await session.execute(
                select(safunc.count(Project.id)).where(Project.status == "approved_for_proposal")
            )).scalar() or 0
            n_proposals = (await session.execute(select(safunc.count(Proposal.id)))).scalar() or 0
            n_submitted = (await session.execute(
                select(safunc.count(ProposalSubmission.id)).where(ProposalSubmission.status == "submitted")
            )).scalar() or 0
            platforms = (await session.execute(select(Platform).where(Platform.slug != "demo"))).scalars().all()
            active_ai = (await session.execute(
                select(AIProvider).where(AIProvider.is_active == True)
            )).scalar_one_or_none()
            setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
            token = decrypt_token(setting) if setting and setting.bot_token_encrypted else ""

        plat_lines = []
        for p in platforms:
            icon = "🟢" if p.enabled and p.connection_status == "connected" else "⚪"
            plat_lines.append(f"{icon} {p.name}: {p.connection_status or 'غیرفعال'}")

        ai_name = active_ai.name if active_ai else "تنظیم نشده"
        text = (
            "📊 <b>تله‌متری و وضعیت سامانه NEXUS</b>\n\n"
            "<b>کانال‌های پایش:</b>\n" + "\n".join(plat_lines) + "\n\n"
            f"🤖 تأمین‌کننده AI فعال: <b>{ai_name}</b>\n"
            f"📁 پروژه‌های کشف‌شده: <b>{n_projects}</b>\n"
            f"🎯 پیشنهادشده توسط AI: <b>{n_recommended}</b>\n"
            f"✅ تأییدشده برای نگارش: <b>{n_approved}</b>\n"
            f"📝 پروپوزال‌های تولیدشده: <b>{n_proposals}</b>\n"
            f"🚀 پیشنهادهای ارسال‌شده: <b>{n_submitted}</b>\n\n"
            f"🔔 سرویس تلگرام: <b>{'فعال (Polling)' if setting and setting.enabled else 'متوقف'}</b>"
        )
        kb = _kb([
            [("⚡ اسکن آنی پلتفرم‌ها", "quick:scan"), ("🆕 پروژه‌های اخیر", "quick:projects")],
            [("🎯 پیشنهادهای آماده", "quick:proposals"), ("⚙️ تنظیمات اعلان", "quick:settings")],
        ])
        await send_text(token, str(target_chat_id), text, kb)

    @router.message(Command("status"))
    @router.message(F.text == "📊 وضعیت و آمار")
    async def cmd_status(message: Message):
        if not await _authorized(message.chat.id):
            return
        await _show_status(message.chat.id)

    # --------------------------- Settings ----------------------------------- #
    async def _show_settings(target_chat_id: int):
        from app.models import TelegramSetting
        session_factory = get_session_factory()
        async with session_factory() as session:
            s = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
            if not s:
                return
            token = decrypt_token(s) if s.bot_token_encrypted else ""

            notif_status = "فعال ✅" if s.notify_enabled else "غیرفعال ❌"
            min_score = s.notify_min_score or 0
            text = (
                "⚙️ <b>تنظیمات ربات تلگرام NEXUS</b>\n\n"
                f"🔔 وضعیت ارسال اعلان: <b>{notif_status}</b>\n"
                f"🎯 فیلتر حداقل امتیاز تطابق هوش مصنوعی: <b>{min_score}%</b>\n\n"
                "جهت تغییر مقادیر، روی دکمه‌های شیشه‌ای زیر کلیک کنید:"
            )
            kb = _kb([
                [("🔔 تغییر وضعیت اعلان (روشن/خاموش)", "settg:toggle_notify")],
                [("🎯 حداقل ۰٪ (همه)", "settg:score:0"), ("🎯 حداقل ۵۰٪", "settg:score:50")],
                [("🎯 حداقل ۷۰٪", "settg:score:70"), ("🎯 حداقل ۸۵٪", "settg:score:85")],
                [("⬅️ بازگشت به منو", "quick:start")],
            ])
            await send_text(token, str(target_chat_id), text, kb)

    @router.message(Command("settings"))
    @router.message(F.text == "⚙️ تنظیمات و فیلتر")
    async def cmd_settings(message: Message):
        if not await _authorized(message.chat.id):
            return
        await _show_settings(message.chat.id)

    # --------------------------- Callbacks ---------------------------------- #
    async def _load_project(session, project_id: int):
        from app.models import Project
        return (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()

    @router.callback_query(F.data.startswith("quick:"))
    async def cb_quick(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        action = call.data.split(":")[1]
        await call.answer()
        if action == "projects":
            await _show_projects(call.message.chat.id)
        elif action == "proposals":
            await _show_proposals(call.message.chat.id)
        elif action == "scan":
            progress = await call.message.answer("⚡ <b>در حال استعلام و اسکن زنده تمام پلتفرم‌ها...</b>", parse_mode="HTML")
            await _execute_instant_scan(call.message.chat.id, message_to_edit=progress)
        elif action == "status":
            await _show_status(call.message.chat.id)
        elif action == "settings":
            await _show_settings(call.message.chat.id)
        elif action == "help":
            await cmd_help(call.message)

    @router.callback_query(F.data.startswith("settg:"))
    async def cb_settings_action(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        action_parts = call.data.split(":")
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import TelegramSetting
            s = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
            if s:
                if action_parts[1] == "toggle_notify":
                    s.notify_enabled = not s.notify_enabled
                elif action_parts[1] == "score" and len(action_parts) > 2:
                    s.notify_min_score = int(action_parts[2])
                await session.commit()

                notif_status = "فعال ✅" if s.notify_enabled else "غیرفعال ❌"
                min_score = s.notify_min_score or 0
                text = (
                    "⚙️ <b>تنظیمات ربات تلگرام NEXUS</b>\n\n"
                    f"🔔 وضعیت ارسال اعلان: <b>{notif_status}</b>\n"
                    f"🎯 فیلتر حداقل امتیاز تطابق هوش مصنوعی: <b>{min_score}%</b>\n\n"
                    "جهت تغییر مقادیر، روی دکمه‌های شیشه‌ای زیر کلیک کنید:"
                )
                kb = _kb([
                    [("🔔 تغییر وضعیت اعلان (روشن/خاموش)", "settg:toggle_notify")],
                    [("🎯 حداقل ۰٪ (همه)", "settg:score:0"), ("🎯 حداقل ۵۰٪", "settg:score:50")],
                    [("🎯 حداقل ۷۰٪", "settg:score:70"), ("🎯 حداقل ۸۵٪", "settg:score:85")],
                    [("⬅️ بازگشت به منو", "quick:start")],
                ])
                try:
                    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass
        await call.answer("تنظیمات ذخیره شد")

    @router.callback_query(F.data.startswith("appr:"))
    async def cb_approve(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        pid = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import ProjectStatus
            from datetime import datetime, timezone
            project = await _load_project(session, pid)
            if project is None:
                await call.answer("پروژه یافت نشد", show_alert=True)
                return
            if project.status not in ("recommended", "analyzed", "skipped", "discovered"):
                await call.answer(f"تأیید از وضعیت فعلی ({STATUS_FA.get(project.status, project.status)}) مجاز نیست", show_alert=True)
                return
            project.status = ProjectStatus.APPROVED_FOR_PROPOSAL.value
            project.approved_at = datetime.now(timezone.utc)
            await log_execution(session, "telegram", f"project {pid} approved via Telegram")
            await session.commit()

        kb = _kb([
            [("📝 تولید پیشنهاد هوشمند", f"gen:{pid}"), ("🔍 تحلیل AI", f"anlz:{pid}")],
            [("📄 جزئیات پروژه", f"viewp:{pid}")],
        ])
        await call.message.edit_reply_markup(reply_markup=kb)
        await call.message.answer(
            "✅ <b>پروژه با موفقیت تأیید شد!</b>\nاکنون می‌توانید استراتژی را مشخص و پیشنهاد قیمت تدوین نمایید:",
            reply_markup=_kb([[("📝 تدوین پیشنهاد با AI", f"gen:{pid}")]]),
            parse_mode="HTML"
        )
        await call.answer("پروژه تأیید شد")

    @router.callback_query(F.data.startswith("rej:"))
    async def cb_reject(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        pid = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import ProjectStatus
            from datetime import datetime, timezone
            project = await _load_project(session, pid)
            if project is None:
                await call.answer("پروژه یافت نشد", show_alert=True)
                return
            if project.status == "proposal_submitted":
                await call.answer("برای این پروژه پیشنهاد ارسال شده است", show_alert=True)
                return
            project.status = ProjectStatus.REJECTED_BY_OWNER.value
            project.rejected_at = datetime.now(timezone.utc)
            await log_execution(session, "telegram", f"project {pid} rejected via Telegram")
            await session.commit()
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer("❌ <b>پروژه رد شد</b> و پیشنهادی برای آن تدوین نخواهد شد.", parse_mode="HTML")
        await call.answer("پروژه رد شد")

    @router.callback_query(F.data.startswith("anlz:"))
    async def cb_analyze(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        pid = int(call.data.split(":")[1])
        await call.message.answer("🤖 <b>در حال ارزیابی تخصصی پروژه توسط هوش مصنوعی NEXUS...</b>", parse_mode="HTML")
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.services.analyzer import run_analysis
            from app.models import Platform, Project
            analysis = await run_analysis(session, pid)
            row = (await session.execute(
                select(Project, Platform).join(Platform, Project.platform_id == Platform.id)
                .where(Project.id == pid)
            )).first()
            if row:
                project, platform = row
                text = project_card(project, analysis, platform_name=platform.name)
                kb = project_keyboard(project.id, canonical_url=project.canonical_url)
                await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await call.answer("تحلیل انجام شد")

    @router.callback_query(F.data.startswith("viewp:"))
    async def cb_view(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        pid = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Platform, Project, ProjectAnalysis
            row = (await session.execute(
                select(Project, Platform).join(Platform, Project.platform_id == Platform.id)
                .where(Project.id == pid))).first()
            if row is None:
                await call.answer("پروژه یافت نشد", show_alert=True)
                return
            project, platform = row
            analysis = (await session.execute(
                select(ProjectAnalysis).where(ProjectAnalysis.project_id == pid)
                .order_by(ProjectAnalysis.id.desc()).limit(1))).scalar_one_or_none()

            text = project_card(project, analysis, platform_name=platform.name)
            text += f"\n\nوضعیت فعلی: <b>{STATUS_FA.get(project.status, project.status)}</b>"
            if project.description:
                desc_snippet = html.escape(project.description[:500])
                text += f"\n\n📝 <b>توضیحات کارفرما:</b>\n{desc_snippet}..."
            if analysis:
                risks = analysis.technical_risks or []
                if risks:
                    text += "\n\n⚠️ <b>ریسک‌های فنی:</b> " + html.escape("؛ ".join(risks[:3]))
                if analysis.clarification_questions:
                    text += "\n❓ <b>پرسش‌های کلیدی:</b> " + html.escape("؛ ".join(analysis.clarification_questions[:3]))

            kb_rows = [
                [("📝 تولید پیشنهاد", f"gen:{pid}"), ("✅ تأیید", f"appr:{pid}"), ("❌ رد", f"rej:{pid}")],
            ]
            if project.canonical_url:
                kb_rows.append([("🌐 مشاهده مستقیم در سایت " + platform.name, project.canonical_url)])
            kb = _kb(kb_rows)
        await call.message.answer(text[:4000], reply_markup=kb, disable_web_page_preview=True, parse_mode="HTML")
        await call.answer()

    @router.callback_query(F.data.startswith("gen:"))
    async def cb_generate(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        pid = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Proposal
            proposal = (await session.execute(
                select(Proposal).where(Proposal.project_id == pid))).scalar_one_or_none()
            prop_id = proposal.id if proposal else pid
            await call.message.answer(
                "🎯 <b>استراتژی قیمت‌گذاری و لحن پیشنهاد را انتخاب کنید:</b>",
                reply_markup=strategy_keyboard(prop_id),
                parse_mode="HTML"
            )
        await call.answer()

    @router.callback_query(F.data.startswith("genb:"))
    async def cb_generate_bid(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        _, proposal_id, strategy = call.data.split(":")
        await call.message.answer(f"✍️ <b>در حال تولید پیشنهاد با استراتژی {strategy}...</b>", parse_mode="HTML")
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Proposal, ProposalVersion, Project
            proposal = (await session.execute(
                select(Proposal).where(Proposal.id == int(proposal_id)))).scalar_one_or_none()
            pid = proposal.project_id if proposal else int(proposal_id)
            try:
                await proposal_service.generate_for_project(session, pid, strategy=strategy, actor="telegram")
            except ValueError as exc:
                await call.message.answer(f"⚠️ {html.escape(str(exc))}")
                await call.answer()
                return

            proposal = (await session.execute(
                select(Proposal).where(Proposal.project_id == pid))).scalar_one_or_none()
            if proposal is None or proposal.current_version_id is None:
                await call.message.answer("⚠️ پیشنهاد تولید نشد.")
                await call.answer()
                return
            version = (await session.execute(
                select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id))).scalar_one_or_none()
            project = (await session.execute(
                select(Project).where(Project.id == pid))).scalar_one_or_none()

        text = _proposal_text(version)
        kb = proposal_keyboard(proposal.id, project_url=project.canonical_url if project else "")
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await call.answer("پیشنهاد آماده شد")

    @router.callback_query(F.data.startswith("prop:"))
    async def cb_proposal(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Proposal, ProposalVersion, Project
            proposal = (await session.execute(
                select(Proposal).where(Proposal.id == proposal_id))).scalar_one_or_none()
            if proposal is None:
                await call.answer("یافت نشد", show_alert=True)
                return
            version = (await session.execute(
                select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id))).scalar_one_or_none()
            project = (await session.execute(
                select(Project).where(Project.id == proposal.project_id))).scalar_one_or_none()

        kb = proposal_keyboard(proposal_id, project_url=project.canonical_url if project else "")
        await call.message.answer(_proposal_text(version), reply_markup=kb, parse_mode="HTML")
        await call.answer()

    @router.callback_query(F.data.startswith("regen:"))
    async def cb_regen(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        await call.message.answer("🔄 <b>در حال بازنویسی و ارتقای کیفیت متن پیشنهاد...</b>", parse_mode="HTML")
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Proposal, ProposalVersion, Project
            try:
                await proposal_service.regenerate(session, proposal_id, actor="telegram")
                proposal = (await session.execute(
                    select(Proposal).where(Proposal.id == proposal_id))).scalar_one()
                version = (await session.execute(
                    select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id))).scalar_one()
                project = (await session.execute(
                    select(Project).where(Project.id == proposal.project_id))).scalar_one_or_none()
            except ValueError as exc:
                await call.message.answer(f"⚠️ {html.escape(str(exc))}")
                await call.answer()
                return

        kb = proposal_keyboard(proposal_id, project_url=project.canonical_url if project else "")
        await call.message.answer(_proposal_text(version), reply_markup=kb, parse_mode="HTML")
        await call.answer("نسخه جدید آماده شد")

    @router.callback_query(F.data.startswith("strat:"))
    async def cb_strategy(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        await call.message.answer("🎯 <b>استراتژی قیمت و سبک پیشنهاد:</b>", reply_markup=strategy_keyboard(proposal_id), parse_mode="HTML")
        await call.answer()

    @router.callback_query(F.data.startswith("editp:"))
    async def cb_edit(call: CallbackQuery, state: FSMContext):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        await state.set_state(EditProposal.waiting_content)
        await state.update_data(proposal_id=proposal_id)
        await call.message.answer("✍️ <b>متن جدید پیشنهاد را در قالب یک پیام ارسال کنید:</b>", parse_mode="HTML")
        await call.answer()

    @router.message(EditProposal.waiting_content)
    async def receive_edit(message: Message, state: FSMContext):
        if not await _authorized(message.chat.id):
            await state.clear()
            return
        data = await state.get_data()
        proposal_id = data.get("proposal_id")
        content = (message.text or "").strip()
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Project, Proposal
            try:
                version = await proposal_service.edit_proposal(session, proposal_id, content)
                proposal = (await session.execute(select(Proposal).where(Proposal.id == proposal_id))).scalar_one_or_none()
                project = (await session.execute(select(Project).where(Project.id == proposal.project_id))).scalar_one_or_none() if proposal else None
            except ValueError as exc:
                await message.answer(f"⚠️ {html.escape(str(exc))}\nمتن را دوباره بفرستید یا /help را بزنید.")
                return

        await state.clear()
        kb = proposal_keyboard(proposal_id, project_url=project.canonical_url if project else "")
        await message.answer("✅ <b>نسخه ویرایش‌شده ذخیره شد.</b>\n\n" + _proposal_text(version),
                             reply_markup=kb, parse_mode="HTML")

    @router.callback_query(F.data.startswith("editbid:"))
    async def cb_edit_bid(call: CallbackQuery, state: FSMContext):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        await state.set_state(EditBid.waiting_bid)
        await state.update_data(proposal_id=proposal_id)
        await call.message.answer(
            "💰 <b>تنظیم قیمت و مدت تحویل</b>\n\n"
            "لطفاً مبلغ پیشنهادی (به تومان) و تعداد روز تحویل را با یک فاصله ارسال نمایید:\n\n"
            "مثال: <code>15000000 5</code> (۱۵ میلیون تومان در ۵ روز)",
            parse_mode="HTML"
        )
        await call.answer()

    @router.message(EditBid.waiting_bid)
    async def receive_edit_bid(message: Message, state: FSMContext):
        if not await _authorized(message.chat.id):
            await state.clear()
            return
        data = await state.get_data()
        proposal_id = data.get("proposal_id")
        parts = (message.text or "").strip().split()
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await message.answer(
                "⚠️ فرمت نامعتبر است. لطفاً عدد قیمت و روز را با فاصله بفرستید:\n"
                "مثال: <code>12000000 7</code>"
            )
            return

        price = int(parts[0])
        days = int(parts[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Proposal, ProposalVersion, Project
            proposal = (await session.execute(
                select(Proposal).where(Proposal.id == proposal_id)
            )).scalar_one_or_none()
            if proposal and proposal.current_version_id:
                version = (await session.execute(
                    select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id)
                )).scalar_one_or_none()
                if version:
                    new_v = ProposalVersion(
                        proposal_id=proposal.id,
                        version_no=version.version_no + 1,
                        content=version.content,
                        strategy=version.strategy,
                        price=price,
                        delivery_days=days,
                        quality_score=version.quality_score,
                        word_count=version.word_count,
                    )
                    session.add(new_v)
                    await session.flush()
                    proposal.current_version_id = new_v.id
                    await session.commit()
                    await state.clear()

                    project = (await session.execute(select(Project).where(Project.id == proposal.project_id))).scalar_one_or_none()
                    kb = proposal_keyboard(proposal_id, project_url=project.canonical_url if project else "")
                    await message.answer(
                        "✅ <b>قیمت و زمان تحویل با موفقیت به‌روزرسانی شد:</b>\n\n" + _proposal_text(new_v),
                        reply_markup=kb,
                        parse_mode="HTML"
                    )
                    return

        await state.clear()
        await message.answer("خطا در به‌روزرسانی قیمت پیشنهاد.")

    @router.callback_query(F.data.startswith("submit:"))
    async def cb_submit(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        await call.message.answer("🚀 <b>در حال پردازش و ثبت پیشنهاد نهایی...</b>", parse_mode="HTML")
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                result = await submission_service.request_submission(session, proposal_id, actor="telegram")
            except ValueError as exc:
                await call.message.answer(f"⚠️ {html.escape(str(exc))}")
                await call.answer()
                return

        if result.get("method") == "assisted" and result.get("status") == "assisted_pending":
            assisted = result["assisted"]
            text = (
                "📤 <b>دستورالعمل ارسال دستی پیشنهاد</b>\n\n" +
                html.escape(assisted["instructions"]) +
                f"\n\n💵 قیمت: <b>{assisted['price_display']}</b>"
                f"\n⏳ تحویل: <b>{assisted['delivery_days']} روز</b>\n\n"
                "پس از ثبت پیشنهاد در پلتفرم، دکمه تأیید زیر را بزنید:"
            )
            kb_rows = []
            if assisted.get("url"):
                kb_rows.append([("🌐 باز کردن صفحه پروژه در سایت", assisted["url"])])
            kb_rows.append([("✔️ ارسال کردم و ثبت شد", f"assist:{result['id']}")])
            await call.message.answer(text, reply_markup=_kb(kb_rows), parse_mode="HTML")
        else:
            status_fa = "با موفقیت ارسال شد ✅" if result.get("status") == "submitted" else f"ناموفق ❌ ({result.get('error')})"
            await call.message.answer(f"🚀 <b>نتیجه ارسال پیشنهاد:</b> {status_fa}", parse_mode="HTML")
        await call.answer()

    @router.callback_query(F.data.startswith("assist:"))
    async def cb_assist_confirm(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        submission_id = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                await submission_service.confirm_assisted(session, submission_id, actor="telegram")
            except ValueError as exc:
                await call.message.answer(f"⚠️ {html.escape(str(exc))}")
                await call.answer()
                return
        await call.message.answer("✅ <b>ارسال دستی تأیید و در سیستم ثبت شد.</b> تاریخچه در داشبورد ثبت گردید.", parse_mode="HTML")
        await call.answer("ثبت شد")

    return router


def _proposal_text(version) -> str:
    if version is None:
        return "نسخه‌ای موجود نیست."
    q = version.quality_score
    q_line = f"{q}/100" if q is not None else "—"
    warn = " ⚠️ (زیر حد آستانه)" if q is not None and q < 75 else ""
    return (
        f"<b>📝 پیشنهاد (نسخه {version.version_no} - {version.strategy})</b>\n"
        f"💵 قیمت: {format_toman(version.price)} | ⏳ تحویل: {version.delivery_days} روز\n"
        f"🏁 کیفیت: {q_line}{warn} | 📏 {version.word_count} کلمه\n\n"
        f"{html.escape(version.content)}"
    )


# --------------------------------------------------------------------------- #
# Polling lifecycle                                                           #
# --------------------------------------------------------------------------- #
async def start_polling(session_factory) -> None:
    """Long-running task: starts aiogram polling when a token is configured
    and restarts it when the token changes in the dashboard."""
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    global _supervisor_wakeup
    _supervisor_wakeup = asyncio.Event()

    current_hash = None
    dp = None
    bot = None
    polling_task = None
    log.info("telegram supervisor started")

    while True:
        try:
            async with session_factory() as session:
                from app.models import TelegramSetting
                setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
                token = decrypt_token(setting) if setting and setting.bot_token_encrypted else ""
                enabled = bool(setting and setting.enabled and setting.mode == "polling" and token)
                token_hash = hashlib.sha256(token.encode()).hexdigest() if token else None

            if enabled and token_hash != current_hash:
                if polling_task:
                    polling_task.cancel()
                    try:
                        await polling_task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass
                dp = Dispatcher(storage=MemoryStorage())
                dp.include_router(build_router())
                bot = _bot_for(token)
                await reset_bot()  # force fresh Bot from token
                bot = _bot_for(token)
                polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
                current_hash = token_hash
                async with session_factory() as session:
                    from app.models import TelegramSetting
                    setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one()
                    setting.connection_status = "connected"
                    await session.commit()
                log.info("telegram polling started")
            elif not enabled and current_hash is not None:
                if polling_task:
                    polling_task.cancel()
                    polling_task = None
                current_hash = None
                async with session_factory() as session:
                    from app.models import TelegramSetting
                    setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one()
                    if setting:
                        setting.connection_status = "disconnected"
                        await session.commit()
                log.info("telegram polling stopped")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram supervisor error: %s", exc)

        try:
            await asyncio.wait_for(_supervisor_wakeup.wait(), timeout=10.0)
            _supervisor_wakeup.clear()
        except asyncio.TimeoutError:
            pass


async def stop_polling_task(task: asyncio.Task | None) -> None:
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
