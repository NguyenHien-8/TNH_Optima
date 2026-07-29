# App / Models / Analysis

## Project Overview

Production algorithm module for determining the baseline, fitting the droplet edge, and computing the two internal liquid contact angles.

## Annotated Directory Structure

- `AnalysisManager.py` — facade for selecting baseline/fitting methods.
- `BaselineAnalysis.py` — builds a line equation from two points; mirror method is TODO.
- `DropletAnalysis.py` — Fitzgibbon fit, robust weighted least squares, contact geometry, and baseline-constrained auto edge detection.
- `__init__.py` — package marker.

## Core Algorithms & Implementation

- Fitzgibbon: builds the design matrix `[x²,xy,y²,x,y,1]`, solves the generalized eigenproblem, filters ellipses with `4AC-B²>0`, and converts the conic to `(x0,y0,a,b,theta)`.
- Ellipse refinement: algebraic residual divided by gradient norm (Sampson-like), `exp(-alpha*d_norm²)` weights emphasizing the near-baseline region, and SciPy `least_squares` with `soft_l1`.
- Circle branch: optimizes the radial residual for `(x0,y0,R)`; the UI name is Young-Laplace, but the implementation is only a circular approximation.
- Contact angle: solves line-ellipse/circle intersections, orders left/right contact points, orients the baseline into the footprint, and chooses the tangent from the liquid-side curve branch to avoid `theta` versus `180-theta` errors.
- Auto edge runs only after a baseline `(a,b,c)` exists. The image is converted to grayscale `uint8`, Gaussian-blurred, and mapped accurately between pixels and the 5 mm x 3 mm physical domain.
- The baseline builds a half-plane mask `y > y_baseline(x)` before thresholding; substrate, reflection, and lower-side noise are removed from the binary image at the start.
- After inverse Otsu and image-size-adaptive morphology, contour candidates must meet minimum area, minimum cap height, and contain a continuous arc at least two pixels away from the baseline.
- The longest valid arc is selected by arc length and cap height. The clearance profile from left contact through apex to right contact trims low-clearance substrate tails and prevents the contour from spreading horizontally outside the footprint.
- The two baseline anchors are used as contact hints when close enough to the automatic contacts. Hints far from the contour are ignored; fallback fits each local side by clearance and extrapolates toward the baseline.
- After contact endpoints are restored, the liquid-cap arc is resampled by arc length rather than contour index. The final validation returns only points satisfying `y_point > y_baseline(x_point)`.

## Data Flow

1. Two baseline points -> `BaselineAnalyzer` -> coefficients `(a,b,c)`; the original points are retained as contact hints.
2. Grayscale image + baseline coefficients → half-plane mask → Otsu/morphology → contour candidates.
3. Longest valid arc -> clearance-tail trimming -> contact-hint validation or local-side extrapolation.
4. Liquid-cap arc plus two contact endpoints -> uniform arc-length sampling -> edge points above the baseline.
5. Edge points + baseline coefficients enter ellipse/circle fitting; the baseline is also used to compute intersections and fitting weights.
6. Results include angles, contact points, and tangents -> `DropletAnalysisWindow` draws the overlay/saves the image.
