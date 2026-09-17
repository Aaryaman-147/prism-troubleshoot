FROM python:3.12-slim

WORKDIR /app

# Install CPU-only torch FIRST, from PyTorch's CPU wheel index — otherwise
# pip resolves the default torch package, which pulls in several GB of
# unnecessary CUDA/GPU libraries (cusparse, cublas, cudnn, etc.) that this
# project never uses, since embeddings run on CPU. This alone cuts the
# Docker build from ~gigabytes to a small fraction of that.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY .env.example .env

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
