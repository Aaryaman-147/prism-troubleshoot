FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the embedding model at BUILD time, so a container starts without
# HuggingFace access (an external audit flagged first-start downloads).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app/ ./app/
# No .env inside the image: configuration comes from docker-compose's
# env_file (../.env) at container creation. Baking .env.example in here put
# placeholder keys into the container.

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
