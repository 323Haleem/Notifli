FROM python:3.11-slim

WORKDIR /app

# Set default PORT (Railway will override this)
ENV PORT=8080

# Install dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose the port
EXPOSE $PORT

# Run the app - Railway sets $PORT automatically
CMD python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
