FROM python:3.11
WORKDIR /code
COPY packages/eten-shared /code/packages/eten-shared
COPY whatsapp-bot/requirements.txt /code/whatsapp-bot/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/whatsapp-bot/requirements.txt
COPY whatsapp-bot /code/whatsapp-bot
WORKDIR /code/whatsapp-bot
CMD ["python", "app.py"]
