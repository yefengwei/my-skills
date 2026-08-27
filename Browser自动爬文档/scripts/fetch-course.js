/**
 * fetch-course.js — 复用已登录的 Chrome 会话，批量抓取 codefather.cn 课程文档为本地 Markdown。
 *
 * 原理（已验证最优、绕过反爬）：
 *   1. 通过 CDP 连接本机已登录的 Chrome（debugging port），读取 cookie。
 *   2. 调用内部 API `api.codefather.cn/api/course_catalog/list/page/vo/course` 拿到完整目录树。
 *   3. 对每个文章项，在真实浏览器里打开 section 页，监听 XHR 响应
 *      `api.codefather.cn/api/course_article/get/vo/safe`，直接取回原始 Markdown（content 字段）。
 *      —— 不解析 DOM，因此无需对抗 DevTools 检测的 about:blank 跳转。
 *   4. 按标题/父级归类到子目录，清洗零宽字符与 base64 内嵌图，落盘为 .md。
 *
 * 用法：
 *   node fetch-course.js --course-id <ID> --target-dir <DIR> [--exclude "已废弃"] [--chrome-port 9222]
 *
 * 依赖：playwright-core（npm i playwright-core），以及本机 Chrome 已开启远程调试（见 references/workflow.md）。
 */
const { chromium } = require('playwright-core');
const https = require('https');
const fs = require('fs');
const path = require('path');

function parseArgs(argv) {
  const a = { courseId: '', targetDir: '', exclude: '已废弃', chromePort: 9222 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--course-id') a.courseId = argv[++i];
    else if (k === '--target-dir') a.targetDir = argv[++i];
    else if (k === '--exclude') a.exclude = argv[++i];
    else if (k === '--chrome-port') a.chromePort = argv[++i];
  }
  return a;
}

const ARGS = parseArgs(process.argv.slice(2));
const CDP_URL = `http://127.0.0.1:${ARGS.chromePort}`;
const COURSE_ID = ARGS.courseId;
const EXCLUDE_CHAPTER = ARGS.exclude;
// Windows 不允许目录名含 |，统一替换为全角 ｜
const TARGET_DIR = ARGS.targetDir.replace(/\|/g, '｜');

if (!COURSE_ID || !ARGS.targetDir) {
  console.error('用法: node fetch-course.js --course-id <ID> --target-dir <DIR> [--exclude "已废弃"]');
  process.exit(1);
}

function fetchUrl(url, headers = {}) {
  return new Promise((resolve) => {
    const client = url.startsWith('https:') ? https : require('http');
    const req = client.get(url, { headers }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        fetchUrl(res.headers.location, headers).then(resolve);
        return;
      }
      let body = '';
      res.on('data', (c) => (body += c));
      res.on('end', () => resolve({ status: res.statusCode, body }));
    });
    req.on('error', () => resolve({ status: 0, body: '' }));
    req.setTimeout(60000, () => req.destroy());
  });
}

async function getCookies() {
  const browser = await chromium.connectOverCDP(CDP_URL);
  let ctx = browser.contexts()[0];
  let cookies;
  if (ctx) {
    cookies = await ctx.cookies('https://www.codefather.cn');
  }
  // 若没有可用上下文或 cookie 为空，先访问站点触发登录态写入
  if (!cookies || cookies.length === 0) {
    if (!ctx) ctx = await browser.newContext();
    const page = await ctx.newPage();
    try {
      await page.goto('https://www.codefather.cn', { waitUntil: 'domcontentloaded', timeout: 20000 });
      await page.waitForTimeout(3000);
    } catch (e) {}
    cookies = await ctx.cookies('https://www.codefather.cn');
    await page.close();
  }
  await browser.close();
  return cookies.map((c) => `${c.name}=${c.value}`).join('; ');
}

async function getCatalog(cookieStr) {
  const url = `https://api.codefather.cn/api/course_catalog/list/page/vo/course?courseId=${COURSE_ID}`;
  const r = await fetchUrl(url, {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    Cookie: cookieStr,
    Accept: 'application/json',
    Referer: 'https://www.codefather.cn/',
  });
  if (r.status !== 200) throw new Error('catalog status ' + r.status);
  return JSON.parse(r.body).data || [];
}

function flattenCatalog(items, result = []) {
  for (const item of items) {
    result.push(item);
    if (Array.isArray(item.children)) flattenCatalog(item.children, result);
  }
  return result;
}

async function fetchArticleBySection(articleId) {
  const browser = await chromium.connectOverCDP(CDP_URL);
  const ctx = browser.contexts()[0] || (await browser.newContext());
  const page = await ctx.newPage();
  let captured = null;
  let lastError = null;
  page.on('response', async (resp) => {
    const u = resp.url();
    if (u.includes('api.codefather.cn/api/course_article/get/vo/safe')) {
      try {
        const body = await resp.text();
        lastError = body.slice(0, 200);
        const parsed = JSON.parse(body);
        if (parsed.data && String(parsed.data.id) === String(articleId)) captured = parsed.data;
      } catch (e) {}
    }
  });
  const url = `https://www.codefather.cn/course/${COURSE_ID}/section/${articleId}`;
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(5000);
  } catch (e) {
    console.log('  goto warn:', e.message);
  }
  await page.close();
  await browser.close();
  return { captured, lastError };
}

// 按标题关键词与父级归类到子目录；可按需修改此函数适配不同课程结构
function classifyFolder(title, parentTitle = '') {
  const t = title.replace(/\s+/g, '');
  const pt = (parentTitle || '').replace(/\s+/g, '');
  if (pt.includes('文字教程')) return '文字教程';
  if (t.includes('介绍')) return '项目介绍';
  if (t.includes('大纲')) return '项目大纲';
  if (t.includes('源码') || t.includes('部署运行') || t.includes('代码版') || pt.includes('源码')) return '项目源码';
  if (t.includes('简历')) return '简历写法';
  if (t.includes('面试')) return '项目面试题';
  if (t.includes('面经')) return '项目真实面经';
  if (t.includes('答疑') || t.includes('问答')) return '问题答疑';
  return '其他资料';
}

function sanitize(s) {
  return s.replace(/[\\/:*?"<>|]/g, '_').trim();
}
function cleanMarkdown(md) {
  return md
    .replace(/[\u200B-\u200D\uFEFF]/g, '') // 去除零宽字符/水印
    .replace(/!\[.*?\]\(data:image\/[^)]+\)/g, ''); // 去除 base64 内嵌图
}

async function main() {
  const cookieStr = await getCookies();
  const catalog = await getCatalog(cookieStr);
  const allItems = flattenCatalog(catalog);
  console.log('目录项总数:', allItems.length);

  function isUnderExcluded(item) {
    if (item.title.includes(EXCLUDE_CHAPTER)) return true;
    let p = item;
    while (p && p.parentId && p.parentId !== '0') {
      const parent = allItems.find((i) => i.id === p.parentId);
      if (!parent) break;
      if (parent.title.includes(EXCLUDE_CHAPTER)) return true;
      p = parent;
    }
    return false;
  }

  const toFetch = allItems.filter(
    (item) => !isUnderExcluded(item) && item.catalogType !== 'chapter'
  );
  console.log('待抓取项:', toFetch.length);

  let ok = 0;
  let fail = 0;
  for (const item of toFetch) {
    const title = item.title.trim();
    const articleId = item.courseArticleId;
    const type = item.catalogType;
    const parent = allItems.find((i) => i.id === item.parentId);
    const parentTitle = parent ? parent.title : '';
    const folder = classifyFolder(title, parentTitle);
    const dir = path.join(TARGET_DIR, folder);
    fs.mkdirSync(dir, { recursive: true });

    // 外部链接项（relatedLink 且无 articleId）：保存跳转链接
    if (type === 'relatedLink' && !articleId) {
      const link = item.relatedLink || '';
      const filename = sanitize(title) + '(程序员鱼皮).md';
      const fpath = path.join(dir, filename);
      fs.writeFileSync(
        fpath,
        '# ' + title + '\n\n> 外部链接，请点击下方地址访问。\n\n' + link + '\n',
        'utf8'
      );
      console.log('✓ 链接:', fpath, '->', link);
      ok++;
      continue;
    }
    if (!articleId) {
      console.log('✗ 跳过（无 articleId）:', title);
      fail++;
      continue;
    }

    console.log('\n抓取:', title, '->', folder);
    const { captured, lastError } = await fetchArticleBySection(articleId);
    if (!captured || !captured.content) {
      console.log('✗ 未获取内容:', title, lastError ? '| ' + lastError : '');
      fail++;
      continue;
    }
    const filename = sanitize(title) + '(程序员鱼皮).md';
    const fpath = path.join(dir, filename);
    const md = cleanMarkdown(captured.content);
    fs.writeFileSync(fpath, md, 'utf8');
    console.log('✓ 已保存:', fpath, '(' + md.length + ' 字符)');
    ok++;
  }
  console.log(`\n全部完成: 成功 ${ok}, 失败 ${fail}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
