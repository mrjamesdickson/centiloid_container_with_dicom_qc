# XNAT Integration Guide

This guide explains how to set up and use the complete XNAT integration for the Centiloid container, including automatic assessment creation and file uploads.

## Overview

The Centiloid container now includes built-in XNAT integration that:

1. **Processes PET data** using the Centiloid methodology
2. **Automatically creates** a structured assessment in XNAT
3. **Uploads all output files** (QC images, PDFs, DICOM files, results)
4. **Stores quantitative metrics** in a queryable format

## Prerequisites

### 1. Install the Centiloid XNAT Plugin

First, install the Centiloid datatype plugin on your XNAT server:

```bash
# Build the plugin
cd ../pet_centiloid_xnat_datatype
./gradlew build

# Copy to XNAT plugins directory
cp build/libs/xnat-centiloid-plugin-1.0.0.jar /path/to/xnat/plugins/

# Restart XNAT server
```

### 2. Verify Plugin Installation

Test the plugin installation:

```bash
cd ../pet_centiloid_xnat_datatype
python examples/test_plugin.py
```

### 3. Update Container Image

Build the updated container with XNAT integration:

```bash
cd ../centiloid_container_with_dicom_qc
docker build -t xnatworks/xnat_centiloid_container:v1.1.0 .
```

## Usage

### Manual Container Execution

Run the container with XNAT upload enabled:

```bash
docker run --rm \
  -v /path/to/dicom:/input \
  -v /path/to/output:/output \
  xnatworks/xnat_centiloid_container:v1.1.0 \
  python -m app.pipeline \
  --dicom-dir /input \
  --template /maskdata/template_space.nii.gz \
  --target-mask /maskdata/centiloid_ctx_mask.nii.gz \
  --ref-mask /maskdata/whole_cerebellum_mask.nii.gz \
  --tracer FBP \
  --mode amyloid \
  --out-dir /output \
  --reg-mode rigid \
  --xnat-host https://your-xnat.com \
  --xnat-user your_username \
  --xnat-pass your_password \
  --xnat-project PROJECT_ID \
  --xnat-session SESSION_ID
```

### XNAT Container Service Integration

The container automatically integrates with XNAT Container Service. When launched from XNAT:

1. **Update the container command** in XNAT Container Service to use the new image
2. **XNAT parameters are automatically filled** - no manual configuration needed
3. **Assessments are created automatically** after successful processing

#### Container Service Configuration

Update your container service configuration:

```json
{
  "image": "xnatworks/xnat_centiloid_container:v1.1.0",
  "command-line": "python -m app.pipeline --dicom-dir /input --template #TEMPLATE# --target-mask #TARGET_MASK# --ref-mask #REF_MASK# --tracer #TRACER# --mode #MODE# --out-dir /output --reg-mode #REG_MODE# --xnat-host #XNAT_BASE_URL# --xnat-user #USER_ID# --xnat-pass #USER_PASSWORD# --xnat-project #PROJECT_ID# --xnat-session #SUBJECT_ID#"
}
```

## What Gets Created in XNAT

When processing completes successfully, the following is created in XNAT:

### Centiloid Assessment

A new assessment of type `centiloid:centiloidAssessmentData` containing:

**Quantitative Results:**
- Target region mean value
- Reference region mean value
- Global cortical SUVR
- Centiloid value and units

**Processing Parameters:**
- Input tracer, mode, registration settings
- Template and mask file paths
- Container version and processing date

**Output File References:**
- QC overlay image path
- QC PDF report path
- DICOM parametric map path
- Results JSON/CSV paths

### Uploaded Files

All output files are uploaded to the assessment:

- `centiloid.json` - Complete results in JSON format
- `centiloid.csv` - Summary metrics in CSV format
- `qc_overlay.png` - Quality control overlay image
- `qc_report.pdf` - Comprehensive QC report
- DICOM files - Parametric maps and overlay series

## Testing the Integration

### 1. Test XNAT Connection

```bash
cd ../centiloid_container_with_dicom_qc
python test_xnat_integration.py
```

### 2. Run Test Processing

Process a test dataset with XNAT upload:

```bash
# Update configuration in test script
python create_test_data.py

# Run container with test data
docker run --rm \
  -v $PWD/test_data:/input \
  -v $PWD/test_output:/output \
  xnatworks/xnat_centiloid_container:v1.1.0 \
  python -m app.pipeline \
  --dicom-dir /input/dicom \
  --template /input/template_space.nii.gz \
  --target-mask /input/centiloid_ctx_mask.nii.gz \
  --ref-mask /input/whole_cerebellum_mask.nii.gz \
  --tracer FBP \
  --mode amyloid \
  --out-dir /output \
  --reg-mode rigid \
  --xnat-host http://localhost:8080 \
  --xnat-user admin \
  --xnat-pass admin \
  --xnat-project TestProject \
  --xnat-session TestSession
```

### 3. Verify Results in XNAT

1. Log into XNAT web interface
2. Navigate to your test project and session
3. Check for the new Centiloid assessment
4. Verify quantitative metrics are displayed correctly
5. Download and review uploaded files

## Error Handling

The integration includes robust error handling:

### Container Processing Continues
- If XNAT upload fails, the container processing still completes normally
- All output files are still written to the output directory
- Error details are logged for debugging

### Upload Status Reporting
- XNAT upload status is included in the final JSON output
- Success/failure is clearly indicated
- Error messages provide debugging information

### Common Issues and Solutions

**Connection Failed:**
- Check XNAT host URL and network connectivity
- Verify username/password are correct
- Ensure XNAT is accessible from the container environment

**Assessment Creation Failed:**
- Verify the Centiloid plugin is installed and active
- Check that the project and session exist in XNAT
- Ensure user has sufficient permissions

**File Upload Failed:**
- Check available disk space on XNAT server
- Verify output files were created successfully
- Check XNAT file upload limits and permissions

## Security Considerations

### Credential Handling
- XNAT passwords are not logged or stored
- Use XNAT tokens instead of passwords when possible
- Consider using environment variables for sensitive data

### Network Security
- Use HTTPS for XNAT connections in production
- Ensure proper firewall rules for container-to-XNAT communication
- Consider using VPN or private networks for sensitive data

### Data Privacy
- Ensure DICOM data is properly de-identified before processing
- Follow institutional policies for data handling and storage
- Be aware of data residency requirements

## Monitoring and Logging

The integration provides detailed logging:

```
=== XNAT Upload ===
Uploading results to XNAT:
  Host: https://xnat.example.com
  Project: MyProject
  Session: MySession
✓ Successfully uploaded results to XNAT

=== Final Results ===
{
  "inputs": {...},
  "metrics": {...},
  "xnat_upload": {
    "status": "success",
    "project": "MyProject", 
    "session": "MySession"
  }
}
```

## Support

For issues with the integration:

1. **Check the logs** - Detailed error messages are provided
2. **Test components separately** - Use the test scripts to isolate issues
3. **Verify prerequisites** - Ensure plugin is installed and XNAT is accessible
4. **Review permissions** - Check user permissions in XNAT

## Future Enhancements

Planned improvements:

- **Batch processing** - Process multiple sessions in one container run
- **Enhanced QC metrics** - Additional quality control measures
- **Custom templates** - Support for site-specific templates and masks
- **Automated reporting** - Generate summary reports across multiple assessments