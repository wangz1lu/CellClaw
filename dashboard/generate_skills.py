#!/usr/bin/env python3
"""Generate skills.json from skills folder"""
import json
import os
from pathlib import Path

def generate_skills():
    skills_dir = Path(__file__).parent.parent / "skills"
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    
    skills = []
    if skills_dir.exists():
        for d in skills_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                # Get name from SKILL.md first line
                name = d.name
                try:
                    with open(d / "SKILL.md", 'r') as f:
                        first_line = f.readline().strip()
                        if first_line.startswith('# '):
                            name = first_line[2:].strip()
                except:
                    pass
                skills.append({'id': d.name, 'name': name})
    
    # Write to static/skills.json
    with open(static_dir / 'skills.json', 'w') as f:
        json.dump(skills, f, indent=2)
    
    print(f"Generated {len(skills)} skills")
    return skills

if __name__ == "__main__":
    generate_skills()
