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
    "全面对接lmarena(模型竞技场)",
    "v2.0.6",
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
        self.prompt_map = {}
        self.prompt_map_keys = []
        self._lode_prompt_map()

    def _lode_prompt_map(self):
        prompt_list = self.conf["prompt_list"].copy()
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
        cmd = text.split()[0].strip() if text else ""
        # 纯文本模式、图片+自定义提示词模式
        if cmd == self.conf["extra_prefix"]:
            text = text.removeprefix(cmd).strip()
        # 图片+预设提示词模式
        elif cmd and cmd in self.prompt_map_keys:
            text = self.prompt_map.get(cmd) or ""
        else:
            return
        images: list[bytes | str] = await self.workflow.get_images(event)
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

    @filter.command("lm添加", alias={"lma"})
    async def add_lm_prompt(self, event: AstrMessageEvent):
        """lm添加 触发词:描述词（触发词重复则覆盖）"""
        raw = event.message_str.removeprefix("lm添加").removeprefix("lma").strip()
        if ":" not in raw:
            yield event.plain_result(
                "格式错误，正确示例：\n姿势表:为这幅图创建一个姿势表，摆出各种姿势"
            )
            return

        key, new_value = map(str.strip, raw.split(":", 1))

        # 1. 先尝试覆盖
        for idx, item in enumerate(self.conf["prompt_list"]):
            if item.startswith(key + ":"):  # 触发词相同
                self.conf["prompt_list"][idx] = f"{key}:{new_value}"
                break
        else:
            # 2. 没找到就新增
            self.conf["prompt_list"].append(f"{key}:{new_value}")

        self.conf.save_config()
        self._lode_prompt_map()
        yield event.plain_result(f"已保存LM生图提示语:\n{key}:{new_value}")

    @filter.command("lm帮助", alias={"lmh"})
    async def help(self, event: AstrMessageEvent, keyword: str | None = None):
        """Lmarena帮助"""
        if not keyword:
            msg = "可用的生图提示词：\n"
            msg += "、".join(self.prompt_map.keys())
            yield event.plain_result(msg)
            return
        prompt = self.prompt_map.get(keyword)
        if not prompt:
            yield event.plain_result("未找到此提示词")
            return
        yield event.plain_result(f"{keyword}:\n{prompt}")

    async def terminate(self):
        await self.workflow.terminate()
        if self.api:
            self.api.stop()
        if self.image_server:
            self.image_server.stop()
