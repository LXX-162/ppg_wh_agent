import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from mail.mail_reader import MailReader
reader = MailReader()
mails = reader.fetch_recent(limit=None, search_criteria='(SINCE "13-Jul-2026")')
for m in mails:
    if 'JXHJ' in m['subject'] or 'FGDT' in m['subject']:
        print(m['subject'], ' | SENDER:', m['sender'])
