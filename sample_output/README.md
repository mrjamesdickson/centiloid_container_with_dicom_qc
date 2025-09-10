# Sample Output

This directory contains example outputs from the Centiloid PET processing container using synthetic test data.

## Files Generated

### Primary Outputs
- `centiloid.json` - Complete processing results in JSON format
- `centiloid.csv` - Summary metrics in CSV format  
- `qc_overlay.png` - Quality control visualization showing mask overlays on PET data

### Intermediate Files
- `registration/pet_in_template.nii.gz` - PET image registered to template space
- `registration/pet_to_template.tfm` - SimpleITK transformation parameters

## Results Summary

**Input**: Synthetic amyloid PET data with elevated cortical signal
**Processing**: FBP tracer calibration, rigid registration to template space
**Output Metrics**:
- SUVR: 2.07 (cortical/cerebellar ratio)
- Centiloid Score: 212.2 (indicating high synthetic amyloid burden)

## Usage
These sample outputs demonstrate the expected file structure and content when processing PET data through the container. The high Centiloid score reflects the intentionally elevated cortical signal in the synthetic test data.