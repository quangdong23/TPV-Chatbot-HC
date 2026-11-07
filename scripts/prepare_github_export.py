#!/usr/bin/env python3
"""Export current source without old Git history, local secrets or runtime data."""
from pathlib import Path
import argparse
import re
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=root.parent / 'TPV-Chatbot-HC-github')
args = parser.parse_args()
destination = args.output.resolve()
if destination == root or destination.is_relative_to(root):
    parser.error('Thư mục xuất phải nằm ngoài dự án hiện tại.')
if destination.exists():
    parser.error('Thư mục xuất đã tồn tại; chọn một đường dẫn mới để không ghi đè dữ liệu.')


def git(*args):
    return subprocess.check_output(['git', '-C', str(root), *args])


# Refuse to re-export the known credential from HEAD; never print its value.
old_api = git('show', 'HEAD:frontend/js/api.js').decode()
match = re.search(r"var DEFAULT_ACCESS_TOKEN\s*=\s*(['\"])(.*?)\1", old_api)
legacy_secret = match[2].encode() if match and match[2] else None
names = set(git('ls-files', '-co', '--exclude-standard', '-z').decode().split('\0'))
local_roots = ('backend/data', 'backend/.runtime', 'backend/legal_data', 'backend/qdrant_storage')
selected = []
for name in sorted(names):
    if not name or any(name == prefix or name.startswith(prefix + '/') for prefix in local_roots):
        continue
    path = root / name
    if not path.is_file():
        continue
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise SystemExit(f'Không xuất liên kết file: {name}')
    basename = path.name.lower()
    if (basename.startswith('.env') and basename != '.env.example') or path.suffix.lower() in {'.pem','.key','.p12','.pfx','.bak','.mdf','.ndf','.ldf'}:
        continue
    data = path.read_bytes()
    if legacy_secret and legacy_secret in data:
        raise SystemExit(f'Còn token cũ trong file {name}; chưa tạo bản xuất.')
    if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', data):
        raise SystemExit(f'Có khóa riêng trong {name}; chưa tạo bản xuất.')
    selected.append((path, name))

# All checks happen before writing, so a rejected export does not leave a partial snapshot.
destination.mkdir(parents=True)
for path, name in selected:
    target = destination / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
print(f'Đã xuất {len(selected)} file vào {destination}')
print('Không mang theo .git, cấu hình .env riêng và dữ liệu chạy cục bộ.')
print('Chưa khởi tạo commit hoặc push lên GitHub. Cần đổi token backend cũ nếu vẫn còn hiệu lực.')
