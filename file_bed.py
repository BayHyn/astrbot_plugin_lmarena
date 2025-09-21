import base64
import shutil
import threading
from pathlib import Path
import time
from fastapi import Body, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig


class UploadPayload(BaseModel):
    file_name: str
    file_data: str  # data URI
    api_key: str


class ImageServer:
    def __init__(self, config: AstrBotConfig, upload_dir: Path):
        self.clear_cache_interval = config["image_server"]["clear_cache_interval"]
        self.host = config["image_server"]["host"]
        self.port = config["image_server"]["port"]
        self.api_key = config["image_server"]["api_key"]
        self.upload_dir = upload_dir
        self.app = FastAPI()
        self._server = None
        self._thread = None
        self._cleaner_thread = None
        self._stop_cleaner = threading.Event()

        self.app.mount(
            "/uploads", StaticFiles(directory=self.upload_dir), name="uploads"
        )
        self._setup_routes()

    def _setup_routes(self):
        @self.app.post("/upload")
        async def upload(payload: UploadPayload = Body(...)):
            # 校验 API key
            if payload.api_key != self.api_key:
                raise HTTPException(403)

            # 解析 base64
            if payload.file_data.startswith("data:"):
                base64_str = payload.file_data.split(",", 1)[1]
            else:
                base64_str = payload.file_data
            file_bytes = base64.b64decode(base64_str)

            # 保存文件
            save_path = self.upload_dir / payload.file_name
            with open(save_path, "wb") as f:
                f.write(file_bytes)

            return {"success": True, "filename": payload.file_name}

    def _clear_cache(self):
        try:
            if self.upload_dir.exists():
                shutil.rmtree(self.upload_dir)
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            logger.info("[图床] 定时清理完成，缓存已清空")
        except Exception as e:
            logger.error(f"[图床] 清理缓存失败: {e}")

    def _start_cleaner(self, interval_hours: int = 6):
        self._stop_cleaner.clear()
        def _loop():
            while not self._stop_cleaner.is_set():
                remaining = interval_hours * 3600
                # 分段 sleep，避免 OverflowError
                while remaining > 0 and not self._stop_cleaner.is_set():
                    chunk = min(remaining, 24 * 3600)  # 每次最多睡 24h
                    time.sleep(chunk)
                    remaining -= chunk
                if not self._stop_cleaner.is_set():
                    self._clear_cache()

        self._cleaner_thread = threading.Thread(target=_loop, daemon=True)
        self._cleaner_thread.start()

    def start(self):
        if self._server:
            return
        import uvicorn

        config = uvicorn.Config(app=self.app, host=self.host, port=self.port)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        if self.clear_cache_interval:
            self._start_cleaner(interval_hours=self.clear_cache_interval)
        logger.info(f"图床服务器已启动: http://{self.host}:{self.port}")

    def stop(self):
        if self._server:
            self._server.should_exit = True
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
            self._server = None
            self._thread = None
            if self._cleaner_thread and self._cleaner_thread.is_alive():
                self._stop_cleaner.set()
                self._cleaner_thread.join(timeout=5)
                self._cleaner_thread = None
            logger.info("图床服务器已优雅关闭")
