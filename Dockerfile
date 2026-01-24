# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy application code
COPY . .

# Default port if not set
ENV PORT=8080

# Run with gunicorn using shell-form CMD to expand PORT variable
CMD sh -c "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 120 app:app"
