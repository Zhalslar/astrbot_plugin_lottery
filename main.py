import re

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_tools import StarTools

from .core.lottery import LotteryManager, LotteryPersistence, PrizeLevel
from .utils import get_nickname


class LotteryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        self.lottery_data_file = (
            StarTools.get_data_dir("astrbot_plugin_lottery") / "lottery_data.json"
        )
        self.persistence = LotteryPersistence(str(self.lottery_data_file))
        self.manager = LotteryManager(self.persistence, config)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("开启抽奖")
    async def start_lottery(self, event: AstrMessageEvent):
        """开启抽奖活动"""
        _, msg = self.manager.start_activity(event.get_group_id())
        yield event.plain_result(msg)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("抽奖")
    async def draw_lottery(self, event: AstrMessageEvent):
        """参与抽奖"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        nickname = await get_nickname(event, user_id)
        msg, prize_level = self.manager.draw_lottery(group_id, user_id, nickname)

        if not prize_level:
            yield event.plain_result(msg)
            return
        activity = self.manager.activities.get(group_id)
        if not activity or prize_level not in activity.prize_config:
            yield event.plain_result(msg)   # 降级回退
            return

        prize_name = activity.prize_config[prize_level]["name"]
        yield event.plain_result(f"{prize_level.emoji} {msg}: {prize_name}")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("设置奖项")
    async def set_prize(self, event: AstrMessageEvent):
        """设置当前活动的奖项
        用法：设置奖项 <奖项等级> <概率> <数量>
        """
        m = re.match(
            r"设置奖项\s+(特等奖|一等奖|二等奖|三等奖)\s+(\d*\.?\d+)\s+(\d+)",
            event.message_str,
        )
        if not m:
            yield event.plain_result("格式错误\n正确示例：设置奖项 特等奖 0.01 1")
            return

        prize_name, prob, count = m.group(1), float(m.group(2)), int(m.group(3))
        if not (0 <= prob <= 1) or count <= 0:
            yield event.plain_result("概率须在 0-1 之间，数量须为正整数")
            return

        lvl = PrizeLevel.from_name(prize_name)
        if not lvl:
            yield event.plain_result(f"未知的奖项等级：{prize_name}")
            return

        ok = self.manager.set_prize_config(event.get_group_id(), lvl, prob, count)
        if not ok:
            yield event.plain_result("当前群没有进行中的抽奖活动")
            return

        yield event.plain_result(
            f"{lvl.emoji} 已设置 {prize_name}：\n"
            f"中奖概率：{prob * 100:.1f} %\n"
            f"奖品数量：{count} 个"
        )

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("关闭抽奖")
    async def stop_lottery(self, event: AstrMessageEvent):
        """关闭抽奖活动"""
        _, msg = self.manager.stop_activity(event.get_group_id())
        yield event.plain_result(msg)

    @filter.command("重置抽奖")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def reset_lottery(self, event: AstrMessageEvent):
        ok = self.manager.delete_activity(event.get_group_id())
        yield event.plain_result("本群抽奖已清空，可重新开启" if ok else "当前无抽奖可重置")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("抽奖状态")
    async def lottery_status(self, event: AstrMessageEvent):
        data = self.manager.get_status_and_winners(event.get_group_id())
        if not data:
            yield event.plain_result("当前群聊没有抽奖活动")
            return

        ov = data["overview"]
        lines = [
            f"📊 本群抽奖活动{'进行中' if ov['active'] else '已结束'}",
            f"参与 {ov['participants']} 人　中奖 {ov['winners']} 人",
            "🎁 奖品剩余：",
        ]
        lines += [f"{p['name']}：{p['remaining']}/{p['total']}" for p in data["prize_left"]]
        yield event.plain_result("\n".join(lines))

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.command("中奖名单")
    async def winner_list(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        activity = self.manager.activities.get(group_id)
        if not activity:
            yield event.plain_result("当前群聊没有抽奖活动")
            return
        data = self.manager.get_status_and_winners(group_id)
        if not data or not data["winners_by_lvl"]:
            yield event.plain_result("暂无中奖者" if data else "当前群聊没有抽奖活动")
            return

        lines = ["🏆 中奖名单："]
        for lvl, uids in data["winners_by_lvl"].items():
            user_names = [activity.participants.get(uid, uid) for uid in uids]
            lines.append(f"{lvl}：{'、'.join(user_names)}")
        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        """插件终止时"""
        logger.info("抽奖插件已终止")
