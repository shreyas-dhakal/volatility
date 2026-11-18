const assert = require('node:assert/strict');
const {basename} = require('node:path');
const {chromium} = require(process.env.E2E_PLAYWRIGHT || 'playwright');

const [origin, file, quote, correction, formula] = process.argv.slice(2);

async function exercise(page) {
  const button = name => page.getByRole('button', {name, exact: true});
  const visible = (text, scope = page) => scope.getByText(text, {exact: true}).first().waitFor();
  const saved = page.getByText(/^Saved revision /);
  const filename = basename(file);

  await page.goto(origin);
  await button('Create your first project').click();
  await page.getByLabel('Project name', {exact: true}).fill('Parking operations');
  const created = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/projects' && response.request().method() === 'POST'
  );
  await button('Create project').click();
  const projectResponse = await created;
  assert.ok(projectResponse.ok(), 'project creation: ' + await projectResponse.text());
  const project = await projectResponse.json();
  const projectPath = origin + '/api/projects/' + project.id + '/design-engine';
  const token = async () => page.evaluate(() => window.Clerk.session.getToken());
  const apiGet = async path => page.request.get(origin + '/api' + path, {
    headers: {Authorization: 'Bearer ' + await token()},
  });
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
  await button('View source 1').first().click();
  const evidence = page.getByRole('dialog', {name: 'Source evidence'});
  await visible(filename, evidence);
  await visible('Cited excerpt', evidence);
  await visible(quote, evidence);
  console.log('Opened upload citation:', filename, JSON.stringify(quote));
  await button('Close source').click();
  const base = (await (await apiGet('/projects/' + project.id + '/design-engine')).json()).revision;
  const gateIds = snapshot => [
    ...snapshot.volatilities.filter(v => v.decision === 'Gate vendor'),
    ...snapshot.components.filter(c => c.name === 'Gate access'),
    ...snapshot.contracts.filter(c => c.name === 'Gate access contract'),
  ].map(row => row.id);
  await visible('Configure the site rate');
  await visible('Can each site choose its own charging formula, or does it only set the rate?');
  await button('Answer this question').click();
  await page.getByLabel('Your answer', {exact:true}).fill(formula);
  await button('Submit answer').click();
  await visible('The boundary changed.');
  await visible('Current approach · Encapsulate the formula in Pricing');
  await button('Inspect previous revision').click();
  await visible('Configure the site rate');
  const amended = await saved.innerText();
  assert.notEqual(amended, original);
  await page.reload();
  await button('View design').click();
  await visible('The boundary changed.');
  await visible('Recorded answer');
  await visible(formula);
  assert.equal(await saved.innerText(), amended);
  const after = (await (await apiGet('/projects/' + project.id + '/design-engine')).json()).revision;
  assert.equal(after.parent_revision_id, base.id);
  assert.equal(after.snapshot.volatilities[0].answers[0].question_id,base.snapshot.questions[0].id);
  assert.deepEqual(gateIds(base.snapshot),gateIds(after.snapshot));
  assert.deepEqual(await (await apiGet('/projects/' + project.id + '/design-engine/revisions/' + base.id)).json(),base);
  console.log('Answered the formula question, reloaded its decision diff and verified gate IDs.');
  await button('Close design').click();

  await page.getByRole('dialog', {name: 'System design'}).waitFor({state: 'hidden'});
  const editor = page.locator('[contenteditable=true]');
  await editor.click();
  await editor.fill(correction);
  await button('Send').click();
  await visible('Apply this as a correction to revise the tariff.');
  await button('View design').click();
  assert.equal(await saved.innerText(), amended, 'Chat alone changed the published revision');
  await button('Close design').click();
  await button('Apply as correction').last().click();
  await button('View design').click();
  await page.getByRole('tab', {name: 'Overview', exact: true}).click();
  await visible('Revision changes');
  await visible('Changed · Tariff policy');
  await page.getByText(/^Updated /).filter({hasText: correction}).first().waitFor();
  const revised = await saved.innerText();
  assert.notEqual(revised, original);
  await button('Inspect previous revision').click();
  await visible(amended.replace(/^Saved revision /, ''));
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
    if (!process.env.CLERK_E2E_STORAGE_STATE) throw new Error('Set CLERK_E2E_STORAGE_STATE to a Playwright storage-state file signed in to the configured Clerk instance.');
    const context = await browser.newContext({
      viewport: {width: 1440, height: 1000},
      storageState: process.env.CLERK_E2E_STORAGE_STATE,
    });
    const page = await context.newPage();
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
