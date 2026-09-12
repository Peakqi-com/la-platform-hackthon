FROM python:3.12-slim
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgeos-dev libproj-dev && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml ./backend/
RUN pip install --no-cache-dir "./backend[llm]"
COPY backend ./backend
COPY rules ./rules
COPY fixtures ./fixtures
WORKDIR /srv/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
