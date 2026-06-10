FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy app code
COPY cloudora/ cloudora/

# Create data directory
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["cloudora"]
