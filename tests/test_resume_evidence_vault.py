import io
import json
import pytest
from reportlab.pdfgen.canvas import Canvas
from app import resume_evidence
from app.models import Organization, StudentProfile, User, UserRole, Resume, StudentDocument
from app.routers import students, enterprise
from app.storage import save_file
from test_learning_hub import hub  # noqa: F401


def pdf_bytes(lines):
    buffer = io.BytesIO()
    c = Canvas(buffer)
    for i, text in enumerate(lines):
        c.drawString(40, 800-i*22, text)
    c.save()
    return buffer.getvalue()


@pytest.fixture
def evidence(hub):
    hub.client.app.include_router(students.router)
    hub.client.app.include_router(enterprise.router)
    org = Organization(name='Evidence College', slug='evidence-college')
    other_org = Organization(name='Other College', slug='other-evidence-college')
    hub.db.add_all([org, other_org]); hub.db.flush()
    hub.owner.organization_id = org.id
    hub.other.organization_id = org.id
    profile = StudentProfile(user_id=hub.owner.id, organization_id=org.id, full_name='Test student', degree='B.Tech', current_semester=4)
    admin = User(username='evidence-admin',email='admin@evidence.invalid',hashed_password='test-only',role=UserRole.institution_admin,organization_id=org.id)
    outsider = User(username='evidence-outsider',email='admin@other.invalid',hashed_password='test-only',role=UserRole.institution_admin,organization_id=other_org.id)
    hub.db.add_all([profile,admin,outsider,StudentProfile(user_id=hub.other.id,organization_id=org.id)]); hub.db.commit()
    hub.profile=profile;hub.admin=admin;hub.outsider=outsider;hub.org=org
    return hub


def test_resume_quote_credit_negations_profile_claims_and_no_fabricated_skill(evidence):
    p=evidence.profile
    p.target_role='Data engineer';p.skills=['Redis']
    p.role_requirements_json=json.dumps([{'label':s,'priority':'required'} for s in ['Python','SQL','Redis','Docker']])
    raw=pdf_bytes(['Education: Bachelor of Engineering','Projects','Built Python pipelines for 100 records',
                   'Skills: SQL','No Redis experience','Learning Docker basics','Portfolio https://github.com/example'])
    result=resume_evidence.analyze(raw,p)
    assert result['resume_score']==40 and result['score_adjustments']
    entries={x['label']:x for x in result['requirements']}
    assert entries['Python']['status']=='documented'
    assert entries['SQL']['status']=='partial'
    assert entries['Redis']['status']=='not_found' and entries['Redis']['credit']==0 and entries['Redis']['profile_claim']
    assert entries['Docker']['status']=='partial'
    lines,_=resume_evidence.extract_lines(raw)
    for item in result['requirements']:
        for quote in item['evidence']:
            assert quote in lines
    # Profile-only claims and an AI-generated summary cannot manufacture resume quotes.
    p.role_requirements_json=json.dumps([{'label':'Kubernetes','priority':'required'}])
    assert resume_evidence.analyze(raw,p)['role_score']==0
    assert resume_evidence.analyze(raw,p)['requirements'][0]['evidence']==[]


def test_resume_api_upload_review_target_change_and_account_isolation(evidence):
    api=evidence.client
    target={'role':'Data engineer','requirements':[{'label':'Python','priority':'required'},{'label':'Redis','priority':'preferred'}]}
    assert api.put('/students/resume/target',json=target).status_code==200
    raw=pdf_bytes(['Education: Bachelor of Engineering','Projects','Built Python pipelines for 100 records','Skills: Python, SQL'])
    assert api.post('/students/resume',files={'file':('resume.pdf',raw,'application/pdf')}).status_code==201
    reviewed=api.post('/students/resume/evidence');assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()['role_score']==66
    assert api.get('/students/resume/evidence').json()['alignment']['current']
    target['requirements'][0]['label']='Java'
    api.put('/students/resume/target',json=target)
    assert api.get('/students/resume/evidence').json()['alignment']['score'] is None
    assert api.put('/students/resume/target',json={'role':'Role','requirements':[{'label':'  '}]}).status_code==422
    assert api.put('/students/resume/target',json={**target,'score':100}).status_code==422
    evidence.actor[0]=evidence.other
    assert api.get('/students/resume/evidence').json()['review'] is None
    assert api.post('/students/resume/evidence').status_code==404
    evidence.actor[0]=evidence.admin
    assert api.get('/students/resume/evidence').status_code==403


def test_private_document_requires_specific_consent_and_withdrawal_is_immediate(evidence):
    api=evidence.client
    raw=pdf_bytes(['Semester 4 academic record for isolated local test'])
    response=api.post('/enterprise/documents?document_type=marksheet&semester=4&visibility=institution_only',files={'file':('semester4.pdf',raw,'application/pdf')})
    assert response.status_code==201,response.text
    identifier=response.json()['id'];path='/enterprise/documents/'+identifier
    evidence.actor[0]=evidence.admin
    assert api.get('/enterprise/documents?student_id='+evidence.profile.id).json()==[]
    assert api.get(path+'/download').status_code==404
    evidence.actor[0]=evidence.owner
    assert api.post(path+'/submit',json={'consent':False,'organization_id':evidence.org.id}).status_code==422
    assert api.post(path+'/submit',json={'consent':True,'organization_id':evidence.outsider.organization_id}).status_code==403
    assert api.post(path+'/submit',json={'consent':True,'organization_id':evidence.org.id}).status_code==200
    assert api.patch(path+'/metadata',json={'semester':3}).status_code==409
    evidence.actor[0]=evidence.admin
    directory=api.get('/enterprise/documents/institution?semester=4&course=B.Tech').json()
    assert directory['students'][0]['name']=='Test student'
    assert directory['students'][0]['documents'][0]['semester']==4
    assert api.get(path+'/download').status_code==200
    evidence.actor[0]=evidence.outsider
    assert api.get('/enterprise/documents/institution').json()['students']==[]
    assert api.get(path+'/download').status_code==404
    evidence.actor[0]=evidence.other
    assert api.get(path+'/download').status_code==404
    assert api.delete(path+'/submission').status_code==404
    evidence.actor[0]=evidence.owner
    assert api.delete(path+'/submission').status_code==200
    assert api.patch(path+'/metadata',json={'semester':3,'label':'Semester 3'}).status_code==200
    assert api.get(path+'/download').status_code==200
    evidence.actor[0]=evidence.admin
    assert api.get(path+'/download').status_code==404
    assert api.get('/enterprise/documents/institution').json()['students'][0]['documents']==[]


def test_profile_semester_validation_and_missing_profile_blocks_submission(evidence):
    api=evidence.client
    assert api.put('/students/profile',json={'current_semester':21}).status_code==422
    assert api.put('/students/profile',json={'current_semester':6,'enrollment_number':'TEST-06','academic_year':'2026–27'}).status_code==200
    assert api.get('/students/profile').json()['current_semester']==6
    assert api.get('/enterprise/documents/context').json()['semester']==6
    assert api.post('/enterprise/documents?document_type=untrusted',files={'file':('x.pdf',pdf_bytes(['test']),'application/pdf')}).status_code==422


def test_changing_role_names_or_ai_parsing_does_not_inflate_readiness(evidence):
    from app.services import placement_readiness
    p=evidence.profile
    before=placement_readiness(p,evidence.db)
    p.desired_roles=['Engineer','Analyst','Developer','Scientist']
    p.resume=Resume(original_filename='resume.pdf',filepath='test',is_parsed=True,ai_parsed_data_json=json.dumps({'summary':'Expert at everything','experience':[{'description':'invented'}]}))
    evidence.db.add(p);evidence.db.commit()
    after=placement_readiness(p,evidence.db)
    components={x['name']:x['score'] for x in after['components']}
    assert components['Role alignment']==0 and components['Resume strength']==0 and components['Project evidence']==0
    old={x['name']:x['score'] for x in before['components']}
    for key in ['Academic eligibility','Interview readiness']:
        assert components[key]==old[key]


def test_ai_coaching_requires_consent_rejects_invented_quotes_and_cannot_set_scores(evidence,monkeypatch):
    from app import ai_provider
    from app.ai_rate_limit import student_ai_guard
    evidence.client.app.dependency_overrides[student_ai_guard]=lambda:None
    raw=pdf_bytes(['Education: Bachelor of Engineering','Projects','Built Python pipelines for 100 records','Skills: Python'])
    api=evidence.client
    api.post('/students/resume',files={'file':('resume.pdf',raw,'application/pdf')})
    original=api.post('/students/resume/evidence').json()
    calls=[]
    result={'findings':[{'page':1,'line':3,'quote':'Invented leadership experience','suggestion':'Add a clear account of your contribution.'}]}
    def model(prompt,**kwargs):
        calls.append(prompt)
        return json.dumps(result)
    monkeypatch.setattr(ai_provider,'call_ai_text',model)
    assert api.post('/students/resume/coaching',json={'consent':False}).status_code==422
    assert calls==[]
    assert api.post('/students/resume/coaching',json={'consent':True}).status_code==502
    assert 'coaching' not in api.get('/students/resume/evidence').json()['review']
    quote=original['project_examples'][0]
    result['findings'][0]={**quote,'suggestion':'Explain your own contribution and how you validated the pipeline result.'}
    response=api.post('/students/resume/coaching',json={'consent':True})
    assert response.status_code==200,response.text
    assert api.get('/students/resume/evidence').json()['review']['resume_score']==original['resume_score']
    result['score']=100
    assert api.post('/students/resume/coaching',json={'consent':True}).status_code==502
