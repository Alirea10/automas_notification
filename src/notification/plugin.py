from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.plugins import PluginContext
    from app.plugins import PluginHttpRequest

from .schema import Config


class NotifyService:
    def __init__(self, ctx: "PluginContext", config: Config) -> None:
        self.ctx = ctx
        self.config = config
        self._channels: dict[str, Any] = {}

    def register_channel(self, name: str, channel: Any) -> None:
        channel_name = str(name or "").strip()
        if not channel_name:
            raise ValueError("通知通道名称不能为空")
        self._channels[channel_name] = channel
        self.ctx.logger.info(f"已注册通知通道: {channel_name}")

    def unregister_channel(self, name: str) -> None:
        channel_name = str(name or "").strip()
        if self._channels.pop(channel_name, None) is not None:
            self.ctx.logger.info(f"已注销通知通道: {channel_name}")

    def channels(self, detail: bool = False) -> list[str] | list[dict[str, Any]]:
        if not detail:
            return sorted(self._channels)

        rows: list[dict[str, Any]] = []
        for name in sorted(self._channels):
            channel = self._channels[name]
            config = getattr(channel, "config", None)
            enabled = getattr(config, "enabled", None)
            rows.append(
                {
                    "name": name,
                    "type": type(channel).__name__,
                    "enabled": bool(enabled) if enabled is not None else None,
                    "supports_send": callable(getattr(channel, "send", None)),
                }
            )
        return rows

    async def should_send_task_result(self, message: dict[str, Any]) -> bool:
        policy = self.config.send_task_result_time
        if policy == "never":
            return False
        if policy == "failed_only":
            try:
                return int(message.get("uncompleted_count", 0)) != 0
            except Exception:
                return False
        return True

    async def should_send_statistic(self) -> bool:
        return bool(self.config.send_statistic)

    async def should_send_six_star(self) -> bool:
        return bool(self.config.send_six_star)

    async def send(
        self,
        *,
        title: str,
        text: str,
        kind: str = "generic",
        serverchan_content: str | None = None,
        koishi_message: str | None = None,
        data: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        channels: list[str] | tuple[str, ...] | set[str] | str | None = None,
    ) -> dict[str, bool]:
        payload = {
            "kind": kind,
            "title": title,
            "text": text,
            "serverchan_content": serverchan_content or text,
            "koishi_message": koishi_message or f"{title}\n\n{text}",
            "signature": self.config.signature,
            "data": data or {},
            "extra": extra or {},
        }
        return await self.send_payload(payload, channels=channels)

    async def send_payload(
        self,
        payload: dict[str, Any],
        *,
        channels: list[str] | tuple[str, ...] | set[str] | str | None = None,
    ) -> dict[str, bool]:
        if not isinstance(payload, dict):
            raise ValueError("notification payload must be a dict")

        normalized = dict(payload)
        title = str(normalized.get("title") or "AUTO-MAS 通知")
        text = str(normalized.get("text") or "")
        normalized["title"] = title
        normalized["text"] = text
        normalized.setdefault("kind", "generic")
        normalized.setdefault("serverchan_content", text)
        normalized.setdefault("koishi_message", f"{title}\n\n{text}")
        normalized.setdefault("signature", self.config.signature)
        if not isinstance(normalized.get("data"), dict):
            normalized["data"] = {}
        if not isinstance(normalized.get("extra"), dict):
            normalized["extra"] = {}

        channel_names = self.resolve_channels(channels)
        if channel_names == []:
            return {}
        if channel_names is None:
            return await self._broadcast(normalized)
        return {
            name: await self._send_to(name, normalized)
            for name in channel_names
        }

    async def send_test_notification(self) -> dict[str, bool]:
        text = (
            "这是 AUTO-MAS 外部通知测试信息。如果你看到这段内容，"
            "说明插件化通知通道已经配置并可以正常工作。"
        )
        return await self.send(
            title="AUTO-MAS 测试通知",
            text=text,
            kind="test",
            serverchan_content=f"{text}\n\n{self.config.signature}",
            koishi_message=f"AUTO-MAS 测试通知\n\n{text}\n\n{self.config.signature}",
        )

    async def send_system(
        self,
        *,
        title: str,
        message: str,
        ticker: str = "",
        timeout: int = 3,
    ) -> bool:
        return await self._send_to("system", {
            "kind": "system",
            "title": title,
            "text": message,
            "ticker": ticker,
            "timeout": timeout,
        })

    async def send_mail(
        self,
        *,
        mode: str,
        title: str,
        content: str,
        to_address: str,
    ) -> bool:
        return await self._send_to("mail", {
            "kind": "mail",
            "title": title,
            "mail_mode": mode,
            "mail_content": content,
            "to_address": to_address,
        })

    async def send_serverchan(self, *, title: str, content: str, send_key: str) -> bool:
        return await self._send_to("serverchan", {
            "kind": "serverchan",
            "title": title,
            "serverchan_content": content,
            "send_key": send_key,
        })

    async def send_webhook(self, *, title: str, content: str, webhook: Any) -> bool:
        return await self._send_to("webhook", {
            "kind": "webhook",
            "title": title,
            "text": content,
            "webhook": webhook,
        })

    async def send_legacy_webhook(self, *, title: str, content: str, webhook_url: str) -> bool:
        return await self._send_to("webhook", {
            "kind": "legacy_webhook",
            "title": title,
            "text": content,
            "webhook_url": webhook_url,
        })

    async def send_webhook_image(self, *, image_path: Path, webhook_url: str) -> bool:
        return await self._send_to("webhook", {
            "kind": "webhook_image",
            "image_path": image_path,
            "webhook_url": webhook_url,
        })

    async def send_koishi(
        self,
        *,
        message: str,
        msgtype: str = "text",
        client_name: str = "Koishi",
    ) -> bool:
        return await self._send_to("koishi", {
            "kind": "koishi",
            "koishi_message": message,
            "msgtype": msgtype,
            "client_name": client_name,
        })

    async def send_onebot(
        self,
        *,
        title: str,
        content: str,
        target_type: str = "private",
        target_id: int = 0,
    ) -> bool:
        return await self._send_to("onebot", {
            "kind": "onebot",
            "title": title,
            "text": content,
            "target_type": target_type,
            "target_id": target_id,
        })

    @staticmethod
    def resolve_channels(
        channels: list[str] | tuple[str, ...] | set[str] | str | None,
    ) -> list[str] | None:
        """Normalize channel selection while preserving its three-state contract.

        ``None`` means use the default broadcast behavior, an explicit empty
        collection means do not send, and ``all`` requests a broadcast.
        """

        if channels is None:
            return None
        if isinstance(channels, str):
            raw_items = [channels]
        elif isinstance(channels, (list, tuple, set)):
            raw_items = list(channels)
        else:
            raw_items = [channels]

        result: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            name = str(item or "").strip()
            if not name or name in seen:
                continue
            if name == "all":
                return None
            seen.add(name)
            result.append(name)
        return result

    @classmethod
    def is_channel_selected(
        cls,
        channels: list[str] | tuple[str, ...] | set[str] | str | None,
        channel: str,
    ) -> bool:
        """Return whether a channel is included by the supplied selection."""

        channel_name = str(channel or "").strip()
        if not channel_name:
            return False
        resolved = cls.resolve_channels(channels)
        return resolved is None or channel_name in resolved

    async def _broadcast(self, payload: dict[str, Any]) -> dict[str, bool]:
        if not self._channels:
            self.ctx.logger.warning("无可用通知通道，通知已跳过")
            return {}

        tasks = {
            name: asyncio.create_task(self._safe_send(name, channel, payload))
            for name, channel in list(self._channels.items())
        }
        return {name: await task for name, task in tasks.items()}

    async def _send_to(self, name: str, payload: dict[str, Any]) -> bool:
        channel = self._channels.get(name)
        if channel is None:
            self.ctx.logger.warning(f"通知通道未启用: {name}")
            return False
        return await self._safe_send(name, channel, payload)

    async def _safe_send(self, name: str, channel: Any, payload: dict[str, Any]) -> bool:
        try:
            result = await channel.send(payload)
            return bool(result)
        except Exception as e:
            self.ctx.logger.warning(
                f"通道发送失败: channel={name}, error={type(e).__name__}: {e}"
            )
            return False


class Plugin:
    provides = "notify"

    def __init__(self, ctx: "PluginContext") -> None:
        self.ctx = ctx
        self.service: NotifyService | None = None

    async def on_start(self) -> None:
        raw_config = self.ctx.config.to_dict() if hasattr(self.ctx.config, "to_dict") else dict(self.ctx.config)
        config = Config.model_validate(raw_config)
        self.service = NotifyService(self.ctx, config)
        self.ctx.set("notify", self.service)
        self.ctx.server.http(
            "/notification/channels",
            self.handle_channels,
            methods=["GET"],
        )
        self.ctx.server.http(
            "/notification/send",
            self.handle_send,
            methods=["POST"],
        )
        self.ctx.server.http(
            "/notification/test",
            self.handle_test,
            methods=["POST"],
        )
        self.ctx.logger.info("notify 服务已启动")

    async def on_stop(self, reason: str) -> None:
        if self.service is not None:
            self.service._channels.clear()
        self.ctx.logger.info(f"插件停止, reason={reason}")

    async def handle_channels(self, request: "PluginHttpRequest") -> dict[str, Any]:
        if self.service is None:
            return {"code": 503, "status": "error", "message": "notify service is unavailable"}

        detail_raw = str(request.query.get("detail") or "").strip().lower()
        detail = detail_raw in {"1", "true", "yes", "on"}
        return {
            "code": 200,
            "status": "success",
            "channels": self.service.channels(detail=detail),
        }

    async def handle_send(self, request: "PluginHttpRequest") -> dict[str, Any]:
        if self.service is None:
            return {"code": 503, "status": "error", "message": "notify service is unavailable"}
        if not isinstance(request.json, dict):
            return {"code": 400, "status": "error", "message": "request body must be a JSON object"}

        body = dict(request.json)
        channels = body.pop("channels", None)
        title = str(body.get("title") or "").strip()
        text = str(body.get("text") or "").strip()
        if not title or not text:
            return {"code": 400, "status": "error", "message": "title and text are required"}

        result = await self.service.send_payload(body, channels=channels)
        return {
            "code": 200,
            "status": "success",
            "result": result,
            "succeeded": sorted(name for name, ok in result.items() if ok),
            "failed": sorted(name for name, ok in result.items() if not ok),
        }

    async def handle_test(self, request: "PluginHttpRequest") -> dict[str, Any]:
        _ = request
        if self.service is None:
            return {"code": 503, "status": "error", "message": "notify service is unavailable"}

        result = await self.service.send_test_notification()
        return {
            "code": 200,
            "status": "success",
            "result": result,
            "succeeded": sorted(name for name, ok in result.items() if ok),
            "failed": sorted(name for name, ok in result.items() if not ok),
        }
