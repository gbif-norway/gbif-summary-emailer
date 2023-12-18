import smtplib
from email.message import EmailMessage
from datetime import datetime
from jinja2 import Template
import os


def send_email(name, email, datasets):
    msg = EmailMessage()
    msg['Subject'] = f'Your {datetime.now().strftime("%b %Y")} GBIF dataset status update'
    msg['From'] = os.getenv('SMTP_EMAIL')
    msg['To'] = os.getenv('TEST_EMAILS') # email
    template = Template(open('template.html').read())
    print(len(datasets))
    rendered_html = template.render(name=name, all_datasets_link='https://www.gbif.org/occurrence/search?' + '&'.join([f'dataset_key={k["key"]}' for k in datasets]), datasets=datasets,date=datetime.now().strftime("%B %Y"))
    # with open('rendered_html.html', 'w') as file:
        # file.write(rendered_html)
    import pdb; pdb.set_trace()
    msg.set_content(rendered_html, subtype='html')

    with smtplib.SMTP(os.getenv('SMTP_SERVER'), 587) as smtp:
        smtp.starttls()
        smtp.login(os.getenv('SMTP_EMAIL'), os.getenv('SMTP_PASSWORD'))
        smtp.send_message(msg)
        smtp.quit()