FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose the port Railway assigns
ENV PORT=8080
EXPOSE $PORT

# Run the app
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
