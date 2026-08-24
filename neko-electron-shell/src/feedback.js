const { BrowserWindow, screen, ipcMain, app } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const crypto = require('node:crypto');
const archiver = require('archiver');
const FormData = require('form-data');
const http = require('node:http');
const { isTrustedSender } = require('./main/utils/trust-guard');

let feedbackWindow = null;

// 反馈页面的本地化文本
const feedbackLocales = {
  'zh-CN': {
    windowTitle: '用户反馈',
    title: '用户反馈',
    contactLabel: '联系方式（可选）：',
    contactPlaceholder: '请输入您的联系方式（邮箱、QQ、微信等）...',
    feedbackLabel: '请输入您的反馈：',
    feedbackPlaceholder: '请在此输入您的反馈内容...',
    cancel: '取消',
    submit: '提交',
    emptyFeedback: '请输入反馈内容',
    contactPrefix: '联系方式：',
    feedbackPrefix: '用户反馈：',
    packingLogs: '正在打包日志...',
    uploading: '正在上传...',
    successWithLogs: '反馈已提交，日志已上传，感谢您的反馈！',
    successNoLogs: '反馈已提交，感谢您的反馈！（日志不可用，未上传日志）',
    packFailed: '日志打包失败: {{error}}\n反馈内容已记录。',
    uploadFailed: '上传失败: {{error}}',
    operationFailed: '操作失败: {{error}}'
  },
  'zh-TW': {
    windowTitle: '使用者回饋',
    title: '使用者回饋',
    contactLabel: '聯絡方式（選填）：',
    contactPlaceholder: '請輸入您的聯絡方式（電子郵件、QQ、微信等）...',
    feedbackLabel: '請輸入您的回饋：',
    feedbackPlaceholder: '請在此輸入您的回饋內容...',
    cancel: '取消',
    submit: '提交',
    emptyFeedback: '請輸入回饋內容',
    contactPrefix: '聯絡方式：',
    feedbackPrefix: '使用者回饋：',
    packingLogs: '正在打包日誌...',
    uploading: '正在上傳...',
    successWithLogs: '回饋已提交，日誌已上傳，感謝您的回饋！',
    successNoLogs: '回饋已提交，感謝您的回饋！（日誌不可用，未上傳日誌）',
    packFailed: '日誌打包失敗: {{error}}\n回饋內容已記錄。',
    uploadFailed: '上傳失敗: {{error}}',
    operationFailed: '操作失敗: {{error}}'
  },
  'en': {
    windowTitle: 'User Feedback',
    title: 'User Feedback',
    contactLabel: 'Contact (optional):',
    contactPlaceholder: 'Enter your contact info (email, QQ, WeChat, etc.)...',
    feedbackLabel: 'Please enter your feedback:',
    feedbackPlaceholder: 'Enter your feedback here...',
    cancel: 'Cancel',
    submit: 'Submit',
    emptyFeedback: 'Please enter feedback content',
    contactPrefix: 'Contact: ',
    feedbackPrefix: 'User Feedback: ',
    packingLogs: 'Packing logs...',
    uploading: 'Uploading...',
    successWithLogs: 'Feedback submitted, logs uploaded. Thank you!',
    successNoLogs: 'Feedback submitted. Thank you! (Logs unavailable, not uploaded)',
    packFailed: 'Log packing failed: {{error}}\nFeedback content recorded.',
    uploadFailed: 'Upload failed: {{error}}',
    operationFailed: 'Operation failed: {{error}}'
  },
  'ja': {
    windowTitle: 'フィードバック',
    title: 'フィードバック',
    contactLabel: '連絡先（任意）：',
    contactPlaceholder: '連絡先を入力してください（メール、QQ、WeChatなど）...',
    feedbackLabel: 'フィードバックを入力してください：',
    feedbackPlaceholder: 'こちらにフィードバックを入力してください...',
    cancel: 'キャンセル',
    submit: '送信',
    emptyFeedback: 'フィードバック内容を入力してください',
    contactPrefix: '連絡先：',
    feedbackPrefix: 'フィードバック：',
    packingLogs: 'ログをパッケージ中...',
    uploading: 'アップロード中...',
    successWithLogs: 'フィードバックを送信しました。ログもアップロードされました。ありがとうございます！',
    successNoLogs: 'フィードバックを送信しました。ありがとうございます！（ログは利用できないため、アップロードされませんでした）',
    packFailed: 'ログのパッケージに失敗しました: {{error}}\nフィードバック内容は記録されました。',
    uploadFailed: 'アップロードに失敗しました: {{error}}',
    operationFailed: '操作に失敗しました: {{error}}'
  },
  'es': {
    windowTitle: 'Comentarios del usuario',
    title: 'Comentarios del usuario',
    contactLabel: 'Contacto (opcional):',
    contactPlaceholder: 'Introduce tu información de contacto (email, QQ, WeChat, etc.)...',
    feedbackLabel: 'Introduce tus comentarios:',
    feedbackPlaceholder: 'Escribe tus comentarios aquí...',
    cancel: 'Cancelar',
    submit: 'Enviar',
    emptyFeedback: 'Por favor introduce el contenido de los comentarios',
    contactPrefix: 'Contacto: ',
    feedbackPrefix: 'Comentarios del usuario: ',
    packingLogs: 'Empaquetando registros...',
    uploading: 'Subiendo...',
    successWithLogs: 'Comentarios enviados y registros subidos. ¡Gracias!',
    successNoLogs: 'Comentarios enviados. ¡Gracias! (Registros no disponibles, no se subieron)',
    packFailed: 'Error al empaquetar registros: {{error}}\nContenido de comentarios registrado.',
    uploadFailed: 'Error al subir: {{error}}',
    operationFailed: 'Error en la operación: {{error}}'
  },
  'pt': {
    windowTitle: 'Comentários do usuário',
    title: 'Comentários do usuário',
    contactLabel: 'Contato (opcional):',
    contactPlaceholder: 'Digite suas informações de contato (email, QQ, WeChat, etc.)...',
    feedbackLabel: 'Digite seus comentários:',
    feedbackPlaceholder: 'Escreva seus comentários aqui...',
    cancel: 'Cancelar',
    submit: 'Enviar',
    emptyFeedback: 'Por favor digite o conteúdo dos comentários',
    contactPrefix: 'Contato: ',
    feedbackPrefix: 'Comentários do usuário: ',
    packingLogs: 'Empacotando registros...',
    uploading: 'Enviando...',
    successWithLogs: 'Comentários enviados e registros carregados. Obrigado!',
    successNoLogs: 'Comentários enviados. Obrigado! (Registros indisponíveis, não enviados)',
    packFailed: 'Falha ao empacotar registros: {{error}}\nConteúdo dos comentários registrado.',
    uploadFailed: 'Falha no envio: {{error}}',
    operationFailed: 'Falha na operação: {{error}}'
  }
};

// 当前语言（默认英文）
let currentLanguage = 'en';
let backendUrlProvider = null;

const LOG_UPLOAD_SERVER_MAX_BYTES = 3 * 1024 * 1024;
const LOG_ZIP_RAW_BUDGET_BYTES = 2 * 1024 * 1024;
const LOG_ZIP_ELECTRON_BUDGET_BYTES = 256 * 1024;
const LOG_ZIP_PYTHON_BUDGET_BYTES = LOG_ZIP_RAW_BUDGET_BYTES - LOG_ZIP_ELECTRON_BUDGET_BYTES;
const LOG_ZIP_MAX_FILES = 18;
const LOG_ZIP_MIN_TAIL_BYTES = 8 * 1024;
const LOG_FILE_TAIL_BYTES = 256 * 1024;
const LOG_ERROR_FILE_TAIL_BYTES = 512 * 1024;
const LOG_ELECTRON_FILE_TAIL_BYTES = 128 * 1024;
const LOG_DISCOVERY_TIMEOUT_MS = 1200;

function configureFeedback(options = {}) {
  if (typeof options.getBackendUrl === 'function') {
    backendUrlProvider = options.getBackendUrl;
  }
}

// 获取系统语言
function getSystemLanguage() {
  try {
    const locale = app.getLocale();
    if (locale && locale.toLowerCase().startsWith('zh')) {
      // 繁体中文地区
      if (locale === 'zh-TW' || locale === 'zh-HK' || locale === 'zh-Hant') {
        return 'zh-TW';
      }
      return 'zh-CN';
    }
    if (locale && locale.toLowerCase().startsWith('ja')) {
      return 'ja';
    }
    if (locale && locale.toLowerCase().startsWith('es')) {
      return 'es';
    }
    if (locale && locale.toLowerCase().startsWith('pt')) {
      return 'pt';
    }
    return 'en';
  } catch (err) {
    return 'en';
  }
}

// 初始化语言
function initializeLanguage() {
  currentLanguage = getSystemLanguage();
}

// 获取本地化文本
function t(key) {
  const texts = feedbackLocales[currentLanguage] || feedbackLocales['en'];
  return texts[key] || key;
}

// 获取core_config.txt配置
// 优先读取 userData 下的用户覆盖（可写），回退到打包的只读默认
function getCoreConfig() {
  const userPath = path.join(app.getPath('userData'), 'core_config.txt');
  const bundledBase = app.isPackaged ? process.resourcesPath : process.cwd();
  const bundledPath = path.join(bundledBase, 'core_config.txt');
  for (const p of [userPath, bundledPath]) {
    if (fs.existsSync(p)) {
      try {
        return JSON.parse(fs.readFileSync(p, 'utf-8'));
      } catch (error) {
        console.warn('读取core_config.txt失败:', p, error.message);
      }
    }
  }
  return {};
}

// 获取日志服务器URL
function getLogStoreServerUrl() {
  const config = getCoreConfig();
  return config.logStoreServerUrl || 'http://localhost:8000';
}

// 获取图标路径（从 main.js 复制）
function getIcon() {
  const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
  const platform = process.platform;
  let iconPath;
  
  if (platform === 'darwin') {
    // macOS 使用 .icns 或 .png
    const icnsPath = path.join(basePath, 'icon.icns');
    const pngPath = path.join(basePath, 'icon.png');
    if (fs.existsSync(icnsPath)) {
      iconPath = icnsPath;
    } else if (fs.existsSync(pngPath)) {
      iconPath = pngPath;
    } else {
      // 如果没有找到 macOS 格式的图标，尝试使用 build 目录下的
      const buildIcnsPath = path.join(basePath, 'build', 'icon.icns');
      if (fs.existsSync(buildIcnsPath)) {
        iconPath = buildIcnsPath;
      } else {
        iconPath = path.join(basePath, 'icon.ico'); // 最后的回退
      }
    }
  } else if (platform === 'win32') {
    // Windows 使用 .ico
    iconPath = path.join(basePath, 'icon.ico');
  } else {
    // Linux 使用 .png
    const pngPath = path.join(basePath, 'icon.png');
    iconPath = fs.existsSync(pngPath) ? pngPath : path.join(basePath, 'icon.ico');
  }
  
  return iconPath;
}

// 获取文档目录路径（根据系统不同）
function getDocumentsDirectory() {
  const platform = process.platform;

  if (platform === 'win32') {
    return app.getPath('documents');
  }
  if (platform === 'darwin') {
    return app.getPath('documents');
  }

  // Linux/Ubuntu: 优先使用XDG_DOCUMENTS_DIR，否则使用Documents
  const xdgDocs = process.env.XDG_DOCUMENTS_DIR;
  if (xdgDocs && fs.existsSync(xdgDocs)) {
    return xdgDocs;
  }
  return app.getPath('documents');
}

function getLegacyRuntimeRoot() {
  return path.join(getDocumentsDirectory(), 'N.E.K.O');
}

// 兼容旧调用：旧版本日志目录为 Documents/N.E.K.O/logs
function getLogsDirectory() {
  return path.join(getLegacyRuntimeRoot(), 'logs');
}

function dedupePaths(candidates) {
  const result = [];
  const seen = new Set();
  for (const candidate of candidates) {
    const raw = String(candidate || '').trim();
    if (!raw) continue;
    let normalized;
    try {
      normalized = path.resolve(raw);
    } catch (_) {
      continue;
    }
    const key = process.platform === 'win32' ? normalized.toLowerCase() : normalized;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(normalized);
  }
  return result;
}

function getConfiguredBackendUrl() {
  if (typeof backendUrlProvider === 'function') {
    try {
      const provided = String(backendUrlProvider() || '').trim();
      if (provided) return provided;
    } catch (error) {
      console.warn('读取后端URL失败:', error.message);
    }
  }

  const envUrl = String(process.env.NEKO_MAIN_SERVER_URL || '').trim();
  if (envUrl) return envUrl;

  const envPort = String(process.env.NEKO_MAIN_SERVER_PORT || '').trim();
  const port = envPort || '48911';
  return `http://127.0.0.1:${port}/`;
}

function requestJson(urlString, timeoutMs = LOG_DISCOVERY_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let requestUrl;
    try {
      requestUrl = new URL(urlString);
    } catch (error) {
      reject(error);
      return;
    }

    const httpModule = requestUrl.protocol === 'https:' ? require('node:https') : http;
    const req = httpModule.request({
      method: 'GET',
      hostname: requestUrl.hostname,
      port: requestUrl.port || (requestUrl.protocol === 'https:' ? 443 : 80),
      path: `${requestUrl.pathname}${requestUrl.search}`,
      headers: { Accept: 'application/json' },
      timeout: timeoutMs
    }, (res) => {
      let responseData = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        responseData += chunk;
      });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(responseData || '{}'));
        } catch (error) {
          reject(error);
        }
      });
    });

    req.on('timeout', () => {
      req.destroy(new Error('request timeout'));
    });
    req.on('error', reject);
    req.end();
  });
}

function buildBackendApiUrl(endpoint, backendUrl = getConfiguredBackendUrl()) {
  const base = new URL(backendUrl);
  if (!base.pathname.endsWith('/')) {
    base.pathname = `${base.pathname}/`;
  }
  base.search = '';
  base.hash = '';
  return new URL(String(endpoint || '').replace(/^\/+/, ''), base).toString();
}

async function fetchBackendStorageRoot() {
  const backendUrl = getConfiguredBackendUrl();
  if (!backendUrl) return '';

  const endpoints = [
    'api/storage/location/status',
    'api/storage/location/bootstrap',
    'api/storage/location/diagnostics'
  ];

  for (const endpoint of endpoints) {
    try {
      const url = buildBackendApiUrl(endpoint, backendUrl);
      const payload = await requestJson(url);
      const candidate = (
        payload.effective_root
        || payload.current_root
        || (payload.layout && payload.layout.effective_root)
        || ''
      );
      if (String(candidate || '').trim()) {
        return String(candidate).trim();
      }
    } catch (error) {
      console.warn(`读取后端存储路径失败 (${endpoint}):`, error.message);
    }
  }

  return '';
}

function getFallbackRuntimeRoots() {
  const roots = [getLegacyRuntimeRoot()];

  try {
    if (process.platform === 'win32' && process.env.APPDATA) {
      roots.push(path.join(process.env.APPDATA, 'N.E.K.O'));
    } else if (process.platform === 'darwin') {
      roots.push(path.join(os.homedir(), 'Library', 'Application Support', 'N.E.K.O'));
    } else {
      const xdgDataHome = String(process.env.XDG_DATA_HOME || '').trim();
      roots.push(xdgDataHome
        ? path.join(xdgDataHome, 'N.E.K.O')
        : path.join(os.homedir(), '.local', 'share', 'N.E.K.O'));
    }
  } catch (_) {
    // ignored
  }

  try {
    const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
    roots.push(basePath);
  } catch (_) {
    // ignored
  }

  return roots;
}

async function getLogDirectoryCandidates() {
  const runtimeRoots = [];

  const selectedRootEnv = String(process.env.NEKO_STORAGE_SELECTED_ROOT || '').trim();
  if (selectedRootEnv) {
    runtimeRoots.push(selectedRootEnv);
  }

  const backendStorageRoot = await fetchBackendStorageRoot();
  if (backendStorageRoot) {
    runtimeRoots.push(backendStorageRoot);
  }

  runtimeRoots.push(...getFallbackRuntimeRoots());

  return dedupePaths(runtimeRoots.map(root => path.join(root, 'logs')));
}

function isLogFileName(fileName) {
  return /\.log(?:\.\d+)?$/i.test(String(fileName || ''));
}

function collectLogFilesFromDirectory(logsDir, sourceIndex) {
  const root = path.resolve(logsDir);
  const collected = [];
  const stack = [{ dir: root, depth: 0 }];

  while (stack.length > 0) {
    const { dir, depth } = stack.pop();
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (error) {
      console.warn(`读取日志目录失败: ${dir}`, error.message);
      continue;
    }

    for (const entry of entries) {
      const filePath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (depth < 2) {
          stack.push({ dir: filePath, depth: depth + 1 });
        }
        continue;
      }
      if (!entry.isFile() || !isLogFileName(entry.name)) {
        continue;
      }

      try {
        const stats = fs.statSync(filePath);
        if (!stats.isFile()) continue;
        collected.push({
          filePath,
          mtimeMs: stats.mtimeMs,
          size: stats.size,
          sourceIndex,
          relativePath: path.relative(root, filePath),
          isErrorLog: /_error\.log(?:\.\d+)?$/i.test(entry.name)
        });
      } catch (error) {
        console.warn(`读取日志文件信息失败: ${filePath}`, error.message);
      }
    }
  }

  return collected;
}

function selectLogFiles(files, budgetBytes = LOG_ZIP_PYTHON_BUDGET_BYTES) {
  const unique = [];
  const seen = new Set();
  const sorted = [...files].sort((a, b) => {
    if (a.isErrorLog !== b.isErrorLog) {
      return a.isErrorLog ? -1 : 1;
    }
    return b.mtimeMs - a.mtimeMs;
  });

  let remainingBytes = Math.max(0, budgetBytes);
  for (const file of sorted) {
    const key = process.platform === 'win32' ? file.filePath.toLowerCase() : file.filePath;
    if (seen.has(key)) continue;
    if (unique.length >= LOG_ZIP_MAX_FILES) break;
    if (remainingBytes < LOG_ZIP_MIN_TAIL_BYTES) {
      break;
    }
    const perFileLimit = file.isErrorLog ? LOG_ERROR_FILE_TAIL_BYTES : LOG_FILE_TAIL_BYTES;
    const bytesToInclude = Math.min(file.size, perFileLimit, remainingBytes);
    if (bytesToInclude < LOG_ZIP_MIN_TAIL_BYTES && file.size > LOG_ZIP_MIN_TAIL_BYTES) {
      continue;
    }
    seen.add(key);
    unique.push({
      ...file,
      bytesToInclude,
      originalSize: file.size,
      truncated: file.size > bytesToInclude
    });
    remainingBytes -= bytesToInclude;
  }

  return unique;
}

function sanitizeZipSegment(segment) {
  return String(segment || 'logs')
    .replace(/\\/g, '/')
    .split('/')
    .filter(Boolean)
    .pop()
    ?.replace(/[^a-zA-Z0-9._-]/g, '_') || 'logs';
}

function buildLogZipName(entry, logDirCount) {
  const relative = String(entry.relativePath || path.basename(entry.filePath))
    .split(path.sep)
    .join('/');
  if (logDirCount <= 1) {
    return `logs/${relative}`;
  }
  const sourceLabel = `source-${entry.sourceIndex + 1}-${sanitizeZipSegment(path.dirname(path.resolve(entry.filePath)))}`;
  return `logs/${sourceLabel}/${relative}`;
}

function selectElectronLogFiles(files, budgetBytes = LOG_ZIP_ELECTRON_BUDGET_BYTES) {
  const selected = [];
  let remainingBytes = Math.max(0, budgetBytes);
  for (const file of files) {
    if (remainingBytes < LOG_ZIP_MIN_TAIL_BYTES) break;
    const bytesToInclude = Math.min(file.size, LOG_ELECTRON_FILE_TAIL_BYTES, remainingBytes);
    if (bytesToInclude < LOG_ZIP_MIN_TAIL_BYTES && file.size > LOG_ZIP_MIN_TAIL_BYTES) {
      continue;
    }
    selected.push({
      ...file,
      bytesToInclude,
      originalSize: file.size,
      truncated: file.size > bytesToInclude
    });
    remainingBytes -= bytesToInclude;
  }
  return selected;
}

function getElectronLogFiles() {
  const files = [];
  try {
    const logPath = path.join(app.getPath('userData'), 'neko-electron-debug.log');
    for (const candidate of [logPath, `${logPath}.old`]) {
      if (!fs.existsSync(candidate)) continue;
      const stats = fs.statSync(candidate);
      if (stats.isFile()) {
        files.push({
          filePath: candidate,
          zipName: `electron/${path.basename(candidate)}`,
          size: stats.size
        });
      }
    }
  } catch (error) {
    console.warn('读取 Electron 日志失败:', error.message);
  }
  return selectElectronLogFiles(files);
}

function readFileTail(entry) {
  const originalSize = Number(entry.originalSize || entry.size || 0);
  const requestedBytes = Math.max(0, Number(entry.bytesToInclude || 0));
  if (requestedBytes <= 0) {
    return Buffer.alloc(0);
  }

  const start = Math.max(0, originalSize - requestedBytes);
  const buffer = Buffer.alloc(Math.min(requestedBytes, originalSize || requestedBytes));
  let fd = null;
  try {
    fd = fs.openSync(entry.filePath, 'r');
    const bytesRead = fs.readSync(fd, buffer, 0, buffer.length, start);
    const payload = buffer.subarray(0, bytesRead);
    if (start <= 0) {
      return payload;
    }
    const header = Buffer.from(
      `[N.E.K.O feedback package: showing last ${bytesRead} of ${originalSize} bytes from ${entry.filePath}]\n\n`,
      'utf8'
    );
    return Buffer.concat([header, payload]);
  } finally {
    if (fd !== null) {
      try {
        fs.closeSync(fd);
      } catch (_) {
        // ignored
      }
    }
  }
}

function createFeedbackPackageId() {
  try {
    if (typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch (_) {
    // fallback below
  }
  return crypto.randomBytes(16).toString('hex');
}

function buildLogPackageManifest({ packageId, logDirs, selectedFiles, electronFiles }) {
  const lines = [
    'N.E.K.O log upload package',
    `package_id=${packageId || '-'}`,
    `created_at=${new Date().toISOString()}`,
    `backend_url=${getConfiguredBackendUrl() || '-'}`,
    `server_file_limit_bytes=${LOG_UPLOAD_SERVER_MAX_BYTES}`,
    `raw_tail_budget_bytes=${LOG_ZIP_RAW_BUDGET_BYTES}`,
    '',
    'scanned_log_directories:',
    ...logDirs.map(dir => `- ${dir}${fs.existsSync(dir) ? '' : ' (missing)'}`),
    '',
    `python_log_files=${selectedFiles.length}`,
    ...selectedFiles.map(file => (
      `- ${file.filePath} (included ${file.bytesToInclude}/${file.originalSize} bytes${file.truncated ? ', tail only' : ''})`
    )),
    '',
    `electron_log_files=${electronFiles.length}`,
    ...electronFiles.map(file => (
      `- ${file.filePath} (included ${file.bytesToInclude}/${file.originalSize} bytes${file.truncated ? ', tail only' : ''})`
    ))
  ];

  if (selectedFiles.length === 0) {
    lines.push('', 'note=No Python log files were found in the scanned directories.');
  }
  lines.push('', 'note=Large logs are truncated from the beginning; recent tail content is preserved.');

  return `${lines.join('\n')}\n`;
}

function ensureFeedbackTempDir() {
  const tempDir = path.join(app.getPath('temp'), 'N.E.K.O', 'feedback');
  fs.mkdirSync(tempDir, { recursive: true });
  cleanupLegacyFeedbackZipFiles(tempDir);
  return tempDir;
}

function isManagedFeedbackZipPath(zipPath) {
  if (!zipPath) return false;
  try {
    const tempDir = path.resolve(app.getPath('temp'), 'N.E.K.O', 'feedback');
    const resolvedZipPath = path.resolve(String(zipPath));
    const relative = path.relative(tempDir, resolvedZipPath);
    return Boolean(relative) && !relative.startsWith('..') && !path.isAbsolute(relative);
  } catch (_) {
    return false;
  }
}

function getFeedbackZipSignature(zipPath) {
  if (!isManagedFeedbackZipPath(zipPath)) {
    return null;
  }

  try {
    const stats = fs.statSync(zipPath);
    if (!stats.isFile()) {
      return null;
    }
    return {
      size: stats.size,
      mtimeMs: stats.mtimeMs,
      sha256: crypto.createHash('sha256').update(fs.readFileSync(zipPath)).digest('hex')
    };
  } catch (_) {
    return null;
  }
}

function feedbackZipSignatureMatches(zipPath, expectedSignature) {
  if (!expectedSignature) {
    return true;
  }
  const currentSignature = getFeedbackZipSignature(zipPath);
  return Boolean(
    currentSignature
    && currentSignature.size === expectedSignature.size
    && currentSignature.mtimeMs === expectedSignature.mtimeMs
    && currentSignature.sha256 === expectedSignature.sha256
  );
}

function cleanupManagedFeedbackZip(zipPath, reason = 'cleanup', options = {}) {
  if (!isManagedFeedbackZipPath(zipPath)) {
    return;
  }

  const expectedSignature = options.expectedSignature || null;
  if (options.requireSignature && !expectedSignature) {
    console.warn(`跳过反馈临时zip清理 (${reason}): 缺少文件签名`, zipPath);
    return;
  }
  const retries = Number.isInteger(options.retries)
    ? options.retries
    : (expectedSignature ? 3 : 0);

  const attempt = (remaining) => {
    try {
      if (fs.existsSync(zipPath)) {
        if (!feedbackZipSignatureMatches(zipPath, expectedSignature)) {
          console.warn(`跳过反馈临时zip清理 (${reason}): 文件已被新的日志包替换`, zipPath);
          return;
        }
        fs.unlinkSync(zipPath);
        console.log(`已清理反馈临时zip文件 (${reason}):`, zipPath);
      }
    } catch (cleanupErr) {
      if (remaining > 0) {
        setTimeout(() => attempt(remaining - 1), 250);
        return;
      }
      console.warn('清理反馈临时zip文件失败（不影响上传结果）:', cleanupErr.message);
    }
  };

  attempt(retries);
}

function cleanupLegacyFeedbackZipFiles(tempDir) {
  try {
    for (const entry of fs.readdirSync(tempDir, { withFileTypes: true })) {
      if (!entry.isFile() || !/^logs-\d+\.zip$/i.test(entry.name)) {
        continue;
      }
      cleanupManagedFeedbackZip(path.join(tempDir, entry.name), 'stale', { retries: 0 });
    }
  } catch (error) {
    console.warn('清理旧反馈临时zip文件失败:', error.message);
  }
}

async function zipLogsDirectory() {
  const logDirs = await getLogDirectoryCandidates();
  const existingLogDirs = logDirs.filter(dir => {
    try {
      return fs.existsSync(dir) && fs.statSync(dir).isDirectory();
    } catch (_) {
      return false;
    }
  });

  const discoveredFiles = [];
  existingLogDirs.forEach((logsDir, sourceIndex) => {
    discoveredFiles.push(...collectLogFilesFromDirectory(logsDir, sourceIndex));
  });

  const selectedFiles = selectLogFiles(discoveredFiles);
  const electronFiles = getElectronLogFiles();
  const tempDir = ensureFeedbackTempDir();
  const zipPath = path.join(tempDir, 'logs.zip');
  const packageId = createFeedbackPackageId();

  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      fn(value);
    };

    const output = fs.createWriteStream(zipPath);
    const archive = archiver('zip', {
      zlib: { level: 9 }
    });

    output.on('close', () => {
      console.log(`日志已打包完成: ${zipPath} (${archive.pointer()} bytes)`);
      finish(resolve, {
        zipPath,
        hasLogs: selectedFiles.length > 0,
        logCount: selectedFiles.length,
        logDirs,
        existingLogDirs
      });
    });
    output.on('error', (err) => finish(reject, err));
    archive.on('warning', (err) => {
      console.warn('日志打包警告:', err.message);
    });
    archive.on('error', (err) => finish(reject, err));

    archive.pipe(output);

    selectedFiles.forEach((entry) => {
      try {
        archive.append(readFileTail(entry), { name: buildLogZipName(entry, existingLogDirs.length) });
        console.log(`加入日志文件尾部: ${entry.filePath} (${entry.bytesToInclude}/${entry.originalSize} bytes)`);
      } catch (error) {
        console.warn(`读取日志文件尾部失败: ${entry.filePath}`, error.message);
      }
    });

    electronFiles.forEach((entry) => {
      try {
        archive.append(readFileTail(entry), { name: entry.zipName });
        console.log(`加入 Electron 日志尾部: ${entry.filePath} (${entry.bytesToInclude}/${entry.originalSize} bytes)`);
      } catch (error) {
        console.warn(`读取 Electron 日志尾部失败: ${entry.filePath}`, error.message);
      }
    });

    archive.append(
      buildLogPackageManifest({ packageId, logDirs, selectedFiles, electronFiles }),
      { name: 'diagnostics/log-package.txt' }
    );

    archive.finalize();
  });
}

// 查找最新的日志文件（按日期），返回最多maxCount个
function findLatestLogFiles(logsDir, prefix, maxCount = 3) {
  try {
    const files = fs.readdirSync(logsDir);
    const pattern = new RegExp(`^${prefix}_\\d{8}\\.log$`);
    const matchingFiles = files
      .filter(file => pattern.test(file))
      .map(file => {
        const filePath = path.join(logsDir, file);
        const stats = fs.statSync(filePath);
        return {
          name: file,
          path: filePath,
          mtime: stats.mtime
        };
      })
      .sort((a, b) => b.mtime - a.mtime); // 按修改时间降序排序

    return matchingFiles.slice(0, maxCount);
  } catch (error) {
    console.warn(`查找日志文件失败 (${prefix}):`, error.message);
    return [];
  }
}

// 查找所有error日志文件
function findAllErrorLogFiles(logsDir) {
  try {
    const files = fs.readdirSync(logsDir);
    // 匹配所有 *_error.log 文件
    const pattern = /^.+_error\.log$/;
    const matchingFiles = files
      .filter(file => pattern.test(file))
      .map(file => {
        const filePath = path.join(logsDir, file);
        return {
          name: file,
          path: filePath
        };
      });

    return matchingFiles;
  } catch (error) {
    console.warn('查找error日志文件失败:', error.message);
    return [];
  }
}

// 上传日志zip文件和反馈内容到log_store_server
// 回退模式：如果zipPath为null，只上传反馈内容，不上传日志
function uploadLogsAndFeedback(zipPath, feedback) {
  return new Promise((resolve, reject) => {
    // 从core_config.txt读取服务器地址
    const serverUrl = getLogStoreServerUrl();
    const uploadUrl = new URL(buildBackendApiUrl('api/upload_log', serverUrl));
    
    // 创建FormData
    const form = new FormData();
    
    // 添加反馈内容
    const description = feedback || '用户反馈';
    form.append('description', description);
    
    // 回退模式：如果zipPath为null或文件不存在，只上传反馈内容
    let hasLogFile = false;
    let zipStream = null;
    let zipSignature = null;
    if (zipPath && fs.existsSync(zipPath)) {
      // 添加文件
      zipSignature = getFeedbackZipSignature(zipPath);
      zipStream = fs.createReadStream(zipPath);
      form.append('log_zip', zipStream, {
        filename: path.basename(zipPath),
        contentType: 'application/zip'
      });
      hasLogFile = true;
      console.log('将上传日志文件:', zipPath);
    } else {
      console.warn('日志文件不可用，只上传反馈内容');
    }
    
    // 获取文件信息用于日志（仅当有日志文件时）
    if (hasLogFile) {
      const fileStats = fs.statSync(zipPath);
      console.log('日志文件大小:', fileStats.size, 'bytes');
    }
    
    // 解析URL
    let port = uploadUrl.port;
    if (!port) {
      port = uploadUrl.protocol === 'https:' ? 443 : 80;
    } else {
      port = parseInt(port, 10);
    }
    
    const options = {
      hostname: uploadUrl.hostname,
      port: port,
      path: uploadUrl.pathname,
      method: 'POST',
      headers: form.getHeaders()
    };
    
    // 打印请求信息
    console.log('上传日志请求:', uploadUrl.toString());
    
    // 选择http或https
    const httpModule = uploadUrl.protocol === 'https:' ? require('node:https') : http;
    
    // 发送请求
    const req = httpModule.request(options, (res) => {
      let responseData = '';
      
      res.on('data', (chunk) => {
        responseData += chunk;
      });
      
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            const result = JSON.parse(responseData);
            console.log('上传成功:', result);
            cleanupManagedFeedbackZip(zipPath, 'upload-success', { expectedSignature: zipSignature, requireSignature: true });
            
            resolve(result);
          } catch (err) {
            cleanupManagedFeedbackZip(zipPath, 'response-parse-failed', { expectedSignature: zipSignature, requireSignature: true });
            reject(new Error(`解析响应失败: ${err.message}`));
          }
        } else {
          cleanupManagedFeedbackZip(zipPath, `upload-http-${res.statusCode}`, { expectedSignature: zipSignature, requireSignature: true });
          reject(new Error(`上传失败: HTTP ${res.statusCode} - ${responseData}`));
        }
      });
    });
    
    req.on('error', (err) => {
      if (zipStream) {
        try {
          zipStream.destroy();
        } catch (_) {
          // ignored
        }
      }
      cleanupManagedFeedbackZip(zipPath, 'upload-error', { expectedSignature: zipSignature, requireSignature: true });
      reject(new Error(`上传请求失败: ${err.message}`));
    });
    
    // 发送FormData
    form.pipe(req);
  });
}

// 创建反馈窗口
function createFeedbackWindow() {
  // 初始化语言
  initializeLanguage();
  
  // 如果窗口已存在，先关闭
  if (feedbackWindow && !feedbackWindow.isDestroyed()) {
    feedbackWindow.close();
  }

  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  const windowWidth = 500;
  const windowHeight = 500;

  feedbackWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    x: Math.floor((width - windowWidth) / 2),
    y: Math.floor((height - windowHeight) / 2),
    frame: true,
    resizable: false,
    icon: getIcon(),
    title: t('windowTitle'),
    webPreferences: {
      preload: path.join(__dirname, 'preload-feedback.js'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      sandbox: false // preload-feedback.js 仅依赖 electron 内置模块，sandbox:false 以兼容 contextBridge 全量 API
    }
  });
  // 标记为"设置类"窗口（main.js 的 getWindowZRank 据此归入 rank 4）
  feedbackWindow._nekoKind = 'settings';

  feedbackWindow.loadURL(getFeedbackDataURL());
  feedbackWindow.show();
}

function getFeedbackHTML() {
  const lang = currentLanguage === 'zh-CN' ? 'zh-CN' : 'en';
  return `
<!DOCTYPE html>
<html lang="${lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${t('title')}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            width: 100%;
            height: 100vh;
            display: flex;
            flex-direction: column;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: #f5f5f5;
        }
        .container {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        h2 {
            margin-bottom: 15px;
            color: #333;
            font-size: 18px;
        }
        .feedback-label {
            margin-bottom: 8px;
            color: #666;
            font-size: 14px;
        }
        input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            font-family: inherit;
            margin-bottom: 15px;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #4a90e2;
        }
        textarea {
            flex: 1;
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            font-family: inherit;
            resize: none;
            margin-bottom: 15px;
            min-height: 150px;
        }
        textarea:focus {
            outline: none;
            border-color: #4a90e2;
        }
        .button-container {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }
        button {
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            font-size: 14px;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        .submit-btn {
            background-color: #4a90e2;
            color: white;
        }
        .submit-btn:hover {
            background-color: #357abd;
        }
        .submit-btn:active {
            background-color: #2a5f8f;
        }
        .cancel-btn {
            background-color: #e0e0e0;
            color: #333;
        }
        .cancel-btn:hover {
            background-color: #d0d0d0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>${t('title')}</h2>
        <label class="feedback-label" for="contact-input">${t('contactLabel')}</label>
        <input type="text" id="contact-input" placeholder="${t('contactPlaceholder')}">
        <label class="feedback-label" for="feedback-input">${t('feedbackLabel')}</label>
        <textarea id="feedback-input" placeholder="${t('feedbackPlaceholder')}"></textarea>
        <div class="button-container">
            <button class="cancel-btn" onclick="handleCancel()">${t('cancel')}</button>
            <button class="submit-btn" onclick="handleSubmit()">${t('submit')}</button>
        </div>
    </div>
    <script>
        // contextIsolation:true 下页面无法 require('electron')，改用 preload 注入的 nekoFeedback 桥
        const ipcRenderer = window.nekoFeedback;
        
        // 本地化文本（从主进程传入）
        const i18n = {
            emptyFeedback: ${JSON.stringify(t('emptyFeedback'))},
            contactPrefix: ${JSON.stringify(t('contactPrefix'))},
            feedbackPrefix: ${JSON.stringify(t('feedbackPrefix'))},
            packingLogs: ${JSON.stringify(t('packingLogs'))},
            uploading: ${JSON.stringify(t('uploading'))},
            successWithLogs: ${JSON.stringify(t('successWithLogs'))},
            successNoLogs: ${JSON.stringify(t('successNoLogs'))},
            packFailed: ${JSON.stringify(t('packFailed'))},
            uploadFailed: ${JSON.stringify(t('uploadFailed'))},
            operationFailed: ${JSON.stringify(t('operationFailed'))}
        };
        
        async function handleSubmit() {
            const contact = document.getElementById('contact-input').value.trim();
            const feedback = document.getElementById('feedback-input').value.trim();
            
            if (!feedback) {
                alert(i18n.emptyFeedback);
                return;
            }
            
            // 组合联系方式和反馈内容
            let combinedFeedback = '';
            if (contact) {
                combinedFeedback = i18n.contactPrefix + contact + '\\n' + i18n.feedbackPrefix + feedback;
            } else {
                combinedFeedback = i18n.feedbackPrefix + feedback;
            }
            
            // 显示打包中提示
            const submitBtn = document.querySelector('.submit-btn');
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            let operationSucceeded = false;
            
            try {
                // 第一步：打包logs目录
                submitBtn.textContent = i18n.packingLogs;
                const zipResult = await ipcRenderer.zipLogs();
                const zipPath = zipResult.zipPath;
                const hasLogs = !!zipResult.hasLogs;
                
                if (hasLogs) {
                    console.log('Log packing completed:', zipPath, 'logCount:', zipResult.logCount);
                } else {
                    console.log('No Python logs found; uploading diagnostic package:', zipPath);
                }
                
                // 第二步：上传日志和反馈
                submitBtn.textContent = i18n.uploading;
                await ipcRenderer.invoke('upload-logs-and-feedback', zipPath, combinedFeedback);
                console.log('Feedback content:', combinedFeedback);
                
                if (hasLogs) {
                    alert(i18n.successWithLogs);
                } else {
                    alert(i18n.successNoLogs);
                }
                operationSucceeded = true;
            } catch (error) {
                console.error('Operation failed:', error);
                const errorMsg = error.message || 'Unknown error';
                if (errorMsg.includes('打包') || errorMsg.includes('pack')) {
                    alert(i18n.packFailed.replace('{{error}}', errorMsg));
                } else if (errorMsg.includes('上传') || errorMsg.includes('upload')) {
                    alert(i18n.uploadFailed.replace('{{error}}', errorMsg));
                } else {
                    alert(i18n.operationFailed.replace('{{error}}', errorMsg));
                }
            } finally {
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
                // 成功后关闭窗口；失败时保留窗口，方便用户调整后重试。
                if (operationSucceeded) {
                    ipcRenderer.closeWindow();
                }
            }
        }
        
        function handleCancel() {
            ipcRenderer.closeWindow();
        }
    </script>
</body>
</html>
  `;
}

function getFeedbackDataURL() {
  return `data:text/html;charset=utf-8,${encodeURIComponent(getFeedbackHTML())}`;
}

// 初始化 IPC 处理器
function initFeedbackIPC(options = {}) {
  configureFeedback(options);

  ipcMain.on('close-feedback-window', (event) => {
    if (!isTrustedSender(event)) return;
    if (feedbackWindow && !feedbackWindow.isDestroyed()) {
      feedbackWindow.close();
      feedbackWindow = null;
    }
  });
  
  // 处理打包logs目录的请求
  ipcMain.handle('zip-logs', async (event) => {
    if (!isTrustedSender(event)) {
      throw new Error('非法的调用来源');
    }
    try {
      const zipResult = await zipLogsDirectory();
      return { success: true, ...zipResult };
    } catch (error) {
      console.error('打包logs目录失败:', error);
      throw error;
    }
  });
  
  // 处理上传日志和反馈的请求
  ipcMain.handle('upload-logs-and-feedback', async (event, zipPath, feedback) => {
    if (!isTrustedSender(event)) {
      throw new Error('非法的调用来源');
    }
    // 安全：zipPath 来自渲染进程，只允许上传受管临时目录内的反馈包，防止任意文件上传
    if (!isManagedFeedbackZipPath(zipPath)) {
      console.warn('拒绝上传非法反馈zip路径:', zipPath);
      throw new Error('非法的反馈包路径');
    }
    try {
      const result = await uploadLogsAndFeedback(zipPath, feedback);
      return { success: true, result };
    } catch (error) {
      console.error('上传日志和反馈失败:', error);
      throw error;
    }
  });
}

module.exports = {
  createFeedbackWindow,
  initFeedbackIPC,
  configureFeedback
};
