import email.utils
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from mail.mail_reader import MailReader
reader = MailReader()
mails = reader.fetch_recent(limit=None, search_criteria='(SINCE "13-Jul-2026")')
for m in mails:
    if 'JXHJ' in m['subject'] or 'FGDT' in m['subject']:
        date_str = m['message'].get('Date')
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.day == 14 and dt.month == 7 and dt.year == 2026:
            print("SUBJECT:", m['subject'], " | SENDER:", m['sender'], " | DATE:", dt)
