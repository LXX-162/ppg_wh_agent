import email.utils
import time
from mail.mail_reader import MailReader
from mail.email_saver import save_attachments

reader = MailReader()
mails = []
for _ in range(5):
    try:
        mails = reader.fetch_recent(limit=None, search_criteria='(SINCE "13-Jul-2026")')
        break
    except Exception as e:
        print("Retry", e)
        time.sleep(2)

for m in mails:
    if 'JXHJ' in m['subject'] and 'FGDT' in m['subject'] and '11点计划' in m['subject'] and '何' in m['subject']:
        date_str = m['message'].get('Date')
        dt = email.utils.parsedate_to_datetime(date_str)
        print("SUBJECT:", m['subject'], " | SENDER:", m['sender'], " | DATE:", dt)
        
        # Call save_attachments
        saved = save_attachments(m['uid'], m['message'], output_dir='file/pdf_test/')
        print("Saved PDFs:", saved)
