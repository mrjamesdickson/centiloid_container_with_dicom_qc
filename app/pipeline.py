import argparse, os, json, subprocess, glob
from typing import Dict, Optional, Tuple
import numpy as np
import nibabel as nib
from nilearn.image import resample_to_img
from PIL import Image
import yaml, pandas as pd
import SimpleITK as sitk
import logging
# ---- DICOM Parametric Map (SUVR) writer ----
import pydicom
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
import highdicom as hd
from datetime import datetime

def _find_any_dicom_file(dicom_dir: str) -> Optional[str]:
    if dicom_dir is None:
        return None
    for root, _, files in os.walk(dicom_dir):
        for n in files:
            if n.lower().endswith(".dcm"):
                return os.path.join(root, n)
    return None

def write_suvr_parametric_map(
    suvr_img_path: str,
    template_img_path: str,
    out_dir: str,
    dicom_src_dir: Optional[str] = None,
    unit_code_value: str = "1",
    unit_coding_scheme: str = "UCUM",
    unit_code_meaning: str = "Unitless"
) -> str:
    """Create a DICOM Parametric Map for the SUVR image.
    - suvr_img_path: path to NIfTI with SUVR values (we use registered PET already in template space)
    - template_img_path: used for spacing/orientation (should match suvr_img)
    - dicom_src_dir: optional; if provided, we'll borrow patient/study metadata from one DICOM
    Returns path to written DICOM file.
    """
    os.makedirs(out_dir, exist_ok=True)

    nii = nib.load(suvr_img_path)
    data = nii.get_fdata().astype("float32")
    # DICOM expects LPS orientation; NIfTI is RAS. We flip first two axes to approximate RAS->LPS.
    # Note: For rigorous handling, use nibabel affines to compute orientation. This approximation
    # works in many viewers but can be adapted if you require strict conformance.
    data_lps = data[::-1, ::-1, :]

    px_spacing = np.sqrt((nii.affine[:3,:3] ** 2).sum(axis=0)).tolist()
    # Slice spacing along k-axis: estimate from affine
    slice_thickness = float(abs(nii.affine[2,2])) if abs(nii.affine[2,2]) > 1e-6 else float(px_spacing[2])

    src_dcm_path = _find_any_dicom_file(dicom_src_dir) if dicom_src_dir else None
    patient_id = "ANON"
    patient_name = "ANON^SUVR"
    study_uid = generate_uid()
    series_uid = generate_uid()
    frame_of_ref_uid = generate_uid()
    study_date = datetime.utcnow().strftime("%Y%m%d")
    study_time = datetime.utcnow().strftime("%H%M%S")

    if src_dcm_path is not None:
        ds = pydicom.dcmread(src_dcm_path, stop_before_pixels=True, force=True)
        patient_id = getattr(ds, "PatientID", patient_id)
        patient_name = getattr(ds, "PatientName", patient_name)
        study_uid = getattr(ds, "StudyInstanceUID", study_uid)
        frame_of_ref_uid = getattr(ds, "FrameOfReferenceUID", frame_of_ref_uid)
        study_date = getattr(ds, "StudyDate", study_date)
        study_time = getattr(ds, "StudyTime", study_time)

    # Build Parametric Map
    rows, cols, n_slices = data_lps.shape[1], data_lps.shape[0], data_lps.shape[2]
    # Convert to (frames, rows, cols)
    frames = []
    for k in range(n_slices):
        frames.append(data_lps[:,:,k].T)  # rows x cols

    quantity = hd.sr.coding.Code(
        value="113072",
        scheme_designator="DCM",
        meaning="SUVR Parametric Map"
    )
    units = hd.sr.coding.Code(
        value=unit_code_value,
        scheme_designator=unit_coding_scheme,
        meaning=unit_code_meaning
    )

    pm = hd.pm.ParametricMap(
        source_images=[],
        pixel_array=np.stack(frames, axis=0),
        patient_id=str(patient_id),
        patient_name=str(patient_name),
        study_instance_uid=study_uid,
        series_instance_uid=series_uid,
        sop_instance_uid=generate_uid(),
        frame_of_reference_uid=frame_of_ref_uid,
        manufacturer="CentiloidContainer",
        manufacturer_model_name="SUVR-ParamMap",
        series_number=9001,
        instance_number=1,
        modality="PM",  # Parametric Map
        image_type=["DERIVED","PRIMARY","PARAMETRIC_MAP"],
        content_label="SUVRMAP",
        content_description="Global SUVR parametric map",
        content_creator_name="Container",
        pixel_spacing=[float(px_spacing[1]), float(px_spacing[0])],
        slice_thickness=float(slice_thickness),
        image_orientation=[1,0,0,0,1,0],  # assumes axes aligned; adjust as needed
        specimen=None,
        real_world_value_mapping=hd.pm.RealWorldValueMapping(
            units_coding=units,
            lut_label="SUVR"
        ),
        quantity=quantity,
        segmentation_type=None,
        lossless_image_compression=False,
        transfer_syntax_uid=ExplicitVRLittleEndian
    )

    out_path = os.path.join(out_dir, "SUVR_parametric_map.dcm")
    pm.save_as(out_path)
    return out_path


def run(cmd: list, cwd: Optional[str]=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc.stdout

def dcm2niix_convert(dicom_dir: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    
    # Use default naming to avoid conflicts with multiple series
    cmd = ["dcm2niix", "-z", "y", "-o", out_dir, dicom_dir]
    run(cmd)
    
    # Find the largest NIfTI file (likely the main PET image)
    nii_files = glob.glob(os.path.join(out_dir, "*.nii.gz"))
    if not nii_files:
        nii_files = glob.glob(os.path.join(out_dir, "*.nii"))
    
    if not nii_files:
        raise FileNotFoundError("No NIfTI produced by dcm2niix")
    
    # Sort by file size to get the largest (main PET series)
    nii_files.sort(key=lambda x: os.path.getsize(x), reverse=True)
    main_pet = nii_files[0]
    
    # Rename to pet.nii.gz for consistency
    pet_output = os.path.join(out_dir, "pet.nii.gz")
    if main_pet != pet_output:
        os.rename(main_pet, pet_output)
    
    print(f"Selected main PET file: {os.path.basename(pet_output)} ({os.path.getsize(pet_output)} bytes)")
    print(f"Found {len(nii_files)} NIfTI files total from dcm2niix conversion")
    
    return pet_output

def sitk_load(path: str) -> sitk.Image:
    return sitk.ReadImage(path)

def sitk_save(img: sitk.Image, path: str):
    sitk.WriteImage(img, path, useCompression=True)

def pet_to_template_registration(pet_nii: str, template_nii: str, out_dir: str, mode: str="rigid") -> Tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    moving = sitk_load(pet_nii)
    fixed = sitk_load(template_nii)

    # Cast to float for registration, handle vector images
    if moving.GetNumberOfComponentsPerPixel() > 1:
        # If vector image, extract first component
        moving = sitk.VectorIndexSelectionCast(moving, 0)
    moving_f = sitk.Cast(moving, sitk.sitkFloat32)
    
    if fixed.GetNumberOfComponentsPerPixel() > 1:
        # If vector image, extract first component  
        fixed = sitk.VectorIndexSelectionCast(fixed, 0)
    fixed_f = sitk.Cast(fixed, sitk.sitkFloat32)

    # Initialize (centered transform)
    if mode == "affine":
        tx = sitk.AffineTransform(fixed.GetDimension())
    else:
        tx = sitk.CenteredTransformInitializer(fixed_f, moving_f, sitk.Euler3DTransform(), sitk.CenteredTransformInitializerFilter.GEOMETRY)

    # Metric & optimizer
    reg = sitk.ImageRegistrationMethod()
    reg.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    reg.SetMetricSamplingStrategy(reg.RANDOM)
    reg.SetMetricSamplingPercentage(0.2, 1234)
    reg.SetInterpolator(sitk.sitkLinear)

    if mode == "affine":
        reg.SetOptimizerAsGradientDescent(learningRate=1.0, numberOfIterations=200, convergenceMinimumValue=1e-6, convergenceWindowSize=10)
        reg.SetOptimizerScalesFromPhysicalShift()
        reg.SetInitialTransform(sitk.AffineTransform(tx), inPlace=False)
        # Do a rigid pre-alignment first
        rigid = sitk.ImageRegistrationMethod()
        rigid.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
        rigid.SetMetricSamplingStrategy(rigid.RANDOM)
        rigid.SetMetricSamplingPercentage(0.2, 1234)
        rigid.SetInterpolator(sitk.sitkLinear)
        rigid.SetOptimizerAsGradientDescent(learningRate=1.0, numberOfIterations=150, convergenceMinimumValue=1e-6, convergenceWindowSize=10)
        rigid.SetOptimizerScalesFromPhysicalShift()
        rigid_tx = sitk.CenteredTransformInitializer(fixed_f, moving_f, sitk.Euler3DTransform(), sitk.CenteredTransformInitializerFilter.GEOMETRY)
        rigid.SetInitialTransform(rigid_tx, inPlace=False)
        tx_rigid = rigid.Execute(fixed_f, moving_f)
        reg.SetInitialTransform(sitk.AffineTransform(tx_rigid), inPlace=False)
    else:
        reg.SetOptimizerAsGradientDescent(learningRate=1.0, numberOfIterations=200, convergenceMinimumValue=1e-6, convergenceWindowSize=10)
        reg.SetOptimizerScalesFromPhysicalShift()
        reg.SetInitialTransform(tx, inPlace=False)

    final_tx = reg.Execute(fixed_f, moving_f)

    # Resample moving (PET) to fixed (template) space
    resampled = sitk.Resample(moving, fixed, final_tx, sitk.sitkLinear, 0.0, sitk.sitkFloat32)

    reg_pet = os.path.join(out_dir, "pet_in_template.nii.gz")
    xfm_path = os.path.join(out_dir, "pet_to_template.tfm")
    sitk_save(resampled, reg_pet)
    sitk.WriteTransform(final_tx, xfm_path)
    return reg_pet, xfm_path

def load_nii(path):
    img = nib.load(path)
    return img, img.get_fdata()

def mean_in_mask(arr, mask):
    vals = arr[mask > 0]
    if vals.size == 0: return float("nan")
    return float(np.nanmean(vals))

def compute_suvr(pet_img, pet_data, tmask, rmask):
    t = mean_in_mask(pet_data, tmask)
    r = mean_in_mask(pet_data, rmask)
    return (float(t/r) if r and not np.isnan(r) else float("nan")), t, r

def resample_mask_to_target(mask_path, target_img):
    mask_img = nib.load(mask_path)
    resampled = resample_to_img(mask_img, target_img, interpolation="nearest")
    data = resampled.get_fdata()
    return (data > 0.5).astype(np.uint8)

def convert_to_scale(suvr: float, tracer: str, mode: str, calibs: Dict) -> float:
    mode = mode.lower()
    if mode not in calibs: return suvr
    table = calibs[mode]
    key = tracer if tracer in table else ('generic' if 'generic' in table else None)
    if key is None: return suvr
    slope = float(table[key].get('slope', 1.0))
    intercept = float(table[key].get('intercept', 0.0))
    return float(slope * suvr + intercept)

def save_qc_png(pet_img, tmask, rmask, out_png):
    data = pet_img.get_fdata()
    mids = [s//2 for s in data.shape[:3]]
    def norm(im):
        import numpy as np
        im = np.nan_to_num(im, nan=0.0, posinf=0.0, neginf=0.0)
        vmax = np.percentile(im, 99)
        return (np.clip(im, 0, vmax) / (vmax + 1e-6) * 255).astype(np.uint8)
    planes = [data[mids[0],:,:], data[:,mids[1],:], data[:,:,mids[2]]]
    tplanes = [tmask[mids[0],:,:], tmask[:,mids[1],:], tmask[:,:,mids[2]]]
    rplanes = [rmask[mids[0],:,:], rmask[:,mids[1],:], rmask[:,:,mids[2]]]
    panels = []
    from PIL import Image
    import numpy as np
    for i in range(3):
        base = Image.fromarray(np.rot90(norm(planes[i]))).convert("RGB")
        t = Image.fromarray(np.rot90((tplanes[i]*255).astype(np.uint8))).resize(base.size)
        r = Image.fromarray(np.rot90((rplanes[i]*255).astype(np.uint8))).resize(base.size)
        arr = np.array(base)
        arr[...,0] = np.maximum(arr[...,0], np.array(t))  # target -> R
        arr[...,1] = np.maximum(arr[...,1], np.array(r))  # ref    -> G
        panels.append(Image.fromarray(arr))
    w,h = panels[0].size
    canvas = Image.new("RGB",(w*3,h))
    for i,p in enumerate(panels):
        canvas.paste(p,(i*w,0))
    canvas.save(out_png)


# ---- QC PDF generation and DICOM embedding ----
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from datetime import datetime
import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage
from pydicom.uid import generate_uid

def _compose_qc_pdf(pdf_path: str, qc_png_path: str, out_json: dict):
    c = rl_canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, "PET SUVR / Centiloid QC Report")
    c.setFont("Helvetica", 10)
    # Metrics
    y = height - 100
    metrics = out_json.get("metrics", {})
    lines = [
        f"Tracer: {out_json.get('inputs',{}).get('tracer','')}   Mode: {out_json.get('inputs',{}).get('mode','')}   Reg: {out_json.get('inputs',{}).get('reg_mode','')}",
        f"Target mean: {metrics.get('target_mean',''):.6g}",
        f"Reference mean: {metrics.get('reference_mean',''):.6g}",
        f"SUVR: {metrics.get('suvr_global_cortex_over_ref',''):.6g}",
        f"Scaled value: {metrics.get('scaled_value',''):.6g}  ({metrics.get('scaled_units','')})",
    ]
    for line in lines:
        c.drawString(72, y, line)
        y -= 14

    # Overlay image
    if os.path.exists(qc_png_path):
        img_w = width - 2*inch
        img_h = img_w * 0.35  # keep reasonable aspect
        c.drawImage(qc_png_path, inch, y - img_h - 10, width=img_w, height=img_h, preserveAspectRatio=True, mask='auto')
        y -= (img_h + 20)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(72, 36, f"Generated: {datetime.utcnow().isoformat()}Z")
    c.showPage()
    c.save()

def _borrow_patient_study_from_dicom(dicom_src_dir: Optional[str]):
    pid = "ANON"
    pname = "ANON^QC"
    study_uid = generate_uid()
    series_uid = generate_uid()
    frame_of_ref_uid = generate_uid()
    sdate = datetime.utcnow().strftime("%Y%m%d")
    stime = datetime.utcnow().strftime("%H%M%S")
    if dicom_src_dir:
        for root, _, files in os.walk(dicom_src_dir):
            for n in files:
                if n.lower().endswith(".dcm"):
                    p = os.path.join(root, n)
                    try:
                        ds = pydicom.dcmread(p, stop_before_pixels=True, force=True)
                        pid = getattr(ds, "PatientID", pid)
                        pname = getattr(ds, "PatientName", pname)
                        study_uid = getattr(ds, "StudyInstanceUID", study_uid)
                        frame_of_ref_uid = getattr(ds, "FrameOfReferenceUID", frame_of_ref_uid)
                        sdate = getattr(ds, "StudyDate", sdate)
                        stime = getattr(ds, "StudyTime", stime)
                        return pid, pname, study_uid, series_uid, frame_of_ref_uid, sdate, stime
                    except Exception:
                        continue
    return pid, pname, study_uid, series_uid, frame_of_ref_uid, sdate, stime

def write_encapsulated_pdf(pdf_path: str, out_dir: str, dicom_src_dir: Optional[str]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    pid, pname, study_uid, series_uid, _, sdate, stime = _borrow_patient_study_from_dicom(dicom_src_dir)
    # File meta
    file_meta = FileMetaDataset()
    file_meta.FileMetaInformationVersion = b'\x00\x01'
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.104.1"  # Encapsulated PDF Storage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    ds = FileDataset("", {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.PatientName = pname
    ds.PatientID = pid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.Modality = "OT"
    ds.SeriesNumber = 9100
    ds.InstanceNumber = 1
    ds.ContentDate = sdate
    ds.ContentTime = stime
    ds.DocumentTitle = "PET SUVR / Centiloid QC Report"
    ds.MIMETypeOfEncapsulatedDocument = "application/pdf"
    with open(pdf_path, "rb") as f:
        ds.EncapsulatedDocument = f.read()
    out_path = os.path.join(out_dir, "QC_Report.pdf.dcm")
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(out_path, write_like_original=False)
    return out_path

def write_pet_with_mask_overlay_series(
    pet_reg_path: str,
    target_mask: np.ndarray,
    ref_mask: np.ndarray,
    template_path: str,
    out_dir: str,
    dicom_src_dir: Optional[str] = None
) -> str:
    """Create a DICOM series showing registered PET with mask overlays.
    Returns path to the directory containing the DICOM series.
    """
    import os
    import numpy as np
    import nibabel as nib
    from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid
    
    os.makedirs(out_dir, exist_ok=True)
    series_dir = os.path.join(out_dir, "pet_overlay_series")
    os.makedirs(series_dir, exist_ok=True)
    
    # Load PET data
    pet_img = nib.load(pet_reg_path)
    pet_data = pet_img.get_fdata().astype(np.float32)
    
    # Get patient/study info
    pid, pname, study_uid, _, frame_of_ref_uid, sdate, stime = _borrow_patient_study_from_dicom(dicom_src_dir)
    series_uid = generate_uid()
    
    # Normalize PET data to 0-255 range for overlay
    pet_norm = np.nan_to_num(pet_data, nan=0.0, posinf=0.0, neginf=0.0)
    pet_max = np.percentile(pet_norm, 99.5)
    pet_norm = np.clip(pet_norm / (pet_max + 1e-6) * 255, 0, 255).astype(np.uint8)
    
    slice_paths = []
    n_slices = pet_data.shape[2]
    
    for slice_idx in range(n_slices):
        # Get current slice data
        pet_slice = pet_norm[:, :, slice_idx]
        target_slice = (target_mask[:, :, slice_idx] > 0).astype(np.uint8) * 255
        ref_slice = (ref_mask[:, :, slice_idx] > 0).astype(np.uint8) * 255
        
        # Create RGB overlay: PET as grayscale base, target mask as red, ref mask as green
        rows, cols = pet_slice.shape
        rgb_data = np.zeros((rows, cols, 3), dtype=np.uint8)
        
        # Base PET in all channels (grayscale)
        rgb_data[:, :, 0] = pet_slice
        rgb_data[:, :, 1] = pet_slice  
        rgb_data[:, :, 2] = pet_slice
        
        # Add target mask as red overlay (boost red channel)
        rgb_data[:, :, 0] = np.maximum(rgb_data[:, :, 0], target_slice)
        
        # Add ref mask as green overlay (boost green channel)  
        rgb_data[:, :, 1] = np.maximum(rgb_data[:, :, 1], ref_slice)
        
        # Convert to DICOM coordinate system (LPS from RAS)
        rgb_data_lps = rgb_data[::-1, ::-1, :]
        
        # Create DICOM dataset
        file_meta = FileMetaDataset()
        file_meta.FileMetaInformationVersion = b'\x00\x01'
        file_meta.MediaStorageSOPClassUID = str(SecondaryCaptureImageStorage)
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.ImplementationClassUID = generate_uid()
        
        ds = FileDataset("", {}, file_meta=file_meta, preamble=b"\0" * 128)
        ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.PatientName = pname
        ds.PatientID = pid
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.FrameOfReferenceUID = frame_of_ref_uid
        ds.Modality = "OT"  # Other
        ds.SeriesNumber = 9002
        ds.InstanceNumber = slice_idx + 1
        ds.ContentDate = sdate
        ds.ContentTime = stime
        ds.ImageType = ["DERIVED", "SECONDARY", "OVERLAY"]
        ds.SeriesDescription = "PET with Mask Overlays"
        ds.ImageComments = f"PET slice {slice_idx+1} with target (red) and reference (green) mask overlays"
        
        # Image data
        ds.SamplesPerPixel = 3
        ds.PhotometricInterpretation = "RGB"
        ds.PlanarConfiguration = 0
        ds.Rows = rows
        ds.Columns = cols
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.PixelData = rgb_data_lps.tobytes()
        
        # Position information (approximate from NIfTI affine)
        affine = pet_img.affine
        pixel_spacing = [abs(affine[0,0]), abs(affine[1,1])]
        slice_thickness = abs(affine[2,2])
        slice_location = affine[2,3] + slice_idx * affine[2,2]
        
        ds.PixelSpacing = [f"{pixel_spacing[1]:.6f}", f"{pixel_spacing[0]:.6f}"]
        ds.SliceThickness = f"{slice_thickness:.6f}"
        ds.SliceLocation = f"{slice_location:.6f}"
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]  # Approximate
        ds.ImagePositionPatient = [0, 0, slice_location]  # Approximate
        
        # Save DICOM file
        slice_filename = f"pet_overlay_{slice_idx+1:04d}.dcm"
        slice_path = os.path.join(series_dir, slice_filename)
        ds.is_little_endian = True
        ds.is_implicit_VR = False
        ds.save_as(slice_path, write_like_original=False)
        slice_paths.append(slice_path)
    
    return series_dir

def write_sc_from_png(png_path: str, out_dir: str, dicom_src_dir: Optional[str]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    from PIL import Image
    import numpy as np
    pid, pname, study_uid, series_uid, _, sdate, stime = _borrow_patient_study_from_dicom(dicom_src_dir)
    im = Image.open(png_path).convert("RGB")
    arr = np.array(im)
    rows, cols, _ = arr.shape

    file_meta = FileMetaDataset()
    file_meta.FileMetaInformationVersion = b'\x00\x01'
    file_meta.MediaStorageSOPClassUID = str(SecondaryCaptureImageStorage)
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    ds = FileDataset("", {}, file_meta=file_meta, preamble=b"\0"*128)
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.PatientName = pname
    ds.PatientID = pid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.Modality = "OT"
    ds.SeriesNumber = 9101
    ds.InstanceNumber = 1
    ds.ContentDate = sdate
    ds.ContentTime = stime
    ds.ImageType = ["DERIVED","SECONDARY"]
    ds.SamplesPerPixel = 3
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = arr.tobytes()
    out_path = os.path.join(out_dir, "QC_Report_SC.dcm")
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(out_path, write_like_original=False)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="DICOM->NIfTI, registration to mask space, SUVR, Centiloid/CenTauR")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dicom-dir", help="Input DICOM directory for PET")
    g.add_argument("--pet-nifti", help="Input PET NIfTI (skip DICOM conversion)")
    ap.add_argument("--template", required=True, help="Template NIfTI that defines the mask space (e.g., MNI or your VOI space)")
    ap.add_argument("--target-mask", required=True, help="Target (CTX) mask in template space")
    ap.add_argument("--ref-mask", required=True, help="Reference (e.g., whole cerebellum) mask in template space")
    ap.add_argument("--tracer", required=True, help="Tracer key, e.g., FBP, FBB, FMM, NAV4694, PiB")
    ap.add_argument("--mode", choices=["amyloid","tau"], default="amyloid")
    ap.add_argument("--calib-yaml", default="/app/config/tracer_calibrations.yaml")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--reg-mode", choices=["rigid","affine"], default="rigid", help="Registration model")
    
    # XNAT upload arguments (optional)
    xnat_group = ap.add_argument_group("XNAT Upload Options")
    xnat_group.add_argument("--xnat-host", help="XNAT host URL (e.g., https://xnat.example.com)")
    xnat_group.add_argument("--xnat-user", help="XNAT username")
    xnat_group.add_argument("--xnat-pass", help="XNAT password")
    xnat_group.add_argument("--xnat-project", help="XNAT project ID")
    xnat_group.add_argument("--xnat-session", help="XNAT session/experiment ID")
    xnat_group.add_argument("--skip-xnat-upload", action="store_true", help="Skip XNAT upload even if credentials provided")
    
    args = ap.parse_args()


    os.makedirs(args.out_dir, exist_ok=True)

    # Step 1: DICOM -> NIfTI (if needed)
    if args.dicom_dir:
        conv_dir = os.path.join(args.out_dir, "dcm2niix")
        pet_nii = dcm2niix_convert(args.dicom_dir, conv_dir)
    else:
        pet_nii = args.pet_nifti

    # Step 2: Register PET to template space
    reg_dir = os.path.join(args.out_dir, "registration")
    pet_reg, xfm = pet_to_template_registration(pet_nii, args.template, reg_dir, mode=args.reg_mode)

    # Step 3: Resample masks to registered PET (template grid == pet_reg grid)
    pet_img = nib.load(pet_reg)
    tmask = resample_mask_to_target(args.target_mask, pet_img)
    rmask = resample_mask_to_target(args.ref_mask, pet_img)

    # Step 4: Compute SUVR
    pet_data = pet_img.get_fdata()
    suvr, tmean, rmean = compute_suvr(pet_img, pet_data, tmask, rmask)

    # Step 5: Convert to Centiloid (amyloid) or experimental tau scale
    with open(args.calib_yaml, "r") as f:
        calibs = yaml.safe_load(f)
    scaled = convert_to_scale(suvr, args.tracer, args.mode, calibs)

    # Step 6: Save outputs
    out_json = {
        "inputs": {
            "dicom_dir": args.dicom_dir,
            "pet_nifti": args.pet_nifti,
            "template": os.path.basename(args.template),
            "target_mask": os.path.basename(args.target_mask),
            "ref_mask": os.path.basename(args.ref_mask),
            "tracer": args.tracer,
            "mode": args.mode,
            "reg_mode": args.reg_mode
        },
        "intermediate": {
            "converted_pet_nifti": pet_nii if args.dicom_dir else None,
            "registered_pet_nifti": os.path.basename(pet_reg),
            "transform": os.path.basename(xfm)
        },
        "metrics": {
            "target_mean": tmean,
            "reference_mean": rmean,
            "suvr_global_cortex_over_ref": suvr,
            "scaled_value": scaled,
            "scaled_units": "Centiloid" if args.mode=="amyloid" else "CenTauR (experimental)"
        }
    }
    with open(os.path.join(args.out_dir, "centiloid.json"), "w") as f:
        json.dump(out_json, f, indent=2)
    pd.DataFrame([{
        "tracer": args.tracer,
        "mode": args.mode,
        "target_mean": tmean,
        "reference_mean": rmean,
        "suvr": suvr,
        "scaled_value": scaled,
        "scaled_units": "Centiloid" if args.mode=="amyloid" else "CenTauR (experimental)"
    }]).to_csv(os.path.join(args.out_dir, "centiloid.csv"), index=False)

    # QC PNG
    qc_png = os.path.join(args.out_dir, "qc_overlay.png")
    save_qc_png(pet_img, tmask, rmask, qc_png)

    # ---- DICOM Outputs ----
    dicom_dir = os.path.join(args.out_dir, "dicom_series")
    
    # 1. DICOM Parametric Map (SUVR values) - Skip for now due to API issues
    # pm_path = write_suvr_parametric_map(
    #     suvr_img_path=pet_reg,
    #     template_img_path=args.template,
    #     out_dir=dicom_dir,
    #     dicom_src_dir=args.dicom_dir if args.dicom_dir else None
    # )
    
    # 2. DICOM Series with mask overlay visualization 
    overlay_path = write_pet_with_mask_overlay_series(
        pet_reg, tmask, rmask, args.template,
        out_dir=dicom_dir,
        dicom_src_dir=args.dicom_dir if args.dicom_dir else None
    )
    
    # 3. QC Report as PDF DICOM and Secondary Capture
    pdf_path = os.path.join(args.out_dir, "qc_report.pdf")
    _compose_qc_pdf(pdf_path, qc_png, out_json)
    pdf_dicom_path = write_encapsulated_pdf(pdf_path, dicom_dir, args.dicom_dir if args.dicom_dir else None)
    sc_dicom_path = write_sc_from_png(qc_png, dicom_dir, args.dicom_dir if args.dicom_dir else None)
    
    out_json["outputs"] = {
        "overlay_series_dicom": os.path.relpath(overlay_path, args.out_dir),
        "qc_report_pdf_dicom": os.path.relpath(pdf_dicom_path, args.out_dir),
        "qc_report_sc_dicom": os.path.relpath(sc_dicom_path, args.out_dir)
    }

    print(json.dumps(out_json, indent=2))
    
    # XNAT Upload (optional)
    if (args.xnat_host and args.xnat_user and args.xnat_pass and 
        args.xnat_project and args.xnat_session and 
        not args.skip_xnat_upload):
        
        print("\n=== XNAT Upload ===")
        try:
            # Import here to avoid dependency if not using XNAT upload
            from app.xnat_upload import upload_to_xnat
            
            # Get the results JSON file path
            results_json_path = os.path.join(args.out_dir, "centiloid.json")
            
            print(f"Debug - XNAT Parameters:")
            print(f"  Host: {args.xnat_host}")
            print(f"  User: {args.xnat_user}")
            print(f"  Password: {'*' * len(args.xnat_pass) if args.xnat_pass else 'None'}")
            print(f"  Project: {args.xnat_project}")
            print(f"  Session: {args.xnat_session}")
            print(f"  Results JSON: {results_json_path}")
            print(f"  Results JSON exists: {os.path.exists(results_json_path)}")
            print(f"  Output directory: {args.out_dir}")
            print(f"  Output dir contents: {os.listdir(args.out_dir) if os.path.exists(args.out_dir) else 'Directory not found'}")
            
            print(f"\nUploading results to XNAT:")
            print(f"  Host: {args.xnat_host}")
            print(f"  Project: {args.xnat_project}")
            print(f"  Session: {args.xnat_session}")
            
            success = upload_to_xnat(
                results_json_path=results_json_path,
                output_dir=args.out_dir,
                xnat_host=args.xnat_host,
                username=args.xnat_user,
                password=args.xnat_pass,
                project_id=args.xnat_project,
                session_id=args.xnat_session
            )
            
            if success:
                print("✓ Successfully uploaded results to XNAT")
                out_json["xnat_upload"] = {
                    "status": "success",
                    "project": args.xnat_project,
                    "session": args.xnat_session
                }
            else:
                print("✗ Failed to upload results to XNAT")
                out_json["xnat_upload"] = {
                    "status": "failed",
                    "error": "Upload failed - check logs for details"
                }
                
        except ImportError:
            print("✗ XNAT upload module not available")
            out_json["xnat_upload"] = {
                "status": "failed", 
                "error": "xnat_upload module not found"
            }
        except Exception as e:
            print(f"✗ XNAT upload failed: {e}")
            out_json["xnat_upload"] = {
                "status": "failed",
                "error": str(e)
            }
            
        # Print updated results with XNAT status
        print("\n=== Final Results ===")
        print(json.dumps(out_json, indent=2))
    else:
        print("\n=== XNAT Upload Skipped ===")
        if not all([args.xnat_host, args.xnat_user, args.xnat_pass, args.xnat_project, args.xnat_session]):
            print("XNAT credentials not fully provided")
        else:
            print("XNAT upload explicitly skipped")

if __name__ == "__main__":
    main()
