import ast

with open("app.py", "r", encoding="utf-8") as f:
    source = f.read()

tree = ast.parse(source)
models = []
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == 'BaseModel':
                models.append(node)

with open("src/schemas/__init__.py", "w", encoding="utf-8") as f:
    f.write("from pydantic import BaseModel, Field\nfrom typing import List, Optional, Dict, Any\nfrom datetime import datetime\n\n")
    for model in models:
        f.write(ast.unparse(model) + "\n\n")

print(f"Extracted {len(models)} models.")
