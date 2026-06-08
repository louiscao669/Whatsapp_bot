FROM python:3.9
WORKDIR /code
COPY backend/requirements.txt /code/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/backend/requirements.txt
COPY backend /code/backend
COPY supabase /code/supabase
WORKDIR /code/backend
CMD ["python", "app.py"]
