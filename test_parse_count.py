import sys
import os
import json
import io
import time
import email.utils
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from mail.mail_reader import MailReader
from mail.mail_filter import MailFilter
from mail.email_saver import save_attachments
from parser.pdf_parser import PDFParser
from parser.content_parser import ContentParser
import logging

logging.getLogger('parser').setLevel(logging.WARNING)

reader = MailReader()
mails = []
for _ in range(5):
    try:
        mails = reader.fetch_recent(limit=None, search_criteria='(SINCE "13-Jul-2026")')
        break
    except Exception as e:
        time.sleep(2)
target_orders = {}

for m in mails:
    date_str = m['message'].get('Date')
    dt = email.utils.parsedate_to_datetime(date_str)
    if dt.year == 2026 and dt.month == 7 and dt.day == 14:
        if MailFilter.get_type(m) == 'PDF_ORDER':
            saved = save_attachments(m['uid'], m['message'], output_dir='file/pdf_test_run/')
            for pdf_path in saved:
                raw_text = PDFParser.parse_pdf(pdf_path)
                order = ContentParser.parse_pdf_text(raw_text, os.path.basename(pdf_path))
                if order:
                    from business.field_normalizer import FieldNormalizer
                    order = FieldNormalizer.normalize(order)
                if order and order['order_no']:
                    target_orders[order['order_no']] = order

print('Extracted orders:', len(target_orders))
for o in ['11966082', '11966160', '11966175', '11966184', '11966191', '11966192', '11966194', '11966195', '11966207']:
    if o in target_orders:
        print(o, 'True')
    else:
        print(o, 'False')
