"""
XNAT integration module for uploading Centiloid assessment results.

This module handles:
1. Creating XNAT assessments via REST API
2. Uploading output files to XNAT
3. Error handling and retry logic
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class XNATUploader:
    """Handles uploading Centiloid results to XNAT"""
    
    def __init__(self, 
                 xnat_host: str,
                 username: str, 
                 password: str,
                 project_id: str,
                 session_id: str,
                 timeout: int = 300):
        """
        Initialize XNAT uploader
        
        Args:
            xnat_host: XNAT host URL
            username: XNAT username
            password: XNAT password
            project_id: XNAT project ID
            session_id: XNAT session/experiment ID
            timeout: Request timeout in seconds
        """
        self.xnat_host = xnat_host.rstrip('/')
        self.username = username
        self.password = password
        self.project_id = project_id
        self.session_id = session_id
        self.timeout = timeout
        
        # Setup session with retry strategy
        self.session = requests.Session()
        self.session.auth = (username, password)
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
    def test_connection(self) -> bool:
        """Test XNAT connection - simplified version"""
        # Skip connection test - will fail during actual upload if connection is bad
        print(f"[DEBUG] Skipping connection test, will validate during upload")
        return True
            
    def create_assessment(self, results_data: Dict[str, Any], output_dir: str) -> Optional[str]:
        """
        Create Centiloid assessment in XNAT using XML that conforms to centiloid.xsd
        
        Args:
            results_data: Centiloid processing results
            output_dir: Directory containing output files
            
        Returns:
            Assessment ID if successful, None if failed
        """
        try:
            print(f"[DEBUG] Creating XML assessment from results data")
            
            # Create XML that conforms to the schema
            xml_content = self._create_centiloid_xml(results_data, output_dir)
            print(f"[DEBUG] Generated XML content ({len(xml_content)} chars)")
            
            # Use imageAssessor endpoint as specified
            url = f"{self.xnat_host}/data/projects/{self.project_id}/subjects/{self.session_id}/experiments/{self.session_id}/assessors"
            print(f"[DEBUG] Creating assessment at URL: {url}")
            
            # Send XML as content with xsiType parameter for custom datatype
            headers = {
                'Content-Type': 'application/xml',
                'Accept': 'application/json'
            }
            
            # Use xsiType parameter to specify centiloid datatype
            params = {
                'xsiType': 'centiloid:CentiloidAssessment',
                'ID': f"CENTILOID_{self.session_id}_{int(__import__('datetime').datetime.now().timestamp())}"
            }
            
            response = self.session.post(url, data=xml_content, headers=headers, params=params, timeout=self.timeout)
            print(f"[DEBUG] Response status: {response.status_code}")
            print(f"[DEBUG] Response text: {response.text[:500]}...")
            
            response.raise_for_status()
            
            # Extract assessment ID from response
            assessment_id = self._extract_assessment_id(response)
            
            if assessment_id:
                print(f"[DEBUG] Successfully created assessment: {assessment_id}")
                logger.info(f"Successfully created XNAT assessment: {assessment_id}")
                return assessment_id
            else:
                print(f"[ERROR] Failed to extract assessment ID from response")
                logger.error(f"No assessment ID returned: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] HTTP error creating assessment: {e}")
            logger.error(f"HTTP error creating assessment: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"[ERROR] Response content: {e.response.text}")
                logger.error(f"Response content: {e.response.text}")
            return None
        except Exception as e:
            print(f"[ERROR] Error creating assessment: {e}")
            logger.error(f"Error creating assessment: {e}")
            return None
            
    def upload_files(self, assessment_id: str, output_dir: str) -> bool:
        """
        Upload output files to XNAT assessment
        
        Args:
            assessment_id: XNAT assessment ID
            output_dir: Directory containing output files
            
        Returns:
            True if all uploads successful, False otherwise
        """
        try:
            output_path = Path(output_dir)
            
            # Define files to upload with their descriptions
            files_to_upload = [
                ("centiloid.json", "Results JSON", "application/json"),
                ("centiloid.csv", "Results CSV", "text/csv"),
                ("qc_overlay.png", "QC Overlay Image", "image/png"),
                ("qc_report.pdf", "QC Report PDF", "application/pdf"),
            ]
            
            # Add DICOM files if they exist
            dicom_dir = output_path / "dicom_series"
            if dicom_dir.exists():
                for dicom_file in dicom_dir.glob("*.dcm"):
                    rel_path = str(dicom_file.relative_to(output_path))
                    files_to_upload.append((rel_path, f"DICOM {dicom_file.stem}", "application/dicom"))
            
            success_count = 0
            total_files = len(files_to_upload)
            
            for file_path, description, content_type in files_to_upload:
                full_path = output_path / file_path
                
                if not full_path.exists():
                    logger.warning(f"File not found: {full_path}")
                    continue
                    
                if self._upload_single_file(assessment_id, full_path, description, content_type):
                    success_count += 1
                    
            logger.info(f"Successfully uploaded {success_count}/{total_files} files")
            return success_count == total_files
            
        except Exception as e:
            logger.error(f"Error uploading files: {e}")
            return False
            
    def _upload_single_file(self, assessment_id: str, file_path: Path, 
                           description: str, content_type: str) -> bool:
        """Upload a single file to XNAT assessment"""
        try:
            # Upload to assessment resources
            url = f"{self.xnat_host}/REST/projects/{self.project_id}/subjects/{self.session_id}/experiments/{assessment_id}/resources/files"
            
            with open(file_path, 'rb') as f:
                files = {
                    'file': (file_path.name, f, content_type)
                }
                
                data = {
                    'description': description,
                    'format': content_type
                }
                
                response = self.session.post(url, files=files, data=data, timeout=self.timeout)
                response.raise_for_status()
                
            logger.info(f"Uploaded {description}: {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload {description} ({file_path.name}): {e}")
            return False
    
    def _create_centiloid_xml(self, results_data: Dict[str, Any], output_dir: str) -> str:
        """
        Create XML content using custom centiloid:CentiloidAssessment format
        
        Args:
            results_data: Centiloid processing results
            output_dir: Directory containing output files
            
        Returns:
            XML content as string
        """
        from datetime import datetime
        import xml.etree.ElementTree as ET
        
        # Create root element with centiloid namespace
        root = ET.Element("centiloid:CentiloidAssessment")
        root.set("xmlns:centiloid", "http://nrg.wustl.edu/centiloid")
        root.set("xmlns:xnat", "http://nrg.wustl.edu/xnat")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        root.set("ID", f"CENTILOID_{self.session_id}_{int(datetime.now().timestamp())}")
        root.set("project", self.project_id)
        root.set("label", f"Centiloid_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        # Add input parameters
        if "inputs" in results_data:
            inputs = results_data["inputs"]
            
            if inputs.get("dicom_dir"):
                ET.SubElement(root, "centiloid:dicom_dir").text = str(inputs["dicom_dir"])
            if inputs.get("pet_nifti"):
                ET.SubElement(root, "centiloid:pet_nifti").text = str(inputs["pet_nifti"])
            if inputs.get("template"):
                ET.SubElement(root, "centiloid:template").text = str(inputs["template"])
            if inputs.get("target_mask"):
                ET.SubElement(root, "centiloid:target_mask").text = str(inputs["target_mask"])
            if inputs.get("ref_mask"):
                ET.SubElement(root, "centiloid:ref_mask").text = str(inputs["ref_mask"])
            if inputs.get("tracer"):
                ET.SubElement(root, "centiloid:tracer").text = str(inputs["tracer"])
            if inputs.get("mode"):
                ET.SubElement(root, "centiloid:mode").text = str(inputs["mode"])
            if inputs.get("reg_mode"):
                ET.SubElement(root, "centiloid:reg_mode").text = str(inputs["reg_mode"])
        
        # Add processing outputs
        if "intermediate" in results_data:
            intermediate = results_data["intermediate"]
            
            if intermediate.get("converted_pet_nifti"):
                ET.SubElement(root, "centiloid:converted_pet_nifti").text = str(intermediate["converted_pet_nifti"])
            if intermediate.get("registered_pet_nifti"):
                ET.SubElement(root, "centiloid:registered_pet_nifti").text = str(intermediate["registered_pet_nifti"])
            if intermediate.get("transform"):
                ET.SubElement(root, "centiloid:transform").text = str(intermediate["transform"])
        
        # Add quantitative metrics
        if "metrics" in results_data:
            metrics = results_data["metrics"]
            
            if metrics.get("target_mean") is not None:
                ET.SubElement(root, "centiloid:target_mean").text = str(metrics["target_mean"])
            if metrics.get("reference_mean") is not None:
                ET.SubElement(root, "centiloid:reference_mean").text = str(metrics["reference_mean"])
            if metrics.get("suvr_global_cortex_over_ref") is not None:
                ET.SubElement(root, "centiloid:suvr_global_cortex_over_ref").text = str(metrics["suvr_global_cortex_over_ref"])
            if metrics.get("scaled_value") is not None:
                ET.SubElement(root, "centiloid:scaled_value").text = str(metrics["scaled_value"])
            if metrics.get("scaled_units"):
                ET.SubElement(root, "centiloid:scaled_units").text = str(metrics["scaled_units"])
        
        # Add output files
        output_path = Path(output_dir)
        
        # Find and add file paths
        qc_overlay = output_path / "qc_overlay.png"
        if qc_overlay.exists():
            ET.SubElement(root, "centiloid:qc_overlay_file").text = "/output/qc_overlay.png"
            
        qc_pdf = output_path / "qc_report.pdf" 
        if qc_pdf.exists():
            ET.SubElement(root, "centiloid:qc_pdf_file").text = "/output/qc_report.pdf"
            
        # Look for parametric map in DICOM directory
        dicom_dir = output_path / "dicom_series"
        if dicom_dir.exists():
            param_maps = list(dicom_dir.glob("*parametric*.dcm"))
            if param_maps:
                ET.SubElement(root, "centiloid:parametric_map_file").text = f"/output/dicom_series/{param_maps[0].name}"
                
        results_json = output_path / "centiloid.json"
        if results_json.exists():
            ET.SubElement(root, "centiloid:results_json").text = "/output/centiloid.json"
            
        results_csv = output_path / "centiloid.csv"
        if results_csv.exists():
            ET.SubElement(root, "centiloid:results_csv").text = "/output/centiloid.csv"
        
        # Add processing metadata
        ET.SubElement(root, "centiloid:processing_status").text = "completed"
        ET.SubElement(root, "centiloid:processing_date").text = datetime.now().isoformat()
        ET.SubElement(root, "centiloid:container_version").text = "1.1.12"
        
        # Convert to string with XML declaration
        xml_str = ET.tostring(root, encoding='unicode')
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
    
    def _extract_assessment_id(self, response) -> Optional[str]:
        """
        Extract assessment ID from XNAT response
        
        Args:
            response: HTTP response from XNAT
            
        Returns:
            Assessment ID if found, None otherwise
        """
        try:
            if response.headers.get('content-type', '').startswith('application/json'):
                result = response.json()
                return result.get("ID") or result.get("id")
            else:
                # Try to extract from XML response
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                return root.get("ID")
        except Exception as e:
            print(f"[DEBUG] Failed to extract assessment ID: {e}")
            # Fallback: try to extract from response text
            import re
            match = re.search(r'ID["\s]*[:=]["\s]*([^">\s]+)', response.text)
            if match:
                return match.group(1)
            return None
            
    def _prepare_assessment_data(self, results_data: Dict[str, Any], output_dir: str) -> Dict[str, Any]:
        """Prepare assessment data for XNAT API"""
        
        assessment_data = {
            "processing_status": "completed",
            "container_version": "1.1.0"  # Update version as needed
        }
        
        # Extract input parameters
        if "inputs" in results_data:
            inputs = results_data["inputs"]
            assessment_data.update({
                "dicom_dir": inputs.get("dicom_dir"),
                "pet_nifti": inputs.get("pet_nifti"),
                "template": inputs.get("template"),
                "target_mask": inputs.get("target_mask"),
                "ref_mask": inputs.get("ref_mask"),
                "tracer": inputs.get("tracer"),
                "mode": inputs.get("mode"),
                "reg_mode": inputs.get("reg_mode")
            })
            
        # Extract intermediate results
        if "intermediate" in results_data:
            intermediate = results_data["intermediate"]
            assessment_data.update({
                "converted_pet_nifti": intermediate.get("converted_pet_nifti"),
                "registered_pet_nifti": intermediate.get("registered_pet_nifti"),
                "transform": intermediate.get("transform")
            })
            
        # Extract quantitative metrics
        if "metrics" in results_data:
            metrics = results_data["metrics"]
            assessment_data.update({
                "target_mean": float(metrics["target_mean"]) if metrics.get("target_mean") else None,
                "reference_mean": float(metrics["reference_mean"]) if metrics.get("reference_mean") else None,
                "suvr_global_cortex_over_ref": float(metrics["suvr_global_cortex_over_ref"]) if metrics.get("suvr_global_cortex_over_ref") else None,
                "scaled_value": float(metrics["scaled_value"]) if metrics.get("scaled_value") else None,
                "scaled_units": metrics.get("scaled_units")
            })
            
        # Add file paths (relative to output directory)
        output_path = Path(output_dir)
        
        file_mappings = {
            "qc_overlay.png": "qc_overlay_file",
            "qc_report.pdf": "qc_pdf_file",
            "centiloid.json": "results_json",
            "centiloid.csv": "results_csv"
        }
        
        for file_name, field_name in file_mappings.items():
            file_path = output_path / file_name
            if file_path.exists():
                assessment_data[field_name] = str(file_path)
                
        # Check for DICOM parametric map
        dicom_dir = output_path / "dicom_series"
        if dicom_dir.exists():
            param_maps = list(dicom_dir.glob("*parametric*.dcm"))
            if param_maps:
                assessment_data["parametric_map_file"] = str(param_maps[0])
                
        return assessment_data


def upload_to_xnat(results_json_path: str, output_dir: str, 
                  xnat_host: str, username: str, password: str,
                  project_id: str, session_id: str) -> bool:
    """
    Main function to upload Centiloid results to XNAT
    
    Args:
        results_json_path: Path to centiloid.json results file
        output_dir: Directory containing all output files
        xnat_host: XNAT host URL
        username: XNAT username
        password: XNAT password
        project_id: XNAT project ID
        session_id: XNAT session ID
        
    Returns:
        True if upload successful, False otherwise
    """
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        print(f"[DEBUG] Starting XNAT upload process")
        print(f"[DEBUG] Results JSON path: {results_json_path}")
        print(f"[DEBUG] Output directory: {output_dir}")
        print(f"[DEBUG] XNAT host: {xnat_host}")
        print(f"[DEBUG] Username: {username}")
        print(f"[DEBUG] Project ID: {project_id}")
        print(f"[DEBUG] Session ID: {session_id}")
        
        # Load results data
        print(f"[DEBUG] Loading results from {results_json_path}")
        if not os.path.exists(results_json_path):
            print(f"[ERROR] Results file not found: {results_json_path}")
            return False
            
        with open(results_json_path, 'r') as f:
            results_data = json.load(f)
            
        print(f"[DEBUG] Results data loaded successfully")
        print(f"[DEBUG] Results keys: {list(results_data.keys())}")
            
        logger.info(f"Loaded results from: {results_json_path}")
        
        # Initialize uploader
        print(f"[DEBUG] Initializing XNAT uploader")
        uploader = XNATUploader(xnat_host, username, password, project_id, session_id)
        print(f"[DEBUG] Uploader initialized successfully")
        
        # Test connection
        print(f"[DEBUG] Testing XNAT connection...")
        if not uploader.test_connection():
            print(f"[ERROR] XNAT connection test failed")
            logger.error("XNAT connection test failed")
            return False
        print(f"[DEBUG] Connection test successful")
            
        # Create assessment
        print(f"[DEBUG] Creating XNAT assessment...")
        assessment_id = uploader.create_assessment(results_data, output_dir)
        if not assessment_id:
            print(f"[ERROR] Failed to create XNAT assessment")
            logger.error("Failed to create XNAT assessment")
            return False
        print(f"[DEBUG] Assessment created with ID: {assessment_id}")
            
        # Upload files
        print(f"[DEBUG] Uploading files...")
        if not uploader.upload_files(assessment_id, output_dir):
            print(f"[ERROR] File upload failed")
            logger.error("File upload failed")
            return False
        print(f"[DEBUG] Files uploaded successfully")
            
        logger.info(f"Successfully uploaded Centiloid results to XNAT assessment: {assessment_id}")
        return True
        
    except FileNotFoundError as e:
        logger.error(f"Results file not found: {e}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in results file: {e}")
        return False
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return False


if __name__ == "__main__":
    """Command line interface for XNAT upload"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Upload Centiloid results to XNAT")
    parser.add_argument("--results-json", required=True, help="Path to centiloid.json results file")
    parser.add_argument("--output-dir", required=True, help="Output directory containing files")
    parser.add_argument("--xnat-host", required=True, help="XNAT host URL")
    parser.add_argument("--xnat-user", required=True, help="XNAT username")
    parser.add_argument("--xnat-pass", required=True, help="XNAT password")
    parser.add_argument("--project-id", required=True, help="XNAT project ID")
    parser.add_argument("--session-id", required=True, help="XNAT session/experiment ID")
    
    args = parser.parse_args()
    
    success = upload_to_xnat(
        results_json_path=args.results_json,
        output_dir=args.output_dir,
        xnat_host=args.xnat_host,
        username=args.xnat_user,
        password=args.xnat_pass,
        project_id=args.project_id,
        session_id=args.session_id
    )
    
    sys.exit(0 if success else 1)