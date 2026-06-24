FROM python:3.11
WORKDIR /code
COPY packages/eten-shared /code/packages/eten-shared
COPY message-bot/requirements.txt /code/message-bot/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/message-bot/requirements.txt
COPY message-bot /code/message-bot
WORKDIR /code/message-bot
CMD ["python", "app.py"]
