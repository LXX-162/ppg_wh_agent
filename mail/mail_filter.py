import json
import os
import logging

logger = logging.getLogger(__name__)

class MailFilter:
    def __init__(self, processed_uid_file="processed_uid.json"):
        self.processed_uid_file = processed_uid_file
        self.processed_uids = self._load_processed_uids()

    def _load_processed_uids(self):
        if os.path.exists(self.processed_uid_file):
            with open(self.processed_uid_file, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        return set()

    def save_processed_uid(self, uid):
        self.processed_uids.add(uid)
        with open(self.processed_uid_file, 'w', encoding='utf-8') as f:
            json.load(list(self.processed_uids), f)

    def is_processed(self, uid):
        return uid in self.processed_uids

    def filter_by_sender_or_subject(self, sender, subject):
        """根据发件人名单或标题关键词进行过滤"""
        pass
