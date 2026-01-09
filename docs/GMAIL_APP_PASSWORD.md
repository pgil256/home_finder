# Gmail App Password Setup

## Steps

1. **Enable 2-Step Verification**
   - Go to https://myaccount.google.com/security
   - Under "Signing in to Google", click "2-Step Verification"
   - Follow the prompts to enable it

2. **Generate App Password**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" as the app
   - Select your device type
   - Click "Generate"
   - Copy the 16-character password shown

3. **Update .env**
   ```
   EMAIL_HOST_USER='your-email@gmail.com'
   EMAIL_HOST_PASSWORD='xxxx xxxx xxxx xxxx'
   ```

4. **Test**
   ```bash
   venv/bin/python manage.py shell -c "
   from django.core.mail import send_mail
   send_mail('Test', 'It works!', None, ['your-email@gmail.com'])
   "
   ```
