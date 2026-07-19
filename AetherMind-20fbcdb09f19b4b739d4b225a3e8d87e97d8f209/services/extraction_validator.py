import os
from pathlib import Path
from typing import Any, Dict, Tuple
import cv2
import numpy as np


class ExtractionValidator:
    @staticmethod
    def compare_images(original_path: str, reconstructed_path: str) -> Dict[str, float]:
        original = cv2.imread(original_path)
        reconstructed = cv2.imread(reconstructed_path)

        if original is None or reconstructed is None:
            return {
                "ssim": 0.0,
                "layout_similarity": 0.0,
                "border_similarity": 0.0,
                "table_similarity": 0.0,
                "checkbox_similarity": 0.0,
                "passed": 0.0
            }
        h, w = original.shape[:2]
        reconstructed = cv2.resize(reconstructed, (w, h))
        gray_orig = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        gray_recon = cv2.cvtColor(reconstructed, cv2.COLOR_BGR2GRAY)
        try:
            from skimage.metrics import structural_similarity as ssim
            ssim_score, _ = ssim(gray_orig, gray_recon, full=True)
            ssim_score = float(max(0.0, min(1.0, ssim_score)))
        except Exception:
            mse = np.mean((gray_orig - gray_recon) ** 2)
            ssim_score = float(max(0.0, 1.0 - (mse / 65025.0)))
        edges_orig = cv2.Canny(gray_orig, 50, 150)
        edges_recon = cv2.Canny(gray_recon, 50, 150)
        intersection = np.logical_and(edges_orig, edges_recon)
        union = np.logical_or(edges_orig, edges_recon)
        union_sum = np.sum(union)
        layout_similarity = float(np.sum(intersection) / union_sum) if union_sum > 0 else 1.0
        thresh_orig = cv2.threshold(gray_orig, 200, 255, cv2.THRESH_BINARY_INV)[1]
        thresh_recon = cv2.threshold(gray_recon, 200, 255, cv2.THRESH_BINARY_INV)[1]

        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))

        lines_orig = cv2.morphologyEx(thresh_orig, cv2.MORPH_OPEN, h_kernel) + cv2.morphologyEx(thresh_orig, cv2.MORPH_OPEN, v_kernel)
        lines_recon = cv2.morphologyEx(thresh_recon, cv2.MORPH_OPEN, h_kernel) + cv2.morphologyEx(thresh_recon, cv2.MORPH_OPEN, v_kernel)
        
        line_intersect = np.logical_and(lines_orig > 0, lines_recon > 0)
        line_union = np.logical_or(lines_orig > 0, lines_recon > 0)
        line_union_sum = np.sum(line_union)
        border_similarity = float(np.sum(line_intersect) / line_union_sum) if line_union_sum > 0 else 1.0

        def get_checkbox_count(thresh_img):
            cnts = cv2.findContours(thresh_img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            cnts = cnts[0] if len(cnts) == 2 else cnts[1]
            box_count = 0
            for c in cnts:
                x, y, w, h = cv2.boundingRect(c)
                aspect = w / h if h > 0 else 0
                if 8 <= w <= 32 and 8 <= h <= 32 and 0.8 <= aspect <= 1.25:
                    box_count += 1
            return box_count

        cb_orig = get_checkbox_count(thresh_orig)
        cb_recon = get_checkbox_count(thresh_recon)
        if cb_orig == 0 and cb_recon == 0:
            checkbox_similarity = 1.0
        else:
            checkbox_similarity = float(min(cb_orig, cb_recon) / max(cb_orig, cb_recon))

        table_similarity = float(max(border_similarity, layout_similarity) * 0.95 + ssim_score * 0.05)

        # Adjust for slide layouts (landscape images without form-specific lines/checkboxes)
        is_slide = (w / h) > 1.2
        if is_slide:
            border_similarity = 1.0
            checkbox_similarity = 1.0
            table_similarity = ssim_score
            avg_score = ssim_score
        else:
            scores = [ssim_score, layout_similarity, border_similarity, checkbox_similarity, table_similarity]
            avg_score = sum(scores) / len(scores)
            
        passed = 1.0 if avg_score >= 0.80 else 0.0

        return {
            "ssim": ssim_score,
            "layout_similarity": layout_similarity,
            "border_similarity": border_similarity,
            "table_similarity": table_similarity,
            "checkbox_similarity": checkbox_similarity,
            "passed": passed
        }
