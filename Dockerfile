FROM python:3.11-slim

WORKDIR /app

# Copy all source code and install
COPY pyproject.toml .
COPY cloudora/ cloudora/

RUN pip install --no-cache-dir .

# Create data directory
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["cloudora"]
