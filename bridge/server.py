import asyncio
import json
from aiohttp import web
import threading
from astrbot.api import logger
import uuid
from fastapi import WebSocket, WebSocketDisconnect, Request, HTTPException, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from astrbot.core.config.astrbot_config import AstrBotConfig
from typing import Optional
from .models import AvailableModelsManager
from .response import ResponseManager
from .process import Process
from .model_endpoint_map import get_mapping


class FastAPIWrapper:
    def __init__(self, server, config: AstrBotConfig):
        """
        server: LMArenaBridgeServer 实例
        """
        self.server = server
        self.host = config["server"]["host"]
        self.port = config["server"]["port"]
        self.app = FastAPI(lifespan=self.lifespan)  # type: ignore
        self._uvicorn_server = None
        self._server_thread: Optional[threading.Thread] = None

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._setup_routes()

    @staticmethod
    async def lifespan(app: FastAPI):
        yield

    def _setup_routes(self):
        app = self.app
        s = self.server

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            await s.websocket_endpoint(ws)

        @app.get("/v1/models")
        async def get_models():
            return await s.get_models()

        @app.post("/v1/chat/completions")
        async def chat_completions(request: Request):
            return await s.chat_completions(request)

        @app.post("/internal/update_available_models")
        async def update_available_models(request: Request):
            return await s.update_available_models_endpoint(request)

    def start(self):
        if self._uvicorn_server and self._uvicorn_server.started:
            return
        import uvicorn

        config = uvicorn.Config(self.app, host=self.host, port=self.port)
        self._uvicorn_server = uvicorn.Server(config)
        self._server_thread = threading.Thread(
            target=self._uvicorn_server.run, daemon=True
        )
        self._server_thread.start()
        logger.info("[LMArena Bridge] 服务器已启动...")
        logger.info(f"监听地址: {self.host}:{self.port}")
        logger.info(f"WebSocket 端点: ws://{self.host}:{self.port}/ws")

    def stop(self):
        if self._uvicorn_server:
            # 请求 Server 停止
            self._uvicorn_server.should_exit = True

            # 等待 Server 彻底退出
            if self._server_thread and self._server_thread.is_alive():
                logger.info("等待 Uvicorn 线程退出...")
                self._server_thread.join(timeout=5)

            # 尝试显式清理引用
            self._uvicorn_server = None
            self._server_thread = None
            logger.info("Uvicorn 已关闭，端口应已释放。")


class LMArenaBridgeServer:
    """
    LMArena Bridge 后端服务
    """

    browser_ws: WebSocket | None = None  # 与单个油猴脚本的 WebSocket 连接

    def __init__(self, config: AstrBotConfig):
        self.conf = config
        # 可用模型管理器
        self.modelmgr = AvailableModelsManager(config)
        # 进程处理器
        self.processor = Process(config, self.modelmgr.model_map)
        # 响应管理器
        self.responser = ResponseManager(config)
        self.responser.callback = self.refresh
        # 是否正在因人机验证而刷新
        self.is_refreshing_flag = False
        logger.info("[LMArena Bridge] 后端已启动...")

    # ---------------- WS处理 ----------------
    async def websocket_endpoint(self, websocket: WebSocket):
        """处理来自油猴脚本的 WebSocket 连接。"""
        await websocket.accept()
        self.browser_ws = websocket
        logger.info("✅ 油猴脚本已成功连接 WebSocket。")
        try:
            while True:
                # 等待并接收来自油猴脚本的消息
                message_str = await websocket.receive_text()
                logger.debug(f"[油猴->本地]: {message_str[:100]}")
                message = json.loads(message_str)

                request_id = message.get("request_id")
                data = message.get("data")

                if not request_id or data is None:
                    logger.warning(f"[油猴脚本]无效消息: {message}")
                    continue

                # 将收到的数据放入对应的响应通道
                if request_id in self.responser.channels:
                    await self.responser.channels[request_id].put(data)
                else:
                    logger.warning(f"[油猴脚本]未知响应: {request_id}")

        except WebSocketDisconnect:
            logger.warning("❌ 油猴脚本客户端已断开连接。")
        except Exception as e:
            logger.error(f"WebSocket 处理时发生未知错误: {e}", exc_info=True)
        finally:
            self.browser_ws = None
            for queue in self.responser.channels.values():
                await queue.put({"error": "Browser disconnected during operation"})
            self.responser.channels.clear()

    async def ws_send(self, payload: dict):
        if not self.browser_ws:
            raise HTTPException(
                status_code=503,
                detail="油猴脚本客户端未连接。请确保 LMArena 页面已打开并激活脚本。",
            )

        await self.browser_ws.send_text(json.dumps(payload, ensure_ascii=False))
        truncated_payload = json.dumps(payload, ensure_ascii=False)[:200]
        logger.debug(f"[本地->油猴]: {truncated_payload}...")

    # ---------------- main.py调用的接口 ----------------
    async def refresh(self):
        await self.ws_send({"command": "refresh"})

    async def update_id(
        self, host: str = "127.0.0.1", port: int = 5103, timeout: int = 20
    ) -> str:
        """
        一次性 aiohttp 监听器，等待 Tampermonkey 推送 {sessionId, messageId}
        """
        await self.ws_send({"command": "activate_id_capture"})
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        async def handler(request: web.Request):
            # 统一处理 OPTIONS + POST
            if request.method == "OPTIONS":
                return web.Response(
                    status=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type",
                    },
                )

            data = await request.json()
            sid, mid = data.get("sessionId"), data.get("messageId")
            if sid and mid:
                if not future.done():
                    future.set_result((sid, mid))
                return web.json_response(
                    {"status": "success"}, headers={"Access-Control-Allow-Origin": "*"}
                )
            return web.json_response(
                {"error": "Missing sessionId or messageId"},
                status=400,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        app = web.Application()
        app.router.add_route("*", "/update", handler)
        runner = web.AppRunner(app)

        try:
            await runner.setup()
            await web.TCPSite(runner, host, port).start()
            logger.info(
                f"🚀 捕获监听中: http://{host}:{port}/update (timeout={timeout})"
            )
            try:
                sid, mid = await asyncio.wait_for(future, timeout)
                self.conf.update({"session_id": sid, "message_id": mid})
                self.conf.save_config()
                logger.info(f"✅ 成功捕获并保存: {sid}, {mid}")
                return f"已捕获会话ID: {sid[:8]}..."
            except asyncio.TimeoutError:
                logger.warning("⏳ 捕获超时")
                return "捕获超时"
        except OSError as e:
            logger.error(f"❌ 监听器启动失败 {host}:{port}: {e}")
            return "监听器启动失败"
        finally:
            await runner.cleanup()



    async def trigger_model_update(self):
        """让油猴发送页面源代码"""
        await self.ws_send({"command": "send_page_source"})

    async def update_available_models_endpoint(self, request: Request):
        """
        接收来自油猴脚本的页面 HTML，提取并更新 available_models.json。
        """
        html_content = await request.body()
        if not html_content:
            logger.warning("模型更新请求未收到任何 HTML 内容。")
            return
        logger.info("收到来自油猴脚本的页面内容，开始提取可用模型...")
        self.modelmgr.update_from_html(html_content.decode("utf-8"))

    # ---------------- FastAPI调用 ----------------
    async def get_models(self):
        """提供兼容 OpenAI 的模型列表。"""
        return self.modelmgr.get_models_list()

    async def chat_completions(self, request: Request):
        """
        FastAPI 路由函数
        负责解析请求体、API Key 验证，然后转发给逻辑函数。
        """
        # Json检查
        try:
            openai_req = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="无效的 JSON 请求体")

        # API Key 验证
        if self.conf["server"]["api_key"]:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=401,
                    detail="未提供 API Key。请在 Authorization 头部中以 'Bearer YOUR_KEY' 格式提供。",
                )
            provided_key = auth_header.split(" ")[1]
            if provided_key != self.conf["server"]["api_key"]:
                raise HTTPException(status_code=401, detail="提供的 API Key 不正确。")

        # 获取模型名
        model_name = openai_req.get("model")
        if not model_name:
            raise HTTPException(
                status_code=400,
                detail="未指定模型名。请检查请求体。",
            )

        # 会话ID映射
        session_id, message_id, mode_override, battle_target_override = get_mapping(
            model_name
        )

        # 全局回退
        if not session_id:
            session_id = self.conf["session_id"]
            message_id = self.conf["message_id"]
            logger.debug(f"使用全局 Session ID: {session_id}")

        # 验证最终会话信息
        if (
            not session_id
            or not message_id
            or "YOUR_" in session_id
            or "YOUR_" in message_id
        ):
            raise HTTPException(
                status_code=400,
                detail="会话ID或消息ID无效。请检查配置",
            )

        # 生成请求ID
        request_id = str(uuid.uuid4())

        # 参数转换
        message_templates = self.processor.openai_to_lmarena(
            openai_req,
            mode_override=mode_override,
            battle_target_override=battle_target_override,
        )

        # 确定目标模型 ID
        target_model_id = self.modelmgr.get_model_id(model_name)
        logger.debug(f"[{model_name}]:{target_model_id}")
        # 创建响应通道
        self.responser.channels[request_id] = asyncio.Queue()

        # 发送载荷到油猴脚本
        payload = {
            "request_id": request_id,
            "payload": {
                "message_templates": message_templates,
                "target_model_id": target_model_id,
                "session_id": session_id,
                "message_id": message_id,
            },
        }
        # print(payload)
        await self.ws_send(payload)

        # 返回响应（stream 参数开启流式响应）
        try:
            if openai_req.get("stream", False):
                return StreamingResponse(
                    self.responser.stream_generator(
                        request_id, model_name or "default_model"
                    ),
                    media_type="text/event-stream",
                )
            else:
                return await self.responser.non_stream_response(
                    request_id, model_name or "default_model"
                )
        except Exception as e:
            logger.error(
                f"API CALL [ID: {request_id[:8]}]: 处理请求时发生致命错误: {e}",
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail=str(e))
