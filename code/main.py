import requests
import pandas as pd
import zipfile
import io
import os
import plotly.express as px
from datetime import datetime, timedelta
from minio import Minio

import requests
import re
import json
from send_email import send_email

def get_records_difference(dwca_endpoint, target_date):
    response = requests.get(dwca_endpoint.replace('archive.do', 'resource'))
    html = response.text

    # Extract aDataSet using a regular expression
    pattern = r'var aDataSet = (\[.*?\]);\s*\n\s*\$\(document\)'
    match = re.search(pattern, html, re.DOTALL)
    if match:
        aDataSet_raw = match.group(1)
        aDataSet_no_comments = re.sub(r'/\*.*?\*/', '', aDataSet_raw, flags=re.DOTALL)
        aDataSet_no_newlines = aDataSet_no_comments.replace('&nbsp;', ' ').replace('\n', '')
        aDataSet_no_single_quotes = re.sub(r"(?<!\\)'", '"', aDataSet_no_newlines)
        aDataSet_clean = re.sub(r"<[^>]+>", "", aDataSet_no_single_quotes)

        try:
            ds_json = json.loads(aDataSet_clean)
        except json.JSONDecodeError as e:
            print("Error parsing JSON:", e)
            import pdb; pdb.set_trace()
        
        most_recent_count = int(ds_json[0][2].replace(',', '').replace('.', ''))
        filtered_sorted_data = sorted(
            (item for item in ds_json if datetime.strptime(item[1], '%Y-%m-%d %H:%M:%S') < target_date),
            key=lambda x: datetime.strptime(x[1], '%Y-%m-%d %H:%M:%S'),
            reverse=True
        )
        target_count = filtered_sorted_data[0] if filtered_sorted_data else min(ds_json, key=lambda x: datetime.strptime(x[1], '%Y-%m-%d %H:%M:%S'))
        target_count = int(target_count[2].replace(',', '').replace('.', ''))
        return most_recent_count - target_count  # Note this number could be negative

def get_missing_attributions_bionomia(key):
    file = 'missing_attributions.csv'
    url = f'https://bionomia.net/dataset/{key}/{file}.zip'
    response = requests.get(url)
    zipfile_obj = zipfile.ZipFile(io.BytesIO(response.content))
    zipfile_obj.extractall('.')
    df = pd.read_csv(f'./{file}', usecols=['user_id'])
    frequent_values = df['user_id'].value_counts().nlargest(5)
    os.remove(f'./{file}')

    file = 'users.csv'
    users_url = f'https://bionomia.net/dataset/{key}/{file}.zip'
    response = requests.get(users_url)
    zipfile_obj = zipfile.ZipFile(io.BytesIO(response.content))
    zipfile_obj.extractall('.')
    users = pd.read_csv(f'./{file}', usecols=['name', 'id'])
    merged_data = users[users['id'].isin(frequent_values.index)].drop_duplicates()
    
    os.remove(f'./{file}')

    merged_data = merged_data.merge(frequent_values.rename('frequency'), left_on='id', right_index=True)
    title_text = 'ORCIDs missing from Collections Management System<br><sub>Top 5 people identifiers by number of new attributions in Bionomia</sub>'
    fig = px.bar(merged_data, x='name', y='frequency', title=title_text, color='name')
    fig.update_layout(
        xaxis_title='',
        yaxis_title='attribution #',
        showlegend=False
    )
    return fig, len(df), url

def save_figure(fig, key, minio_client):
    image_name = f"plot_{datetime.now().strftime('%Y-%m')}.png"
    fig.write_image(image_name)

    with open(image_name, 'rb') as file_data:
        file_stat = os.stat(image_name)
        minio_client.put_object('misc', f'static/{key}/{image_name}', file_data, file_stat.st_size)

    os.remove(image_name)
    return f'{os.getenv("MINIO_URI")}/misc/static/{key}/{image_name}'

def get_curator_info():
    base_url = 'http://api.gbif.org/v1'
    datasets_info = {}

    response = requests.get(f'{base_url}/dataset/search?publishingCountry=NO&subtype=SPECIMEN')
    if response.status_code == 200:
        datasets = response.json()['results'][0:2]
        for dataset in datasets:
            mc_client = Minio(os.getenv('MINIO_URI'), access_key=os.getenv('MINIO_ACCESS_KEY'), secret_key=os.getenv('MINIO_SECRET_KEY'))
            dataset_info = requests.get(f'{base_url}/dataset/{dataset["key"]}').json()
            citation_count = requests.get(f'{base_url}/literature/search?gbifDatasetKey={dataset["key"]}&limit=1').json()['count']
            contacts = [c for c in dataset_info['contacts'] if c['type'] == 'ADMINISTRATIVE_POINT_OF_CONTACT' and 'email' in c]
            if contacts:
                dwca_endpoint = next((d['url'] for d in dataset_info['endpoints'] if '/archive.do?r=' in d['url']), None)
                stats_image, bionomia_count, bionomia_url = get_missing_attributions_bionomia(dataset['key'])
                stats_image_url = save_figure(stats_image, dataset['key'], mc_client)
                dataset_details = {
                    'citation_count': citation_count,
                    'title': dataset_info['title'],
                    'new_records': get_records_difference(dwca_endpoint, datetime.now() - timedelta(days=365)),
                    'bionomia_count': bionomia_count,
                    'stats_image': stats_image_url,
                    'bionomia_url': bionomia_url,
                    'key': dataset['key']
                }
                
                for contact in contacts:
                    if 'email' in contact and contact['email']:
                        email = contact['email'][0]
                        if email not in datasets_info:
                            datasets_info[email] = {
                                'name': f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip(),
                                'datasets': [dataset_details]
                            }
                        else:
                            datasets_info[email]['datasets'].append(dataset_details)

    return datasets_info

def send_emails():
    curators = get_curator_info()
    for email, info in curators.items():
        send_email(info['name'], email, info['datasets'])

send_emails()

    
