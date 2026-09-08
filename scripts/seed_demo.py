#!/usr/bin/env python3
"""Create a self-contained PlaceAI 3.1 demo tenant. Development use only."""
from __future__ import annotations

import os
import secrets
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base, SessionLocal, engine
from app.models import (
    Announcement, Application, ApplicationStatus, ApprovalStatus, AttendanceSession,
    CommunicationMessage, CommunicationThread, CustomFieldDefinition, CustomFieldValue,
    DriveStage, DriveStatus, IncidentReport, InstitutionPolicy, InterviewEvaluation,
    InterviewSchedule, Job, Notification, NotificationPreference, Offer, Organization,
    OrganizationType, PlacementDrive, ProfileChangeRequest, RecruiterProfile,
    StudentProfile, User, UserRole, utcnow,
)
from app.utils import get_hashed_password

DEMO_PASSWORD = "PlaceAI-Demo-2026!"


def get_user(db, email, username, role, organization_id=None):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, username=username, hashed_password=get_hashed_password(DEMO_PASSWORD), role=role, organization_id=organization_id, email_verified=True)
        db.add(user); db.flush()
    return user


def add_notification_once(db, user, org, title, message, category, priority="normal", link=None):
    exists = db.query(Notification).filter(Notification.user_id == user.id, Notification.title == title).first()
    if not exists:
        db.add(Notification(user_id=user.id, organization_id=org.id if org else None, title=title, message=message, category=category, priority=priority, link=link))


def main():
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise SystemExit("Refusing to seed demo data in production.")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "northstar").first()
        if not org:
            org = Organization(name="Northstar Institute of Technology", slug="northstar", organization_type=OrganizationType.institution, city="Pune", state="Maharashtra", domain="northstar.example.com", website="https://northstar.example.com")
            db.add(org); db.flush()

        platform = get_user(db, "platform@placeai.example.com", "platformadmin", UserRole.platform_admin)
        tpo = get_user(db, "tpo@northstar.example.com", "northstartpo", UserRole.institution_admin, org.id)
        recruiter_user = get_user(db, "recruiter@acme.example.com", "acmerecruiter", UserRole.recruiter)
        recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == recruiter_user.id).first()
        if not recruiter:
            recruiter = RecruiterProfile(user_id=recruiter_user.id)
            db.add(recruiter); db.flush()
        recruiter.full_name = "Aarav Recruiter"
        recruiter.company_name = "Acme Technologies (Demo)"
        recruiter.company_website = "https://acme.example.com"
        recruiter.industry = "Technology"
        recruiter.designation = "Campus Talent Partner"
        recruiter.linkedin_url = "https://www.linkedin.com/company/acme-technologies-demo"
        recruiter.cin = "U72900MH2020PTC000001"  # fictional demo identifier
        recruiter.gstin = "27ABCDE1234F1Z5"       # fictional demo identifier
        recruiter.company_address = "Demo Corporate Office, Pune, Maharashtra"
        recruiter.official_email_domain = "acme.example.com"
        recruiter.past_college_relationships = ["Northstar Institute (Demo)", "Westbridge University (Demo)"]
        recruiter.previous_successful_placements = 18
        recruiter.job_consistency_score = 88
        recruiter.is_verified = True
        recruiter.provisioned_by_organization_id = org.id

        students = []
        sample = [
            ("student@northstar.example.com","studentone","Aarav Shah",8.7,["Python","SQL","FastAPI","Docker"],["AWS Cloud Practitioner"]),
            ("riya@northstar.example.com","riyamehta","Riya Mehta",8.4,["Python","PostgreSQL","Docker","AWS"],["NPTEL Cloud Computing"]),
            ("vihaan@northstar.example.com","vihaank","Vihaan Kumar",8.1,["Java","Spring","SQL","Git"],["Oracle Java Foundations"]),
        ]
        for email,username,name,cgpa,skills,certs in sample:
            u = get_user(db,email,username,UserRole.student,org.id)
            s = db.query(StudentProfile).filter(StudentProfile.user_id == u.id).first()
            if not s:
                s=StudentProfile(user_id=u.id,organization_id=org.id)
                db.add(s); db.flush()
            s.full_name=name; s.college=org.name; s.degree="B.Tech"; s.branch="Computer Science"; s.graduation_year=2026; s.cgpa=cgpa
            s.tenth_percentage=91.2; s.twelfth_percentage=86.5; s.active_backlogs=0; s.historical_backlogs=0; s.academic_gap_months=0
            s.work_authorization="India"; s.is_verified=True; s.skills=skills; s.certifications=certs; s.desired_roles=["Software Engineer","Backend Developer"]
            students.append(s)

        job = db.query(Job).filter(Job.recruiter_id == recruiter.id, Job.title == "Graduate Software Engineer").first()
        if not job:
            job=Job(recruiter_id=recruiter.id,title="Graduate Software Engineer",description="Build reliable APIs, backend services and data-driven product features with the graduate engineering team.",location="Pune",job_type="Full-time",salary_range="₹7–9 LPA",experience_required="Fresher",visibility="campus",target_organization_id=org.id,approval_status=ApprovalStatus.approved,is_active=True)
            job.required_skills=["Python","SQL","REST APIs"]; job.preferred_roles=["Backend Developer","Software Engineer"]
            db.add(job); db.flush()

        public_job = db.query(Job).filter(Job.recruiter_id == recruiter.id, Job.title == "Data Operations Intern").first()
        if not public_job:
            public_job=Job(recruiter_id=recruiter.id,title="Data Operations Intern",description="Support product analytics and data quality workflows using SQL, spreadsheets and Python automation.",location="Hybrid",job_type="Internship",salary_range="₹25,000/month",visibility="public",approval_status=ApprovalStatus.approved,is_active=True)
            public_job.required_skills=["SQL","Python","Excel"]
            db.add(public_job)

        now = utcnow()
        drive=db.query(PlacementDrive).filter(PlacementDrive.organization_id==org.id,PlacementDrive.job_id==job.id).first()
        if not drive:
            drive=PlacementDrive(organization_id=org.id,job_id=job.id,title="Acme Graduate Hiring 2026",status=DriveStatus.open,min_cgpa=7.0)
            db.add(drive); db.flush()
        drive.min_tenth_percentage=60; drive.min_twelfth_percentage=60; drive.max_active_backlogs=0; drive.max_academic_gap_months=24; drive.work_authorization_required="India"; drive.allow_placed_students=True
        drive.allowed_graduation_years=[2026]; drive.allowed_branches=["Computer Science","Information Technology"]
        drive.required_skills=["Python","SQL"]; drive.required_certifications=[]; drive.required_documents=[]
        drive.registration_deadline=now+timedelta(days=3); drive.event_date=now+timedelta(days=7)

        defaults = [
            ("registration","Registration","registration"),("eligibility-screening","Eligibility Screening","screening"),
            ("online-assessment","Online Assessment","assessment"),("technical-round-1","Technical Round 1","interview"),
            ("technical-round-2","Technical Round 2","interview"),("hr-interview","HR Interview","interview"),
            ("offer","Offer","offer"),("joined","Joined","terminal"),
        ]
        for idx,(key,name,stype) in enumerate(defaults):
            if not db.query(DriveStage).filter(DriveStage.drive_id==drive.id,DriveStage.stage_key==key).first():
                db.add(DriveStage(drive_id=drive.id,stage_key=key,name=name,order_index=idx,stage_type=stype,is_terminal=key=="joined"))

        apps=[]
        statuses=[ApplicationStatus.shortlisted,ApplicationStatus.interview,ApplicationStatus.applied]
        stages=["technical-round-1","hr-interview","registration"]
        for i,s in enumerate(students):
            app=db.query(Application).filter(Application.student_id==s.id,Application.job_id==job.id).first()
            if not app:
                app=Application(student_id=s.id,job_id=job.id)
                db.add(app); db.flush()
            app.status=statuses[i]; app.drive_id=drive.id; app.pipeline_stage_key=stages[i]; app.cover_note="Interested in the graduate engineering opportunity."; app.ai_match_score=[92,87,81][i]; app.ai_match_reasoning="Demo score: review skills, resume, academics and interview evidence before any decision."
            apps.append(app)

        # Interview + human evaluation demo.
        iv = db.query(InterviewSchedule).filter(InterviewSchedule.application_id==apps[0].id).first()
        if not iv:
            iv=InterviewSchedule(application_id=apps[0].id,drive_id=drive.id,round_name="Technical Round 1",scheduled_at=now+timedelta(days=2,hours=2),mode="online",meeting_url="https://meet.example.com/placeai-demo",interviewer="Engineering Panel",student_slot="11:30 AM",instructions="Join 10 minutes early with a valid college ID.",created_by_user_id=recruiter_user.id)
            db.add(iv); db.flush()
        if not db.query(InterviewEvaluation).filter(InterviewEvaluation.interview_id==iv.id).first():
            db.add(InterviewEvaluation(interview_id=iv.id,evaluator_user_id=recruiter_user.id,technical_knowledge=8,communication=7,problem_solving=9,role_fit=8,recommendation="Proceed",notes="Structured demo evaluation; human-authored evidence."))

        # Offer lifecycle demo (for the second student) without fabricating outcomes for the primary student account.
        offer = db.query(Offer).filter(Offer.application_id==apps[1].id).first()
        if not offer:
            offer=Offer(application_id=apps[1].id,company_name=recruiter.company_name,role=job.title,ctc_lpa=8.5,fixed_pay_lpa=7.5,variable_pay_lpa=1.0,location="Pune",joining_date=now+timedelta(days=90),status="issued",bond_terms="No bond (demo data)",ppo_status="Not applicable")
            db.add(offer)

        if not db.query(InstitutionPolicy).filter(InstitutionPolicy.organization_id==org.id,InstitutionPolicy.policy_key=="offer-participation").first():
            pol=InstitutionPolicy(organization_id=org.id,policy_key="offer-participation",name="Offer participation policy",description="Demo policy for placement participation",is_active=True); pol.rules={"max_offers_per_student":2,"dream_company_exception":True,"dream_company_min_ctc_lpa":12,"internship_offers_do_not_block":True,"placed_salary_floor_multiplier":1.25}; db.add(pol)

        if not db.query(AttendanceSession).filter(AttendanceSession.organization_id==org.id,AttendanceSession.title=="Acme Pre-Placement Talk").first():
            db.add(AttendanceSession(organization_id=org.id,drive_id=drive.id,title="Acme Pre-Placement Talk",session_type="pre_placement_talk",starts_at=now+timedelta(days=6),closes_at=now+timedelta(days=6,hours=3),token=secrets.token_urlsafe(24),created_by_user_id=tpo.id,is_active=True))

        if not db.query(Announcement).filter(Announcement.organization_id==org.id,Announcement.title=="Acme drive registration closes soon").first():
            ann=Announcement(organization_id=org.id,created_by_user_id=tpo.id,title="Acme drive registration closes soon",body="Eligible students should review their academic profile and complete registration before the deadline.",audience_type="eligible_students",priority="high",starts_at=now,expires_at=drive.registration_deadline); ann.audience_value={"drive_id":drive.id}; db.add(ann)

        thread=db.query(CommunicationThread).filter(CommunicationThread.organization_id==org.id,CommunicationThread.subject=="Acme Graduate Hiring 2026").first()
        if not thread:
            thread=CommunicationThread(organization_id=org.id,recruiter_profile_id=recruiter.id,drive_id=drive.id,subject="Acme Graduate Hiring 2026",created_by_user_id=tpo.id);db.add(thread);db.flush()
        if not db.query(CommunicationMessage).filter(CommunicationMessage.thread_id==thread.id).first():
            db.add(CommunicationMessage(thread_id=thread.id,sender_user_id=tpo.id,message="The campus job is approved. Please confirm assessment and interview slots for the drive."))

        # Resolved incident demonstrates governance without penalising live trust confidence.
        if not db.query(IncidentReport).filter(IncidentReport.organization_id==org.id,IncidentReport.category=="offer_discrepancy_demo").first():
            db.add(IncidentReport(organization_id=org.id,student_id=students[2].id,recruiter_id=recruiter.id,job_id=job.id,category="offer_discrepancy_demo",description="Demo-only resolved incident used to demonstrate confidential placement governance.",status="resolved",confidential=True,resolution_notes="Resolved as demo data."))

        field=db.query(CustomFieldDefinition).filter(CustomFieldDefinition.organization_id==org.id,CustomFieldDefinition.field_key=="university_registration_no").first()
        if not field:
            field=CustomFieldDefinition(organization_id=org.id,entity_type="student",label="University Registration No.",field_key="university_registration_no",field_type="text",required=True);db.add(field);db.flush()
        if not db.query(CustomFieldValue).filter(CustomFieldValue.definition_id==field.id,CustomFieldValue.student_id==students[0].id).first():
            db.add(CustomFieldValue(definition_id=field.id,student_id=students[0].id,value_text="NIT-DEMO-2026-001"))

        if not db.query(ProfileChangeRequest).filter(ProfileChangeRequest.student_id==students[2].id,ProfileChangeRequest.field_name=="cgpa",ProfileChangeRequest.status=="pending").first():
            db.add(ProfileChangeRequest(student_id=students[2].id,organization_id=org.id,field_name="cgpa",old_value="8.1",new_value="8.2",status="pending"))

        for u in [platform,tpo,recruiter_user,*[s.user for s in students]]:
            if not db.query(NotificationPreference).filter(NotificationPreference.user_id==u.id).first():
                db.add(NotificationPreference(user_id=u.id,in_app=True,email=True,whatsapp=False,sms=False,high_priority_only_external=True))

        add_notification_once(db, students[0].user, org, "Technical interview scheduled", "Your Acme Technologies (Demo) Technical Round 1 is scheduled in two days.", "interview", "high", "interviews")
        add_notification_once(db, students[0].user, org, "Drive deadline approaching", "Acme Graduate Hiring registration closes in three days.", "drive", "normal", "drives")
        add_notification_once(db, recruiter_user, org, "Campus opportunity approved", "Northstar Institute approved your Graduate Software Engineer opportunity.", "approval", "normal", "jobs")
        add_notification_once(db, tpo, org, "Profile approval pending", "One student academic profile change is waiting for placement-office review.", "profile", "normal", "approvals")
        add_notification_once(db, platform, None, "Demo tenant active", "Northstar Institute enterprise demo data is ready for product review.", "platform", "normal", None)

        db.commit()
        print("PlaceAI 3.1 demo data ready.")
        print(f"Password for all demo users: {DEMO_PASSWORD}")
        print("Institution admin: tpo@northstar.example.com")
        print("Recruiter: recruiter@acme.example.com")
        print("Student: student@northstar.example.com")
        print("Platform admin: platform@placeai.example.com")
    finally:
        db.close()

if __name__ == "__main__":
    main()
