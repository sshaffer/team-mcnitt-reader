#docker build -t blogger-notifier .
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the script into the container
COPY blogger-notifier.py .

# Run the script
CMD ["python", "-u", "blogger-notifier.py"]
