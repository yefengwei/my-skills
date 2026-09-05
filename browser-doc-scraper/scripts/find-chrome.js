/**
 * find-chrome.js — 首次使用时从默认地址查找本机 Chrome.exe，找不到则提示需询问用户。
 *
 * 行为：
 *   1. 若已存在配置文件 scripts/.chrome-config.json（含有效 chrome 路径），直接输出并退出（不重复询问）。
 *   2. 否则按默认候选路径查找 Chrome.exe；找到则输出 { chrome, userDataDir } 并写入配置文件。
 *   3. 都找不到则输出 NOT_FOUND 并以退出码 2 结束 —— 此时调用方应询问用户 Chrome.exe 路径。
 *
 * 手动设置（在询问用户拿到路径后调用，写入配置以便后续复用）：
 *   node find-chrome.js --set "D:/path/Chrome.exe"
 *   node find-chrome.js --set "D:/path/Chrome.exe" --user-data-dir "D:/path/Data"
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

const CONFIG_FILE = path.join(__dirname, '.chrome-config.json');

function exists(p) {
  try {
    return !!p && fs.existsSync(p);
  } catch (e) {
    return false;
  }
}

function defaultUserDataDir(chromePath) {
  if (!chromePath) return null;
  // 便携版：Chrome.exe 旁常有 Data / User Data 目录
  const appDir = path.dirname(chromePath); // ...\App 或 ...\Application
  const baseDir = path.dirname(appDir); // ...\Chrome
  for (const name of ['Data', 'User Data']) {
    const cand = path.join(baseDir, name);
    if (exists(cand)) return cand;
  }
  // 标准 Google Chrome 默认用户数据目录
  const std = path.join(os.homedir(), 'AppData', 'Local', 'Google', 'Chrome', 'User Data');
  if (exists(std)) return std;
  return null;
}

function searchChrome() {
  const user = os.homedir();
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\Chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\Chrome.exe',
    path.join(user, 'AppData', 'Local', 'Google', 'Chrome', 'Application', 'Chrome.exe'),
    path.join(user, 'AppData', 'Local', 'Chrome', 'Application', 'Chrome.exe'),
    path.join(user, 'AppData', 'Local', 'Chromium', 'Application', 'Chrome.exe'),
    'D:\\Softwares\\Daily\\Chrome\\App\\Chrome.exe',
    'C:\\Softwares\\Daily\\Chrome\\App\\Chrome.exe',
  ];
  for (const c of candidates) if (exists(c)) return c;
  return null;
}

function readConfig() {
  try {
    const cfg = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
    if (cfg && typeof cfg.chrome === 'string' && exists(cfg.chrome)) return cfg;
  } catch (e) {}
  return null;
}

function saveConfig(cfg) {
  try {
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2), 'utf8');
  } catch (e) {}
}

function printResult(cfg) {
  console.log(JSON.stringify(cfg, null, 2));
}

function main() {
  // 手动设置模式
  const setIdx = process.argv.indexOf('--set');
  if (setIdx >= 0) {
    const chrome = process.argv[setIdx + 1];
    if (!chrome) {
      console.error('用法: node find-chrome.js --set "<Chrome.exe路径>" [--user-data-dir "<数据目录>"]');
      process.exit(1);
    }
    if (!exists(chrome)) {
      console.error('NOT_FOUND: 指定路径不存在 -> ' + chrome);
      process.exit(2);
    }
    const udIdx = process.argv.indexOf('--user-data-dir');
    const userDataDir = udIdx >= 0 ? process.argv[udIdx + 1] : defaultUserDataDir(chrome);
    const cfg = { chrome, userDataDir: userDataDir || null };
    saveConfig(cfg);
    console.log('已保存配置:');
    printResult(cfg);
    process.exit(0);
  }

  // 1) 已有配置且有效
  const cached = readConfig();
  if (cached) {
    printResult(cached);
    process.exit(0);
  }

  // 2) 默认地址查找
  const found = searchChrome();
  if (found) {
    const cfg = { chrome: found, userDataDir: defaultUserDataDir(found) };
    saveConfig(cfg);
    printResult(cfg);
    process.exit(0);
  }

  // 3) 找不到
  console.log('NOT_FOUND');
  process.exit(2);
}

main();
