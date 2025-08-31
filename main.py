
from datetime import datetime
from astrbot.api.event import filter
from astrbot import logger
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Image
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .bridge.server import LMArenaBridgeServer, FastAPIWrapper
from .workflow import Workflow
from .prompt import prompt_map


@register(
    "astrbot_plugin_lmarena",
    "Zhalslar",
    "全面对接lmarena(模型竞技场)，免费无限调用最新模型，如调用nano-banana进行手办化",
    "v2.0.0",
)
class LMArenaPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_lmarena")
        self.base_url = self.conf["base_url"]
        self.server = None
        self.api = None
        # base_url为空时，改用本地桥梁连接油猴脚本
        if not self.base_url:
            self.base_url = (
                f"http://{self.conf['server']['host']}:{self.conf['server']['port']}"
            )
            # 创建核心 Server
            self.server = LMArenaBridgeServer(config)
            # 启动 FastAPI
            self.api = FastAPIWrapper(self.server, config)
            self.api.start()
        # 启动工作流
        self.wf = Workflow(self.base_url)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=3)
    async def on_lmarena(self, event: AstrMessageEvent):
        """/lm+文字 | 手办化+图片"""
        if self.conf["prefix"] and not event.is_at_or_wake_command:
            return

        cmd, _, text = event.message_str.partition(" ")
        image = None
        if cmd == "lm":
            text = text.strip()
        elif cmd in prompt_map:
            image = await self.wf.get_first_image(event)
            if not text or text.startswith("@"):
                text = prompt_map[cmd]
        else:
            return

        chat_res = await self.wf.fetch_content(
            image, text, self.conf["model"], self.conf["retries"]
        )

        if isinstance(chat_res, bytes):
            yield event.chain_result([Image.fromBytes(chat_res)])
            if self.conf["save_image"]:
                save_path = (
                    self.plugin_data_dir
                    / f"{self.conf['model']}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                )
                with save_path.open("wb") as f:
                    f.write(chat_res)

        elif isinstance(chat_res, str):
            yield event.plain_result(chat_res)

        else:
            yield event.plain_result("生成失败")

    @filter.command("LM更新", alias={"lm更新"})
    async def trigger_model_update(self, event: AstrMessageEvent):
        """更新LM模型列表"""
        if not self.server:
            yield event.plain_result("无法操作, 当前用的不是内置LM桥梁")
            return
        try:
            await self.server.trigger_model_update()
            yield event.plain_result("已更新模型列表")
        except Exception:
            yield event.plain_result("模型列表更新失败")

    @filter.command("LM模型", alias={"lm模型"})
    async def models(self, event: AstrMessageEvent, index: int = 0):
        "查看模型列表，切换模型"
        ids = await self.wf.fetch_models()
        if not ids:
            yield event.plain_result("模型列表为空")
            return
        if 0 < index <= len(ids):
            sel_model = ids[index - 1]
            yield event.plain_result(f"已选择模型：{sel_model}")
            self.conf["model"] = sel_model
            self.conf.save_config()
        else:
            msg = "\n".join(f"{i + 1}. {m}" for i, m in enumerate(ids))
            yield event.plain_result(msg)

    @filter.command("LM捕获", alias={"lm捕获"})
    async def update_id(self, event: AstrMessageEvent):
        """捕获会话ID"""
        if not self.server:
            yield event.plain_result("无法操作, 当前用的不是内置LM桥梁")
            return
        yield event.plain_result("已发送捕获命令, 请在浏览器中刷新目标模型")
        result = await self.server.update_id()
        yield event.plain_result(result)


    @filter.command("LM刷新", alias={"lm刷新"})
    async def refresh(self, event: AstrMessageEvent):
        """刷新lmarena网页"""
        if not self.server:
            yield event.plain_result("无法操作, 当前用的不是内置LM桥梁")
            return
        try:
            await self.server.refresh()
            yield event.plain_result("已发送指令刷新lmarena网页")
        except Exception:
            yield event.plain_result("网页刷新失败")

    async def terminate(self):
        await self.wf.terminate()
        logger.info("[ImageWorkflow] session已关闭")
        if self.api:
            self.api.stop()
            logger.info("[FastAPIWrapper] 已关闭")
