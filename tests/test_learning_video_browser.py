from copy import deepcopy
import os
import shutil
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401
from test_learning_video import course_plan, script
from app.learning_video_media import captions, render_video


@pytest.fixture(scope="module")
def video_browser(local_server):  # noqa: F811
    del local_server
    # Bundled Chromium omits proprietary media codecs on Linux. GitHub's Ubuntu
    # runner includes Google Chrome; use it to verify actual H.264/AAC playback.
    executable = (os.getenv('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or shutil.which('google-chrome')
                  or shutil.which('google-chrome-stable'))
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True, **({'executable_path':executable} if executable else {}))
        try:
            yield instance
        finally:
            instance.close()


def test_video_learning_playback_practice_mobile_and_cleanup(video_browser):
    browser = video_browser
    page = browser.new_page(viewport={"width":1440,"height":1000})
    page.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
    content = script()
    media, duration, timings = render_video(content, narrate=lambda _: b'\0'*48000)
    content.update(timings=timings, sources=[{"title":"PostgreSQL SELECT","url":"https://www.postgresql.org/docs/current/sql-select.html"}])
    course = {"id":"video-browser-course", "title":"SQL foundations", "status":"ready", "introduction":course_plan()['introduction'],
              "prerequisites":[], "sources":content['sources'], "videos_completed":0, "practice_completed":0,
              "lessons":[{**outline,"position":i,"status":"ready" if i<2 else "queued", "duration_seconds":duration if i<2 else 0,
                          "video_completed":False,"practice_completed":False,"position_seconds":1 if i==0 else 0,"watched_seconds":0}
                         for i,outline in enumerate(course_plan()['lessons'])]}
    calls = []
    def api(route):
        path = route.request.url.split(BASE_URL)[-1].split('?')[0]
        if path.endswith('/media'):
            route.fulfill(body=media,content_type='video/mp4'); return
        if path.endswith('/captions'):
            route.fulfill(body=captions(content),content_type='text/vtt'); return
        if route.request.resource_type not in {'fetch','xhr'}:
            route.continue_(); return
        data = {"items":[],"summary":{},"actions":[]}
        if path == '/auth/refresh': data = {"access_token":"isolated-browser-token"}
        elif path == '/auth/me': data = {"id":"video-student","role":"student","email":"student@example.invalid","username":"Student"}
        elif path in {'/students/applications','/students/jobs'}: data = []
        elif path == '/billing/status': data = {"student_kind":"university","premium_access":True,"access_mode":"institution_sponsored"}
        elif path == '/learning-hub': data = {"items":[],"generation_available":True}
        elif path == '/learning-hub/video':
            data = {"items":[course,{**deepcopy(course),"id":"failed-course","title":"Failed video course","status":"failed"}],"generation_available":True}
            if route.request.method == 'POST': calls.append(route.request.post_data_json); data = course
        elif path.endswith('/progress'):
            calls.append(route.request.post_data_json)
            index = int(path.split('/lessons/')[1].split('/')[0])
            data = {"position_seconds":route.request.post_data_json['position_seconds'],"watched_seconds":duration,"video_completed":True,"practice_completed":course['lessons'][index]['practice_completed']}
            course['lessons'][index].update(data)
        elif path.endswith('/practice'):
            index = int(path.split('/lessons/')[1].split('/')[0])
            data = {"results":[{"correct":True,"answer":0,"explanation":q['explanation']} for q in content['quiz']],
                    "solution":content['solution'],"practice_completed":True,"video_completed":True}
            course['lessons'][index].update(practice_completed=True,video_completed=True)
        elif '/lessons/' in path:
            index = int(path.split('/lessons/')[1].split('/')[0])
            safe = deepcopy(content); safe.pop('solution'); safe['quiz']=[{"question":q['question'],"options":q['options']} for q in content['quiz']]
            data = {"title":f"Query concept {index}","status":"ready","content":safe,"duration_seconds":duration,"position_seconds":course['lessons'][index]['position_seconds']}
        elif path.startswith('/learning-hub/video/'): data = course
        route.fulfill(json=data)
    page.route(BASE_URL+'/**', api)
    page.goto(BASE_URL,wait_until='networkidle')
    page.locator('#app-nav [data-view="learning-hub"]').click()
    page.get_by_role('button',name='Video learning',exact=True).click()
    page.get_by_label('Video topic',exact=True).fill('SQL')
    page.get_by_role('button',name='Find or create course',exact=True).click()
    expect(page.get_by_role('heading',name='Course overview',exact=True)).to_be_visible()
    expect(page.locator('.learning-video-study-layout')).not_to_be_visible()
    expect(page.locator('[data-video-library]')).not_to_contain_text('Failed video course')
    expect(page.locator('[data-video-begin]')).to_have_count(0)
    expect(page.locator('[data-video-library]')).to_contain_text('Processing')
    expect(page.locator('.learning-video-preparation')).to_have_text('Processing')
    page.get_by_role('button',name='All courses',exact=True).click()
    for item in course['lessons']:item['status']='ready'
    page.locator('[data-video-id="video-browser-course"]').click()
    page.get_by_role('button',name='Begin learning',exact=True).click()
    expect(page.locator('.learning-video-lessons').first).to_be_visible()
    expect(page.locator('[data-video-library]')).to_contain_text('Ready to begin')
    expect(page.locator('.learning-video-preparation')).to_contain_text('Ready to begin')
    expect(page.locator('[data-video-outline]')).to_contain_text('1.1 Query concept 0')
    expect(page.locator('[data-video-outline]')).to_contain_text('1.2 Query concept 1')
    expect(page.locator('[data-video-outline]')).to_contain_text('2.1 Query concept 2')
    assert calls[0]['topic']=='SQL' and 'level' not in calls[0] and 'goal' not in calls[0]
    assert page.get_by_label('Starting level',exact=True).count() == 0
    assert not page.locator('#learning-hub-form').is_visible()
    page.locator('[data-video-outline] [data-video-lesson="0"]').click()
    video = page.locator('.learning-video-player')
    expect(video).to_be_visible()
    page.wait_for_function("() => document.querySelector('.learning-video-player')?.readyState >= 2")
    assert video.evaluate('v=>v.duration') == duration
    assert video.evaluate('v=>v.currentTime') == 1
    assert video.locator('track').get_attribute('src').startswith('blob:')
    expect(page.locator('[data-video-outline] [data-video-lesson="0"]')).to_have_attribute('aria-current','step')
    expect(page.get_by_role('button',name='Previous lesson',exact=True)).to_be_disabled()
    assert page.locator('.learning-video-quiz').evaluate('(el)=>Boolean(el.previousElementSibling)')
    page.get_by_label('Playback speed',exact=True).select_option('1.5')
    assert video.evaluate('v=>v.playbackRate')==1.5
    for fieldset in page.locator('[data-video-practice] fieldset').all():
        fieldset.locator('input').first.check()
    page.get_by_role('button',name='Check answers',exact=True).click()
    expect(page.locator('[data-video-feedback]')).to_contain_text('Practice completed.')
    expect(page.locator('[data-video-outline] [data-video-lesson="0"]')).to_have_attribute('data-complete','true')
    expect(page.get_by_role('progressbar',name='Course completion')).to_have_attribute('value','25')
    page.locator('[data-video-move="1"]').click()
    expect(page.locator('.learning-video-player')).to_have_attribute('aria-label','Query concept 1')
    expect(page.locator('[data-video-outline] [data-video-lesson="1"]')).to_have_attribute('aria-current','step')
    expect(page.locator('[data-video-move="1"]')).to_be_enabled()
    output=Path(__file__).resolve().parents[3]/'output/design'
    output.mkdir(parents=True,exist_ok=True)
    for width in (1440,736,390,320):
        page.set_viewport_size({"width":width,"height":1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
        if width in (1440,390):
            page.screenshot(path=str(output/f'PlaceAI_course_player_layout_{width}.png'),full_page=True)
    page.get_by_role('button',name='Back to course',exact=True).click()
    expect(page.locator('.learning-video-study-layout')).not_to_be_visible()
    expect(page.get_by_role('heading',name='Course overview',exact=True)).to_be_focused()
    page.get_by_role('button',name='All courses',exact=True).click()
    for item in course['lessons']:item['status']='ready'
    course['requires_full_preparation']=True
    page.locator('[data-video-id="video-browser-course"]').click()
    expect(page.locator('.learning-video-study-layout')).not_to_be_visible()
    expect(page.locator('[data-video-begin]')).to_have_count(0)
    expect(page.get_by_role('region',name='Course preparation checks')).to_contain_text('Processing quality checks')
    for item in course['lessons']:item['quality_checked']=True
    page.get_by_role('button',name='All courses',exact=True).click()
    page.locator('[data-video-id="video-browser-course"]').click()
    expect(page.locator('.learning-video-preparation')).to_have_text('Ready to begin')
    page.get_by_role('button',name='Continue learning',exact=True).click()
    page.locator('[data-video-outline] [data-video-lesson="1"]').click()
    video = page.locator('.learning-video-player')
    page.get_by_role('button',name='Detailed notes',exact=True).click()
    expect(page.locator('#learning-hub-form')).to_be_visible()
    assert video.evaluate('v=>v.paused')
    page.set_viewport_size({"width":1440,"height":1000})
    page.locator('#app-nav [data-view="opportunities"]').click()
    assert not page.locator('.learning-video-player').count()
    assert not errors
    page.close()
