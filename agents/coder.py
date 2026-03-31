"""
CoderAgent - Code Generation
===========================

Generates R/Python code based on task requirements.
Integrates with Skill knowledge bases.
"""

from __future__ import annotations
import os
import logging
from typing import Optional, Callable
from dataclasses import dataclass

from agents.base import BaseAgent
from agents.models import AgentConfig, AgentType, TaskStep

logger = logging.getLogger(__name__)


@dataclass
class CodeResult:
    """Result of code generation"""
    code: str
    language: str  # "R" or "Python"
    script_path: Optional[str] = None
    issues: list[str] = None  # Warnings or problems detected
    skill_used: Optional[str] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []


class CoderAgent:
    """
    CoderAgent generates executable code for bioinformatics tasks.
    
    Responsibilities:
    - Generate R/Python scripts
    - Integrate with Skill knowledge bases
    - Handle script file creation
    - Validate generated code
    """
    
    # Skill to template mapping
    SKILL_TEMPLATES = {
        "deg_analysis": {
            "R": """# DEG Analysis Template
library(Seurat)
library(dplyr)

# Load data
data <- ReadRDS("{input_file}")
DefaultAssay(data) <- "RNA"

# Find markers
markers <- FindAllMarkers(
    object = data,
    only.pos = TRUE,
    min.pct = 0.25,
    thresh.use = 0.25
)

# Save results
write.csv(markers, "{output_file}", row.names = FALSE)
cat("DEG analysis complete. Found", nrow(markers), "markers.\\n")
""",
            "Python": """# DEG Analysis Template
import scanpy as sc
import pandas as pd

# Load data
adata = sc.read_h5ad("{input_file}")

# Find markers
sc.tl.rank_genes_groups(adata, groupby="{groupby}", method="t-test")
result = adata.uns["rank_genes_groups"]
markers = pd.DataFrame(result["names"]).head(100)

# Save results
markers.to_csv("{output_file}", index=False)
print(f"DEG analysis complete. Found {len(markers)} markers.")
"""
        },
        "visualization_R": {
            "R": """# Visualization Template
library(Seurat)
library(ggplot2)

# Load data
data <- ReadRDS("{input_file}")

# UMAP visualization
p1 <- DimPlot(data, reduction = "umap", label = TRUE)
p2 <- FeaturePlot(data, features = c("{feature}"))

# Combine plots
combined <- p1 + p2
ggsave("{output_file}", combined, width = 12, height = 6)
cat("Visualization saved to {output_file}\\n")
"""
        },
        "batch_harmony": {
            "R": """# Batch Correction with Harmony
library(Seurat)
library(harmony)

# Load data
data <- ReadRDS("{input_file}")
data <- NormalizeData(data)

# Variable features
data <- FindVariableFeatures(data, nfeatures = 2000)
data <- ScaleData(data)

# Run PCA
data <- RunPCA(data, npcs = 30)

# Harmony integration
data <- RunHarmony(data, group.by.vars = "{batch_var}")
data <- RunUMAP(data, reduction = "harmony", dims = 1:30)

# Save
saveRDS(data, "{output_file}")
cat("Harmony batch correction complete.\\n")
"""
        }
    }
    
    def __init__(self, config: AgentConfig = None, shared_memory=None):
        self.config = config or AgentConfig.default_for(AgentType.CODER)
        self.name = self.config.name
        self.base = BaseAgent()
        
        # Shared memory for cross-agent knowledge
        self.shared_memory = shared_memory
        
        # API config
        self._api_key = self.config.api_key or os.getenv("CODER_API_KEY") or os.getenv("OMICS_LLM_API_KEY")
        self._base_url = self.config.base_url or os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._model = self.config.model or os.getenv("CODER_MODEL") or os.getenv("OMICS_LLM_MODEL", "deepseek-chat")
        
        # Script directory
        self._script_dir = "/tmp/cellclaw_scripts"
        os.makedirs(self._script_dir, exist_ok=True)
    
    # ───────────────────────────────────────────────────────────────
    # Code Generation
    # ───────────────────────────────────────────────────────────────
    
    async def generate(self, task_description: str, skill_id: str = None, 
                     language: str = "R", context: dict = None) -> CodeResult:
        """
        Generate code for a task.
        
        Args:
            task_description: What the code should do
            skill_id: Skill to use (uses template if provided)
            language: "R" or "Python"
            context: Additional context (input_file, output_file, etc.)
            
        Returns:
            CodeResult with generated code
        """
        context = context or {}
        
        # Check for skill template first
        if skill_id and skill_id in self.SKILL_TEMPLATES:
            code = await self._generate_from_skill(skill_id, language, context)
            return CodeResult(
                code=code,
                language=language,
                skill_used=skill_id,
            )
        
        # Generate from scratch using task description
        code = await self._generate_from_description(task_description, language, context)
        
        return CodeResult(code=code, language=language)
    
    async def _generate_from_skill(self, skill_id: str, language: str, 
                                  context: dict) -> str:
        """Generate code from skill template"""
        template = self.SKILL_TEMPLATES.get(skill_id, {}).get(language)
        
        if not template:
            logger.warning(f"No template for {skill_id}/{language}, using description generation")
            return await self._generate_from_description(f"Use {skill_id}", language, context)
        
        # Fill in template
        code = template.format(
            input_file=context.get("input_file", "/path/to/input.h5ad"),
            output_file=context.get("output_file", "/path/to/output.csv"),
            feature=context.get("feature", "marker_gene"),
            groupby=context.get("groupby", "cell_type"),
            batch_var=context.get("batch_var", "batch"),
        )
        
        logger.info(f"Generated code from skill template: {skill_id}")
        
        return code
    
    async def _generate_from_description(self, task_description: str, 
                                        language: str, context: dict) -> str:
        """Generate code from task description using LLM"""
        # Check shared memory for similar successful codes
        if self.shared_memory:
            relevant_codes = self.shared_memory.get_relevant(
                task_description, category="code", limit=3
            )
            for entry in relevant_codes:
                logger.info(f"Coder: Found relevant code from {entry.agent}: {entry.id}")
        # For now, return a placeholder
        
        if language == "R":
            code = f"""# Auto-generated code for: {task_description}
# TODO: Implement based on task

# Load library
library(Seurat)

# Your code here
print("Task: {task_description}")
"""
        else:
            code = f'''# Auto-generated code for: {task_description}
# TODO: Implement based on task

import scanpy as sc

# Your code here
print("Task: {task_description}")
'''
        
        logger.info(f"Generated placeholder code for task: {task_description[:50]}")
        
        return code
    
    # ───────────────────────────────────────────────────────────────
    # Script File Management
    # ───────────────────────────────────────────────────────────────
    
    async def save_code_to_memory(self, code: str, skill_id: str = None, language: str = "R"):
        """Save generated code to shared memory for future reference"""
        if self.shared_memory and skill_id:
            self.shared_memory.add_code_template(
                agent="coder",
                skill_id=skill_id,
                code=code,
                language=language
            )
            logger.info(f"Coder: Saved code to shared memory for skill {skill_id}")
    
    async def save_script(self, code: str, language: str, 
                         filename: str = None) -> str:
        """
        Save generated code to a file.
        
        Args:
            code: The code to save
            language: "R" or "Python"
            filename: Optional custom filename
            
        Returns:
            Path to saved script
        """
        import time
        
        if not filename:
            ext = ".R" if language == "R" else ".py"
            filename = f"script_{int(time.time())}{ext}"
        
        filepath = os.path.join(self._script_dir, filename)
        
        with open(filepath, "w") as f:
            f.write(code)
        
        logger.info(f"Saved script to {filepath}")
        
        return filepath
    
    async def fix(self, code: str, issues: list[str]) -> str:
        """
        Fix code based on review issues.
        
        Args:
            code: Original code
            issues: List of issues to fix
            
        Returns:
            Fixed code
        """
        # TODO: Use LLM to fix issues
        # For now, just log
        
        logger.info(f"Fixing {len(issues)} issues in code")
        
        for issue in issues:
            logger.info(f"  - {issue}")
        
        # Simple fixes could be applied here
        # For now, return as-is
        return code
    
    # ───────────────────────────────────────────────────────────────
    # Skill Integration
    # ───────────────────────────────────────────────────────────────
    
    def get_available_skills(self) -> list[str]:
        """Get list of skills with code templates"""
        return list(self.SKILL_TEMPLATES.keys())
    
    def has_skill_template(self, skill_id: str, language: str) -> bool:
        """Check if skill has a template for given language"""
        return skill_id in self.SKILL_TEMPLATES and language in self.SKILL_TEMPLATES[skill_id]
    
    def get_skill_template(self, skill_id: str, language: str) -> str:
        """Get skill template for given language"""
        return self.SKILL_TEMPLATES.get(skill_id, {}).get(language, "")
    
    def __repr__(self) -> str:
        return f"<CoderAgent: {self.name}>"
