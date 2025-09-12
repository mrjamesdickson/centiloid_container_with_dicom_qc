FROM python:3.11-slim

# System deps: dcm2niix for DICOM->NIfTI conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
        dcm2niix \
        libglib2.0-0 libgl1-mesa-dri libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY config /app/config

# Copy template and mask files to /maskdata/ for default usage
RUN mkdir -p /maskdata
COPY test_data/template_space.nii.gz /maskdata/template_space.nii.gz
COPY test_data/centiloid_ctx_mask.nii.gz /maskdata/centiloid_ctx_mask.nii.gz
COPY test_data/whole_cerebellum_mask.nii.gz /maskdata/whole_cerebellum_mask.nii.gz

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "app.pipeline"]
