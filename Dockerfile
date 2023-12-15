FROM python:3-slim
RUN apt-get update && apt-get install vim -y
RUN pip install --upgrade pip && pip install requests pandas
RUN pip install openai plotly minio jinja2 kaleido
#COPY ./main.py /srv/main.py
CMD ["tail", "-f", "/dev/null"]