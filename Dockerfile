
# Use an official Python runtime as a base image
FROM python:3.11-slim
 
# Set the working directory
WORKDIR /app
 
# Install system dependencies (needed for some Google packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
&& rm -rf /var/lib/apt/lists/*
 
# Copy and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy the application code
COPY . .
 
# Set Python path to include the app directory
ENV PYTHONPATH=/app
 
# Expose the correct port (main.py uses 8000)
EXPOSE 5000
 
# Run the application (without --reload for production)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
