"""Media probing, frame access, analysis, and PPM composition."""

from frame_proxy.media.avi import AviDescriptor, probe_avi
from frame_proxy.media.contact import GridResult, compose_grid, plan_grid
from frame_proxy.media.detector import AnalysisResult, analyze_frames
from frame_proxy.media.frames import Frame, decode_frame_at
from frame_proxy.media.ppm import parse_ppm_header

__all__ = [
    "AnalysisResult",
    "AviDescriptor",
    "Frame",
    "GridResult",
    "analyze_frames",
    "compose_grid",
    "decode_frame_at",
    "parse_ppm_header",
    "plan_grid",
    "probe_avi",
]

