#!/usr/bin/env python3
"""
Test script for XNAT integration functionality.
This script tests the XNAT upload module without running the full container.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from xnat_upload import XNATUploader, upload_to_xnat

def create_test_data():
    """Create test data files for XNAT upload testing"""
    
    # Create temporary directory
    test_dir = tempfile.mkdtemp(prefix="centiloid_test_")
    print(f"Creating test data in: {test_dir}")
    
    # Create mock centiloid.json results
    test_results = {
        "inputs": {
            "dicom_dir": "/data/pet_dicom",
            "template": "template_space.nii.gz",
            "target_mask": "centiloid_ctx_mask.nii.gz",
            "ref_mask": "whole_cerebellum_mask.nii.gz",
            "tracer": "FBP",
            "mode": "amyloid",
            "reg_mode": "rigid"
        },
        "intermediate": {
            "converted_pet_nifti": "/output/dcm2niix/pet.nii.gz",
            "registered_pet_nifti": "pet_in_template.nii.gz",
            "transform": "pet_to_template.tfm"
        },
        "metrics": {
            "target_mean": 6660.752110451892,
            "reference_mean": 5060.199002210051,
            "suvr_global_cortex_over_ref": 1.3163024038269635,
            "scaled_value": 63.14994331352912,
            "scaled_units": "Centiloid"
        }
    }
    
    # Write results JSON
    results_path = Path(test_dir) / "centiloid.json"
    with open(results_path, 'w') as f:
        json.dump(test_results, f, indent=2)
        
    # Create mock CSV file
    csv_path = Path(test_dir) / "centiloid.csv"
    with open(csv_path, 'w') as f:
        f.write("tracer,mode,target_mean,reference_mean,suvr,scaled_value,scaled_units\n")
        f.write("FBP,amyloid,6660.752110451892,5060.199002210051,1.3163024038269635,63.14994331352912,Centiloid\n")
        
    # Create mock QC overlay image (placeholder)
    qc_path = Path(test_dir) / "qc_overlay.png"
    with open(qc_path, 'wb') as f:
        # Write minimal PNG header (placeholder)
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(b'Test QC image placeholder')
        
    # Create mock PDF (placeholder)
    pdf_path = Path(test_dir) / "qc_report.pdf"
    with open(pdf_path, 'wb') as f:
        f.write(b'%PDF-1.4\nTest PDF placeholder')
        
    print(f"Created test files:")
    print(f"  - {results_path}")
    print(f"  - {csv_path}")
    print(f"  - {qc_path}")
    print(f"  - {pdf_path}")
    
    return test_dir, str(results_path)

def test_xnat_connection(host, username, password):
    """Test XNAT connection"""
    print(f"\n=== Testing XNAT Connection ===")
    print(f"Host: {host}")
    print(f"User: {username}")
    
    uploader = XNATUploader(host, username, password, "TEST", "TEST")
    
    if uploader.test_connection():
        print("✓ XNAT connection successful")
        return True
    else:
        print("✗ XNAT connection failed")
        return False

def test_assessment_creation(host, username, password, project, session, test_dir, results_path):
    """Test creating XNAT assessment"""
    print(f"\n=== Testing Assessment Creation ===")
    print(f"Project: {project}")
    print(f"Session: {session}")
    
    try:
        success = upload_to_xnat(
            results_json_path=results_path,
            output_dir=test_dir,
            xnat_host=host,
            username=username,
            password=password,
            project_id=project,
            session_id=session
        )
        
        if success:
            print("✓ Assessment creation successful")
            return True
        else:
            print("✗ Assessment creation failed")
            return False
            
    except Exception as e:
        print(f"✗ Assessment creation failed: {e}")
        return False

def main():
    """Main test function"""
    print("XNAT Integration Test")
    print("=" * 50)
    
    # Configuration - update these for your XNAT instance
    xnat_config = {
        "host": "http://localhost:8080",  # Your XNAT host
        "username": "admin",              # XNAT username
        "password": "admin",              # XNAT password
        "project": "TestProject",        # Test project
        "session": "TestSession"         # Test session
    }
    
    print("Configuration:")
    for key, value in xnat_config.items():
        if key != "password":
            print(f"  {key}: {value}")
        else:
            print(f"  {key}: {'*' * len(value)}")
    
    # Create test data
    test_dir, results_path = create_test_data()
    
    try:
        # Test 1: XNAT connection
        connection_ok = test_xnat_connection(
            xnat_config["host"], 
            xnat_config["username"], 
            xnat_config["password"]
        )
        
        if not connection_ok:
            print("\n❌ XNAT connection failed. Check your configuration.")
            return False
        
        # Test 2: Assessment creation
        assessment_ok = test_assessment_creation(
            xnat_config["host"],
            xnat_config["username"],
            xnat_config["password"],
            xnat_config["project"],
            xnat_config["session"],
            test_dir,
            results_path
        )
        
        if assessment_ok:
            print("\n🎉 All tests passed! XNAT integration is working.")
            print("\nNext steps:")
            print("1. Install the Centiloid plugin on your XNAT server")
            print("2. Build and deploy the updated container")
            print("3. Run centiloid processing with XNAT upload enabled")
            return True
        else:
            print("\n❌ Assessment creation failed.")
            print("\nTroubleshooting:")
            print("1. Ensure the Centiloid plugin is installed on XNAT")
            print("2. Check that the project and session exist")
            print("3. Verify user permissions")
            return False
            
    finally:
        # Cleanup test data
        import shutil
        shutil.rmtree(test_dir)
        print(f"\nCleaned up test data: {test_dir}")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)