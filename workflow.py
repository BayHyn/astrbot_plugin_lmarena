import asyncio
import re
import base64
import random
from pathlib import Path
from typing import Optional
import aiohttp
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
import astrbot.core.message.components as Comp
import io
from PIL import Image



def extract_first_frame(raw: bytes) -> bytes:
    """把 GIF 的第一帧抽出来，返回 PNG/JPEG 字节流"""
    img_io = io.BytesIO(raw)
    img = Image.open(img_io)
    if img.format != "GIF":
        return raw  # 不是 GIF，原样返回
    first_frame = img.convert("RGBA")
    out_io = io.BytesIO()
    first_frame.save(out_io, format="PNG")
    return out_io.getvalue()


async def compress_image(image_bytes: bytes, max_bytes: int) -> bytes:
    """
    线程池里压缩静态图片到指定大小以内，GIF 不处理
    """
    loop = asyncio.get_running_loop()

    def _inner(image_bytes: bytes, max_bytes: int) -> bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes))

            # GIF 不处理
            if img.format == "GIF":
                return image_bytes

            if len(image_bytes) <= max_bytes:
                return image_bytes

            # 2) 先把长边一次性缩到 1024 以下，质量先压到 70
            img.thumbnail((1024, 1024), Image.LANCZOS)  # type: ignore
            resampled = io.BytesIO()
            img.save(resampled, format=img.format, quality=70, optimize=True)
            resampled.seek(0)
            if resampled.tell() <= max_bytes:
                return resampled.getvalue()

            # 3) 还不够小，再进入原有循环微调
            quality, scale = 50, 0.6
            resample = Image.LANCZOS  # type: ignore

            while True:
                resampled.seek(0)
                resampled.truncate(0)

                if scale < 1:
                    w, h = img.size
                    tmp = img.resize((int(w * scale), int(h * scale)), resample)
                else:
                    tmp = img

                tmp.save(resampled, format=img.format, quality=quality, optimize=True)

                if resampled.tell() <= max_bytes or (quality <= 5 and scale <= 0.2):
                    break

                if quality > 5:
                    quality -= 5
                else:
                    scale *= 0.9

            return resampled.getvalue()

        except Exception as e:
            raise ValueError(f"图片压缩失败: {e}")

    return await loop.run_in_executor(None, _inner, image_bytes, max_bytes)




class Workflow:
    """
    工具类
    """
    headers = {"Content-Type": "application/json"}

    def __init__(self, base_url: str):
        """
        :param base_url: API 的 base url
        :param model: 模型名称
        """
        self.base_url = base_url
        self.session = aiohttp.ClientSession()

    async def _download_image(self, url: str, http: bool = True) -> bytes | None:
        """下载图片"""
        if http:
            url = url.replace("https://", "http://")
        try:
            async with self.session.get(url) as resp:
                return await resp.read()
        except Exception as e:
            logger.error(f"图片下载失败: {e}")
            return None

    async def _get_avatar(self, user_id: str) -> bytes | None:
        """根据 QQ 号下载头像"""
        # 简单容错：如果不是纯数字就随机一个
        if not user_id.isdigit():
            user_id = "".join(random.choices("0123456789", k=9))

        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
        try:
            async with self.session.get(avatar_url, timeout=10) as resp:
                resp.raise_for_status()
                return await resp.read()
        except Exception as e:
            logger.error(f"下载头像失败: {e}")
            return None

    async def _load_bytes(self, src: str) -> bytes | None:
        """统一把 src 转成 bytes"""
        raw: Optional[bytes] = None
        # 1. 本地文件
        if Path(src).is_file():
            raw = Path(src).read_bytes()
        # 2. URL
        elif src.startswith("http"):
            raw = await self._download_image(src)
        # 3. Base64（直接返回）
        elif src.startswith("base64://"):
            return base64.b64decode(src[9:])
        if not raw:
            return None
        # 抽 GIF 第一帧
        return extract_first_frame(raw)

    async def get_first_image(self, event: AstrMessageEvent) -> bytes | None:
        """
        获取消息里的第一张图并以 Base64 字符串返回。
        顺序：
        1) 引用消息中的图片
        2) 当前消息中的图片
        3) 当前消息中的 @ 头像
        找不到返回 None。
        """

        # ---------- 1. 先看引用 ----------
        reply_seg = next(
            (s for s in event.get_messages() if isinstance(s, Comp.Reply)), None
        )
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Comp.Image):
                    if seg.url and (img := await self._load_bytes(seg.url)):
                        return img
                    if seg.file and (img := await self._load_bytes(seg.file)):
                        return img

        # ---------- 2. 再看当前消息 ----------
        for seg in event.get_messages():
            if isinstance(seg, Comp.Image):
                if seg.url and (img := await self._load_bytes(seg.url)):
                    return img
                if seg.file and (img := await self._load_bytes(seg.file)):
                    return img

            elif isinstance(seg, Comp.At) and str(seg.qq) != event.get_self_id():
                if avatar := await self._get_avatar(str(seg.qq)):
                    return avatar

            elif isinstance(seg, Comp.Plain):
                plains = seg.text.strip().split()
                if len(plains) == 2 and plains[1].startswith("@"):
                    if avatar := await self._get_avatar(plains[1][1:]):
                        return avatar

        # 兜底：发消息者自己的头像
        return await self._get_avatar(event.get_sender_id())

    async def fetch_content(
        self, image: bytes | None, text: str, model: str, retries: int = 3
    ) -> bytes | str | None:
        """
        发送「手办化」请求并返回图片 bytes；
        HTTP 非 200 时重试 retries 次，最后一次仍失败则返回错误字符串。
        """
        content: list[dict] = [{"type": "text", "text": text}]
        if image:
            compressed_img = await compress_image(image, 3_500_000)
            img = f"data:image/jpeg;base64,{base64.b64encode(compressed_img).decode()}"
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": img},
                }
            )
        data = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "n": 1,
        }
        url = f"{self.base_url}/v1/chat/completions"
        error_msg = None  # 记录最后一次的错误信息
        for attempt in range(retries + 1):
            logger.info(f"请求{model}(第 {attempt + 1} 次): {text[:50]}...")
            try:
                async with self.session.post(url, headers=self.headers, json=data) as resp:
                    result = await resp.json()
                    print(result)
                    if resp.status != 200:
                        error_msg = result.get("error", {}).get("message") or str(
                            result
                        )
                        raise ValueError(error_msg)  # 触发重试

                    # HTTP 200，尝试解析图片 URL
                    content_msg = result["choices"][0]["message"]["content"]
                    if match:= re.search(r"!\[.*?\]\((.*?)\)", content_msg):
                        img_url = match.group(1)
                        logger.info(f"返回图片 URL: {img_url}")
                        img = await self._download_image(img_url, http=False)
                        if not img:
                            error_msg = "图片下载失败"
                            raise ValueError("图片下载失败")  # 触发重试
                        return img
                    elif content_msg:
                        return content_msg
                    else:
                        error_msg = "响应为空"
                        raise ValueError(error_msg)

            except Exception as e:
                logger.error(f"第 {attempt + 1} 次失败: {e}")
                if attempt < retries:
                    await asyncio.sleep(2**attempt)
                # 最后一次循环继续，不会提前 return

        # 走到这里说明所有重试机会已用完
        return error_msg or "unknown error"


    async def fetch_models(self) -> list[str] | None:
        """
        获取 OpenAI 兼容的模型列表
        """
        url = f"{self.base_url}/v1/models"
        async with self.session.get(url, headers=self.headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return [m["id"] for m in data["data"]]
            else:
                logger.error(f"请求失败，状态码：{resp.status}")
                text = await resp.text()
                raise RuntimeError(text)

    async def terminate(self):
        if self.session:
            await self.session.close()
