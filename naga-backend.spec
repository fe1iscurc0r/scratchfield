# -*- mode: python ; coding: utf-8 -*-
"""
NagaAgent Headless Backend - PyInstaller Spec
编译后端为独立二进制，供 Electron 前端打包使用。
排除 PyQt5 及 UI 相关模块。
"""

import os
import sys
from pathlib import Path
#from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from PyInstaller.utils.hooks import (
    collect_submodules, collect_data_files,
    collect_dynamic_libs
)


block_cipher = None


def safe_print(*values, sep=" ", end="\n", file=None):
    stream = file or sys.stdout
    text = sep.join(str(value) for value in values)
    try:
        print(text, end=end, file=stream, flush=True)
        return
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        fallback = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="strict")
        stream.write(fallback)
        stream.write(end)
        stream.flush()

# 项目根目录
# PyInstaller 的 SPECPATH 可能是“spec 所在目录”或“spec 文件路径”，这里统一兼容。
_spec_path = Path(SPECPATH).resolve()
PROJECT_ROOT = str(_spec_path.parent if _spec_path.is_file() else _spec_path)

# 自动扫描项目目录，黑名单排除——开发环境有的全带上，避免手动列目录遗漏
_EXCLUDE_DIRS = {
    # 前端/构建产物/非运行时
    'frontend', 'build', 'dist', 'scripts', 'docs', 'logs', 'sessions',
    'uploaded_documents', 'hooks', '.cache', '.git', '.github',
    '__pycache__', '.venv', '.mypy_cache', '.pytest_cache', '.ruff_cache',
    'node_modules',
    # OpenClaw 打包态从 resources/runtime/openclaw 运行，不再将 vendor 冻结进 _internal
    'vendor',
    # PyQt UI（headless 模式不需要）
    'ui',
    # mcpserver 的 Python 模块由 PyInstaller 冻结导入，data 只额外收集 manifest
    'mcpserver',
}

datas = [('pyproject.toml', '.')]

for entry in os.listdir(PROJECT_ROOT):
    full = os.path.join(PROJECT_ROOT, entry)
    if not os.path.isdir(full):
        continue
    if entry in _EXCLUDE_DIRS or entry.startswith('.'):
        continue
    datas.append((entry, entry))
    safe_print(f"[spec] Include directory: {entry}/")

# mcpserver: 收集所有 agent-manifest.json（前端技能列表 + 工具 schema 扫描需要）
import glob as _glob
_manifest_files = _glob.glob(
    os.path.join(PROJECT_ROOT, 'mcpserver', '**', 'agent-manifest.json'),
    recursive=True,
)
for _mf in _manifest_files:
    _rel = os.path.relpath(_mf, PROJECT_ROOT)          # e.g. mcpserver/agent_weather_time/agent-manifest.json
    _dest = os.path.dirname(_rel)                       # e.g. mcpserver/agent_weather_time
    datas.append((_rel, _dest))
safe_print(f"[spec] Collected {len(_manifest_files)} MCP agent manifests")

# 打包机可能不存在 config.json（仅有 config.json.example）
if os.path.exists(os.path.join(PROJECT_ROOT, 'config.json')):
    datas.append(('config.json', '.'))
elif os.path.exists(os.path.join(PROJECT_ROOT, 'config.json.example')):
    datas.append(('config.json.example', '.'))
else:
    safe_print("[spec] WARN: config.json and config.json.example are both missing; runtime defaults will be used")

# 第三方包的数据文件
datas += collect_data_files('tiktoken')
datas += collect_data_files('tiktoken_ext')
datas += collect_data_files('litellm')
datas += collect_data_files('py2neo')

# 排除不需要的大型库（经审计确认未使用）
excludes = [
    # PyQt / Qt / UI
    'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtGui', 'PyQt5.QtCore', 'PyQt5.QtOpenGL',
    'PyQt6', 'PyQt6.QtWidgets', 'PyQt6.QtGui', 'PyQt6.QtCore',
    'ui', 'tkinter',
    # 深度学习框架（后端调 API，不跑本地模型）
    'torch', 'torchaudio', 'torchvision', 'torchgen', 'torchdata',
    'paddle', 'paddlenlp', 'paddleocr',
    'tensorflow', 'keras',
    'onnxruntime', 'onnx',
    'transformers', 'accelerate', 'diffusers', 'safetensors',
    'modelscope',
    # 科学计算（scipy 项目有用到，不排除）
    'sympy', 'numba', 'llvmlite',
    'statsmodels', 'patsy',
    # 数据处理 / 分析（pandas 项目未使用）
    'pandas', 'polars', '_polars_runtime_32', 'pyarrow', 'dask',
    'geopandas', 'folium', 'branca', 'xyzservices', 'fiona', 'shapely', 'pyproj', 'pyogrio',
    'h5py', 'tables',
    # 可视化
    'matplotlib', 'bokeh', 'plotly', 'seaborn', 'panel', 'holoviews', 'datashader',
    # CV（MCP可选）- 注意：PIL/Pillow 项目有用到，不排除
    'cv2', 'opencv', 'skimage', 'sklearn',
    # NLP 本地库
    'nltk', 'spacy', 'gensim',
    # 分布式 / 大数据
    'pyspark', 'ray', 'distributed',
    # Google / Cloud（不需要）
    'googleapiclient', 'google.cloud', 'google.auth', 'google_auth_httplib2',
    # 音视频处理（MCP可选；语音运行时所需依赖不排除）
    'av',
    # Web 工具（不需要）
    'gradio', 'streamlit', 'dash',
    # Jupyter / 开发工具
    'IPython', 'jupyter', 'notebook', 'nbconvert', 'nbformat', 'nbclassic',
    'sphinx', 'docutils',
    'pytest', 'unittest',
    'spyder', 'pylint', 'autopep8', 'flake8', 'mypy',
    # 浏览器自动化（MCP可选）
    'playwright', 'patchright', 'selenium',
    # 数据库 ORM
    'sqlalchemy', 'alembic',
    # 国际化
    'babel',
    # 其他大型库
    'lxml', 'wandb', 'mlflow',
    'faiss', 'milvus_lite',
    'pymupdf', 'fitz',
    'astropy',
    # GUI 自动化（MCP可选）
    'pyautogui', 'pytesseract', 'pycaw', 'screen_brightness_control',
    # 图可视化（pyvis 未使用；neo4j/py2neo 项目有用到，不排除）
    'pyvis',
    # 游戏 / 音频播放（pygame 项目有用到，不排除）
    # 爬虫（MCP可选）
    'crawl4ai',
    # 压缩（MCP可选）
    'py7zr', 'pyzipper',
    # 其他可选
    'gevent', 'flask', 'docx2pdf', 'img2pdf', 'msoffcrypto', 'pikepdf',
    'Crypto', 'pycryptodome',
    'agents',
    'jieba',
]

# 动态导入的模块（PyInstaller 静态分析可能遗漏）
hiddenimports = [
    # Web 框架
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    # HTTP 客户端
    'httpx',
    'httpcore',
    # LLM
    'langchain_openai',
    'litellm',
    'openai',
    # 数据处理
    'pydantic',
    'json5',
    'charset_normalizer',
    # 异步
    'asyncio',
    'anyio',
    # 系统信息
    'psutil',
    # HTTP / 工具
    'requests',
    # tiktoken 编码
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    # 语音运行时 / 实时语音
    'dashscope',
    'dashscope.audio',
    'dashscope.audio.qwen_omni',
    'pygame',
    'pygame.mixer',
    'pyaudio',
    'soundfile',
    'librosa',
    'voice.output.voice_integration',
    'voice.input.voice_realtime',
    'voice.input.voice_realtime.adapters.qwen_adapter',
    'voice.input.voice_realtime.adapters.qwen.client',
    'voice.input.voice_realtime.adapters.local',
    # 图数据库（项目实际使用，try-except 容错）
    'neo4j',
    'py2neo',
    # 图像处理（screenshot_provider / screen_vision 使用）
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    # 音频 DSP（lip-sync 使用）
    'scipy',
    'scipy.signal',
    'scipy.fft',
    # numpy（音频处理核心）
    'numpy',
]
hiddenimports += collect_submodules('mcpserver')
hiddenimports += collect_submodules('psutil')
hiddenimports += collect_submodules('charset_normalizer')

# charset_normalizer 3.x 的 mypyc 编译模块（如 81d243bd2c585b0f4821__mypyc.pyd）
# 位于 site-packages 根目录，collect_dynamic_libs 找不到，需手动扫描
import charset_normalizer as _cn
_cn_parent = os.path.dirname(os.path.dirname(_cn.__file__))  # site-packages
_mypyc_binaries = []
for _f in os.listdir(_cn_parent):
    if '__mypyc' in _f and (_f.endswith('.pyd') or _f.endswith('.so')):
        _mypyc_binaries.append((os.path.join(_cn_parent, _f), '.'))
        safe_print(f"[spec] Found mypyc binary: {_f}")
if not _mypyc_binaries:
    # fallback: 也检查包目录内部
    for _f in os.listdir(os.path.dirname(_cn.__file__)):
        if '__mypyc' in _f and (_f.endswith('.pyd') or _f.endswith('.so')):
            _mypyc_binaries.append((os.path.join(os.path.dirname(_cn.__file__), _f), '.'))
            safe_print(f"[spec] Found mypyc binary (in pkg): {_f}")

binaries = collect_dynamic_libs('psutil')
binaries += collect_dynamic_libs('charset_normalizer')
binaries += _mypyc_binaries

a = Analysis(
    ['main.py'],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='naga-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # headless 模式需要控制台输出
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='naga-backend',
)
