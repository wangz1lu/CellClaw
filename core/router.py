"""
Intent Router - Parses natural language commands into structured actions
"""

import re
from typing import Optional


class IntentRouter:
    """
    Maps natural language user input to structured analysis intents.
    """

    PATTERNS = [
        # Full pipeline
        (r"(run |execute )?(full |complete )?(pipeline|workflow|analysis) on (.+)", "full_pipeline", "file"),
        # QC
        (r"(run |do |perform )?qc( on (.+))?", "qc", "file"),
        (r"quality control( on (.+))?", "qc", "file"),
        # Clustering
        (r"(run |do )?(cluster|clustering|umap|tsne|dimensionality)", "cluster", None),
        (r"(reduce|embed) (dimensions|data)", "cluster", None),
        # Annotation
        (r"(annotate|annotation|label|identify) (cell ?types?|clusters?)", "annotate", None),
        (r"what (are|cell types) (the )?clusters?", "annotate", None),
        # DEG / Differential expression
        (r"(diff|differential) (expr|expression|genes?)", "deg", None),
        (r"compare (.+) (vs?\.?|versus) (.+)", "deg", "groups"),
        (r"marker genes? for cluster (\d+)", "deg", "cluster"),
        # Trajectory
        (r"(trajectory|pseudotime|rna velocity)", "trajectory", None),
        # Spatial
        (r"(load |read )?visium( (from|data) (.+))?", "spatial_load", "path"),
        (r"spatial (expression|plot|visualization) of (.+)", "spatial_plot", "gene"),
        (r"(show|plot|visualize) (.+) (in space|spatially)", "spatial_plot", "gene"),
        # Status
        (r"(status|info|what'?s loaded|current data)", "status", None),
    ]

    def parse(self, message: str, session=None) -> dict:
        """
        Parse a user message into a structured intent dict.

        Returns:
            dict: {"action": str, "params": dict, "raw": str}
        """
        msg = message.lower().strip()
        # Remove bot mentions
        msg = re.sub(r"@\w+\s*", "", msg).strip()

        for pattern, action, param_type in self.PATTERNS:
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                params = self._extract_params(match, action, param_type, session)
                return {"action": action, "params": params, "raw": message}

        return {"action": "help", "params": {}, "raw": message}

    def _extract_params(self, match, action: str, param_type: Optional[str], session) -> dict:
        params = {}

        if param_type == "file":
            # Try to extract file path from match groups
            for g in match.groups():
                if g and ("/" in g or "." in g or g.endswith(".h5ad") or g.endswith(".h5")):
                    params["filepath"] = g.strip()
                    break
            # Fall back to session's latest registered file
            if "filepath" not in params and session and session.latest_file:
                params["filepath"] = str(session.latest_file)

        elif param_type == "groups":
            groups = [g for g in match.groups() if g and g not in ("vs", "v", "versus")]
            if len(groups) >= 2:
                params["group1"] = groups[0].strip()
                params["group2"] = groups[-1].strip()

        elif param_type == "cluster":
            for g in match.groups():
                if g and g.isdigit():
                    params["cluster_id"] = int(g)
                    break

        elif param_type == "gene":
            for g in match.groups():
                if g and g not in ("in space", "spatially", "show", "plot", "visualize"):
                    params["gene"] = g.strip()
                    break

        elif param_type == "path":
            for g in match.groups():
                if g and ("/" in g or g.startswith(".")):
                    params["path"] = g.strip()
                    break

        return params
