FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create a non-root user for security and switch to it
RUN useradd -m appuser
RUN chown -R appuser:appuser /app
USER appuser

# Create a directory for data if it doesn't exist
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Set up entrypoint command using gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
