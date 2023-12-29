from chatp.proto.services.mail.email_pb2 import email as EmailMessage

confirm_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Confirm</title>
</head>
<body>
    <p>
        Dear,<br>

            Welcome to ChatApp! <br>

            To confirm your account please click on the following link:&nbsp

            <a href="{link}">Confirm Link</a> <br>

            Sincerely, <br>

            The ChatApp Team <br>

            Note: replies to this email address are not monitored. <br>

    </p>
</body>
</html>
"""


def generate_confirm_message(link: str, to_addr: str):
    message = EmailMessage(to_addr=to_addr, template=confirm_html, link=link)
    return message.SerializeToString()
