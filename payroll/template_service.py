"""
Template Email Service
Handles building styled HTML emails from template content with multiple design themes.
"""

import re
import datetime

from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404

from employees.models import Employee


# ─── Public API ──────────────────────────────────────────────────────────────

def send_template_email(employee_id, email_body, subject, template_name="", design_id="corporate"):
    """
    Send a styled HTML email to an employee.
    
    Args:
        employee_id: UUID of the target employee
        email_body: Compiled template content (markdown-like, variables already substituted)
        subject: Email subject line
        template_name: Name of the template (for fallback subject)
        design_id: Design theme ID ('corporate', 'executive', 'gradient', 'minimal')
    
    Returns:
        dict with 'status' and 'message' keys
    
    Raises:
        ValueError: If required parameters are missing
        Employee.DoesNotExist: If employee not found
    """
    if not employee_id:
        raise ValueError("Employee ID is required.")
    if not email_body:
        raise ValueError("Email body content is required.")

    employee = get_object_or_404(Employee, id=employee_id)
    recipient_email = employee.email
    emp_name = f"{employee.first_name} {employee.last_name}"

    if not recipient_email:
        raise ValueError("Selected employee does not have an email address.")

    # Build subject fallback
    if not subject and template_name:
        subject = f"Document: {template_name}"
    elif not subject:
        subject = "HR Document"

    # Build styled HTML
    org_name = employee.organization.name if employee.organization else "B2linq"
    html_content = build_html_email(email_body, design_id, emp_name, template_name, org_name)

    from django.core.mail import get_connection
    
    # Check if notification settings are available
    notification_host = getattr(settings, 'NOTIFICATION_EMAIL_HOST', None)
    if notification_host:
        connection = get_connection(
            backend=getattr(settings, 'NOTIFICATION_EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend'),
            host=notification_host,
            port=int(getattr(settings, 'NOTIFICATION_EMAIL_PORT', 587)),
            username=getattr(settings, 'NOTIFICATION_EMAIL_HOST_USER', ''),
            password=getattr(settings, 'NOTIFICATION_EMAIL_HOST_PASSWORD', ''),
            use_tls=getattr(settings, 'NOTIFICATION_EMAIL_USE_TLS', True),
        )
        from_email_addr = getattr(settings, 'NOTIFICATION_DEFAULT_FROM_EMAIL', 'lakkavaramlinus@gmail.com')
    else:
        connection = None
        from_email_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@b2linq.com')

    # Format dynamic sender name: "Organization Name <sender_email>"
    from_email = f"{org_name} <{from_email_addr}>"

    send_mail(
        subject,
        email_body,  # plain text fallback
        from_email,
        [recipient_email],
        html_message=html_content,
        fail_silently=False,
        connection=connection,
    )

    return {
        "status": "success",
        "message": f"Email sent successfully to {emp_name} ({recipient_email})."
    }


# ─── HTML Email Builder ─────────────────────────────────────────────────────

def build_html_email(body_text, design_id, recipient_name, template_name, org_name="B2linq"):
    """
    Convert markdown-like body text into styled HTML email based on design theme.
    
    Args:
        body_text: Raw template content with markdown-like formatting
        design_id: Design theme identifier
        recipient_name: Name of the employee receiving the email
        template_name: Name of the template document
        org_name: Dynamic name of the organization
    
    Returns:
        Complete HTML email string
    """
    body_html = _markdown_to_html(body_text)
    today = datetime.date.today().strftime('%d %b %Y')

    design_map = {
        'corporate': _design_corporate,
        'executive': _design_executive,
        'gradient': _design_gradient,
        'minimal': _design_minimal,
    }

    renderer = design_map.get(design_id, _design_corporate)
    return renderer(body_html, recipient_name, template_name, today, org_name)


# ─── Markdown-to-HTML Converter ──────────────────────────────────────────────

def _markdown_to_html(text):
    """Convert simple markdown-like syntax to inline-styled HTML for email."""
    lines = text.split('\n')
    html_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            html_lines.append('<div style="height:8px;"></div>')
            continue

        if stripped == '---':
            html_lines.append('<hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0;" />')
            continue

        if stripped.startswith('### '):
            inner = _md_inline(stripped[4:])
            html_lines.append(
                f'<h3 style="font-size:13px;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.05em;margin:16px 0 6px 0;">{inner}</h3>'
            )
            continue

        if stripped.startswith('# '):
            inner = _md_inline(stripped[2:])
            html_lines.append(
                f'<h1 style="font-size:18px;font-weight:800;text-transform:uppercase;'
                f'letter-spacing:0.02em;margin:12px 0 8px 0;">{inner}</h1>'
            )
            continue

        if stripped.startswith('* '):
            inner = _md_inline(stripped[2:])
            html_lines.append(
                f'<div style="padding-left:16px;margin:4px 0;">'
                f'<span style="margin-right:6px;">•</span>{inner}</div>'
            )
            continue

        num_match = re.match(r'^(\d+)\.\s', stripped)
        if num_match:
            inner = _md_inline(re.sub(r'^\d+\.\s', '', stripped))
            num = num_match.group(1)
            html_lines.append(
                f'<div style="padding-left:16px;margin:4px 0;">'
                f'<span style="margin-right:6px;font-weight:700;">{num}.</span>{inner}</div>'
            )
            continue

        inner = _md_inline(stripped)
        html_lines.append(f'<p style="margin:4px 0;line-height:1.6;">{inner}</p>')

    return '\n'.join(html_lines)


def _md_inline(text):
    """Convert **bold** markdown to <strong> tags."""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)


# ─── Design Themes ──────────────────────────────────────────────────────────
# Each design function returns a complete HTML email document string.
# All use table-based layout with inline CSS for maximum email client compatibility.

def _design_corporate(body, name, title, today, org_name="B2linq"):
    """Professional blue corporate letterhead with verification seal."""
    first_char = org_name[0].upper() if org_name else 'B'
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;padding:32px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <!-- Top Bar -->
  <tr><td style="height:4px;background:linear-gradient(90deg,#0a66c2,#6366f1);"></td></tr>
  <!-- Header -->
  <tr><td style="padding:28px 32px 20px 32px;border-bottom:1px solid #e2e8f0;">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td>
        <div style="display:inline-block;width:32px;height:32px;background:linear-gradient(135deg,#0a66c2,#818cf8);border-radius:6px;text-align:center;line-height:32px;color:#fff;font-weight:800;font-size:14px;margin-right:10px;vertical-align:middle;">{first_char}</div>
        <span style="font-size:15px;font-weight:800;color:#1e293b;text-transform:uppercase;letter-spacing:0.02em;vertical-align:middle;">{org_name}</span>
        <div style="font-size:9px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:0.15em;margin-top:4px;">Corporate HR Operations</div>
      </td>
      <td style="text-align:right;vertical-align:top;">
        <div style="display:inline-block;background:#eff6ff;border:1px solid #bfdbfe;border-radius:4px;padding:3px 10px;font-size:9px;font-weight:700;color:#1d4ed8;text-transform:uppercase;letter-spacing:0.1em;">Confidential</div>
        <div style="font-size:9px;color:#94a3b8;margin-top:6px;">{today}</div>
      </td>
    </tr></table>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:28px 32px;font-size:12px;color:#475569;line-height:1.7;">
    {body}
  </td></tr>
  <!-- Footer -->
  <tr><td style="padding:20px 32px 28px 32px;border-top:1px solid #e2e8f0;">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td>
        <div style="display:inline-block;background:#ecfdf5;border:1px solid #a7f3d0;border-radius:20px;padding:4px 12px;">
          <span style="display:inline-block;width:6px;height:6px;background:#10b981;border-radius:50%;margin-right:6px;vertical-align:middle;"></span>
          <span style="font-size:8px;color:#065f46;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;vertical-align:middle;">{org_name} Verified</span>
        </div>
      </td>
      <td style="text-align:right;">
        <div style="font-size:11px;color:#0a66c2;font-style:italic;font-weight:600;">HR Management</div>
        <div style="height:1px;width:100px;background:#e2e8f0;margin:6px 0 4px auto;"></div>
        <div style="font-size:8px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;">Authorized Signatory</div>
      </td>
    </tr></table>
  </td></tr>
</table>
</td></tr></table>
</body></html>'''


def _design_executive(body, name, title, today, org_name="B2linq"):
    """Dark luxury theme with gold signature accents and wax-seal stamp."""
    first_char = org_name[0].upper() if org_name else 'B'
    short_name = org_name[:3].upper() if org_name else 'B2L'
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#0f0f23;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f23;padding:32px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background-color:#1a1a2e;border-radius:8px;overflow:hidden;border:1px solid rgba(245,158,11,0.15);box-shadow:0 8px 32px rgba(0,0,0,0.3);">
  <!-- Gold Top Bar -->
  <tr><td style="height:3px;background:linear-gradient(90deg,#d97706,#fbbf24,#d97706);"></td></tr>
  <!-- Header -->
  <tr><td style="padding:28px 32px 20px 32px;border-bottom:1px solid rgba(245,158,11,0.15);">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td>
        <div style="display:inline-block;width:36px;height:36px;background:linear-gradient(135deg,#d97706,#fbbf24);border-radius:50%;text-align:center;line-height:36px;color:#1a1a2e;font-weight:800;font-size:15px;margin-right:12px;vertical-align:middle;">{first_char}</div>
        <span style="font-size:14px;font-weight:800;color:#fef3c7;text-transform:uppercase;letter-spacing:0.15em;vertical-align:middle;">{org_name}</span>
        <div style="font-size:8px;color:rgba(245,158,11,0.5);font-weight:600;text-transform:uppercase;letter-spacing:0.2em;margin-top:4px;">Executive Division</div>
      </td>
      <td style="text-align:right;vertical-align:top;">
        <div style="display:inline-block;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);border-radius:2px;padding:3px 12px;font-size:9px;font-weight:700;color:#fbbf24;text-transform:uppercase;letter-spacing:0.15em;">★ Premium</div>
        <div style="font-size:9px;color:rgba(245,158,11,0.35);margin-top:6px;">{today}</div>
      </td>
    </tr></table>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:28px 32px;font-size:12px;color:#cbd5e1;line-height:1.7;">
    <div style="color:#cbd5e1;">
    {body}
    </div>
  </td></tr>
  <!-- Footer -->
  <tr><td style="padding:20px 32px 28px 32px;border-top:1px solid rgba(245,158,11,0.12);">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="text-align:center;vertical-align:middle;">
        <div style="display:inline-block;width:48px;height:48px;border:2px solid rgba(245,158,11,0.3);border-radius:50%;text-align:center;line-height:44px;">
          <span style="color:#fbbf24;font-weight:800;font-size:11px;letter-spacing:0.15em;">{short_name}</span>
        </div>
        <div style="font-size:7px;color:rgba(245,158,11,0.4);font-weight:700;text-transform:uppercase;letter-spacing:0.2em;margin-top:4px;">Certified</div>
      </td>
      <td style="text-align:right;">
        <div style="font-size:11px;color:rgba(251,191,36,0.6);font-style:italic;font-weight:600;">Director, HR Operations</div>
        <div style="height:1px;width:110px;background:linear-gradient(90deg,transparent,rgba(245,158,11,0.3));margin:6px 0 4px auto;"></div>
        <div style="font-size:8px;color:rgba(245,158,11,0.3);font-weight:600;text-transform:uppercase;letter-spacing:0.1em;">Authorized Signatory</div>
      </td>
    </tr></table>
  </td></tr>
</table>
</td></tr></table>
</body></html>'''


def _design_gradient(body, name, title, today, org_name="B2linq"):
    """Vibrant gradient header with contemporary layout."""
    first_char = org_name[0].upper() if org_name else 'B'
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;padding:32px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <!-- Gradient Header -->
  <tr><td style="background:linear-gradient(135deg,#7c3aed,#d946ef,#ec4899);padding:28px 32px;">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td>
        <div style="display:inline-block;width:36px;height:36px;background:rgba(255,255,255,0.2);border-radius:8px;text-align:center;line-height:36px;color:#fff;font-weight:800;font-size:15px;margin-right:12px;vertical-align:middle;border:1px solid rgba(255,255,255,0.1);">{first_char}</div>
        <span style="font-size:16px;font-weight:800;color:#ffffff;text-transform:uppercase;letter-spacing:0.02em;vertical-align:middle;">{org_name}</span>
        <div style="font-size:9px;color:rgba(255,255,255,0.6);font-weight:600;text-transform:uppercase;letter-spacing:0.2em;margin-top:4px;padding-left:48px;">Human Resources • Document Services</div>
      </td>
      <td style="text-align:right;vertical-align:top;">
        <div style="display:inline-block;background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.1);border-radius:20px;padding:4px 12px;">
          <span style="display:inline-block;width:5px;height:5px;background:#34d399;border-radius:50%;margin-right:5px;vertical-align:middle;"></span>
          <span style="font-size:8px;color:#fff;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;vertical-align:middle;">Active Document</span>
        </div>
        <div style="font-size:9px;color:rgba(255,255,255,0.4);margin-top:6px;">{today}</div>
      </td>
    </tr></table>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:28px 32px;font-size:12px;color:#475569;line-height:1.7;">
    {body}
  </td></tr>
  <!-- Footer -->
  <tr><td style="padding:20px 32px 28px 32px;border-top:1px solid #e2e8f0;">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td>
        <div style="display:inline-block;width:36px;height:36px;background:linear-gradient(135deg,#7c3aed,#d946ef);border-radius:10px;text-align:center;line-height:36px;color:#fff;font-size:16px;margin-right:10px;vertical-align:middle;">✓</div>
        <div style="display:inline-block;vertical-align:middle;">
          <div style="font-size:9px;color:#7c3aed;font-weight:700;text-transform:uppercase;letter-spacing:0.15em;">Document Verified</div>
          <div style="font-size:8px;color:#94a3b8;">Digitally processed by {org_name} HR Suite</div>
        </div>
      </td>
      <td style="text-align:right;">
        <div style="font-size:11px;color:#7c3aed;font-weight:600;">HR Team</div>
        <div style="height:2px;width:80px;background:linear-gradient(90deg,#7c3aed,#d946ef);border-radius:2px;margin:6px 0 4px auto;"></div>
        <div style="font-size:8px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;">Issuer</div>
      </td>
    </tr></table>
  </td></tr>
</table>
</td></tr></table>
</body></html>'''


def _design_minimal(body, name, title, today, org_name="B2linq"):
    """Clean whitespace with thin serif typography and minimal branding."""
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f8fafc;font-family:Georgia,'Times New Roman',Times,serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc;padding:32px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:4px;overflow:hidden;border:1px solid #e2e8f0;">
  <!-- Thin Top Line -->
  <tr><td style="height:3px;background-color:#1e293b;"></td></tr>
  <!-- Header -->
  <tr><td style="padding:40px 40px 24px 40px;border-bottom:1px solid #e2e8f0;">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td>
        <div style="font-size:20px;font-weight:300;color:#1e293b;text-transform:uppercase;letter-spacing:0.25em;">{org_name}</div>
        <div style="margin-top:10px;">
          <span style="display:inline-block;width:32px;height:1px;background:#cbd5e1;vertical-align:middle;"></span>
          <span style="font-size:9px;color:#94a3b8;letter-spacing:0.3em;text-transform:uppercase;margin:0 12px;vertical-align:middle;">Official Correspondence</span>
          <span style="display:inline-block;width:32px;height:1px;background:#cbd5e1;vertical-align:middle;"></span>
        </div>
      </td>
      <td style="text-align:right;vertical-align:top;">
        <div style="font-size:10px;color:#64748b;letter-spacing:0.1em;">{today}</div>
      </td>
    </tr></table>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:32px 40px;font-size:12px;color:#475569;line-height:1.8;font-family:Arial,Helvetica,sans-serif;">
    {body}
  </td></tr>
  <!-- Footer -->
  <tr><td style="padding:28px 40px 36px 40px;border-top:1px solid #e2e8f0;">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td>
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.2em;margin-bottom:8px;">With regards,</div>
        <div style="font-size:12px;color:#475569;">Human Resources Department</div>
        <div style="height:1px;width:130px;background:#e2e8f0;margin-top:6px;"></div>
      </td>
      <td style="text-align:right;">
        {f'<div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.2em;margin-bottom:8px;">Acknowledged by,</div><div style="font-size:12px;color:#475569;">{name}</div><div style="height:1px;width:130px;background:#e2e8f0;margin-top:6px;margin-left:auto;"></div>' if name else ''}
      </td>
    </tr></table>
    <!-- Brand Mark -->
    <div style="text-align:center;margin-top:28px;opacity:0.3;">
      <span style="display:inline-block;width:24px;height:1px;background:#94a3b8;vertical-align:middle;"></span>
      <span style="font-size:7px;color:#94a3b8;letter-spacing:0.3em;text-transform:uppercase;font-family:Arial,sans-serif;margin:0 8px;vertical-align:middle;">{org_name}</span>
      <span style="display:inline-block;width:24px;height:1px;background:#94a3b8;vertical-align:middle;"></span>
    </div>
  </td></tr>
</table>
</td></tr></table>
</body></html>'''
