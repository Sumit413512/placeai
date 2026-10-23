from __future__ import annotations
from datetime import date, timedelta
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import require_student
from app.models import User, utcnow
from app.study_models import StudyPlan, StudyGoal, NotebookProgress, StudyDaily
from app import study_service as service

router = APIRouter(prefix='/study-tracker', tags=['Study tracker'])


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class PlanInput(Input):
    request_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=3,max_length=180)
    roadmap_id: str | None = Field(default=None,max_length=100)
    daily_minutes: int = Field(default=45,ge=5,le=480)
    target_date: date | None = None
    timezone: str = Field(default='Asia/Kolkata',max_length=64)

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        try: ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError): raise ValueError('Choose a valid time zone') from None
        return value


class PlanUpdate(Input):
    daily_minutes: int = Field(ge=5,le=480)
    target_date: date | None = None
    paused: bool = False


class GoalInput(Input):
    kind: Literal['notes','video','mock','task','milestone']
    resource_id: str = Field(default='',max_length=100)
    title: str = Field(default='',max_length=240)
    target: int = Field(default=1,ge=1,le=1000)


class GoalUpdate(Input):
    completed: int = Field(ge=0,le=1000)


class ReadingInput(Input):
    section_key: str = Field(pattern=r'^\d{1,2}\.\d{1,2}$')
    completed: bool | None = None
    through: bool = False
    source: Literal['web','offline'] = 'web'
    active_seconds: int = Field(default=0,ge=0,le=60)
    event_id: UUID


def owned_plan(db, identifier, user):
    row = db.query(StudyPlan).filter_by(id=identifier,user_id=user.id).first()
    if not row: raise HTTPException(404,'Study plan not found')
    return row


@router.get('')
def overview(user:User=Depends(require_student),db:Session=Depends(get_db)):
    mocks = service.mock_records(db,user)
    plans = db.query(StudyPlan).filter_by(user_id=user.id).order_by(StudyPlan.created_at.desc()).limit(20).all()
    zone = service.user_zone(db,user.id); today=service.local_day(utcnow(),zone)
    daily = {row.day:row for row in db.query(StudyDaily).filter(StudyDaily.user_id==user.id,StudyDaily.day>=today-timedelta(days=27)).all()}
    mock_days = {}
    for row in mocks:
        day=service.local_day(row.created_at,zone);mock_days[day]=mock_days.get(day,0)+1
    days=[]
    for offset in range(27,-1,-1):
        day=today-timedelta(days=offset); row=daily.get(day)
        days.append({'date':str(day),'minutes':round(((row.notes_seconds+row.video_seconds) if row else 0)/60,1),
                     'sections_completed':row.sections_completed if row else 0,'mock_sessions':mock_days.get(day,0)})
    active=lambda item:item['minutes']>0 or item['sections_completed']>0 or item['mock_sessions']>0
    streak=0
    for item in reversed(days if active(days[-1]) else days[:-1]):
        if not active(item):break
        streak+=1
    return {'plans':[service.plan_data(db,p,user,mocks) for p in plans], 'daily':days,'timezone':zone,
            'today_minutes':days[-1]['minutes'],'average_daily_minutes':round(sum(d['minutes'] for d in days[-7:])/7,1),
            'active_days':sum(active(d) for d in days),'streak_days':streak,'completed_mock_sessions':len(mocks),
            'activity_basis':'Recorded active reading and playback time; offline reading is not timed. Mock activity uses session start dates.'}


@router.get('/resources')
def resources(user:User=Depends(require_student),db:Session=Depends(get_db)):
    return service.resource_catalog(db,user)


@router.post('/plans',status_code=201)
def create_plan(body:PlanInput,user:User=Depends(require_student),db:Session=Depends(get_db)):
    service.lock_owner(db,user)
    existing_request=db.query(StudyPlan).filter_by(user_id=user.id,request_id=str(body.request_id)).first()
    if existing_request:
        if any(getattr(existing_request,k)!=getattr(body,k) for k in ('title','roadmap_id','daily_minutes','target_date')):
            raise HTTPException(409,'This request identifier already belongs to another study plan')
        return service.plan_data(db,existing_request,user,service.mock_records(db,user))
    if db.query(StudyPlan).filter_by(user_id=user.id).count()>=20:raise HTTPException(409,'You can keep up to 20 study plans')
    if body.target_date and body.target_date<service.local_day(utcnow(),body.timezone):raise HTTPException(422,'Choose today or a future target date')
    if body.roadmap_id:service.owned_roadmap(db,body.roadmap_id,user)
    # One calendar convention per student avoids splitting the same activity across days.
    existing=db.query(StudyPlan).filter_by(user_id=user.id).order_by(StudyPlan.created_at).first()
    data=body.model_dump()
    data['request_id']=str(body.request_id)
    if existing:data['timezone']=existing.timezone
    row=StudyPlan(user_id=user.id,**data);db.add(row);db.commit()
    return service.plan_data(db,row,user,service.mock_records(db,user))


@router.patch('/plans/{identifier}')
def update_plan(identifier:str,body:PlanUpdate,user:User=Depends(require_student),db:Session=Depends(get_db)):
    service.lock_owner(db,user);row=owned_plan(db,identifier,user)
    for key,value in body.model_dump().items():setattr(row,key,value)
    db.commit();return service.plan_data(db,row,user,service.mock_records(db,user))


@router.post('/plans/{identifier}/goals',status_code=201)
def add_goal(identifier:str,body:GoalInput,user:User=Depends(require_student),db:Session=Depends(get_db)):
    service.lock_owner(db,user);plan=owned_plan(db,identifier,user)
    if db.query(StudyGoal).filter_by(plan_id=plan.id).count()>=30:raise HTTPException(409,'A plan can contain up to 30 goals')
    resource,title,target=body.resource_id,body.title,body.target
    if body.kind=='notes':
        book=service.notebook(db,resource,user);outline=service.sections(book)
        if not outline:raise HTTPException(409,'Wait until the complete notebook is ready')
        title,target=book.title,len(outline)
    elif body.kind=='video':
        from app.routers.learning_video import owner_course,course_data
        course=owner_course(db,resource,user);data=course_data(db,course,user)
        if not data['course_ready']:raise HTTPException(409,'Wait until the complete course is ready')
        title,target=course.title,len(data['lessons'])
    elif body.kind=='mock':resource,title='mock-interview','Mock interview practice'
    elif body.kind=='milestone':
        if not plan.roadmap_id:raise HTTPException(422,'Link a roadmap before adding its outcomes')
        source=service.owned_roadmap(db,plan.roadmap_id,user)
        milestone=next((m for m in service.roadmap_milestones(source) if m['key']==resource),None)
        if not milestone:raise HTTPException(422,'Choose an outcome from the linked roadmap')
        title,target=milestone['title'],1
    else:
        if len(title)<3:raise HTTPException(422,'Describe your task in at least three characters')
        resource=title.casefold()[:100]
    existing=db.query(StudyGoal).filter_by(plan_id=plan.id,kind=body.kind,resource_id=resource).first()
    if existing:return service.goal_data(db,existing,user,service.mock_records(db,user))
    row=StudyGoal(plan_id=plan.id,kind=body.kind,resource_id=resource,title=title,target=target)
    db.add(row);db.commit();return service.goal_data(db,row,user,service.mock_records(db,user))


@router.patch('/goals/{identifier}')
def update_goal(identifier:str,body:GoalUpdate,user:User=Depends(require_student),db:Session=Depends(get_db)):
    service.lock_owner(db,user)
    row=db.query(StudyGoal).join(StudyPlan).filter(StudyGoal.id==identifier,StudyPlan.user_id==user.id).first()
    if not row:raise HTTPException(404,'Goal not found')
    if row.kind not in {'task','milestone'}:raise HTTPException(409,'This goal updates from the linked learning activity')
    if body.completed>row.target:raise HTTPException(422,'Completed units cannot exceed your goal')
    row.manual_completed=body.completed;db.commit();return service.goal_data(db,row,user,service.mock_records(db,user))


@router.delete('/goals/{identifier}',status_code=204)
def remove_goal(identifier:str,user:User=Depends(require_student),db:Session=Depends(get_db)):
    service.lock_owner(db,user)
    row=db.query(StudyGoal).join(StudyPlan).filter(StudyGoal.id==identifier,StudyPlan.user_id==user.id).first()
    if not row:raise HTTPException(404,'Goal not found')
    db.delete(row);db.commit()


@router.get('/notes/{identifier}')
def reading(identifier:str,user:User=Depends(require_student),db:Session=Depends(get_db)):
    return service.reading_data(db,service.notebook(db,identifier,user))


@router.put('/notes/{identifier}')
def save_reading(identifier:str,body:ReadingInput,user:User=Depends(require_student),db:Session=Depends(get_db)):
    service.lock_owner(db,user);book=service.notebook(db,identifier,user);outline=service.sections(book)
    keys=[s['key'] for s in outline]
    if body.section_key not in keys:raise HTTPException(422,'Choose an existing section of the complete notebook')
    if body.through and body.completed is not True:raise HTTPException(422,'Mark-through requires explicit completion')
    row=db.get(NotebookProgress,(identifier,body.section_key))
    if row and row.last_event_id==str(body.event_id):return service.reading_data(db,book)
    now=utcnow();daily=service.day_row(db,user.id,now)
    elapsed=max(0,(now-daily.last_pulse_at).total_seconds()) if daily.last_pulse_at else 0
    if body.source=='web':daily.notes_seconds+=int(min(body.active_seconds,elapsed,60))
    daily.last_pulse_at=now
    selected=keys[:keys.index(body.section_key)+1] if body.through else [body.section_key]
    book.last_read_section=body.section_key
    for key in selected:
        item=db.get(NotebookProgress,(identifier,key))
        if item is None:
            item=NotebookProgress(notebook_id=identifier,section_key=key,completed=False);db.add(item)
        if body.completed is not None and item.completed!=body.completed:
            if body.completed:daily.sections_completed+=1;item.completed_at=now
            elif item.completed_at:
                old=db.get(StudyDaily,(user.id,service.local_day(item.completed_at,service.user_zone(db,user.id))))
                if old:old.sections_completed=max(0,old.sections_completed-1)
                item.completed_at=None
            item.completed=body.completed
        item.source,item.last_read_at,item.last_event_id=body.source,now,str(body.event_id)
    db.commit();return service.reading_data(db,book)
