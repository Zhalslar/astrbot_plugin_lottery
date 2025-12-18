import json
import os
from typing import TYPE_CHECKING

from astrbot.api import logger

if TYPE_CHECKING:
    from .lottery import LotteryManager


class LotteryPersistence:
    """抽奖数据持久化 – 只负责读写文件，不懂业务"""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def save(self, manager: "LotteryManager") -> bool:
        try:
            # ✅ 只存活动列表，每个活动内部已含 prize_config
            payload = {
                "activities": {
                    gid: act.to_dict() for gid, act in manager.activities.items()
                }
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"[LotteryPersistence] 文件写入失败: {e}")
        except TypeError as e:
            logger.error(f"[LotteryPersistence] 序列化失败: {e}")
        return False

    def load(self, manager: "LotteryManager") -> bool:
        if not os.path.exists(self.file_path):
            return False
        try:
            with open(self.file_path, encoding="utf-8") as f:
                payload = json.load(f)

            from .lottery import LotteryActivity

            # ✅ 用外部模板重建活动；活动内部会把自己的 prize_config 覆盖回去
            manager.activities = {
                gid: LotteryActivity.from_dict(d, manager.template)
                for gid, d in payload.get("activities", {}).items()
            }
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"[LotteryPersistence] 文件读取失败: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"[LotteryPersistence] JSON 解析失败: {e}")
        return False
