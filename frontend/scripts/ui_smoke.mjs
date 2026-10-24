/**
 * UI 冒烟：本机 Edge 无头模式，覆盖 2.3 需求全部页面与两条演示链路。
 * 用法：node scripts/ui_smoke.mjs
 */
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const BASE = 'http://127.0.0.1:8000'
const OUT = 'shots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

fs.mkdirSync(OUT, { recursive: true })

const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--window-size=1560,980'],
  defaultViewport: { width: 1560, height: 980, deviceScaleFactor: 1 }
})

const page = await browser.newPage()
const errors = []
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(m.text())
})
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))

/** 按文本点按钮 */
async function clickText(text) {
  const ok = await page.evaluate((t) => {
    const btns = [...document.querySelectorAll('button')]
    const target = btns.find((b) => b.textContent.replace(/\s+/g, '').includes(t))
    if (!target) return false
    target.click()
    return true
  }, text)
  if (!ok) throw new Error(`按钮未找到：${text}`)
}

const result = {}

// 1) 登录
await page.goto(`${BASE}/#/login`, { waitUntil: 'networkidle2' })
await page.screenshot({ path: `${OUT}/01-login.png` })

// 2) 登录后默认落地风险检查页
await clickText('登录')
await page.waitForSelector('.submit', { timeout: 20000 })
await sleep(600)
await page.screenshot({ path: `${OUT}/02-check-empty.png` })

// 3) 风险检查：U1001 + O2001
await clickText('发起风险检查')
await page.waitForSelector('.rsc', { timeout: 60000 })
await sleep(700)
await page.screenshot({ path: `${OUT}/03-check-result.png` })
result.check = await page.evaluate(() => ({
  score: document.querySelector('.ring-label .num')?.textContent || '',
  case: document.querySelector('.case-banner')?.textContent?.trim() || '',
  hits: document.querySelectorAll('.hits li').length
}))

// 4) 对话工作台：第一条链路
await page.goto(`${BASE}/#/workbench`, { waitUntil: 'networkidle2' })
await sleep(500)
await page.type('textarea', '支付环节做一次风控检查：用户 U1001，订单 O2001')
await page.keyboard.press('Enter')
await page.waitForSelector('.tool', { timeout: 120000 })
await page.waitForFunction(() => !document.querySelector('.thinking'), { timeout: 120000 })
await sleep(800)
await page.screenshot({ path: `${OUT}/04-chat-risk-check.png` })

// 5) 停用 R05 → 重查（模型先复述等确认，再确认执行）
await page.type('textarea', 'R05 这条规则先停掉，然后把刚才那个订单重新查一遍，告诉我分数变化')
await page.keyboard.press('Enter')
await page.waitForFunction(
  () => !document.querySelector('.thinking') && document.querySelectorAll('.assistant .bubble').length > 1,
  { timeout: 150000 }
)
await sleep(400)
await page.type('textarea', '确认停用 R05，并重查刚才那个订单')
await page.keyboard.press('Enter')
await page.waitForFunction(() => !document.querySelector('.thinking'), { timeout: 150000 })
await sleep(1000)
await page.screenshot({ path: `${OUT}/05-chat-rule-toggle.png` })
result.chatScores = await page.evaluate(() =>
  [...document.querySelectorAll('.cards-body .ring-label .num')].map((e) => e.textContent)
)

// 6) 规则管理（命中次数）
await page.goto(`${BASE}/#/rules`, { waitUntil: 'networkidle2' })
await sleep(1000)
await page.screenshot({ path: `${OUT}/06-rules.png` })
result.ruleHitColumn = await page.evaluate(() =>
  [...document.querySelectorAll('.hit-count')].slice(0, 6).map((e) => e.textContent.trim())
)

// 7) 案件管理 → 详情抽屉（特征快照）
await page.goto(`${BASE}/#/cases`, { waitUntil: 'networkidle2' })
await page.waitForSelector('.el-table__row', { timeout: 15000 })
await sleep(600)
await page.screenshot({ path: `${OUT}/07-cases.png` })
await clickText('详情')
await page.waitForSelector('.el-drawer__body .feat-groups', { timeout: 15000 })
await sleep(700)
await page.screenshot({ path: `${OUT}/08-case-detail.png` })
result.caseSnapshot = await page.evaluate(() => document.querySelectorAll('.fg-item').length)

// 8) 黑名单批量导入
await page.goto(`${BASE}/#/blacklist`, { waitUntil: 'networkidle2' })
await sleep(800)
await clickText('批量导入')
await page.waitForSelector('.import-wrap textarea', { timeout: 10000 })
await page.type('.import-wrap textarea', 'address,ADDR-DEMO-9,UI 冒烟导入\nip,45.32.99.99,冒烟测试\nip,45.32.99.99,重复行')
await sleep(300)
await page.screenshot({ path: `${OUT}/09-blacklist-import.png` })
await clickText('开始导入')
await page.waitForSelector('.import-result', { timeout: 15000 })
await sleep(600)
await page.screenshot({ path: `${OUT}/10-blacklist-import-result.png` })
result.importResult = await page.evaluate(() => document.querySelector('.ir-row')?.textContent?.replace(/\s+/g, ' ').trim())

// 9) 画像与看板
await page.goto(`${BASE}/#/profile`, { waitUntil: 'networkidle2' })
await sleep(1200)
await page.screenshot({ path: `${OUT}/11-profile.png` })

await page.goto(`${BASE}/#/dashboard`, { waitUntil: 'networkidle2' })
await sleep(1200)
await page.screenshot({ path: `${OUT}/12-dashboard.png` })

await browser.close()
console.log(JSON.stringify({ ...result, errors: errors.slice(0, 6) }, null, 2))
