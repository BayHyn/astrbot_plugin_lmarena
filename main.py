from datetime import datetime
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Image
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from data.plugins.astrbot_plugin_lmarena.file_bed import ImageServer
from .bridge.server import LMArenaBridgeServer, FastAPIWrapper
from .workflow import Workflow


@register(
    "astrbot_plugin_lmarena",
    "Zhalslar",
    "全面对接lmarena(模型竞技场)，免费无限调用最新模型，如调用nano-banana进行手办化",
    "v2.0.4",
)
class LMArenaPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        # 创建数据目录
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_lmarena")
        self.file_bed_dir = self.plugin_data_dir / "file_bed"
        self.file_bed_dir.mkdir(parents=True, exist_ok=True)
        self.file_save_dir = self.plugin_data_dir / "file_save"
        self.file_save_dir.mkdir(parents=True, exist_ok=True)

        self.bridge_server = None
        self.api = None
        # bridge_server_url为空时，改用本地桥梁连接油猴脚本
        if not self.conf["bridge_server"]["url"]:
            # 创建核心 Server
            self.bridge_server = LMArenaBridgeServer(config)
            # 启动 FastAPI
            self.api = FastAPIWrapper(self.bridge_server, config)
            self.api.start()
        # 启动工作流
        self.workflow = Workflow(config)
        # 启动图床
        self.image_server = None
        if self.conf["image_server"]["enable"]:
            self.image_server = ImageServer(config, self.file_bed_dir)
            self.image_server.start()

        # 提示词字典
        prompt_list = config["prompt_list"].copy()
        self.prompt_map = {}
        for item in prompt_list:
            if ":" in item:
                key, value = item.split(":", 1)
                self.prompt_map[key.strip()] = value.strip()
        self.prompt_map_keys = list(self.prompt_map.keys())

    @filter.event_message_type(filter.EventMessageType.ALL, priority=3)
    async def on_lmarena(self, event: AstrMessageEvent):
        """/lm+文字 | 图片+提示词"""
        if self.conf["prefix"] and not event.is_at_or_wake_command:
            return

        text = event.message_str
        images: list[bytes | str] = await self.workflow.get_images(event)
        # 纯文本模式、图片+自定义提示词模式
        if text.startswith(self.conf["extra_prefix"]):
            text = text.removeprefix(self.conf["extra_prefix"]).strip()
        # 图片+预设提示词模式
        elif images and text and text.split()[0] in self.prompt_map_keys:
            text = self.prompt_map.get(text.split()[0]) or ""
        else:
            return

        chat_res = await self.workflow.fetch_content(
            text=text,
            images=images,
            model="default_model",
            retries=self.conf["retries"],
        )

        if isinstance(chat_res, bytes):
            yield event.chain_result([Image.fromBytes(chat_res)])
            if self.conf["save_image"]:
                save_path = (
                    self.file_save_dir
                    / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                )
                with save_path.open("wb") as f:
                    f.write(chat_res)

        elif isinstance(chat_res, str):
            yield event.plain_result(chat_res)

        else:
            yield event.plain_result("生成失败")
        event.stop_event()

    @filter.command("lm捕获", alias={"lmc"})
    async def update_id(self, event: AstrMessageEvent):
        """捕获会话ID"""
        if not self.bridge_server:
            yield event.plain_result("无法操作, 当前用的不是内置LM桥梁")
            return
        yield event.plain_result("已发送捕获命令, 请在浏览器中刷新目标模型")
        result = await self.bridge_server.update_id(
            host=self.conf["bridge_server"]["host"],
            port=int(self.conf["bridge_server"]["port"]) + 1,
            timeout=20,
        )
        yield event.plain_result(result)

    @filter.command("lm刷新", alias={"lmr"})
    async def refresh(self, event: AstrMessageEvent):
        """刷新lmarena网页"""
        if not self.bridge_server:
            yield event.plain_result("无法操作, 当前用的不是内置LM桥梁")
            return
        try:
            await self.bridge_server.refresh()
            yield event.plain_result("已发送指令刷新lmarena网页")
        except Exception:
            yield event.plain_result("网页刷新失败")

    @filter.command("lm帮助", alias={"lmh"})
    async def help(self, event: AstrMessageEvent):
        """Lmarena帮助"""
        help_text = "、".join(self.prompt_map.keys())
        yield event.plain_result(help_text)

    async def terminate(self):
        await self.workflow.terminate()
        if self.api:
            self.api.stop()
        if self.image_server:
            self.image_server.stop()
