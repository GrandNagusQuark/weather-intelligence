"""Account scoped manual feedback with an exact review before transmission."""

import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic
import uuid

from .const import DOMAIN, PROTOTYPE_VERSION
from .feedback_protocol import FEEDBACK_PATH, validate_feedback, validate_message
from .onboarding_accounts import async_actor
from .outage_protocol import PROJECT_ORIGIN
from .reporting_audit import ReportingAudit
from .reporting_device import mobile_report_context
from .reporting_http import ReportTransport

REVIEW_SECONDS = 900
MAX_ACTORS = 100
MAX_FEEDBACK_PER_HOUR = 2


def owned_feedback_devices(hass, actor):
    return [{"id": entry.entry_id, "name": str(entry.data.get("device_name") or entry.title or "Companion device")}
            for entry in hass.config_entries.async_entries("mobile_app")
            if entry.data.get("user_id") == actor.id]


class FeedbackService:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.rows = {}
        self.audits = {}
        self.lock = asyncio.Lock()
        self.budget_store = None

    async def reserve_slot(self, feedback_id):
        lock = self.hass.data.setdefault(DOMAIN, {}).setdefault("feedback_budget_lock", asyncio.Lock())
        async with lock:
            await self._reserve_slot(feedback_id)

    async def _reserve_slot(self, feedback_id):
        """One durable installation budget shared by every signed in account."""
        if self.budget_store is None:
            from homeassistant.helpers.storage import Store
            self.budget_store = self.hass.data.setdefault(DOMAIN, {}).setdefault("feedback_budget_store",
                Store(self.hass, 1, f"{DOMAIN}.feedback_budget"))
        saved = await self.budget_store.async_load()
        now = datetime.now(timezone.utc)
        recent = []
        for item in (saved or {}).get("submissions", []):
            try:
                stamp = datetime.fromisoformat(item["reserved_at"])
                if stamp.tzinfo is None or not isinstance(item["feedback_id"], str):
                    raise ValueError
                # Clock rollback must not create extra slots.
                if stamp > now - timedelta(hours=1):
                    recent.append(item)
            except (ValueError, TypeError, KeyError):
                raise ValueError("The feedback limit could not be verified. Please try later.") from None
        if any(item["feedback_id"] == feedback_id for item in recent):
            return
        if len(recent) >= MAX_FEEDBACK_PER_HOUR:
            raise ValueError("This Home Assistant installation can send two feedback submissions per hour. Please try later.")
        await self.budget_store.async_save({"submissions": [*recent, {
            "feedback_id": feedback_id, "reserved_at": now.isoformat()}]})

    def actor_row(self, actor):
        now = monotonic()
        self.rows = {key: row for key, row in self.rows.items() if now - row["touched"] < 3600}
        self.audits = {key: audit for key, audit in self.audits.items() if key in self.rows}
        if actor.id not in self.rows:
            if len(self.rows) >= MAX_ACTORS:
                raise ValueError("Feedback is busy. Please try later.")
            self.rows[actor.id] = {"touched": now, "review": None}
        row = self.rows[actor.id]
        row["touched"] = now
        if row["review"] and now - row["review"]["created"] >= REVIEW_SECONDS:
            row["review"] = None
        return row

    async def audit(self, actor):
        if actor.id not in self.audits:
            from homeassistant.helpers.storage import Store
            audit = ReportingAudit(Store(self.hass, 1, f"{DOMAIN}.feedback_history.{self.entry.entry_id}.{actor.id}"))
            await audit.load()
            self.audits[actor.id] = audit
        return self.audits[actor.id]

    async def snapshot(self, actor):
        async with self.lock:
            self.actor_row(actor)
            history = await (await self.audit(actor)).snapshot()
            return {"devices": owned_feedback_devices(self.hass, actor),
                    "destination": PROJECT_ORIGIN + FEEDBACK_PATH, "history": history}

    async def prepare(self, actor, category, message, device_id=""):
        async with self.lock:
            row = self.actor_row(actor)
            if device_id and device_id not in {item["id"] for item in owned_feedback_devices(self.hass, actor)}:
                raise ValueError("Choose one of your own registered devices.")
            try:
                from homeassistant.const import __version__ as ha_version
            except ImportError:
                ha_version = "unknown"
            message = validate_message(message.strip().replace("\r\n", "\n"))
            report = validate_feedback({"schema_version": 1, "feedback_id": uuid.uuid4().hex,
                "category": category, "message": message, "integration_version": PROTOTYPE_VERSION,
                "home_assistant_version": ha_version,
                "timestamp": datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat(),
                **mobile_report_context(self.hass, device_id)})
            row["review"] = {"created": monotonic(), "report": report, "sent": False,
                             "device_id": device_id, "audit_id": None}
            return {"report": report, "destination": PROJECT_ORIGIN + FEEDBACK_PATH}

    async def send(self, actor, feedback_id, consent):
        async with self.lock:
            row = self.actor_row(actor)
            review = row["review"]
            if (consent is not True or not review or review["report"]["feedback_id"] != feedback_id):
                raise ValueError("Review this feedback again before sending.")
            if review["sent"]:
                return {"accepted": True}
            if review.get("last_attempt") is not None and monotonic() - review["last_attempt"] < 30:
                raise ValueError("Wait 30 seconds before retrying this submission.")
            if review["device_id"] and review["device_id"] not in {item["id"] for item in owned_feedback_devices(self.hass, actor)}:
                raise ValueError("This device is no longer registered to your account. Review again.")
            audit = await self.audit(actor)
            if review["audit_id"] is None:
                await self.reserve_slot(feedback_id)
                review["audit_id"] = await audit.prepare(PROJECT_ORIGIN + FEEDBACK_PATH, review["report"])
            review["last_attempt"] = monotonic()
            transport = ReportTransport()
            try:
                status, protocol = await transport.send(PROJECT_ORIGIN + FEEDBACK_PATH, review["report"])
                accepted = status == 202 and protocol is True
                review["sent"] = accepted
                await audit.finish(review["audit_id"], "accepted" if accepted else "not_accepted")
                return {"accepted": accepted}
            except Exception:
                await audit.finish(review["audit_id"], "unconfirmed")
                raise ValueError("Delivery could not be confirmed. Retrying this review will not create a duplicate.") from None
            finally:
                await transport.close()


def feedback_service(hass, entry):
    services = hass.data.setdefault(DOMAIN, {}).setdefault("feedback", {})
    if entry.entry_id not in services:
        services[entry.entry_id] = FeedbackService(hass, entry)
    return services[entry.entry_id]


def register_feedback_commands(hass, get_entry):
    import voluptuous as vol
    from homeassistant.components import websocket_api

    async def handle(hass, connection, msg, action):
        try:
            actor = await async_actor(hass, connection)
            service = feedback_service(hass, get_entry(hass))
            if action == "get":
                result = await service.snapshot(actor)
            elif action == "prepare":
                result = await service.prepare(actor, msg["category"], msg["message"], msg["device_id"])
            else:
                result = await service.send(actor, msg["feedback_id"], msg["consent"])
        except ValueError as error:
            connection.send_error(msg["id"], "invalid_feedback", str(error))
            return
        except Exception:
            connection.send_error(msg["id"], "feedback_unavailable", "Feedback or its local history is unavailable.")
            return
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/feedback/get"})
    @websocket_api.async_response
    async def get_feedback(hass, connection, msg):
        await handle(hass, connection, msg, "get")

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/feedback/prepare",
        vol.Required("category"): str, vol.Required("message"): vol.All(str, vol.Length(max=1000)),
        vol.Optional("device_id", default=""): str})
    @websocket_api.async_response
    async def prepare_feedback(hass, connection, msg):
        await handle(hass, connection, msg, "prepare")

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/feedback/send",
        vol.Required("feedback_id"): str, vol.Required("consent"): bool})
    @websocket_api.async_response
    async def send_feedback(hass, connection, msg):
        await handle(hass, connection, msg, "send")

    for command in (get_feedback, prepare_feedback, send_feedback):
        websocket_api.async_register_command(hass, command)
