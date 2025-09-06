FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime
ENV USER_AGENT="Mozilla/5.0 (Linux; Ubuntu 20.04) AppleWebKit/537.36 Chrome/91.0.4472.124"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tft_model-epoch=16-val_loss=9.4569.ckpt ./
COPY training_tft_model.pkl ./
COPY nbeats_model-epoch=14-val_loss=9.7598.ckpt ./

COPY app.py .

ENV PYTHONUNBUFFERED=1

CMD ["waitress-serve", "--listen", "*:5000", "app:app"]
