# automas_notification

`notification` 是 AUTO-MAS 的通知编排插件。它提供 `notify` 服务，负责生成统一通知 payload、管理通知通道注册，并把同一条通知分发给所有已注册的通道插件。

具体发送逻辑不在本插件内实现。邮件、系统通知、ServerChan、Webhook、Koishi 等发送能力由独立通道插件提供。

## 服务声明

主插件提供 `notify` 服务：

```python
class Plugin:
    provides = "notify"
```

其他插件需要使用通知服务时，声明依赖：

```python
class Plugin:
    needs = "notify"
```

启动后通过 `self.ctx.get("notify")` 获取服务实例。

## 通道注册

通道插件启动时向 `notify` 注册自己：

```python
notify = self.ctx.get("notify")
notify.register_channel("system", self.channel)
```

停止时注销：

```python
notify = self.ctx.get("notify")
if notify is not None:
    notify.unregister_channel("system")
```

通道对象必须提供异步方法：

```python
async def send(self, payload: dict) -> bool:
    ...
```

返回 `True` 表示该通道发送成功，返回 `False` 表示未发送或发送失败。通道抛出的异常会被 `notification` 捕获并记录为失败，不会阻断其他通道。

## 通用发送接口

推荐新代码使用 `notify.send(...)`：

```python
await notify.send(
    title="代理完成",
    text="代理任务已完成",
    kind="proxy_result",
    data={
        "代理成功": True,
        "代理用户": "username",
        "任务名称": "舟官xxx",
    },
    extra={
        "logs": [
            {
                "name": "proxy.log",
                "content": "任务启动\n任务完成",
                "level": "info",
                "format": "text",
            }
        ],
        "images": [
            {
                "name": "screenshot.png",
                "path": "D:/Dev/AUTO-MAS/debug/screenshot.png",
                "mime": "image/png",
                "caption": "任务截图",
            }
        ],
        "attachments": [
            {
                "name": "detail.json",
                "path": "D:/Dev/AUTO-MAS/debug/detail.json",
                "mime": "application/json",
            }
        ],
        "metadata": {
            "run_id": "20260428-001",
        },
    },
)
```

返回值是通道名到发送结果的映射：

```python
{
    "system": True,
    "mail": False,
    "webhook": True,
}
```

如果没有可用通道，返回 `{}`，并记录“无可用通知通道”日志。

`channels` 使用统一的三态选择协议：

- `None`：使用默认广播行为。
- `[]`：明确不发送通知。
- `["all"]`：广播到全部已注册通道。
- `["system", "mail"]`：仅发送到指定通道；重复项和空字符串会被自动清理。

通道选择由 `NotifyService` 统一归一化，调用方不应自行把空列表转换为广播。

## 通用 payload

`notify.send(...)` 会生成如下 payload：

```python
{
    "kind": "proxy_result",
    "title": "代理完成",
    "text": "代理任务已完成",
    "serverchan_content": "代理任务已完成",
    "koishi_message": "代理完成\n\n代理任务已完成",
    "signature": "AUTO-MAS 敬上",
    "data": {
        "代理成功": True,
        "代理用户": "user@example.com",
        "任务名称": "AutoProxy",
    },
    "extra": {
        "logs": [],
        "images": [],
        "attachments": [],
        "metadata": {},
    },
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `kind` | `str` | 通知语义类型，例如 `generic`、`test`、`proxy_result`。它描述业务语义，不应该因为携带日志或图片而变成新的类型。 |
| `title` | `str` | 通知标题。大多数通道都应该使用。 |
| `text` | `str` | 纯文本正文，是所有通道的基础兜底内容。 |
| `serverchan_content` | `str` | ServerChan 默认正文。未显式传入时等于 `text`。 |
| `koishi_message` | `str` | Koishi 默认消息。未显式传入时为 `"{title}\n\n{text}"`。 |
| `signature` | `str` | 统一通知署名，来自 `notification` 插件配置。 |
| `data` | `dict` | 结构化业务信息，供通道自行渲染。主插件不解释其含义。 |
| `extra` | `dict` | 日志、图片、附件和元数据等补充内容。通道按自身能力处理。 |

## `data` 与 `extra` 的区别

`data` 用来描述业务字段，适合被通道渲染成表格、键值列表、Markdown 字段或平台专用消息。例如：

```python
data={
    "代理成功": True,
    "代理用户": "user@example.com",
    "失败数量": 0,
}
```

`extra` 用来携带补充材料，适合追加到正文后或作为附件发送。约定结构如下：

```python
extra={
    "logs": [
        {
            "name": "task.log",
            "content": "日志内容",
            "level": "info",
            "format": "text",
        }
    ],
    "images": [
        {
            "name": "screenshot.png",
            "path": "D:/path/screenshot.png",
            "mime": "image/png",
            "caption": "任务截图",
        }
    ],
    "attachments": [
        {
            "name": "detail.json",
            "path": "D:/path/detail.json",
            "mime": "application/json",
        }
    ],
    "metadata": {
        "run_id": "abc123",
    },
}
```

处理建议：

- SMTP 邮件通道：把日志追加到正文后，长日志可作为 `.txt` 附件；图片和普通附件作为 MIME 附件发送。
- 系统通知通道：把短日志摘要追加到通知正文；图片和附件只显示名称或忽略。
- Webhook、ServerChan、Koishi 通道：把日志摘要、图片名称、附件路径等追加到原消息后；如果平台后续支持文件上传，可在对应通道内部增强。
- 不支持某类 `extra` 的通道必须安全忽略，不能影响主通知发送。

## 测试通知

`send_test_notification()` 会发送 `kind="test"` 的广播通知，用于测试所有已注册通道是否可用：

```python
await notify.send_test_notification()
```

该方法内部仍走 `notify.send(...)`，所以所有通道收到的仍是通用 payload。

## 兼容型通道（暂存，确认不影响后再删除）

主服务还提供若干定向通道接口，用于明确只发送到某一个通道。这些接口不实现具体发送逻辑，只把参数包装成对应通道的 payload，然后调用指定通道。

新业务代码优先使用 `notify.send(...)`。只有在确实需要只调用某个通道的专有能力时，才使用这些定向接口。

### `send_system`

```python
await notify.send_system(
    title="标题",
    message="正文",
    ticker="提示",
    timeout=3,
)
```

发送到 `system` 通道：

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

发送到 `mail` 通道：

```python
{
    "kind": "mail",
    "title": "标题",
    "mail_mode": "网页",
    "mail_content": "<b>正文</b>",
    "to_address": "user@example.com",
}
```

`mail_content` 是邮件通道专用字段，只在显式定向调用邮件通道时使用。普通广播通知不会携带 HTML 正文，邮件通道会自行生成 HTML 或纯文本内容。

### `send_serverchan`

```python
await notify.send_serverchan(
    title="标题",
    content="正文",
    send_key="SCT...",
)
```

发送到 `serverchan` 通道：

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

发送到 `webhook` 通道：

```python
{
    "kind": "webhook",
    "title": "标题",
    "text": "正文",
    "webhook": webhook_config,
}
```

`webhook` 字段由 `notification_webhook` 通道解释。

### `send_legacy_webhook`

```python
await notify.send_legacy_webhook(
    title="标题",
    content="正文",
    webhook_url="https://example.com/webhook",
)
```

发送到 `webhook` 通道：

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

发送到 `webhook` 通道：

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

发送到 `koishi` 通道：

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
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}

        # 在这里根据通道能力渲染 title、text、data 和 extra。
        self.ctx.logger.info(f"sent: {title} {text} data={data} extra={extra}")
        return True
```

通道插件结构：

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
- 保存通知策略配置，例如任务结果、统计信息、高价值结果是否需要通知。

通道插件负责：

- 管理自身配置。
- 解释自己关心的 payload 字段。
- 按自身能力渲染格式，例如邮件通道生成 HTML，Koishi 和 Webhook 生成平台消息。
- 执行具体发送逻辑。
- 返回布尔发送结果。
