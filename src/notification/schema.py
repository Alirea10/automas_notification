from typing import Literal

from app.plugins.fields import PluginField
from pydantic import BaseModel, ConfigDict


class Config(BaseModel):
    model_config = ConfigDict(extra="allow")

    send_task_result_time: Literal["always", "failed_only", "never"] = PluginField(
        default="always",
        description="任务结果通知",
    )
    send_statistic: bool = PluginField(
        default=True,
        description="发送统计信息",
    )
    send_six_star: bool = PluginField(
        default=True,
        description="发送六星/高价值结果",
    )
    signature: str = PluginField(
        default="AUTO-MAS 敬上",
        description="通知署名",
    )
