import os
import json
import logging

logger = logging.getLogger(__name__)

class SeenMailsManager:
    """
    管理已处理过的邮件 UID，防止重复处理。
    持久化到 output/cache/seen_mails.json。
    格式：{ "seen_uids": ["12345", "12346", ...] } 保持添加顺序
    """
    CACHE_FILE = os.path.join("output", "cache", "seen_mails.json")

    @classmethod
    def load(cls) -> set:
        """加载已读邮件 UID 集合，返回 set。"""
        if not os.path.exists(cls.CACHE_FILE):
            return set()
        try:
            with open(cls.CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("seen_uids", []))
        except Exception as e:
            logger.error(f"加载 seen_mails 失败: {e}")
            return set()

    @classmethod
    def save(cls, seen_uids: set):
        """保存已读邮件 UID 集合（按数字升序排列）。"""
        os.makedirs(os.path.dirname(cls.CACHE_FILE), exist_ok=True)
        try:
            # 转 int 排序再转回 str，保证数字顺序
            sorted_list = sorted(seen_uids, key=lambda x: int(x))
            data = {"seen_uids": sorted_list}
            with open(cls.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.debug(f"已保存 {len(seen_uids)} 条已读记录至 {cls.CACHE_FILE}")
        except Exception as e:
            logger.error(f"保存 seen_mails 失败: {e}")

    @classmethod
    def mark_seen(cls, uid: str):
        """将单个 UID 标记为已处理，并立即持久化。"""
        seen = cls.load()
        seen.add(str(uid))
        cls.save(seen)

    @classmethod
    def mark_seen_batch(cls, uids):
        """批量标记 UID 为已处理。"""
        seen = cls.load()
        for uid in uids:
            seen.add(str(uid))
        cls.save(seen)

    @classmethod
    def is_seen(cls, uid: str, seen_set: set = None) -> bool:
        """
        判断 UID 是否已被处理过。
        可传入已加载的 set 避免重复读文件（在批量处理时推荐）。
        """
        if seen_set is not None:
            return str(uid) in seen_set
        return str(uid) in cls.load()
