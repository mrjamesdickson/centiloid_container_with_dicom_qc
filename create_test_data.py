#!/usr/bin/env python3
import numpy as np
import nibabel as nib
import os
from scipy.ndimage import gaussian_filter
from PIL import Image
import argparse

def create_synthetic_brain_data(out_dir="test_data"):
    os.makedirs(out_dir, exist_ok=True)
    
    # Create a 3D brain-like template (91x109x91, MNI-like dimensions)
    shape = (91, 109, 91)
    
    # Template: brain-shaped volume with realistic intensities
    template = np.zeros(shape)
    center = np.array([45, 54, 45])
    
    # Create brain-like shape (ellipsoid)
    x, y, z = np.ogrid[:shape[0], :shape[1], :shape[2]]
    brain_mask = ((x - center[0])/35)**2 + ((y - center[1])/45)**2 + ((z - center[2])/35)**2 < 1
    
    template[brain_mask] = 100 + 50 * np.random.randn(*template[brain_mask].shape)
    template = gaussian_filter(template, sigma=2)
    template = np.clip(template, 0, 255)
    
    # Create affine matrix (2mm isotropic, MNI-like)
    affine = np.array([
        [-2.0,  0.0,  0.0,  90.0],
        [ 0.0,  2.0,  0.0, -126.0],
        [ 0.0,  0.0,  2.0,  -72.0],
        [ 0.0,  0.0,  0.0,   1.0]
    ])
    
    # Save template
    template_img = nib.Nifti1Image(template, affine)
    nib.save(template_img, os.path.join(out_dir, "template_space.nii.gz"))
    
    # Create cortical target mask
    cortical_mask = np.zeros(shape)
    # Outer cortical shell
    outer_brain = ((x - center[0])/32)**2 + ((y - center[1])/42)**2 + ((z - center[2])/32)**2 < 1
    inner_brain = ((x - center[0])/28)**2 + ((y - center[1])/38)**2 + ((z - center[2])/28)**2 < 1
    cortical_mask[outer_brain & ~inner_brain] = 1
    # Remove bottom part (cerebellum area)
    cortical_mask[:, :, :25] = 0
    
    cortical_img = nib.Nifti1Image(cortical_mask.astype(np.uint8), affine)
    nib.save(cortical_img, os.path.join(out_dir, "centiloid_ctx_mask.nii.gz"))
    
    # Create cerebellar reference mask
    cereb_mask = np.zeros(shape)
    # Cerebellum in posterior-inferior region
    cereb_center = np.array([45, 25, 30])
    cereb_brain = ((x - cereb_center[0])/15)**2 + ((y - cereb_center[1])/15)**2 + ((z - cereb_center[2])/12)**2 < 1
    cereb_mask[cereb_brain] = 1
    
    cereb_img = nib.Nifti1Image(cereb_mask.astype(np.uint8), affine)
    nib.save(cereb_img, os.path.join(out_dir, "whole_cerebellum_mask.nii.gz"))
    
    # Create synthetic amyloid PET data
    pet_data = np.zeros(shape)
    pet_data[brain_mask] = 1000 + 200 * np.random.randn(*pet_data[brain_mask].shape)
    
    # Add amyloid signal in cortical regions (higher uptake)
    pet_data[cortical_mask > 0] *= 1.8  # Elevated cortical signal
    
    # Lower signal in cerebellum (reference region)
    pet_data[cereb_mask > 0] *= 0.7
    
    # Add realistic noise and smoothing
    pet_data = gaussian_filter(pet_data, sigma=1.5)
    pet_data = np.clip(pet_data, 0, None)
    
    pet_img = nib.Nifti1Image(pet_data, affine)
    nib.save(pet_img, os.path.join(out_dir, "pet.nii.gz"))
    
    print(f"Created synthetic test data in {out_dir}/")
    print(f"- Template: {os.path.join(out_dir, 'template_space.nii.gz')}")
    print(f"- Cortical mask: {os.path.join(out_dir, 'centiloid_ctx_mask.nii.gz')}")
    print(f"- Cerebellum mask: {os.path.join(out_dir, 'whole_cerebellum_mask.nii.gz')}")
    print(f"- PET data: {os.path.join(out_dir, 'pet.nii.gz')}")
    
    # Calculate expected SUVR for validation
    target_mean = np.mean(pet_data[cortical_mask > 0])
    ref_mean = np.mean(pet_data[cereb_mask > 0])
    expected_suvr = target_mean / ref_mean
    print(f"\nExpected SUVR: {expected_suvr:.3f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create synthetic test data for Centiloid container")
    parser.add_argument("--out-dir", default="test_data", help="Output directory")
    args = parser.parse_args()
    
    create_synthetic_brain_data(args.out_dir)