import uuid
import threading
from pathlib import Path
from fastapi import FastAPI, File, UploadFile
from fastapi.staticfiles import StaticFiles
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig


class ImageServer:
    def __init__(self, config: AstrBotConfig, upload_dir:Path):
        self.host = config["image_server"]["host"]
        self.port = config["image_server"]["port"]
        self.upload_dir = upload_dir
        self.app = FastAPI()
        self._server = None
        self._thread = None

        self.app.mount(
            "/uploads", StaticFiles(directory=self.upload_dir), name="uploads"
        )
        self._setup_routes()

    def _setup_routes(self):
        @self.app.post("/upload")
        async def upload(file: UploadFile = File(...)):
            filename = (
                f"{uuid.uuid4().hex}{Path(file.filename).suffix}"
                if file.filename
                else f"{uuid.uuid4().hex}.bin"
            )
            save_path = self.upload_dir / filename
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(await file.read())
            return {"url": f"http://{self.host}:{self.port}/uploads/{filename}"}

    def start(self):
        if self._server:
            return
        import uvicorn

        config = uvicorn.Config(app=self.app, host=self.host, port=self.port)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        logger.info(f"图床服务器已启动: http://{self.host}:{self.port}")

    def stop(self):
        if self._server:
            self._server.should_exit = True
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
            self._server = None
            self._thread = None
            logger.info("图床服务器已优雅关闭")


