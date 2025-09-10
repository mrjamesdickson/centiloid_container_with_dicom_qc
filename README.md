# Centiloid PET Container — DICOM in → NIfTI → Register to mask space → SUVR → Centiloid

This version accepts **DICOM** input, converts to **NIfTI** inside the container using **dcm2niix**, registers PET to your **mask/template space** using **SimpleITK** (rigid by default), then computes global cortical **SUVR** and **Centiloid** (for amyloid).

## Build
```
docker build -t xnatworks/xnat_centiloid_container .
```

## Run (DICOM input)
```
docker run --rm -v $PWD:/data xnatworks/xnat_centiloid_container   --dicom-dir /data/pet_dicom/   --template /data/template_space.nii.gz   --target-mask /data/centiloid_ctx_mask.nii.gz   --ref-mask /data/whole_cerebellum_mask.nii.gz   --tracer FBP   --mode amyloid   --out-dir /data/out   --reg-mode rigid
```
- Outputs:
  - `out/dcm2niix/pet.nii.gz` (converted NIfTI)
  - `out/registration/pet_in_template.nii.gz` (registered to mask space)
  - `out/registration/pet_to_template.tfm` (SimpleITK transform)
  - `out/centiloid.json`, `out/centiloid.csv`
  - `out/qc_overlay.png`

## Run (NIfTI input, skipping DICOM conversion)
```
docker run --rm -v $PWD:/data xnatworks/xnat_centiloid_container   --pet-nifti /data/pet.nii.gz   --template /data/template_space.nii.gz   --target-mask /data/centiloid_ctx_mask.nii.gz   --ref-mask /data/whole_cerebellum_mask.nii.gz   --tracer NAV4694   --mode amyloid   --out-dir /data/out   --reg-mode affine
```

## Notes
- Supply a **template NIfTI** that defines the coordinate space of your masks (e.g., MNI or your validated VOI space). PET is registered **to this template**; masks are assumed to already be in this space.
- Registration uses **Mattes MI**, random sampling, linear interpolation; choose `--reg-mode affine` if rigid isn’t sufficient.
- For **tau**, provide your experimental coefficients in `config/tracer_calibrations.yaml` under `tau:` and set `--mode tau`.
- Tracer Centiloid equations live in `config/tracer_calibrations.yaml` and can be adjusted to match your processing (Level‑2 calibration, different reference regions, timing, etc.).


---
## NEW: DICOM Parametric Map (SUVR) output
The pipeline now writes a **DICOM Parametric Map** (SOP Class: Parametric Map Storage) containing the SUVR volume:
- Location: `out/parametric_map/SUVR_parametric_map.dcm`
- Modality = `PM`, ImageType = `DERIVED\PRIMARY\PARAMETRIC_MAP`
- Units = Unitless (UCUM "1")
- Patient/Study information is copied from the input DICOM when available.

> This is intended for viewing/archival of the SUVR image in DICOM workflows. For strict conformance and orientation, ensure your template and NIfTI orientation match your site’s conventions; adjust the plane orientation calculation if needed.


---
## NEW: QC PDF and DICOM-embedded report
The pipeline now produces a **PDF QC report** with the mask overlays and key metrics and embeds it back into DICOM:
- PDF: `out/qc/QC_Report.pdf`
- Encapsulated PDF DICOM: `out/qc_dicom/QC_Report.pdf.dcm` (SOP Class: Encapsulated PDF Storage)
- Secondary Capture DICOM: `out/qc_dicom/QC_Report_SC.dcm` (single-frame RGB derived image)

These carry Patient/Study metadata copied from the source DICOM (when available), enabling archival in PACS.
