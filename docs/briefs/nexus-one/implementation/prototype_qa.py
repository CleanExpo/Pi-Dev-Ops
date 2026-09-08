"""Local prototype QA. Requires Python, PyYAML, Playwright and Chromium.
Runs no model, provider API, worker or production-system tests.
"""
from pathlib import Path
import json, shutil, re
import yaml
from playwright.sync_api import sync_playwright
root = Path(__file__).resolve().parent
policy_path=root/'policy.proposal.yaml'
sources=json.loads((root/'sources.json').read_text())
h=(root/'cockpit-preview.html').read_text()
report={'scope':'Local self-contained HTML prototype and static package checks only. NOT the live Mission Control, native CLIs, user devices or the 50 proposed live acceptance cases.', 'independent_external_model_review':'NOT_RUN','checked_on':'2026-09-08','checks':[], 'failures':[]}
def check(name,ok,detail=None):
 row={'name':name,'pass':bool(ok)}
 if detail is not None:row['detail']=detail
 report['checks'].append(row)
 if not ok:report['failures'].append(row)
policy=yaml.safe_load(policy_path.read_text())
check('policy disabled',policy['activation']['enabled'] is False)
check('policy mode observe',policy['activation']['execution_mode']=='observe')
check('no inferred grants',policy['activation']['inferred_grants_allowed'] is False)
check('50 distinct acceptance cases',len(set(re.findall(r'\bT\d{2}\b',(root/'ACCEPTANCE.md').read_text())))==50)
check('source register parses',len(sources['primary_documentation'])>=18)
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
 report['browser']=browser.version
 page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
 page.set_default_timeout(5000)
 errors=[];requests=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:requests.append(r.url))
 page.set_content(h,wait_until='load')
 check('simulation warning visible',page.locator('.preview').is_visible())
 for width,height in [(320,800),(375,812),(430,932),(768,1024),(1024,1366),(1440,900)]:
  page.set_viewport_size({'width':width,'height':height})
  for view in ['now','work','decisions','explore']:
   page.locator('#tab-'+view).click()
   check(f'{width}x{height} {view} active',page.locator('#view-'+view).is_visible())
   dimensions=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
   check(f'{width}x{height} {view} no horizontal overflow',dimensions['scroll']<=width,dimensions)
  page.locator('#tab-now').click()
  if width==1440:page.screenshot(path=str(root/'cockpit-desktop.png'),full_page=True)
  if width==375:page.screenshot(path=str(root/'cockpit-phone.png'),full_page=True)
  if width==768:page.screenshot(path=str(root/'cockpit-tablet.png'),full_page=True)
 page.set_viewport_size({'width':1440,'height':900})
 page.locator('#tab-now').click();page.locator('[data-evidence="continuity"]').first.click()
 check('evidence dialog opens',page.locator('#evidence-dialog').is_visible())
 check('evidence explicitly not run','NOT_RUN' in page.locator('#dialog-content').inner_text())
 page.keyboard.press('Escape');check('Escape closes dialog',not page.locator('#evidence-dialog').is_visible())
 page.locator('#tab-explore').click()
 for key in ['context','runtime','horizon','learning']:
  page.locator(f'#view-explore [data-evidence="{key}"]').click()
  check(f'{key} example opens',page.locator('#evidence-dialog').is_visible())
  check(f'{key} simulation provenance','record_kind: simulation' in page.locator('#dialog-content').inner_text())
  page.locator('#close-dialog').click()
 page.locator('#tab-now').click()
 page.get_by_role('button',name='Pause new work').click()
 check('pause reports no action','prototype' in page.locator('#toast').inner_text().lower())
 page.locator('#chat-input').fill('What prevents budget overruns?')
 page.locator('#chat-form button').click()
 check('local chat response labelled','Prototype explanation' in page.locator('#margot-message').inner_text())
 check('local response explains budget','atomic API' in page.locator('#margot-message').inner_text())
 page.locator('#tab-now').focus();page.keyboard.press('ArrowRight')
 check('tabs keyboard Right',page.locator('#tab-work').get_attribute('aria-selected')=='true')
 page.keyboard.press('End');check('tabs keyboard End',page.locator('#tab-explore').get_attribute('aria-selected')=='true')
 page.keyboard.press('Home');check('tabs keyboard Home',page.locator('#tab-now').get_attribute('aria-selected')=='true')
 page.locator('#search').fill('runtime')
 check('search opens work view',page.locator('#view-work').is_visible())
 check('search returns matches',page.locator('#view-work .task-item:visible').count()>=1)
 page.locator('#search').fill('unlikely-no-result-text')
 check('search hides unmatched tasks',page.locator('#view-work .task-item:visible').count()==0)
 page.locator('#search').fill('')
 check('search clear restores tasks',page.locator('#view-work .task-item:visible').count()>=2)
 page.locator('#tab-decisions').click()
 check('approval disabled',page.locator('#view-decisions button[disabled]').count() >= 1)
 check('no browser script errors',not errors,errors)
 check('no network requests',not requests,requests)
 browser.close()
report['checks_passed']=sum(c['pass'] for c in report['checks'])
report['checks_total']=len(report['checks'])
report['result']='PASS' if not report['failures'] else 'FAIL'
(root/'PROTOTYPE_QA.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['result','checks_passed','checks_total','failures']},indent=2))
