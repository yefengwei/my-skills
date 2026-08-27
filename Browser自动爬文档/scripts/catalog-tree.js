/**
 * catalog-tree.js — 仅拉取并打印 codefather.cn 课程目录树（不抓取内容），用于：
 *   - 确认课程 ID 正确、目录层级、含哪些子章节
 *   - 确认要排除的章节名（如“已废弃”），便于传给 fetch-course.js 的 --exclude
 *
 * 用法：
 *   node catalog-tree.js --course-id <ID> [--chrome-port 9222]
 *
 * 依赖：playwright-core
 */
const { chromium } = require('playwright-core');
const https = require('https');
const fs = require('fs');

function parseArgs(argv) {
  const a = { courseId: '', chromePort: 9222 };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--course-id') a.courseId = argv[++i];
    else if (argv[i] === '--chrome-port') a.chromePort = argv[++i];
  }
  return a;
}
const ARGS = parseArgs(process.argv.slice(2));
const CDP_URL = `http://127.0.0.1:${ARGS.chromePort}`;
const COURSE_ID = ARGS.courseId;

if (!COURSE_ID) {
  console.error('用法: node catalog-tree.js --course-id <ID>');
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
  const ctx = browser.contexts()[0];
  const cookies = await ctx.cookies('https://www.codefather.cn');
  await browser.close();
  return cookies.map((c) => `${c.name}=${c.value}`).join('; ');
}

function printTree(items, indent = 0) {
  for (const item of items) {
    console.log(
      '  '.repeat(indent) +
        `[${item.catalogType}] ${item.title} (id=${item.id}, articleId=${item.courseArticleId || '-'})` +
        (item.relatedLink ? ` link=${item.relatedLink}` : '')
    );
    if (Array.isArray(item.children) && item.children.length) printTree(item.children, indent + 1);
  }
}

async function main() {
  const cookieStr = await getCookies();
  const url = `https://api.codefather.cn/api/course_catalog/list/page/vo/course?courseId=${COURSE_ID}`;
  const r = await fetchUrl(url, {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    Cookie: cookieStr,
    Accept: 'application/json',
    Referer: 'https://www.codefather.cn/',
  });
  if (r.status !== 200) {
    console.log('catalog status', r.status);
    console.log(r.body.slice(0, 500));
    return;
  }
  const data = JSON.parse(r.body).data || [];
  fs.writeFileSync(__dirname + '/catalog.json', JSON.stringify(data, null, 2), 'utf8');
  console.log('目录总数:', data.length, '（已保存 catalog.json）');
  printTree(data);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
