# Sample Output - Real Florbetapir PET Data

This directory contains example outputs from the Centiloid PET processing container using **real clinical florbetapir (AV45) PET data** from an elderly subject.

## Files Generated

### Primary Outputs
- `centiloid.json` - Complete processing results in JSON format
- `centiloid.csv` - Summary metrics in CSV format  
- `qc_overlay.png` - Quality control visualization showing mask overlays on registered PET data

### Intermediate Files
- `dcm2niix/pet.nii.gz` - Original PET data converted from DICOM to NIfTI
- `registration/pet_in_template.nii.gz` - PET image registered to template space
- `registration/pet_to_template.tfm` - SimpleITK transformation parameters

## Results Summary

**Input**: Real florbetapir (AV45) PET DICOM from elderly subject
**Processing**: FBP tracer calibration, rigid registration to template space
**Output Metrics**:
- Target (cortical) mean: 6660.8 SUV units
- Reference (cerebellar) mean: 5060.2 SUV units  
- **SUVR: 1.32** (cortical/cerebellar ratio)
- **Centiloid Score: 63.1** (indicating moderate amyloid burden)

## Clinical Interpretation

A Centiloid score of 63.1 suggests **moderate amyloid pathology**:
- Values >25 are generally considered amyloid-positive
- This score indicates significant amyloid plaque deposition
- Consistent with Alzheimer's disease pathophysiology

## Technical Notes

- DICOM data successfully converted using dcm2niix
- Rigid registration achieved good alignment (see QC overlay)
- FBP calibration applied per published Centiloid methodology
- All processing completed without errors