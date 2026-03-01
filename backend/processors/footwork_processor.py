"""
FootworkProcessor — Real-time ankle tracking via YOLO pose estimation.

Extends the Vision Agents Ultralytics plugin to extract dance footwork metrics
(step count, foot speed, movement intensity) and overlay them onto the video
frames forwarded to the LLM.
"""

import logging
import numpy as np
from vision_agents.plugins.ultralytics import YOLOPoseProcessor

logger = logging.getLogger(__name__)

# COCO keypoint indices
LEFT_ANKLE = 15
RIGHT_ANKLE = 16
STEP_THRESHOLD = 12.0  # pixel‐distance that counts as a "step"


class FootworkProcessor(YOLOPoseProcessor):
    """
    Extends YOLOPoseProcessor to track footwork metrics.
    The parent class already handles:
      - process_video()  → receives video frames from the edge
      - Runs YOLO pose inference and draws skeleton overlays
      - Forwards annotated frames to the LLM via the shared VideoForwarder

    We override on_pose_results() (called after each YOLO inference) to
    extract ankle positions and accumulate dance metrics that the LLM
    can reference via the get_metrics_text() helper.
    """

    def __init__(self, **kwargs):
        super().__init__(
            model_path="yolo11n-pose.pt",
            conf_threshold=0.5,
            **kwargs,
        )
        # Tracking state
        self.prev_left_ankle = None
        self.prev_right_ankle = None
        self.step_count = 0
        self.speed_history: list[float] = []
        self.frame_count = 0
        self.current_speed = 0.0
        self.persons_detected = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _ankle_speed(current, previous):
        if current is None or previous is None:
            return 0.0
        return float(np.linalg.norm(np.array(current) - np.array(previous)))

    def _extract_ankles(self, keypoints):
        """Return (left, right) ankle (x,y) tuples or (None, None)."""
        if keypoints is None or len(keypoints) == 0:
            return None, None
        try:
            left = keypoints[LEFT_ANKLE][:2].tolist()
            right = keypoints[RIGHT_ANKLE][:2].tolist()
            # Confidence check — YOLO returns [x, y, conf]
            if len(keypoints[LEFT_ANKLE]) > 2 and keypoints[LEFT_ANKLE][2] < 0.3:
                left = None
            if len(keypoints[RIGHT_ANKLE]) > 2 and keypoints[RIGHT_ANKLE][2] < 0.3:
                right = None
            return left, right
        except (IndexError, TypeError):
            return None, None

    # ------------------------------------------------------------------
    # Override: called by parent after each YOLO inference
    # ------------------------------------------------------------------
    def on_pose_results(self, results):
        """
        Called automatically by YOLOPoseProcessor after running inference.
        `results` is the Ultralytics Results object for the current frame.
        """
        self.frame_count += 1

        try:
            if results and len(results) > 0 and results[0].keypoints is not None:
                kps = results[0].keypoints.data  # (N, 17, 3)
                self.persons_detected = len(kps)

                if self.persons_detected > 0:
                    person_kps = kps[0]  # first person
                    left, right = self._extract_ankles(person_kps)

                    left_speed = self._ankle_speed(left, self.prev_left_ankle)
                    right_speed = self._ankle_speed(right, self.prev_right_ankle)
                    self.current_speed = max(left_speed, right_speed)

                    self.speed_history.append(self.current_speed)
                    # Keep last 300 speed values (~30 seconds at 10 fps)
                    if len(self.speed_history) > 300:
                        self.speed_history = self.speed_history[-300:]

                    # Count a "step" when ankle displacement exceeds threshold
                    if self.current_speed > STEP_THRESHOLD:
                        self.step_count += 1

                    self.prev_left_ankle = left
                    self.prev_right_ankle = right
            else:
                self.persons_detected = 0
        except Exception as e:
            logger.warning(f"FootworkProcessor.on_pose_results error: {e}")

    # ------------------------------------------------------------------
    # Public: summary string that can be injected into the LLM context
    # ------------------------------------------------------------------
    def get_metrics_text(self) -> str:
        avg = float(np.mean(self.speed_history)) if self.speed_history else 0.0
        peak = float(np.max(self.speed_history)) if self.speed_history else 0.0
        intensity = "🔥 HIGH" if avg > 20 else ("⚡ MEDIUM" if avg > 8 else "💀 LOW")
        return (
            f"[FOOTWORK DATA] Steps: {self.step_count} | "
            f"Avg speed: {avg:.0f} | Peak speed: {peak:.0f} | "
            f"Intensity: {intensity} | "
            f"Persons visible: {self.persons_detected} | "
            f"Frames analyzed: {self.frame_count}"
        )
