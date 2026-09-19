FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY src ./src
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home agent
USER agent
EXPOSE 8080
CMD ["opentelemetry-instrument", "python", "-m", "support_agent.app"]
