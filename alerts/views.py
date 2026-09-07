from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from .models import AlertRecipient
from .whatsapp import normalize_whatsapp_number


def recipient_list(request):
    """View to list, add, and manage alert recipient contacts (Email and WhatsApp)."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone_number = request.POST.get('phone_number', '').strip()
        role = request.POST.get('role', 'security')
        department = request.POST.get('department', '').strip()
        send_email = request.POST.get('send_email') == 'on'
        send_whatsapp = request.POST.get('send_whatsapp') == 'on'

        if not name or not email:
            messages.error(request, "Name and valid email address are required.")
        else:
            recipient, created = AlertRecipient.objects.get_or_create(
                email=email,
                defaults={
                    'name': name,
                    'phone_number': phone_number or None,
                    'role': role,
                    'department': department,
                    'send_email': send_email,
                    'send_whatsapp': send_whatsapp,
                    'is_active': True
                }
            )
            if not created:
                recipient.name = name
                recipient.phone_number = phone_number or None
                recipient.role = role
                recipient.department = department
                recipient.send_email = send_email
                recipient.send_whatsapp = send_whatsapp
                recipient.is_active = True
                recipient.save()
                messages.success(request, f"Updated existing contact '{name}' ({email}).")
            else:
                messages.success(request, f"✔ Added new security alert contact '{name}' successfully!")
        return redirect('alerts:recipient_list')

    recipients = AlertRecipient.objects.all()
    default_recipients = getattr(settings, 'ALERT_RECIPIENT_EMAILS', [])
    default_phones = getattr(settings, 'ALERT_RECIPIENT_PHONES', [])

    # Multi-channel statistics
    total_count = recipients.count()
    email_active_count = recipients.filter(is_active=True, send_email=True).count()
    whatsapp_active_count = recipients.filter(is_active=True, send_whatsapp=True).exclude(phone_number__isnull=True).exclude(phone_number__exact='').count()

    twilio_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '').strip()
    twilio_from = getattr(settings, 'TWILIO_WHATSAPP_FROM', 'whatsapp:+17372212163')
    is_twilio_configured = bool(twilio_sid)

    context = {
        'recipients': recipients,
        'default_recipients': default_recipients,
        'default_phones': default_phones,
        'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL', 'alerts@campusguard.edu'),
        'email_backend': getattr(settings, 'EMAIL_BACKEND', ''),
        'total_count': total_count,
        'email_active_count': email_active_count,
        'whatsapp_active_count': whatsapp_active_count,
        'is_twilio_configured': is_twilio_configured,
        'twilio_from': twilio_from,
    }
    return render(request, 'alerts/recipient_list.html', context)


def recipient_edit(request, pk):
    """Edit an existing alert recipient's details, phone number, and channel preferences."""
    recipient = get_object_or_404(AlertRecipient, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone_number = request.POST.get('phone_number', '').strip()
        role = request.POST.get('role', recipient.role)
        department = request.POST.get('department', '').strip()
        send_email = request.POST.get('send_email') == 'on'
        send_whatsapp = request.POST.get('send_whatsapp') == 'on'
        is_active = request.POST.get('is_active') == 'on'

        if not name or not email:
            messages.error(request, "Name and valid email address are required.")
        else:
            # Check unique email constraint if changed
            if email != recipient.email and AlertRecipient.objects.filter(email=email).exclude(pk=pk).exists():
                messages.error(request, f"Another contact already exists with email '{email}'.")
            else:
                recipient.name = name
                recipient.email = email
                recipient.phone_number = phone_number or None
                recipient.role = role
                recipient.department = department
                recipient.send_email = send_email
                recipient.send_whatsapp = send_whatsapp
                recipient.is_active = is_active
                recipient.save()
                messages.success(request, f"✔ Updated contact details for '{name}' successfully!")

    return redirect('alerts:recipient_list')


def recipient_delete(request, pk):
    """Delete a recipient contact."""
    recipient = get_object_or_404(AlertRecipient, pk=pk)
    if request.method == 'POST':
        email = recipient.email
        recipient.delete()
        messages.info(request, f"Removed alert recipient '{email}'.")
    return redirect('alerts:recipient_list')


def recipient_toggle(request, pk):
    """Toggle active/paused status for an alert recipient."""
    recipient = get_object_or_404(AlertRecipient, pk=pk)
    recipient.is_active = not recipient.is_active
    recipient.save(update_fields=['is_active'])
    status_str = "Active (Receiving Alerts)" if recipient.is_active else "Paused (Not Receiving Alerts)"
    messages.info(request, f"Status for '{recipient.name}' updated to: {status_str}.")
    return redirect('alerts:recipient_list')


def send_test_email(request):
    """Send a test security email to verify email delivery."""
    if request.method == 'POST':
        test_email = request.POST.get('test_email', '').strip()
        if not test_email:
            messages.error(request, "Please enter a test destination email address.")
            return redirect('alerts:recipient_list')

        resend_key = getattr(settings, 'RESEND_API_KEY', '').strip()
        if resend_key:
            from .mailer import send_via_resend
            html_body = f"""
            <div style="font-family: Arial, sans-serif; padding: 25px; background: #0f172a; color: #f8fafc; border-radius: 10px; max-width: 600px; border: 1px solid #38bdf8;">
                <h2 style="color: #38bdf8; margin-top: 0;">🛡️ CampusGuard AI Security Dispatch Check</h2>
                <p>This is an automated verification test sent via <strong>Resend HTTPS REST API (Port 443)</strong>.</p>
                <div style="background: rgba(56, 189, 248, 0.1); border-left: 4px solid #38bdf8; padding: 12px 16px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px; color: #e2e8f0;">
                        <strong>Dispatch Channel Status:</strong> ACTIVE & VERIFIED<br>
                        <strong>Destination:</strong> {test_email}<br>
                        <strong>Network Transport:</strong> Secure HTTPS (Render Cloud Safe)
                    </p>
                </div>
                <p style="font-size: 13px; color: #94a3b8;">When a suspended student is detected, official alerts with CCTV snapshots and disciplinary details will be delivered here instantly.</p>
            </div>
            """
            ok, err = send_via_resend(resend_key, [test_email], "🛡️ [TEST] CampusGuard AI Notification Channel Check", html_body)
            if ok:
                messages.success(request, f"✔ Test security email successfully dispatched to '{test_email}' via Resend HTTPS! Please check your inbox.")
                return redirect('alerts:recipient_list')
            else:
                messages.warning(request, f"Resend reported: {err}. Attempting SMTP fallback...")

        try:
            send_mail(
                subject="🛡️ [TEST] CampusGuard AI Email Notification System Check",
                message="This is a test security alert verification email from CampusGuard AI. If you are receiving this, your alert dispatch channel is functioning properly.",
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'CampusGuard AI <alerts@campusguard.edu>'),
                recipient_list=[test_email],
                fail_silently=False
            )
            messages.success(request, f"✔ Test security email successfully dispatched to '{test_email}'. Check inbox or development console!")
        except Exception as e:
            messages.error(request, f"Failed to send test email: {str(e)}")

    return redirect('alerts:recipient_list')



def send_test_whatsapp(request):
    """Send a test security WhatsApp message to verify WhatsApp delivery."""
    if request.method == 'POST':
        test_phone = request.POST.get('test_phone', '').strip()
        if not test_phone:
            messages.error(request, "Please enter a test WhatsApp phone number.")
            return redirect('alerts:recipient_list')

        to_addr = normalize_whatsapp_number(test_phone)
        if not to_addr:
            messages.error(request, "Invalid phone number. Please include country code (e.g. +91 76718 55983).")
            return redirect('alerts:recipient_list')

        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '').strip()
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '').strip()
        from_whatsapp = getattr(settings, 'TWILIO_WHATSAPP_FROM', 'whatsapp:+17372212163').strip()
        content_sid = getattr(settings, 'TWILIO_WHATSAPP_CONTENT_SID', 'HXfe5ab5f00277942d4d4200328b4d403c').strip()

        if account_sid and auth_token:
            from .whatsapp import send_twilio_message
            test_body = "🛡️ *CampusGuard AI Test Alert*: System WhatsApp notification channel is active and verified!"
            ok, err = send_twilio_message(account_sid, auth_token, from_whatsapp, to_addr, test_body, content_sid)
            if ok:
                messages.success(request, f"✔ Live test WhatsApp message dispatched to '{test_phone}'! Check your WhatsApp.")
            else:
                messages.error(request, f"Failed to send WhatsApp test message: {err}")
        else:
            messages.info(request, f"[SIMULATION] Test WhatsApp alert dispatched to '{to_addr}' (Twilio credentials not configured in production mode).")

    return redirect('alerts:recipient_list')

