import resend
import config

resend.api_key = config.RESEND_API_KEY


def send_verification_code(to_email: str, code: str):
    resend.Emails.send({
        "from": config.RESEND_FROM,
        "to": to_email,
        "subject": f"{code} is your Ideios verification code",
        "text": f"""Welcome to Ideios!

Your verification code is:

    {code}

This code expires in 10 minutes.
If you didn't request this, you can safely ignore this email.

— The Ideios Team"""
    })
