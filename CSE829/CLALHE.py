import numpy as np
import cv2
from scipy.signal import argrelextrema

class CLALHE:
    """
    Contrast Limited Adaptive Local Histogram Equalization (CLALHE)
    Based on: Mohammed & Isa, IEEE Access 2025

    Implementation note - subimage boundary blending
    ------------------------------------------------
    Part 2 of the paper subdivides the image into ONS subimages (Eq. 5-6) and
    equalizes each one independently. Taken literally, that produces visible
    block seams: each subimage derives its own transfer function from its own
    histogram, so two pixels straddling a boundary have almost identical input
    intensities but are mapped through unrelated LUTs, and the output jumps.
    This is the same discontinuity that made plain (non-interpolated) AHE
    unusable, and it is why Zuiderveld's CLAHE bilinearly interpolates between
    tile mappings.

    The paper specifies no remedy. Its Part 2 step (v) says only "combination
    of the enhanced subimages", and Section IX pins that down as literal
    concatenation: "(viii) Merging of subimages involves their concatenation".
    "Bilinear interpolation" appears once in the whole paper, in the literature
    review, describing a different method (ACE-HM, ref [78]) - not CLALHE. The
    reported metrics could not have caught the seams either: PSNR, entropy,
    AMBE, SSI, CII and RMSE are all global statistics that a handful of
    boundary rows and columns barely move. It only shows up when you look at
    the picture.

    So the subdivision is kept exactly as specified - the number of subimages,
    their dimensions and their independent histograms are untouched - and only
    the write-back is changed: each subimage is read with an extra margin of
    context and composited through a linear cross-fade whose weights sum to 1
    across every shared boundary. This is the sub-image-level analogue of the
    tile interpolation CLAHE already performs internally, applied one level up.
    """
    
    def __init__(self):
        self.optimal_cbd = None
        self.optimal_i_cl = None
        
    def _find_peaks_valleys(self, histogram):
        """Identify peaks and valleys in the histogram as per Section V.A"""
        # Smooth histogram slightly to avoid noise-based false peaks
        hist_smooth = np.convolve(histogram, np.ones(3)/3, mode='same')
        
        # Find local maxima (peaks) and minima (valleys)
        peak_indices = argrelextrema(hist_smooth, np.greater, order=1)[0]
        valley_indices = argrelextrema(hist_smooth, np.less, order=1)[0]
        
        # Filter out edge cases if necessary
        peak_values = histogram[peak_indices]
        valley_values = histogram[valley_indices]
        
        return peak_indices, peak_values, valley_indices, valley_values
    
    def _calculate_n_parameter(self, valley_values):
        """Eq. (1): N-parameter = sum(Valley[i]) / NValleys"""
        if len(valley_values) == 0:
            return 1.0  # Fallback
        return np.sum(valley_values) / len(valley_values)
    
    def _calculate_cbd(self, n_peaks):
        """Eq. (2): CBD = ceil(ln(NPeaks)) for both height and width"""
        if n_peaks <= 0:
            return 4  # Default fallback
        cbd = int(np.ceil(np.log(n_peaks)))
        return max(cbd, 2)  # Ensure minimum tile size
    
    def _calculate_i_cl(self, peak_values, n_parameter, valley_values):
        """Eq. (3): I_CL = (Peaks[i] + N-parameter) / Max(Valley)"""
        if len(valley_values) == 0 or np.max(valley_values) == 0:
            return 2.0  # Fallback clip limit
        max_valley = np.max(valley_values)
        # Use the maximum peak for the most representative clip limit
        max_peak = np.max(peak_values) if len(peak_values) > 0 else 0
        i_cl = (max_peak + n_parameter) / max_valley
        return max(i_cl, 1.0)  # Clip limit must be >= 1
    
    def _compute_metrics(self, original, enhanced):
        """Compute PSNR, Entropy, and AMBE for CIQI fitness function"""
        # PSNR
        mse = np.mean((original.astype(np.float64) - enhanced.astype(np.float64)) ** 2)
        if mse == 0:
            psnr = 100.0
        else:
            psnr = 10 * np.log10((255.0 ** 2) / mse)
        
        # Entropy
        hist = cv2.calcHist([enhanced], [0], None, [256], [0, 256])
        prob = hist.ravel() / hist.sum()
        prob = prob[prob > 0]
        entropy = -np.sum(prob * np.log2(prob))
        
        # AMBE (Absolute Mean Brightness Error)
        ambe = abs(np.mean(original.astype(np.float64)) - np.mean(enhanced.astype(np.float64)))
        
        return psnr, entropy, ambe
    
    def _ciqi_score(self, original, enhanced):
        """Eq. (4): CIQI = (PSNR + Entropy) / AMBE"""
        psnr, entropy, ambe = self._compute_metrics(original, enhanced)
        if ambe == 0:
            ambe = 0.001  # Avoid division by zero
        return (psnr + entropy) / ambe
    
    def _apply_clahe_with_params(self, image, cbd, clip_limit):
        """Apply CLAHE with specific CBD and clip limit parameters"""
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(cbd, cbd))
        return clahe.apply(image)
    
    def part1_determine_optimal_params(self, gray_image):
        """
        Part 1: Determine optimum parameters (CBD and I_CL)
        Tests multiple enhancements using peak frequencies
        """
        # Compute histogram
        hist = cv2.calcHist([gray_image], [0], None, [256], [0, 256]).flatten()
        
        # Identify peaks and valleys
        peak_idx, peak_vals, valley_idx, valley_vals = self._find_peaks_valleys(hist)
        n_peaks = len(peak_idx)
        n_valleys = len(valley_idx)
        
        if n_peaks == 0:
            n_peaks = 1  # Prevent log(0)
        
        # Calculate base parameters
        n_param = self._calculate_n_parameter(valley_vals)
        cbd = self._calculate_cbd(n_peaks)
        
        # Test each peak value to find optimal I_CL via CIQI
        best_score = -np.inf
        best_i_cl = 2.0
        
        for p_val in peak_vals:
            candidate_i_cl = self._calculate_i_cl(np.array([p_val]), n_param, valley_vals)
            enhanced = self._apply_clahe_with_params(gray_image, cbd, candidate_i_cl)
            score = self._ciqi_score(gray_image, enhanced)
            
            if score > best_score:
                best_score = score
                best_i_cl = candidate_i_cl
        
        self.optimal_cbd = cbd
        self.optimal_i_cl = best_i_cl
        
        return cbd, best_i_cl, n_peaks, n_valleys
    
    def _blend_profile(self, p_start, p_stop, c_start, c_stop, margin,
                       ramp_head, ramp_tail):
        """
        1D weight profile for one subimage along a single axis.

        The weight is 1.0 in the interior of the subimage core and falls
        linearly to 0.0 across a 2*margin wide band centred on each shared
        boundary. Two adjacent subimages therefore contribute weights that
        sum to exactly 1.0 everywhere in their overlap, so the cross-fade is
        energy preserving and leaves no visible step.
        """
        coords = np.arange(p_start, p_stop, dtype=np.float64)
        weights = np.ones(p_stop - p_start, dtype=np.float64)

        if margin > 0:
            if ramp_head:  # boundary shared with the previous subimage
                weights = np.minimum(
                    weights, np.clip((coords - (c_start - margin)) / (2.0 * margin), 0.0, 1.0)
                )
            if ramp_tail:  # boundary shared with the next subimage
                weights = np.minimum(
                    weights, np.clip(((c_stop + margin) - coords) / (2.0 * margin), 0.0, 1.0)
                )

        return weights

    def part2_enhance(self, gray_image, n_valleys=None, blend_ratio=0.25):
        """
        Part 2: Subdivide image and enhance each subimage independently

        Each subimage is equalized on its own (as the paper specifies), but it
        is read with an extra `blend_ratio` margin of context on every shared
        side and written back through a linear cross-fade. This removes the
        block seams caused by neighbouring subimages using unrelated transfer
        functions, without merging their histograms.
        """
        if self.optimal_cbd is None or self.optimal_i_cl is None:
            raise ValueError("Run part1_determine_optimal_params first!")
        
        h, w = gray_image.shape
        
        # Eq. (5): Calculate Optimum Number of Subimages (ONS)
        if n_valleys is None or n_valleys == 0:
            n_valleys = 4  # Fallback
        ons_log = np.log2(n_valleys)
        ons = int(np.ceil(ons_log))
        if ons % 2 != 0:
            ons += 1  # Ensure even number
        ons = max(ons, 2)  # Minimum 2 subimages
        
        # Eq. (6): Calculate Subimage Dimensions (SID)
        if ons == 2:
            sub_h = h
            sub_w = w // 2
        else:
            sub_h = h // 2
            sub_w = w // (ons // 2) if ons > 2 else w // 2
        
        # Ensure valid dimensions
        sub_h = max(sub_h, 1)
        sub_w = max(sub_w, 1)
        
        # Subdivide and enhance each subimage independently
        rows = max(1, h // sub_h)
        cols = max(1, w // sub_w)

        # Overlap margins: only needed along axes that are actually split
        margin_y = max(1, int(sub_h * blend_ratio)) if rows > 1 else 0
        margin_x = max(1, int(sub_w * blend_ratio)) if cols > 1 else 0

        accumulator = np.zeros((h, w), dtype=np.float64)
        weight_total = np.zeros((h, w), dtype=np.float64)

        for r in range(rows):
            for c in range(cols):
                y_start = r * sub_h
                y_end = min((r + 1) * sub_h, h) if r < rows - 1 else h
                x_start = c * sub_w
                x_end = min((c + 1) * sub_w, w) if c < cols - 1 else w

                # Extended read window: the subimage plus its blending margin
                py_start = max(0, y_start - margin_y)
                py_end = min(h, y_end + margin_y)
                px_start = max(0, x_start - margin_x)
                px_end = min(w, x_end + margin_x)

                subimage = gray_image[py_start:py_end, px_start:px_end]

                # Apply optimal CLAHE to each subimage
                enhanced_sub = self._apply_clahe_with_params(
                    subimage, self.optimal_cbd, self.optimal_i_cl
                )

                # Cross-fade weights, separable along the two axes
                w_y = self._blend_profile(py_start, py_end, y_start, y_end, margin_y,
                                          ramp_head=(r > 0), ramp_tail=(r < rows - 1))
                w_x = self._blend_profile(px_start, px_end, x_start, x_end, margin_x,
                                          ramp_head=(c > 0), ramp_tail=(c < cols - 1))
                weights = w_y[:, None] * w_x[None, :]

                accumulator[py_start:py_end, px_start:px_end] += enhanced_sub * weights
                weight_total[py_start:py_end, px_start:px_end] += weights

        enhanced_image = accumulator / np.maximum(weight_total, 1e-8)
        return np.clip(np.round(enhanced_image), 0, 255).astype(gray_image.dtype)
    
    def enhance(self, image):
        """
        Full CLALHE pipeline for grayscale or color images
        """
        is_color = len(image.shape) == 3
        
        if is_color:
            # Convert to LAB and enhance L channel only
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0]
        else:
            l_channel = image.copy()
        
        # Part 1: Find optimal parameters
        _, _, _, n_valleys = self.part1_determine_optimal_params(l_channel)
        
        # Part 2: Enhance with subimage processing
        enhanced_l = self.part2_enhance(l_channel, n_valleys)
        
        if is_color:
            lab[:, :, 0] = enhanced_l
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            result = enhanced_l
        
        return result


# === USAGE EXAMPLE ===
if __name__ == "__main__":
    # Load image
    img = cv2.imread("public/sdrd.png")
    if img is None:
        print("Error: Could not load image")
    else:
        clalhe = CLALHE()
        enhanced = clalhe.enhance(img)
        
        # cv2.imshow("Original", img)
        # cv2.imshow("CLALHE Enhanced", enhanced)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()
        h, w = img.shape[:2]
        half_w = w // 2
        # left = cv2.resize(img, (half_w, h))
        # right = cv2.resize(enhanced, (w - half_w, h))
        # side_by_side = cv2.hconcat([left, right])
        side_by_side = cv2.hconcat([img, enhanced])
        cv2.imshow("Original | CLALHE Enhanced", side_by_side)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        cv2.imwrite("clalhe_output.jpg", enhanced)
        print(f"Optimal CBD: {clalhe.optimal_cbd}")
        print(f"Optimal I_CL: {clalhe.optimal_i_cl:.4f}")