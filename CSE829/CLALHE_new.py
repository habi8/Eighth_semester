"""
CLALHE: Contrast Limited Adaptive Local Histogram Equalization
Based on: Mohammed & Isa, IEEE Access, 2025
DOI: 10.1109/ACCESS.2025.3558506

Corrected implementation addressing:
- I_CL computation using adjacent valleys (not global max)
- Proper peak/valley detection with robust smoothing
- Correct ONS/SID calculations per Eq. 5 & 6
- Proper CIQI fitness function
- Color image handling via LAB color space
"""

import numpy as np
import cv2
from scipy.signal import argrelextrema


class CLALHE:
    """
    Contrast Limited Adaptive Local Histogram Equalization (CLALHE)
    
    Two-part algorithm:
      Part 1: Determine optimal parameters (CBD, I_CL) via multi-enhancement
      Part 2: Subdivide image and enhance each subimage independently
    """

    def __init__(self):
        self.optimal_cbd = None
        self.optimal_i_cl = None
        self.n_peaks = 0
        self.n_valleys = 0

    # ─────────────────────────────────────────────
    #  PART 1: DETERMINING OPTIMUM PARAMETERS
    # ─────────────────────────────────────────────

    def _find_peaks_valleys(self, histogram):
        """
        Identify peaks and valleys in the histogram (Section V.A, Step iii).
        
        A peak: frequency higher than both neighbours.
        A valley: frequency lower than both neighbours.
        
        Uses light smoothing to suppress noise-induced false extrema.
        """
        # Smooth with a small kernel to remove noise spikes
        kernel_size = 3
        kernel = np.ones(kernel_size) / kernel_size
        hist_smooth = np.convolve(histogram, kernel, mode='same')

        # Detect local maxima (peaks) and minima (valleys)
        peak_indices = argrelextrema(hist_smooth, np.greater, order=1)[0]
        valley_indices = argrelextrema(hist_smooth, np.less, order=1)[0]

        # Extract actual frequencies from the ORIGINAL histogram
        peak_values = histogram[peak_indices].astype(np.float64)
        valley_values = histogram[valley_indices].astype(np.float64)

        return peak_indices, peak_values, valley_indices, valley_values

    def _calculate_n_parameter(self, valley_values):
        """
        Eq. (1): N-parameter = sum(Valley[i]) / NValleys
        Average frequency of all identified valleys.
        """
        if len(valley_values) == 0:
            return 1.0
        return np.sum(valley_values) / len(valley_values)

    def _calculate_cbd(self, n_peaks):
        """
        Eq. (2): CBD = ceil(ln(NPeaks)) x ceil(ln(NPeaks))
        Determines tile grid size for CLAHE.
        """
        if n_peaks <= 1:
            return 2  # Minimum viable tile size
        cbd = int(np.ceil(np.log(n_peaks)))
        return max(cbd, 2)  # Ensure at least 2x2

    def _calculate_i_cl_for_peak(self, peak_idx, peak_freq, n_parameter,
                                  valley_indices, valley_values):
        """
        Eq. (3): I_CL = (Peaks[i] + N-parameter) / Max(Adjacent Valleys)
        
        FIX: Uses only the valleys ADJACENT to the current peak,
        not the global max valley. This prevents distant high-frequency
        valleys from collapsing I_CL to <= 1.
        """
        if len(valley_values) == 0:
            return 2.0

        # Find the nearest valley on each side of this peak
        left_mask = valley_indices < peak_idx
        right_mask = valley_indices > peak_idx

        adjacent_freqs = []

        if np.any(left_mask):
            closest_left_idx = valley_indices[left_mask][-1]
            pos = np.where(valley_indices == closest_left_idx)[0][0]
            adjacent_freqs.append(valley_values[pos])

        if np.any(right_mask):
            closest_right_idx = valley_indices[right_mask][0]
            pos = np.where(valley_indices == closest_right_idx)[0][0]
            adjacent_freqs.append(valley_values[pos])

        if len(adjacent_freqs) == 0:
            return 2.0

        max_adjacent_valley = np.max(adjacent_freqs)

        # Avoid division by zero
        if max_adjacent_valley < 1e-6:
            return 2.0

        i_cl = (peak_freq + n_parameter) / max_adjacent_valley
        return i_cl

    def _compute_psnr(self, original, enhanced):
        """Eq. (10): PSNR = 10 * log10(Max(Ii)^2 / MSE)"""
        mse = np.mean((original.astype(np.float64) - enhanced.astype(np.float64)) ** 2)
        if mse < 1e-10:
            return 100.0
        return 10.0 * np.log10((255.0 ** 2) / mse)

    def _compute_entropy(self, image):
        """Eq. (7): DE = -sum(p(l) * log2(p(l)))"""
        hist = cv2.calcHist([image], [0], None, [256], [0, 256]).flatten()
        prob = hist / hist.sum()
        prob = prob[prob > 0]
        return -np.sum(prob * np.log2(prob))

    def _compute_ambe(self, original, enhanced):
        """Eq. (8): AMBE = |I(w,h)_mean - O(w,h)_mean|"""
        return abs(np.mean(original.astype(np.float64)) -
                   np.mean(enhanced.astype(np.float64)))

    def _ciqi_score(self, original, enhanced):
        """
        Eq. (4): CIQI = (PSNR + Entropy) / AMBE
        
        Fitness function: high PSNR + high entropy, low AMBE → high CIQI.
        """
        psnr = self._compute_psnr(original, enhanced)
        entropy = self._compute_entropy(enhanced)
        ambe = self._compute_ambe(original, enhanced)

        # Prevent division by zero
        if ambe < 1e-6:
            ambe = 1e-6

        return (psnr + entropy) / ambe

    def _apply_clahe(self, image, cbd, clip_limit):
        """
        Apply CLAHE with given tile size and clip limit.
        Clip limit is clamped to a reasonable range for OpenCV.
        """
        clip_limit = np.clip(clip_limit, 1.0, 40.0)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(cbd, cbd))
        return clahe.apply(image)

    def part1_determine_optimal_params(self, gray_image):
        """
        Part 1: Determine optimum parameters (CBD and I_CL).
        
        Steps (Section V.A):
          (i)   Read input image
          (ii)  Acquire image histogram
          (iii) Identify & quantify peaks and valleys
          (iv)  Compute N-parameter, CBD, I_CL
          (v)   Apply CLAHE multiple times (once per peak)
          (vi)  Sort optimum parameters via CIQI
        """
        # Step (ii): Histogram
        hist = cv2.calcHist([gray_image], [0], None, [256], [0, 256]).flatten()

        # Step (iii): Peaks and valleys
        peak_idx, peak_vals, valley_idx, valley_vals = self._find_peaks_valleys(hist)
        self.n_peaks = len(peak_idx)
        self.n_valleys = len(valley_idx)

        if self.n_peaks == 0:
            # Fallback: use default CLAHE parameters
            self.optimal_cbd = 8
            self.optimal_i_cl = 2.0
            return self.optimal_cbd, self.optimal_i_cl

        # Step (iv): Compute parameters
        n_param = self._calculate_n_parameter(valley_vals)
        cbd = self._calculate_cbd(self.n_peaks)

        # Step (v) & (vi): Multi-enhancement loop
        best_score = -np.inf
        best_i_cl = 2.0

        for i in range(self.n_peaks):
            p_idx = peak_idx[i]
            p_freq = peak_vals[i]

            # Compute I_CL using ADJACENT valleys only
            candidate_i_cl = self._calculate_i_cl_for_peak(
                p_idx, p_freq, n_param, valley_idx, valley_vals
            )

            # Clamp to reasonable OpenCV range
            candidate_i_cl = np.clip(candidate_i_cl, 1.0, 40.0)

            # Apply CLAHE with this candidate
            enhanced = self._apply_clahe(gray_image, cbd, candidate_i_cl)

            # Evaluate fitness
            score = self._ciqi_score(gray_image, enhanced)

            if score > best_score:
                best_score = score
                best_i_cl = candidate_i_cl

        self.optimal_cbd = cbd
        self.optimal_i_cl = best_i_cl

        return cbd, best_i_cl

    # ─────────────────────────────────────────────
    #  PART 2: OBTAINING A RESULTANT IMAGE
    # ─────────────────────────────────────────────

    def _calculate_ons(self, n_valleys):
        """
        Eq. (5): ONS = ceil(log2(NValleys))
        If odd, add 1 to make it even.
        """
        if n_valleys <= 1:
            return 2

        ons = int(np.ceil(np.log2(n_valleys)))

        # Force even number
        if ons % 2 != 0:
            ons += 1

        return max(ons, 2)

    def _calculate_sid(self, h, w, ons):
        """
        Eq. (6): Subimage dimensions based on ONS.
        
        If ONS == 2: SID = (M, N/2)      → split width only
        If ONS > 2:  SID = (M/2, N/(ONS/2)) → split both
        """
        if ons == 2:
            sub_h = h
            sub_w = w // 2
        else:
            sub_h = h // 2
            sub_w = w // (ons // 2)

        # Ensure valid dimensions
        sub_h = max(sub_h, 1)
        sub_w = max(sub_w, 1)

        return sub_h, sub_w

    def part2_enhance(self, gray_image):
        """
        Part 2: Subdivide image and enhance each subimage independently.
        
        Steps (Section V.B):
          (i)   Calculate ONS
          (ii)  Calculate SID
          (iii) Subdivide input image
          (iv)  Enhance each subimage with optimal CBD & I_CL
          (v)   Combine enhanced subimages
        """
        if self.optimal_cbd is None or self.optimal_i_cl is None:
            raise ValueError("Run part1_determine_optimal_params() first!")

        h, w = gray_image.shape[:2]

        # Step (i): ONS
        ons = self._calculate_ons(self.n_valleys)

        # Step (ii): SID
        sub_h, sub_w = self._calculate_sid(h, w, ons)

        # Step (iii) & (iv): Subdivide and enhance
        enhanced_image = np.zeros_like(gray_image)

        n_rows = max(1, int(np.ceil(h / sub_h)))
        n_cols = max(1, int(np.ceil(w / sub_w)))

        for r in range(n_rows):
            for c in range(n_cols):
                y_start = r * sub_h
                y_end = min((r + 1) * sub_h, h)
                x_start = c * sub_w
                x_end = min((c + 1) * sub_w, w)

                # Skip empty regions
                if y_end <= y_start or x_end <= x_start:
                    continue

                subimage = gray_image[y_start:y_end, x_start:x_end]

                # Enhance this subimage with optimal parameters
                enhanced_sub = self._apply_clahe(
                    subimage, self.optimal_cbd, self.optimal_i_cl
                )

                # Step (v): Write back
                enhanced_image[y_start:y_end, x_start:x_end] = enhanced_sub

        return enhanced_image

    # ─────────────────────────────────────────────
    #  FULL PIPELINE
    # ─────────────────────────────────────────────

    def enhance(self, image):
        """
        Full CLALHE pipeline.
        Handles both grayscale and color (BGR) images.
        For color: converts to LAB, enhances L-channel only.
        """
        is_color = len(image.shape) == 3

        if is_color:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0].copy()
        else:
            l_channel = image.copy()

        # Part 1: Determine optimal parameters
        self.part1_determine_optimal_params(l_channel)

        # Part 2: Subdivide and enhance
        enhanced_l = self.part2_enhance(l_channel)

        if is_color:
            lab[:, :, 0] = enhanced_l
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            result = enhanced_l

        return result

    def get_metrics(self, original, enhanced):
        """Compute all evaluation metrics for reporting."""
        psnr = self._compute_psnr(original, enhanced)
        entropy_orig = self._compute_entropy(original)
        entropy_enh = self._compute_entropy(enhanced)
        ambe = self._compute_ambe(original, enhanced)
        mse = np.mean((original.astype(np.float64) - enhanced.astype(np.float64)) ** 2)
        rmse = np.sqrt(mse)

        return {
            'PSNR': psnr,
            'Entropy_Original': entropy_orig,
            'Entropy_Enhanced': entropy_enh,
            'AMBE': ambe,
            'RMSE': rmse,
            'CIQI': self._ciqi_score(original, enhanced)
        }


# ═══════════════════════════════════════════════════
#  USAGE EXAMPLE
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    import os
    import time

    # --- Load image ---
    input_path = "input_image.jpg"
    img = cv2.imread(input_path)

    if img is None:
        print(f"[ERROR] Could not load image: {input_path}")
        exit(1)

    # --- Run CLALHE ---
    clalhe = CLALHE()
    start_time = time.time()
    enhanced = clalhe.enhance(img)
    elapsed = time.time() - start_time

    # --- Report parameters ---
    print("=" * 50)
    print("  CLALHE Enhancement Results")
    print("=" * 50)
    print(f"  Input image:      {input_path}")
    print(f"  Image size:       {img.shape[1]} x {img.shape[0]}")
    print(f"  N_Peaks:          {clalhe.n_peaks}")
    print(f"  N_Valleys:        {clalhe.n_valleys}")
    print(f"  Optimal CBD:      {clalhe.optimal_cbd} x {clalhe.optimal_cbd}")
    print(f"  Optimal I_CL:     {clalhe.optimal_i_cl:.4f}")
    print(f"  Processing time:  {elapsed:.4f} s")
    print("-" * 50)

    # --- Compute metrics (grayscale comparison) ---
    if len(img.shape) == 3:
        gray_orig = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_enh = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
    else:
        gray_orig = img
        gray_enh = enhanced

    metrics = clalhe.get_metrics(gray_orig, gray_enh)
    for key, val in metrics.items():
        print(f"  {key:<20s}: {val:.4f}")
    print("=" * 50)

    # --- Save output ---
    output_path = "clalhe_output.jpg"
    cv2.imwrite(output_path, enhanced)
    print(f"\n  Output saved to: {output_path}")

    # --- Display side by side ---
    # cv2.imshow("Original", img)
    # cv2.imshow("CLALHE Enhanced", enhanced)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()
    h, w = img.shape[:2]
    half_w = w // 2
    left = cv2.resize(img, (half_w, h))
    right = cv2.resize(enhanced, (w - half_w, h))
    side_by_side = cv2.hconcat([left, right])
    cv2.imshow("Original | CLALHE Enhanced", side_by_side)
    cv2.waitKey(0)
    cv2.destroyAllWindows()