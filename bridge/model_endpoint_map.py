import random
from astrbot.api import logger

model_endpoint_map ={
  "o3-xxx": [
    {
      "session_id": "b2096d33-2651-4802-97c1-c9b788c01c7a",
      "message_id": "151968ec-b43f-4d0b-a655-e508156af578",
      "mode": "direct_chat"
    },
    {
      "session_id": "session_for_battle_A",
      "message_id": "message_for_battle_A",
      "mode": "battle",
      "battle_target": "A"
    },
    {
      "session_id": "session_for_battle_B",
      "message_id": "message_for_battle_B",
      "mode": "battle",
      "battle_target": "B"
    }
  ],
  "gemini-xxx": {
      "session_id": "session_for_battle_A",
      "message_id": "message_for_battle_A",
      "mode": "battle",
      "battle_target": "A"
    }
}


def get_mapping(model_name: str):
    """
    根据模型名从 model_endpoint_map 中获取 session_id、message_id、mode、battle_target。
    支持 list 随机选择 和 dict 单个映射两种格式。
    """
    entry = model_endpoint_map.get(model_name)
    if not entry:
        return None, None, None, None

    if isinstance(entry, list):
        selected = random.choice(entry)
        logger.info(f"为模型 '{model_name}' 从ID列表中随机选择了一个映射。")
    elif isinstance(entry, dict):
        selected = entry
        logger.info(f"为模型 '{model_name}' 找到了单个端点映射（旧格式）。")
    else:
        return None, None, None, None

    session_id = selected.get("session_id")
    message_id = selected.get("message_id")
    mode = selected.get("mode")
    battle_target = selected.get("battle_target")

    # 日志输出
    log_msg = f"将使用 Session ID: ...{session_id[-6:] if session_id else 'N/A'}"
    if mode:
        details = [f"模式: {mode}"]
        if mode == "battle":
            details.append(f"目标: {battle_target or 'A'}")
        log_msg += " (" + ", ".join(details) + ")"
    logger.info(log_msg)

    return session_id, message_id, mode, battle_target
