import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from api.config import settings

def send_email(to_email: str, subject: str, body_html: str) -> bool:
    """Core email dispatch function using SMTP."""
    if not settings.SMTP_USER or "your-email" in settings.SMTP_USER:
        print(f"[Email Simulation to {to_email}]: {subject}")
        print(body_html)
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        msg["To"] = to_email

        html_part = MIMEText(body_html, "html")
        msg.attach(html_part)

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.sendmail(settings.SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[Email Delivery Error]: {e}")
        return False

def send_welcome_email(tenant_email: str, tenant_name: str, account_number: str, paybill: str, due_date: str):
    """Sends onboarding email to new tenants with Paybill and Account Number."""
    subject = f"Welcome to Your New Home - Rent Payment Credentials ({account_number})"
    body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 12px; border: 1px solid #e2e8f0;">
      <h2 style="color: #059669;">Welcome, {tenant_name}!</h2>
      <p style="color: #475569; line-height: 1.6;">Your tenancy onboarding is complete. Below are your official M-Pesa payment details:</p>
      
      <div style="background: #f0fdf4; padding: 16px; border-radius: 8px; border-left: 4px solid #10b981; margin: 20px 0;">
        <p style="margin: 4px 0;"><strong>M-Pesa Paybill:</strong> {paybill}</p>
        <p style="margin: 4px 0;"><strong>Account Number:</strong> <span style="font-family: monospace; font-size: 16px; background: #e2e8f0; padding: 2px 6px; border-radius: 4px;">{account_number}</span></p>
        <p style="margin: 4px 0;"><strong>Rent Due Date:</strong> 5th of every month</p>
      </div>

      <p style="color: #64748b; font-size: 14px;">You can submit your M-Pesa payment proof directly online without logging in via our Tenant Portal.</p>
      <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
      <p style="color: #94a3b8; font-size: 12px; text-align: center;">Nairobi Rental Management Platform &bull; Email-Only Portal</p>
    </div>
    """
    return send_email(tenant_email or "tenant@example.com", subject, body)

def send_receipt_email(tenant_email: str, tenant_name: str, amount: float, period: str, balance: float):
    """Sends official rent payment receipt to tenant."""
    subject = f"Official Rent Payment Receipt - KES {amount:,.2f}"
    balance_status = f"KES {balance:,.2f}" if balance > 0 else "KES 0.00 (Fully Settled)"
    body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 12px; border: 1px solid #e2e8f0;">
      <h2 style="color: #0284c7;">Payment Receipt Confirmed</h2>
      <p style="color: #475569;">Dear {tenant_name},</p>
      <p style="color: #475569;">We have successfully approved your rent payment for <strong>{period}</strong>.</p>
      
      <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
        <tr style="background: #f8fafc;">
          <td style="padding: 10px; border: 1px solid #e2e8f0;"><strong>Amount Paid:</strong></td>
          <td style="padding: 10px; border: 1px solid #e2e8f0; color: #16a34a; font-weight: bold;">KES {amount:,.2f}</td>
        </tr>
        <tr>
          <td style="padding: 10px; border: 1px solid #e2e8f0;"><strong>Remaining Arrears/Balance:</strong></td>
          <td style="padding: 10px; border: 1px solid #e2e8f0;">{balance_status}</td>
        </tr>
      </table>

      <p style="color: #64748b; font-size: 14px;">Thank you for your prompt payment.</p>
    </div>
    """
    return send_email(tenant_email or "tenant@example.com", subject, body)

def send_rejection_email(tenant_email: str, tenant_name: str, reason: str):
    """Notifies tenant of a payment rejection with detailed reason."""
    subject = "ALERT: Rent Payment Record Verification Failed"
    body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 12px; border: 1px solid #fee2e2;">
      <h2 style="color: #dc2626;">Payment Verification Notice</h2>
      <p style="color: #475569;">Dear {tenant_name},</p>
      <p style="color: #475569;">Your submitted rent transaction proof could not be verified by the property administrator.</p>
      
      <div style="background: #fef2f2; padding: 16px; border-radius: 8px; border-left: 4px solid #ef4444; margin: 20px 0;">
        <p style="margin: 0; color: #991b1b;"><strong>Reason for Rejection:</strong> {reason}</p>
      </div>

      <p style="color: #64748b; font-size: 14px;">Please re-submit your valid M-Pesa transaction code or contact your property manager.</p>
    </div>
    """
    return send_email(tenant_email or "tenant@example.com", subject, body)

def send_landlord_alert_email(landlord_email: str, tenant_name: str, unit_number: str, amount: float):
    """Alerts landlord when a tenant submits a new M-Pesa payment via public portal."""
    subject = f"NEW PAYMENT SUBMITTED: Unit {unit_number} - KES {amount:,.2f}"
    body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 12px; border: 1px solid #e2e8f0;">
      <h2 style="color: #7c3aed;">New Pending Payment Submission</h2>
      <p style="color: #475569;">A tenant has submitted an M-Pesa payment proof for verification:</p>
      <ul>
        <li><strong>Unit Number:</strong> {unit_number}</li>
        <li><strong>Tenant / Phone:</strong> {tenant_name}</li>
        <li><strong>Amount Submitted:</strong> KES {amount:,.2f}</li>
      </ul>
      <p style="color: #475569;">Log into your Landlord Approval Queue to approve or reject this payment.</p>
    </div>
    """
    return send_email(landlord_email or "landlord@example.com", subject, body)
