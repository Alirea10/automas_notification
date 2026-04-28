# automas_notification

`notification` 是 AUTO-MAS 的通知编排插件。它提供 `notify` 服务，负责统一生成通知 payload、管理通道注册，并把通知分发给所有已注册的通道插件。

具体发送逻辑不在本插件内实现。邮件、系统通知、ServerChan、Webhook、Koishi 等发送能力由独立通道插件提供。

## 服务声明

```python
class Plugin:
    provides = "notify"
```

其他插件需要使用通知服务时，应声明：

```python
class Plugin:
    needs = "notify"
```

然后通过 `self.ctx.get("notify")` 获取服务实例。

## 通道注册

通道插件启动时向 `notify` 注册自己：

```python
notify = self.ctx.get("notify")
notify.register_channel("system", self.channel)
```

停止时注销：

```python
notify = self.ctx.get("notify")
notify.unregister_channel("system")
```

通道对象必须提供异步 `send(payload: dict) -> bool` 方法。返回 `True` 表示发送成功，返回 `False` 表示该通道未发送或发送失败。抛出的异常会被 `notification` 捕获并记录为失败。

## 通用广播接口

推荐新代码使用统一接口：

```python
await notify.send(
    title="AUTO-MAS 通知",
    text="通知正文",
    kind="generic",
    serverchan_content=None,
    koishi_message=None,
    data={"代理成功": True, "代理用户": "user@example.com"},
)
```

该接口会广播给所有已注册通道，返回值是通道名到发送结果的映射：

```python
{
    "system": True,
    "mail": False,
    "webhook": True,
}
```

如果没有可用通道，返回 `{}`。

## 通用 payload

广播时，`notification` 会构造如下 payload：

```python
{
    "kind": "generic",
    "title": "AUTO-MAS 通知",
    "text": "通知正文",
    "serverchan_content": "通知正文",
    "koishi_message": "AUTO-MAS 通知\n\n通知正文",
    "signature": "AUTO-MAS 敬上",
    "data": {"代理成功": True, "代理用户": "user@example.com"},
    "extra": {},
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `kind` | `str` | 通知类型。常见值有 `generic`、`test`、`mail`、`system`、`serverchan`、`webhook`、`legacy_webhook`、`webhook_image`、`koishi`。通道可按需区分处理。 |
| `title` | `str` | 通知标题。大多数通道都应使用。 |
| `text` | `str` | 纯文本正文。通道的基础兜底内容。 |
| `serverchan_content` | `str` | ServerChan 使用的正文。未显式传入时等于 `text`。 |
| `koishi_message` | `str` | Koishi 使用的消息文本。未显式传入时为 `"{title}\n\n{text}"`。 |
| `signature` | `str` | 统一通知署名，来自 `notification` 插件配置。 |
| `data` | `dict` | 结构化语义字段，例如代理是否成功、代理用户、任务名等。具体展示方式由通道决定。 |
| `extra` | `dict` | 日志、图片、附件等补充内容。 |

通道实现应该优先读取自己关心的字段，并对缺失字段使用合理兜底。例如系统通知通道读取 `title` 和 `text`，邮件通道根据 `title`、`text` 和 `data` 自行渲染邮件内容，ServerChan 通道读取 `serverchan_content`。

## 测试通知 payload

`send_test_notification()` 会发送 `kind="test"` 的广播通知，用于测试所有通道是否可用：

```python
await notify.send_test_notification()
```

该方法内部仍走 `notify.send(...)`，所以所有通道收到的仍是通用 payload，只是：

```python
{
    "kind": "test",
    "title": "AUTO-MAS 测试通知",
    "text": "...测试信息...",
    "serverchan_content": "...测试信息...\n\nAUTO-MAS 敬上",
    "koishi_message": "AUTO-MAS 测试通知\n\n...测试信息...\n\nAUTO-MAS 敬上",
    "signature": "AUTO-MAS 敬上",
}
```

## 兼容层定向接口

为了兼容旧的 `app/services/notification.py::Notify` API，`notification` 暂时保留了一组 `send_xxx` 方法。它们不实现具体发送逻辑，只是把旧参数包装成 payload，再转发到指定通道。

这些方法是迁移期兼容接口，新代码应优先使用 `notify.send(...)`。

### `send_system`

```python
await notify.send_system(
    title="标题",
    message="正文",
    ticker="提示",
    timeout=3,
)
```

发送到 `system` 通道，payload：

```python
{
    "kind": "system",
    "title": "标题",
    "text": "正文",
    "ticker": "提示",
    "timeout": 3,
}
```

### `send_mail`

```python
await notify.send_mail(
    mode="网页",
    title="标题",
    content="<b>正文</b>",
    to_address="user@example.com",
)
```

发送到 `mail` 通道，payload：

```python
{
    "kind": "mail",
    "title": "标题",
    "mail_mode": "网页",
    "mail_content": "<b>正文</b>",
    "to_address": "user@example.com",
}
```

`mail_content` 是 mail 通道的兼容专用字段。普通广播通知不会携带 HTML 正文，邮件通道会根据 `title`、`text`、`data`、`signature` 和 `extra` 自行渲染 HTML 或纯文本。

### `send_serverchan`

```python
await notify.send_serverchan(
    title="标题",
    content="正文",
    send_key="SCT...",
)
```

发送到 `serverchan` 通道，payload：

```python
{
    "kind": "serverchan",
    "title": "标题",
    "serverchan_content": "正文",
    "send_key": "SCT...",
}
```

### `send_webhook`

```python
await notify.send_webhook(
    title="标题",
    content="正文",
    webhook=webhook_config,
)
```

发送到 `webhook` 通道，payload：

```python
{
    "kind": "webhook",
    "title": "标题",
    "text": "正文",
    "webhook": webhook_config,
}
```

`webhook` 字段通常是旧配置模型对象或类似对象，由 `notification_webhook` 负责解释。

### `send_legacy_webhook`

```python
await notify.send_legacy_webhook(
    title="标题",
    content="正文",
    webhook_url="https://example.com/webhook",
)
```

发送到 `webhook` 通道，payload：

```python
{
    "kind": "legacy_webhook",
    "title": "标题",
    "text": "正文",
    "webhook_url": "https://example.com/webhook",
}
```

### `send_webhook_image`

```python
await notify.send_webhook_image(
    image_path=Path("result.png"),
    webhook_url="https://example.com/webhook",
)
```

发送到 `webhook` 通道，payload：

```python
{
    "kind": "webhook_image",
    "image_path": Path("result.png"),
    "webhook_url": "https://example.com/webhook",
}
```

### `send_koishi`

```python
await notify.send_koishi(
    message="正文",
    msgtype="text",
    client_name="Koishi",
)
```

发送到 `koishi` 通道，payload：

```python
{
    "kind": "koishi",
    "koishi_message": "正文",
    "msgtype": "text",
    "client_name": "Koishi",
}
```

## 通道实现建议

一个最小通道示例：

```python
class MyChannel:
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config

    async def send(self, payload: dict) -> bool:
        if not self.config.enabled:
            return False

        title = str(payload.get("title") or "AUTO-MAS 通知")
        text = str(payload.get("text") or "")
        # 在这里执行具体发送逻辑
        self.ctx.logger.info(f"sent: {title} {text}")
        return True
```

通道插件：

```python
class Plugin:
    needs = "notify"

    def __init__(self, ctx):
        self.ctx = ctx
        self.channel = None

    async def on_start(self):
        self.channel = MyChannel(self.ctx, self.ctx.config)
        self.ctx.get("notify").register_channel("my_channel", self.channel)

    async def on_stop(self, reason: str):
        notify = self.ctx.get("notify")
        if notify is not None:
            notify.unregister_channel("my_channel")
```

## 职责边界

`notification` 负责：

- 提供 `notify` 服务。
- 管理通道注册和注销。
- 生成统一 payload。
- 广播通知并聚合各通道结果。
- 保留旧通知 API 的兼容包装。

通道插件负责：

- 管理自己的配置。
- 解释自己关心的 payload 字段。
- 按自身能力渲染格式，例如邮件通道自行生成 HTML，Koishi/Webhook 自行生成平台消息。
- 执行具体发送逻辑。
- 返回布尔发送结果。

旧兼容方法后续可以逐步迁移到更通用的 `notify.send(...)` 调用，但在迁移完成前会继续保留。
