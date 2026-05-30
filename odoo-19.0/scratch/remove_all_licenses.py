import os
import re
import shutil

repo_root = r"c:\Users\Shashank patel\Desktop\client codes\FiberaFRP\FibraFRP-client-repo\odoo-19.0"

# Directories/Files to skip entirely
skip_dirs = {".git", "venv19", "node_modules", ".gemini", "brain", "scratch"}

files_to_delete = []
dirs_to_delete = []

for root, dirs, files in os.walk(repo_root):
    # Modify dirs in-place to avoid traversing skipped directories
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    
    # Check for folders named 'license' or 'copying'
    for d in list(dirs):
        d_lower = d.lower()
        if d_lower in ("license", "copying"):
            dirpath = os.path.join(root, d)
            dirs_to_delete.append(dirpath)
            dirs.remove(d) # Don't walk into it
            
    for file in files:
        name_lower = file.lower()
        base, ext = os.path.splitext(name_lower)
        
        # Conditions to identify a license/copying file
        is_license_file = False
        
        # 1. Exact matches (case-insensitive) for common license files
        if name_lower in ("license", "license.txt", "license.md", "copying", "copying.txt", "copying.md", "authors", "authors.txt", "license.rtf"):
            is_license_file = True
        # 2. File containing 'license' or 'copying' and having a text/doc/license extension or no extension
        elif ("license" in name_lower or "copying" in name_lower) and ext in ("", ".txt", ".md", ".rtf", ".license", ".licenses"):
            is_license_file = True
            
        if is_license_file:
            files_to_delete.append(os.path.join(root, file))

# Delete folders
for dirpath in dirs_to_delete:
    print(f"Deleting directory: {dirpath}")
    try:
        shutil.rmtree(dirpath)
    except Exception as e:
        print(f"Error deleting directory {dirpath}: {e}")

# Delete files
for filepath in files_to_delete:
    if os.path.exists(filepath): # Might have been inside a deleted folder
        print(f"Deleting file: {filepath}")
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error deleting file {filepath}: {e}")

# Manifest parsing
manifest_files = []
for root, dirs, files in os.walk(repo_root):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for file in files:
        if file == "__manifest__.py":
            manifest_files.append(os.path.join(root, file))

license_re = re.compile(r'^\s*[\'"]license[\'"]\s*:\s*[\'"].*?[\'"]\s*,?\s*$', re.IGNORECASE)

print(f"Scanning {len(manifest_files)} manifest files...")
modified_count = 0

for manifest_path in manifest_files:
    with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    new_lines = []
    removed = False
    for line in lines:
        if license_re.match(line):
            removed = True
            continue
        new_lines.append(line)
        
    if removed:
        modified_count += 1
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

print(f"Successfully removed license key from {modified_count} manifest files.")
print("Done!")
