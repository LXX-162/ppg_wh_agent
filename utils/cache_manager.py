import os
import json
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    CACHE_FILE = os.path.join("output", "cache", "shipping.json")

    @classmethod
    def load_cache(cls):
        """
        加载 shipping.json 缓存。
        如果文件不存在，返回空字典。
        """
        if not os.path.exists(cls.CACHE_FILE):
            return {}
            
        try:
            with open(cls.CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载缓存文件失败 {cls.CACHE_FILE}: {e}")
            return {}

    @classmethod
    def save_cache(cls, data):
        """
        保存数据到 shipping.json 缓存中。
        如果目录不存在会自动创建。
        
        :param data: 字典格式 { "订单号": { "shipping": "", "danger": "" } }
        """
        # 确保目录存在
        os.makedirs(os.path.dirname(cls.CACHE_FILE), exist_ok=True)
        
        try:
            with open(cls.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"成功保存缓存至 {cls.CACHE_FILE}")
        except Exception as e:
            logger.error(f"保存缓存文件失败 {cls.CACHE_FILE}: {e}")
