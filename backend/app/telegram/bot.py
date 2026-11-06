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

STATUS_FA = {
    "discovered": "کشف شد", "pending_analysis": "در انتظار تحلیل", "analyzing": "در حال تحلیل",
    "analyzed": "تحلیل شد", "recommended": "پیشنهاد ارسال (در انتظار تأیید شما)",
    "skipped": "صرف‌نظر شد (امتیاز پایین)", "approved_for_proposal": "تأییدشده - آماده تولید پیشنهاد",
    "rejected_by_owner": "ردشده توسط شما", "proposal_generating": "در حال تولید پیشنهاد",
    "proposal_ready": "پیشنهاد آماده بررسی", "proposal_submitted": "پیشنهاد ارسال شد",
    "analysis_failed": "تحلیل ناموفق", "unavailable": "ناموجود",
}


def new_pairing_code() -> str:
    return f"{secrets.choice(_pairing_adjectives)}-{secrets.randbelow(900) + 100}"


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
# Cards                                                                       #
# --------------------------------------------------------------------------- #
def _kb(rows: list[list[tuple[str, str]]]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows
    ])


def project_card(project, analysis=None, platform_name: str = "") -> str:
    lines = [f"<b>🆕 پروژه جدید - {html.escape(platform_name or '')}</b>",
             f"<b>{html.escape(project.title[:120])}</b>", ""]
    budget = format_toman(project.budget_min) if project.budget_min else "نامشخص"
    budget_max = format_toman(project.budget_max) if project.budget_max else None
    lines.append(f"💰 بودجه: {budget}" + (f" تا {budget_max}" if budget_max else ""))
    if project.deadline:
        lines.append(f"⏳ مهلت: {project.deadline.strftime('%Y-%m-%d')}")
    if project.skills:
        lines.append("🛠 مهارت‌ها: " + html.escape("، ".join(project.skills[:6])))
    if analysis is not None:
        lines += ["", f"🎯 امتیاز تطابق: <b>{analysis.match_score}/100</b>",
                  f"📊 تحلیل: {html.escape((analysis.summary or '')[:400])}",
                  "💵 پیشنهاد متوازن: " + _bid_line(analysis.balanced_bid)]
    return "\n".join(lines)


def _bid_line(bid: dict) -> str:
    if not bid:
        return "—"
    price = format_toman(bid.get("price"))
    days = bid.get("delivery_days")
    return f"{price} در {days} روز" if days else price


def project_keyboard(project_id: int) -> "InlineKeyboardMarkup":
    return _kb([
        [("✅ تأیید پروژه", f"appr:{project_id}"), ("❌ رد پروژه", f"rej:{project_id}")],
        [("📄 جزئیات بیشتر", f"viewp:{project_id}")],
    ])


def proposal_keyboard(proposal_id: int) -> "InlineKeyboardMarkup":
    return _kb([
        [("✍️ ویرایش متن", f"editp:{proposal_id}"), ("🔄 تولید مجدد", f"regen:{proposal_id}")],
        [("🎯 استراتژی قیمت", f"strat:{proposal_id}"),
         ("🚀 تأیید و ارسال", f"submit:{proposal_id}")],
    ])


def strategy_keyboard(proposal_id: int) -> "InlineKeyboardMarkup":
    return _kb([
        [("💬 تهاجمی", f"genb:{proposal_id}:aggressive"),
         ("⚖️ متوازن", f"genb:{proposal_id}:balanced"),
         ("💎 پرمیوم", f"genb:{proposal_id}:premium")],
        [("بازگشت", f"prop:{proposal_id}")],
    ])


async def send_project_notification(token: str, chat_id: str, project, analysis=None,
                                    platform_name: str = "") -> None:
    text = project_card(project, analysis, platform_name=platform_name)
    kb = project_keyboard(project.id) if analysis is None else _kb([
        [("✅ تأیید پروژه", f"appr:{project.id}"), ("❌ رد پروژه", f"rej:{project.id}")],
        [("📝 تولید پیشنهاد", f"gen:{project.id}"), ("📄 جزئیات", f"viewp:{project.id}")],
    ])
    await send_text(token, chat_id, text, kb)


# --------------------------------------------------------------------------- #
# Outbox delivery handler                                                     #
# --------------------------------------------------------------------------- #
@handler("notify.telegram")
async def deliver_notification(session, payload: dict) -> None:
    from app.models import AuthorizedChatID, Notification, TelegramSetting

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

    kb = None
    if notification.type in ("project.new", "analysis.done", "proposal.ready", "submission.update"):
        pid = notification.project_id
        if notification.type == "project.new":
            kb = project_keyboard(pid)
        elif notification.type == "analysis.done":
            kb = _kb([[("📝 تولید پیشنهاد", f"gen:{pid}"), ("📄 جزئیات", f"viewp:{pid}")],
                      [("✅ تأیید", f"appr:{pid}"), ("❌ رد", f"rej:{pid}")]])
        elif notification.type == "proposal.ready":
            prop_id = (notification.data or {}).get("proposal_id")
            if prop_id:
                kb = proposal_keyboard(prop_id)
        elif notification.type == "submission.update":
            sub_id = (notification.data or {}).get("submission_id")
            if sub_id and (notification.data or {}).get("status") == "assisted_pending":
                kb = _kb([[("✔️ تأیید ارسال دستی", f"assist:{sub_id}")]])

    text = f"<b>{html.escape(notification.title)}</b>"
    if notification.body:
        text += f"\n{html.escape(notification.body)}"
    if (notification.data or {}).get("url"):
        text += f"\n🔗 {notification.data['url']}"
    for chat in chats:
        await send_text(token, chat.chat_id, text, kb)


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
        if setting is None or not setting.pairing_code or code.strip() != setting.pairing_code:
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
        setting_session.add(row)
        await setting_session.commit()
        return True

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext):
        session_factory = get_session_factory()
        async with session_factory() as session:
            args = (message.text or "").split(maxsplit=1)
            code = args[1].strip() if len(args) > 1 else ""
            paired = await _pair(session, message, code) if code else False
            if paired:
                await message.answer("✅ چت شما تأیید شد!\nاز این پس اعلان پروژه‌ها و پیشنهادها اینجا ارسال می‌شود.\n\n/help برای راهنما")
                return
            if await _authorized(message.chat.id):
                await message.answer(
                    "👋 سلام!\nاین ربات دستیار کشف پروژه‌های فریلنسری شماست.\n\n"
                    "/projects - آخرین پروژه‌های پیشنهادی\n/status - خلاصه وضعیت\n/help - راهنما")
                return
            await message.answer(
                "🔒 این چت تأیید نشده است.\n"
                "برای اتصال، در داشبورد وب به بخش «تلگرام» بروید، کد جفت‌سازی را ببینید و اینجا بفرستید:\n\n"
                "/start <کد>")

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        if not await _authorized(message.chat.id):
            return
        await message.answer(
            "🤖 <b>راهنما</b>\n"
            "/projects - پروژه‌های پیشنهادی اخیر\n/status - خلاصه وضعیت\n\n"
            "در اعلان‌ها:\n"
            "✅ تأیید پروژه → فقط اجازه تولید پیشنهاد\n"
            "📝 تولید پیشنهاد → ساخت پروپوزال (پس از تأیید)\n"
            "🚀 تأیید و ارسال → مرحله دوم تأیید برای ارسال\n"
            "هیچ پیشنهادی بدون تأیید دوم شما ارسال نمی‌شود.")

    @router.message(Command("projects"))
    async def cmd_projects(message: Message):
        if not await _authorized(message.chat.id):
            return
        from app.models import Platform, Project, ProjectAnalysis
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Platform, Project, ProjectAnalysis, TelegramSetting
            rows = (await session.execute(
                select(Project, Platform)
                .join(Platform, Project.platform_id == Platform.id)
                .where(Project.status.in_(["recommended", "approved_for_proposal", "proposal_ready"]))
                .order_by(Project.first_discovered_at.desc()).limit(5)
            )).all()
            if not rows:
                await message.answer("فعلاً پروژه پیشنهادی جدیدی نیست.")
                return
            for project, platform in rows:
                analysis = (await session.execute(
                    select(ProjectAnalysis).where(ProjectAnalysis.project_id == project.id)
                    .order_by(ProjectAnalysis.id.desc()).limit(1)
                )).scalar_one_or_none()
                setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
                token = decrypt_token(setting) if setting and setting.bot_token_encrypted else ""
                await send_project_notification(token, str(message.chat.id), project, analysis,
                                                platform_name=platform.name)

    @router.message(Command("status"))
    async def cmd_status(message: Message):
        if not await _authorized(message.chat.id):
            return
        from sqlalchemy import func as safunc
        from app.models import Project, Proposal, ProposalSubmission
        session_factory = get_session_factory()
        async with session_factory() as session:
            n_projects = (await session.execute(select(safunc.count(Project.id)))).scalar()
            n_recommended = (await session.execute(
                select(safunc.count(Project.id)).where(Project.status == "recommended"))).scalar()
            n_proposals = (await session.execute(select(safunc.count(Proposal.id)))).scalar()
            n_submitted = (await session.execute(
                select(safunc.count(ProposalSubmission.id)).where(
                    ProposalSubmission.status == "submitted"))).scalar()
        await message.answer(
            f"📊 <b>خلاصه وضعیت</b>\n"
            f"پروژه‌های کشف‌شده: {n_projects}\n"
            f"در انتظار تأیید شما: {n_recommended}\n"
            f"پیشنهادهای تولیدشده: {n_proposals}\n"
            f"پیشنهادهای ارسال‌شده: {n_submitted}")

    # ------------------------------ callbacks ------------------------------ #
    async def _load_project(session, project_id: int):
        from app.models import Project
        return (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()

    @router.callback_query(F.data.startswith("appr:"))
    async def cb_approve(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        pid = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Project, ProjectStatus
            from datetime import datetime, timezone
            project = await _load_project(session, pid)
            if project is None:
                await call.answer("پروژه یافت نشد", show_alert=True)
                return
            if project.status not in ("recommended", "analyzed", "skipped"):
                await call.answer(f"تأیید از وضعیت فعلی ({STATUS_FA.get(project.status, project.status)}) مجاز نیست", show_alert=True)
                return
            project.status = ProjectStatus.APPROVED_FOR_PROPOSAL.value
            project.approved_at = datetime.now(timezone.utc)
            await log_execution(session, "telegram", f"project {pid} approved via Telegram")
            await session.commit()
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer(
            "✅ پروژه تأیید شد. حالا می‌توانید پیشنهاد تولید کنید (تولید پیشنهاد = اجازه نگارش، نه ارسال).",
            reply_markup=_kb([[("📝 تولید پیشنهاد", f"gen:{pid}")]]))
        await call.answer("تأیید شد")

    @router.callback_query(F.data.startswith("rej:"))
    async def cb_reject(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        pid = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Project, ProjectStatus
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
        await call.message.answer("❌ پروژه رد شد و پیشنهادی برای آن ساخته نمی‌شود.")
        await call.answer("رد شد")

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
            text += f"\n\nوضعیت: {STATUS_FA.get(project.status, project.status)}\n🔗 {project.canonical_url}"
            if analysis:
                risks = analysis.technical_risks or []
                if risks:
                    text += "\n⚠️ ریسک‌ها: " + html.escape("؛ ".join(risks[:3]))
                if analysis.clarification_questions:
                    text += "\n❓ پرسش‌ها: " + html.escape("؛ ".join(analysis.clarification_questions[:3]))
        await call.message.answer(text[:4000])
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
            if proposal is None:
                await call.message.answer("🎯 استراتژی قیمت را انتخاب کنید:", reply_markup=strategy_keyboard(pid))
            else:
                await call.message.answer("🎯 استراتژی قیمت:", reply_markup=strategy_keyboard(proposal.id))
        await call.answer()

    @router.callback_query(F.data.startswith("genb:"))
    async def cb_generate_bid(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        _, proposal_id, strategy = call.data.split(":")
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Proposal
            proposal = (await session.execute(
                select(Proposal).where(Proposal.id == int(proposal_id)))).scalar_one_or_none()
            pid = proposal.project_id if proposal else int(proposal_id)
            try:
                await proposal_service.generate_for_project(session, pid, strategy=strategy, actor="telegram")
            except ValueError as exc:
                await call.message.answer(f"⚠️ {html.escape(str(exc))}")
                await call.answer()
                return
            from app.models import Proposal, ProposalVersion
            proposal = (await session.execute(
                select(Proposal).where(Proposal.project_id == pid))).scalar_one_or_none()
            if proposal is None or proposal.current_version_id is None:
                await call.message.answer("⚠️ پیشنهاد تولید نشد.")
                await call.answer()
                return
            version = (await session.execute(
                select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id))).scalar_one_or_none()
        text = _proposal_text(version)
        await call.message.answer(text, reply_markup=proposal_keyboard(int(proposal_id)))
        await call.answer("پیشنهاد آماده شد")

    @router.callback_query(F.data.startswith("prop:"))
    async def cb_proposal(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        session_factory = get_session_factory()
        async with session_factory() as session:
            from app.models import Proposal, ProposalVersion
            proposal = (await session.execute(
                select(Proposal).where(Proposal.id == proposal_id))).scalar_one_or_none()
            if proposal is None:
                await call.answer("یافت نشد", show_alert=True)
                return
            version = (await session.execute(
                select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id))).scalar_one_or_none()
        await call.message.answer(_proposal_text(version), reply_markup=proposal_keyboard(proposal_id))
        await call.answer()

    @router.callback_query(F.data.startswith("regen:"))
    async def cb_regen(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        await call.message.answer("🔄 در حال تولید نسخه جدید...")
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                await proposal_service.regenerate(session, proposal_id, actor="telegram")
                from app.models import Proposal, ProposalVersion
                proposal = (await session.execute(
                    select(Proposal).where(Proposal.id == proposal_id))).scalar_one()
                version = (await session.execute(
                    select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id))).scalar_one()
            except ValueError as exc:
                await call.message.answer(f"⚠️ {html.escape(str(exc))}")
                await call.answer()
                return
        await call.message.answer(_proposal_text(version), reply_markup=proposal_keyboard(proposal_id))
        await call.answer("نسخه جدید آماده شد")

    @router.callback_query(F.data.startswith("strat:"))
    async def cb_strategy(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        await call.message.answer("🎯 استراتژی قیمت:", reply_markup=strategy_keyboard(proposal_id))
        await call.answer()

    @router.callback_query(F.data.startswith("editp:"))
    async def cb_edit(call: CallbackQuery, state: FSMContext):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
        await state.set_state(EditProposal.waiting_content)
        await state.update_data(proposal_id=proposal_id)
        await call.message.answer("✍️ متن جدید پیشنهاد را بفرستید (یک پیام متنی):")
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
            try:
                version = await proposal_service.edit_proposal(session, proposal_id, content)
            except ValueError as exc:
                await message.answer(f"⚠️ {html.escape(str(exc))}\nمتن را دوباره بفرستید یا /help را بزنید.")
                return
        await state.clear()
        await message.answer("✅ نسخه ویرایش‌شده ذخیره شد.\n" + _proposal_text(version),
                             reply_markup=proposal_keyboard(proposal_id))

    @router.callback_query(F.data.startswith("submit:"))
    async def cb_submit(call: CallbackQuery):
        if not await _authorized(call.message.chat.id):
            await call.answer("چت تأیید نشده است", show_alert=True)
            return
        proposal_id = int(call.data.split(":")[1])
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
            text = ("📤 <b>ارسال دستی</b>\n" + html.escape(assisted["instructions"]) +
                    f"\n\n🔗 {assisted['url']}\n💵 قیمت: {assisted['price_display']}"
                    f"\n⏳ تحویل: {assisted['delivery_days']} روز\n\n"
                    "پس از ارسال در پلتفرم، تأیید کنید:")
            await call.message.answer(text, reply_markup=_kb([[("✔️ ارسال کردم", f"assist:{result['id']}")]]))
        else:
            status_fa = "ارسال شد" if result.get("status") == "submitted" else f"ناموفق: {result.get('error')}"
            await call.message.answer(f"🚀 نتیجه ارسال: {status_fa}")
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
        await call.message.answer("✅ ارسال دستی ثبت شد. تاریخچه در داشبورد قابل مشاهده است.")
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
        await asyncio.sleep(10)


async def stop_polling_task(task: asyncio.Task | None) -> None:
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
