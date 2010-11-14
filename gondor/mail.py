import argia

try:
    from django.core.mail.backends.base import BaseEmailBackend
except ImportError:
    BaseEmailBackend = None


class SendMailTask(object):
    
    queue = "mailer"
    
    @staticmethod
    def perform(runner, messages):
        smtp = smtplib.SMTP("mail1.gondor.ex.eldarion.com", 25, socket.getfqdn())
        for message in messages:
            from_addr, to_addrs, msg = message
            smtp.sendmail(from_addr, to_addrs, msg)
        smtp.quit()


if BaseEmailBackend:
    class QueuedEmailBackend(BaseEmailBackend):
        """
        Django e-mail backend for queueing message with argia.
        """
        
        def send_messages(self, email_messages):
            messages = []
            for email_message in email_messages:
                messages.append((
                    email_message.from_email,
                    email_message.recipients(),
                    email_message.message().as_string()
                ))
            argia.enqueue(SendMailTask, messages)
