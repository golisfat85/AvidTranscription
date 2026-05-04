"""
AAF (Advanced Authoring Format) integration for Avid Media Composer.

Reads MasterClip metadata from an AAF file and can write subtitle segments
back as Avid DescriptiveMarkers (comment markers).

Requires:  pip install aaf2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class AAFError(Exception):
    pass


@dataclass
class ClipInfo:
    """Lightweight container for AAF clip metadata."""
    name: str
    mob_id: str
    duration_frames: int
    fps: float
    media_path: Optional[str] = None


@dataclass
class MarkerEntry:
    start_frame: int
    length_frames: int
    color: str
    comment: str
    user: str = "AvidTranscription"


class AAFHandler:
    """
    Read clip information from an Avid AAF file and optionally write
    subtitle markers back into the AAF.
    """

    def __init__(self, aaf_path: str | Path):
        self.aaf_path = Path(aaf_path)
        if not self.aaf_path.exists():
            raise AAFError(f"AAF file not found: {aaf_path}")
        self._ensure_aaf2()

    @staticmethod
    def _ensure_aaf2() -> None:
        try:
            import aaf2  # noqa: F401
        except ImportError:
            raise AAFError(
                "aaf2 library not installed. Run: pip install aaf2"
            )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def list_clips(self) -> List[ClipInfo]:
        """Return all MasterClip objects found in the AAF."""
        import aaf2

        clips: List[ClipInfo] = []
        with aaf2.open(str(self.aaf_path), "r") as f:
            for mob in f.content.mobs:
                if mob.class_name != "MasterMob":
                    continue
                fps, duration = self._extract_fps_duration(mob)
                media_path = self._find_media_path(mob)
                clips.append(ClipInfo(
                    name=mob.name or "(unnamed)",
                    mob_id=str(mob.mob_id),
                    duration_frames=duration,
                    fps=fps,
                    media_path=media_path,
                ))
        return clips

    def get_clip(self, name: str) -> Optional[ClipInfo]:
        for clip in self.list_clips():
            if clip.name == name:
                return clip
        return None

    def _extract_fps_duration(self, mob) -> tuple[float, int]:
        """Return (fps, total_frames) from the first slot with a valid edit rate."""
        try:
            for slot in mob.slots:
                edit_rate = slot.edit_rate
                if edit_rate and edit_rate.denominator:
                    fps = edit_rate.numerator / edit_rate.denominator
                    seg = slot.segment
                    if hasattr(seg, "length"):
                        return fps, int(seg.length)
        except Exception as e:
            logger.debug("Could not extract edit rate: %s", e)
        return 25.0, 0

    def _find_media_path(self, mob) -> Optional[str]:
        """Try to resolve the linked media file path from EssenceDescriptor."""
        try:
            for slot in mob.slots:
                seg = slot.segment
                if hasattr(seg, "components"):
                    for comp in seg.components:
                        if hasattr(comp, "mob"):
                            for inner_slot in comp.mob.slots:
                                desc = getattr(comp.mob, "descriptor", None)
                                if desc and hasattr(desc, "locator"):
                                    for loc in desc.locator:
                                        path = getattr(loc, "path", None)
                                        if path:
                                            return path
        except Exception as e:
            logger.debug("Could not resolve media path: %s", e)
        return None

    # ------------------------------------------------------------------
    # Writing markers
    # ------------------------------------------------------------------

    def write_markers(
        self,
        markers: List[MarkerEntry],
        mob_name: Optional[str] = None,
        output_path: Optional[str | Path] = None,
    ) -> Path:
        """
        Write subtitle entries as Avid comment markers into (a copy of) the AAF.

        Args:
            markers: List of MarkerEntry objects.
            mob_name: Target MasterMob name; if None all MasterMobs get markers.
            output_path: Where to write the updated AAF. Defaults to <original>_marked.aaf.

        Returns:
            Path to the output AAF.
        """
        import aaf2

        if output_path is None:
            output_path = self.aaf_path.with_stem(self.aaf_path.stem + "_marked")
        output_path = Path(output_path)

        import shutil
        shutil.copy2(self.aaf_path, output_path)

        with aaf2.open(str(output_path), "rw") as f:
            for mob in f.content.mobs:
                if mob.class_name != "MasterMob":
                    continue
                if mob_name and mob.name != mob_name:
                    continue
                self._add_markers_to_mob(f, mob, markers)

        logger.info("Written %d markers to %s", len(markers), output_path)
        return output_path

    def _add_markers_to_mob(self, f, mob, markers: List[MarkerEntry]) -> None:
        """Attach DescriptiveMarker objects to *mob*."""
        try:
            import aaf2

            for entry in markers:
                marker = f.create.DescriptiveMarker()
                marker["Position"].value = entry.start_frame
                marker["Length"].value = entry.length_frames
                marker["Comment"].value = entry.comment

                color_map = {
                    "red": (65535, 0, 0),
                    "green": (0, 65535, 0),
                    "blue": (0, 0, 65535),
                    "yellow": (65535, 65535, 0),
                    "cyan": (0, 65535, 65535),
                    "white": (65535, 65535, 65535),
                }
                rgb = color_map.get(entry.color.lower(), (65535, 0, 0))
                marker["CommentMarkerColor"].value = aaf2.auid.AUID(
                    *rgb, 0
                ) if hasattr(aaf2, "auid") else None

                mob["Slots"].value.append(marker)
        except Exception as e:
            logger.warning("Could not write marker to mob %s: %s", mob.name, e)

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def segments_to_markers(
        segments,
        fps: float = 25.0,
        color: str = "Red",
    ) -> List[MarkerEntry]:
        """Convert TranscriptSegment list → MarkerEntry list."""
        entries = []
        for seg in segments:
            start_frame = int(round(seg.start * fps))
            end_frame = int(round(seg.end * fps))
            length = max(1, end_frame - start_frame)
            entries.append(MarkerEntry(
                start_frame=start_frame,
                length_frames=length,
                color=color,
                comment=seg.text,
            ))
        return entries
