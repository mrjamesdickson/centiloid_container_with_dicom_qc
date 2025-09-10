FROM python:3.11-slim

# System deps: dcm2niix for DICOM->NIfTI conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
        dcm2niix \
        libglib2.0-0 libgl1-mesa-glx libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY config /app/config
COPY centiloid /app/centiloid

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "app.pipeline"]
