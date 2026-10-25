"""Exercise the real model, not a fake ready flag, without any camera input."""
import json
import pytest
from playwright.sync_api import expect
from pathlib import Path
from test_browser_smoke import BASE_URL, ROOT, browser, local_server  # noqa: F401


def test_real_proctor_model_loads_and_runs_inference(browser):
    page=browser.new_page()
    script=(ROOT/'app/static/mock-interview.js').read_text(encoding='utf8')
    script=script.rsplit('})();',1)[0]+'window.proctorTest={state,ensureProctorModel};})();'
    page.route('**/static/mock-interview.js*',lambda route:route.fulfill(body=script,content_type='application/javascript'))
    errors=[];failed=[]
    page.on('console',lambda message:errors.append(message.text) if message.type in ('error','warning') else None)
    page.on('requestfailed',lambda request:failed.append({'url':request.url,'reason':request.failure}))
    page.goto(BASE_URL+'/mock-interview?preview=1',wait_until='domcontentloaded')
    page.wait_for_function('() => window.proctorTest')
    page.evaluate('''() => {
      window.proctorStarted=performance.now();
      proctorTest.ensureProctorModel().then(async ready=>{
        const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;
        const result=ready?await proctorTest.state.proctorModel.detect(canvas):null;
        window.proctorProof={ready,elapsedMs:Math.round(performance.now()-proctorStarted),inference:Array.isArray(result)};
      }).catch(error=>{window.proctorProof={ready:false,error:error.message};});
    }''')
    try:
        page.wait_for_function('() => window.proctorProof',timeout=60000)
    finally:
        proof=page.evaluate('() => window.proctorProof || {ready:false,status:document.querySelector("[data-check=proctor]").textContent}')
        out=Path('../../outputs/placeai-proctor-20261024');out.mkdir(parents=True,exist_ok=True)
        (out/'model-load.json').write_text(json.dumps({'model':proof,'errors':errors,'failed':failed},indent=2),encoding='utf8')
    assert proof['ready'] and proof['inference'],proof
    assert proof['elapsedMs'] < 45000
    assert not errors,errors
    assert page.locator('#start-assessment').is_disabled()
    assert page.evaluate('proctorTest.state.mediaStream===null && proctorTest.state.screenStream===null')
    assert page.evaluate('proctorTest.ensureProctorModel()') is True
    page.evaluate('proctorTest.state.proctorModel.dispose()')
    print(json.dumps(proof))
    page.close()


@pytest.mark.parametrize('failure',['error','stall'])
def test_detector_failure_terminates_and_retry_is_independent_of_media(browser,failure):
    context=browser.new_context()
    script=(ROOT/'app/static/mock-interview.js').read_text(encoding='utf8')
    script=script.rsplit('})();',1)[0]+'window.proctorTest={state,ensureProctorModel};})();'
    context.route('**/static/mock-interview.js*',lambda route:route.fulfill(body=script,content_type='application/javascript'))
    bad="self.onmessage=()=>self.postMessage({type:'error',message:'Detector preparation failed'});" if failure=='error' else 'self.onmessage=()=>{};'
    attempts=[]
    def worker(route):
        attempts.append(1)
        good="self.onmessage=({data})=>self.postMessage(data.type==='load'?{type:'ready'}:{type:'result',id:data.id,predictions:[]});"
        route.fulfill(body=bad if len(attempts)==1 else good,content_type='application/javascript')
    context.route('**/static/proctor-worker.js*',worker)
    page=context.new_page();page.goto(BASE_URL+'/mock-interview?preview=1',wait_until='domcontentloaded')
    page.wait_for_function('() => window.proctorTest');page.clock.install()
    page.evaluate("() => {document.querySelector('#system-panel').classList.remove('hidden');proctorTest.ensureProctorModel().then(value=>window.firstReady=value);}")
    page.wait_for_function('() => window.firstReady === false') if failure=='error' else page.clock.fast_forward(45001)
    expect(page.locator('#retry-proctor')).to_be_enabled()
    expect(page.locator('#proctor-load-detail')).to_contain_text('Retry detector')
    assert page.evaluate('proctorTest.state.proctorModelReady') is False
    assert page.locator('#start-assessment').is_disabled()
    page.locator('#retry-proctor').click()
    page.wait_for_function('() => proctorTest.state.proctorModelReady === true')
    assert len(attempts)==2
    assert page.evaluate('proctorTest.state.mediaStream===null && proctorTest.state.screenStream===null')
    assert page.locator('#start-assessment').is_disabled()
    context.close()
