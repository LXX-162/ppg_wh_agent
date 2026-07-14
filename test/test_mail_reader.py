import unittest
from mail.mail_reader import MailReader

class TestMailReader(unittest.TestCase):
    def test_init(self):
        reader = MailReader("imap.example.com", "user", "pass")
        self.assertEqual(reader.host, "imap.example.com")

if __name__ == '__main__':
    unittest.main()
