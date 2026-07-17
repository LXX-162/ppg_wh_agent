import email.utils
from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter

reader = MailReader()
mails = []
try: 
    mails = reader.fetch_recent(limit=None, search_criteria='(SINCE "13-Jul-2026")')
except Exception as e:
    pass

for m in mails:
    if 'JXHJ' in m['subject'] and 'FGDT' in m['subject'] and '11点计划' in m['subject'] and '何' in m['subject']:
        date_str = m['message'].get('Date')
        dt = email.utils.parsedate_to_datetime(date_str)
        t = MailFilter.get_type(m)
        print('SUBJECT:', m['subject'])
        print('SENDER:', m['sender'])
        print('TYPE:', t)
