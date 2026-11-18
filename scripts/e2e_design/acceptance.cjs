const assert = require('node:assert/strict');
const {basename} = require('node:path');
const {chromium} = require(process.env.E2E_PLAYWRIGHT || 'playwright');

const [origin, file, quote, correction] = process.argv.slice(2);

async function exercise(page) {
  const button = name => page.getByRole('button', {name, exact: true});
  const visible = (text, scope = page) => scope.getByText(text, {exact: true}).first().waitFor();
  const saved = page.getByText(/^Saved revision /);
  const filename = basename(file);

  // The request context shares the browser cookie jar. Product actions below use the UI.
  for (const [endpoint, data] of [
    ['auth/register', {name: 'Parking operator', email: 'parking@example.test', password: 'local-fixture-account'}],
    ['projects', {name: 'Parking operations'}],
  ]) {
    const response = await page.request.post(origin + '/api/' + endpoint, {data});
    assert.ok(response.ok(), endpoint + ': ' + await response.text());
  }
  await page.goto(origin);
  await button('Add files').click();
  await page.locator('input[type=file]').setInputFiles(file);
  await button('Upload to project').click();
  await visible('Uploaded ' + filename);
  await button(filename).click();
  await button('Done').click();
  await button('Design system').click();
  await button('View design').click();
  const original = await saved.innerText();
  await page.getByRole('tab', {name: 'Volatility', exact: true}).click();
  await button('Tariff policy').click();
  await button('View source 1').click();
  const evidence = page.getByRole('dialog', {name: 'Source evidence'});
  await visible(filename, evidence);
  await visible('Cited excerpt', evidence);
  await visible(quote, evidence);
  console.log('Opened upload citation:', filename, JSON.stringify(quote));
  await button('Close source').click();
  await button('Close design').click();

  await page.getByRole('dialog', {name: 'System design'}).waitFor({state: 'hidden'});
  const editor = page.locator('[contenteditable=true]');
  await editor.click();
  await editor.fill(correction);
  await button('Send').click();
  await visible('Apply this as a correction to revise the tariff.');
  await button('View design').click();
  assert.equal(await saved.innerText(), original, 'Chat alone changed the published revision');
  await button('Close design').click();
  await button('Apply as correction').click();
  await button('View design').click();
  await visible('Revision changes');
  await visible('Changed · Tariff policy');
  await page.getByText(/^Updated /).filter({hasText: correction}).first().waitFor();
  const revised = await saved.innerText();
  assert.notEqual(revised, original);
  await button('Inspect previous revision').click();
  await visible(original.replace(/^Saved revision /, ''));
  console.log('Applied correction and inspected tariff diff:', original, '→', revised);

  await page.reload();
  await button('View design').click();
  assert.equal(await saved.innerText(), revised);
  await visible('Changed · Tariff policy');
  console.log('Reload restored the corrected revision and tariff diff.');
}

async function main() {
  const browser = await chromium.launch({executablePath: process.env.E2E_BROWSER});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    page.setDefaultTimeout(45000);
    page.on('pageerror', error => console.error('Browser error:', error.message));
    page.on('response', response => {
      const path = new URL(response.url()).pathname;
      if (path.startsWith('/api/') && !response.ok()) console.error('API request failed:', path, response.status());
    });
    try {
      await exercise(page);
    } catch (error) {
      console.error('Visible workspace at failure:', await page.locator('body').innerText({timeout: 2000}).catch(() => 'unavailable'));
      throw error;
    }
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
