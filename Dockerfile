# Default image: platform (admin SPA + JSON API). Use message-bot/Dockerfile for the webhook service.
FROM node:20 AS frontend
WORKDIR /build
COPY platform/frontend/package.json platform/frontend/package-lock.json* ./
RUN npm install
COPY platform/frontend ./
RUN npm run build

FROM python:3.11
WORKDIR /code
COPY packages/eten-shared /code/packages/eten-shared
COPY platform/requirements.txt /code/platform/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/platform/requirements.txt
COPY platform /code/platform
COPY supabase /code/supabase
COPY --from=frontend /build/dist /code/platform/frontend/dist
WORKDIR /code/platform
CMD ["python", "app.py"]
