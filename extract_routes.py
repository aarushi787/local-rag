import ast

with open("app.py", "r", encoding="utf-8") as f:
    source = f.read()

tree = ast.parse(source)
route_functions = []

for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                func = decorator.func
                if isinstance(func, ast.Attribute) and getattr(func.value, 'id', '') == 'app':
                    route_functions.append(node)
                    break

with open("src/api/routes.py", "w", encoding="utf-8") as f:
    f.write("from fastapi import APIRouter, Depends, HTTPException, Request\n\nrouter = APIRouter()\n\n")
    for func in route_functions:
        # replace @app. with @router.
        for dec in func.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if getattr(dec.func.value, 'id', '') == 'app':
                    dec.func.value.id = 'router'
        f.write(ast.unparse(func) + "\n\n")

print(f"Extracted {len(route_functions)} route functions.")
