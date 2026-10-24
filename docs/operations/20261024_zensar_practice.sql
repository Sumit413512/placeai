
INSERT INTO jobs (id,recruiter_id,title,description,location,job_type,experience_required,
                  required_skills_json,preferred_roles_json,is_active,approval_status,visibility,created_at)
SELECT 'placeai-zensar-practice-v1', j.recruiter_id, 'PlaceAI Zensar Practice Assessment',
       'PlaceAI-authored Zensar preparation: aptitude, logical reasoning, communication, Java and OOP, SQL, programming, coding, resume defence and HR. Same 50-question, 10-section proctored blueprint as the TechNova demo. Not an official Zensar exam, recruitment drive or affiliation.',
       'Online practice', 'Practice assessment', 'Graduate practice',
       '["Java","SQL","Object-oriented programming","Problem solving","Debugging","Communication"]',
       '["Graduate Software Engineer"]', true, 'approved', 'assessment', CURRENT_TIMESTAMP
FROM jobs j JOIN recruiter_profiles r ON r.id=j.recruiter_id
WHERE j.title='PlaceAI TechNova Demo Assessment' AND j.visibility='public'
  AND r.company_name='TechNova Solutions — Demo'
ORDER BY j.created_at, j.id LIMIT 1
ON CONFLICT (id) DO NOTHING
;
