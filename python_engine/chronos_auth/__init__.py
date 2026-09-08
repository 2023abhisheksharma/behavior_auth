"""
Chronos-Auth: Next-Gen Continuous Behavioral Biometrics Authentication Engine.

Components:
- ContextDetector: Active window, application classification, and desktop state telemetry.
- StrokeAnalyzer: Mouse kinematic decomposition (Bézier curves, jerk, tortuosity, click dwell).
- NgramAnalyzer: High-entropy key digraph & trigraph neuromuscular timing matrices.
- ChronosFeatureEngine: Multi-resolution (sub-second fast path + drift tracking) feature extractor.
- ContrastiveModel: Calibrated owner/impostor classifier with measured mouse profile.
- SPRTTrustEngine: Wald's Sequential Probability Ratio Test with bounded FAR/FRR.
"""

__version__ = "2.0.0"
