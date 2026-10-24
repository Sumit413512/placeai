"""PlaceAI-authored practice catalog entry; never an official Zensar hiring exam."""
from copy import deepcopy
import secrets

JOB_ID = 'placeai-zensar-practice-v1'
TITLE = 'PlaceAI Zensar Practice Assessment'
COMPANY = 'Zensar — PlaceAI practice'
VERSION = 'zensar-practice-1'
NOTICE = 'PlaceAI-authored preparation only. Not an official Zensar test, recruitment drive or affiliation.'


def is_zensar_practice(job):
    return bool(job and getattr(job, 'id', None) == JOB_ID and getattr(job, 'title', None) == TITLE
                and getattr(job, 'visibility', None) == 'assessment' and getattr(job, 'recruiter', None)
                and job.recruiter.company_name == 'TechNova Solutions — Demo')


def company_label(job):
    return COMPANY if is_zensar_practice(job) else (job.recruiter.company_name if job and job.recruiter else None)


# Original practice items, not copied company papers. Correct answers remain server-side.
OBJECTIVE = {
    'quantitative': [
        ('A team resolves 72 tickets in 6 equal workdays. At the same rate, how many tickets can it resolve in 9 days?', ['96', '108', '112', '120'], '108'),
        ('A service cost falls from 2,500 to 2,000. What is the percentage decrease?', ['15%', '20%', '25%', '30%'], '20%'),
        ('The average of five test scores is 74. What is their total?', ['350', '360', '370', '380'], '370'),
        ('A task uses developers and testers in a 5:3 ratio. If there are 24 people, how many are testers?', ['8', '9', '12', '15'], '9'),
        ('A batch has 240 records and 15% fail validation. How many records pass?', ['195', '200', '204', '210'], '204'),
        ('Two independent jobs take 18 and 24 minutes. Started together, after how many minutes have both finished?', ['18', '21', '24', '42'], '24'),
        ('A product costs 800 before a 10% discount. What is the discounted price?', ['700', '720', '740', '780'], '720'),
        ('A uniformly random integer is chosen from 1 through 10. What is the probability that it is even?', ['1/5', '2/5', '1/2', '3/5'], '1/2'),
    ],
    'logical': [
        ('Complete the sequence: 5, 11, 23, 47, ?', ['83', '94', '95', '97'], '95'),
        ('All production releases require approval. Release R is a production release. What follows?', ['R requires approval', 'R has already been approved', 'R cannot fail', 'Every approval is a release'], 'R requires approval'),
        ('Task A must finish before B; B before C. Which order is valid?', ['C, A, B', 'A, C, B', 'A, B, C', 'B, A, C'], 'A, B, C'),
        ('Exactly one of P and Q is true. P is false. Which statement follows?', ['Q is true', 'Q is false', 'Both are true', 'Neither can be known'], 'Q is true'),
        ('A system sends an alert if and only if a check fails. No alert was sent. What follows?', ['The check passed', 'The alert service is disabled', 'The check failed', 'Every system is healthy'], 'The check passed'),
        ('In a queue, Arun is ahead of Bela and Bela is ahead of Chen. Who is ahead of both other people?', ['Arun', 'Bela', 'Chen', 'Cannot determine'], 'Arun'),
        ('Three distinct tasks X, Y and Z are scheduled. X cannot be last and Y must be before X. Which is valid?', ['X, Y, Z', 'Y, X, Z', 'Z, X, Y', 'X, Z, Y'], 'Y, X, Z'),
        ('A rule says valid records must have an ID. Record K has no ID. What follows?', ['K is invalid under that rule', 'K is a duplicate', 'Every invalid record lacks an ID', 'The rule can be ignored'], 'K is invalid under that rule'),
    ],
    'communication': [
        ('Choose the grammatically correct sentence.', ['The requirements has changed.', 'The requirements have changed.', 'The requirements is changing.', 'The requirements was changed.'], 'The requirements have changed.'),
        ('Which message best communicates a delivery risk?', ['Everything is fine.', 'A dependency is delayed; delivery may slip by one day. I will confirm the recovery plan by 2 PM.', 'It is someone else’s fault.', 'No update.'], 'A dependency is delayed; delivery may slip by one day. I will confirm the recovery plan by 2 PM.'),
        ('A client request is ambiguous. What is the most useful response?', ['Make an undocumented assumption', 'Ask for a concrete example and acceptance criteria', 'Ignore the request', 'Promise every interpretation'], 'Ask for a concrete example and acceptance criteria'),
        ('Which sentence uses a professional, clear tone?', ['You must have broken it.', 'The latest build fails the login check; could we review the change together?', 'This code is hopeless.', 'Not my problem.'], 'The latest build fails the login check; could we review the change together?'),
        ('A useful meeting summary should primarily record:', ['Decisions, owners and next actions', 'Every spoken word without structure', 'Only opinions', 'Only the meeting title'], 'Decisions, owners and next actions'),
        ('Choose the clearest explanation of a technical issue to a non-technical colleague.', ['It is a race condition, obviously.', 'Two updates arrive together and can overwrite one another; we will make saving them orderly.', 'The stack is broken.', 'You would not understand.'], 'Two updates arrive together and can overwrite one another; we will make saving them orderly.'),
    ],
    'technical': [
        ('In object-oriented programming, encapsulation primarily means:', ['Hiding internal state behind a controlled interface', 'Copying every object', 'Removing all methods', 'Using only global variables'], 'Hiding internal state behind a controlled interface'),
        ('Which SQL construct combines rows from related tables based on a condition?', ['JOIN', 'COMMIT', 'GRANT', 'TRUNCATE'], 'JOIN'),
        ('Which database constraint prevents duplicate values and NULLs in the identifying column?', ['PRIMARY KEY', 'DEFAULT', 'ORDER BY', 'OFFSET'], 'PRIMARY KEY'),
        ('Which HTTP status normally indicates that authentication is required or invalid?', ['200', '301', '401', '500'], '401'),
        ('In Java, an interface is primarily used to define:', ['A contract that implementing classes fulfil', 'A database index', 'A process identifier', 'A private network'], 'A contract that implementing classes fulfil'),
        ('Which property lets a database transaction roll back all its changes together?', ['Atomicity', 'Caching', 'Pagination', 'Compilation'], 'Atomicity'),
        ('Which protocol provides encrypted web transport?', ['HTTPS', 'Plain HTTP', 'Unencrypted FTP', 'Telnet'], 'HTTPS'),
        ('Which structure normally provides FIFO behaviour?', ['Queue', 'Stack', 'Unordered set', 'Binary search tree'], 'Queue'),
    ],
    'programming': [
        ('What is printed by: x = 3; repeat twice { x = x * 2 }; print x?', ['6', '9', '12', '18'], '12'),
        ('A loop visits each of N elements once, doing constant work each time. Its time complexity is:', ['O(1)', 'O(log N)', 'O(N)', 'O(N²)'], 'O(N)'),
        ('A non-empty array has N elements indexed from 0. Its final valid index is:', ['N', 'N - 1', 'N + 1', 'Always 0'], 'N - 1'),
        ('Which approach best prevents resource leaks when handling a file?', ['Close it reliably even if an error occurs', 'Keep every file open forever', 'Ignore exceptions', 'Store the path in a global variable'], 'Close it reliably even if an error occurs'),
        ('A value can be absent. Before accessing its fields, code should:', ['Check or handle the absent value', 'Assume it always exists', 'Suppress every error', 'Convert every object to a number'], 'Check or handle the absent value'),
        ('A failing test reproduces a bug. After fixing the cause, the test should:', ['Remain as a regression check', 'Be deleted because it once failed', 'Always be skipped', 'Be changed to accept any output'], 'Remain as a regression check'),
    ],
}

SPOKEN = {
    'resume': [
        'Choose a software project from your own resume. Explain your contribution, one design decision and how you verified the result.',
        'Describe one SQL or data-handling task you personally implemented. Explain its inputs, output and one edge case you tested.',
        'Defend a technical claim on your resume with a concrete example. State what you did yourself and what your team did.',
        'Describe a limitation in one of your projects. How would you improve reliability for a client-facing deployment?',
    ],
    'behavioral': [
        'Describe a time you worked with a teammate whose approach differed from yours. What did you do and what happened?',
        'Give an example of learning an unfamiliar technology to meet a deadline. Explain your plan, actions and result.',
        'Describe a mistake you made in a project. How did you communicate it, correct it and prevent recurrence?',
        'A client changes a requirement close to delivery. Explain how you would assess the impact and agree on next steps.',
    ],
    'role': [
        'For this PlaceAI-authored Zensar preparation scenario, explain how your current software engineering skills fit a client-services project. Use evidence from your own work.',
        'Which skill would you improve before joining a graduate software team, and what concrete practice would demonstrate improvement?',
    ],
    'situational': [
        'A production API returns incorrect data for a small group of users. Explain your immediate containment, investigation and communication plan.',
        'You are asked to deliver a feature with unclear acceptance criteria. Explain how you would clarify scope, test it and communicate remaining risks.',
    ],
}


def build_questions(base_questions):
    """Retain the tested coding execution contract and exact 50-item section structure."""
    items = deepcopy(base_questions)
    offsets = {}
    for number, item in enumerate(items, 1):
        section = item['section']
        offset = offsets.get(section, 0)
        offsets[section] = offset + 1
        if section in OBJECTIVE:
            question, options, correct = OBJECTIVE[section][offset]
            options = list(options)
            secrets.SystemRandom().shuffle(options)
            item.update(question=question, options=options, correct_answer=correct, answer_type='mcq')
        elif section in SPOKEN:
            item.update(question=SPOKEN[section][offset])
        item.update(question_id=number, practice_exam=VERSION)
    if len(items) != 50 or any(offsets.get(key) != len(value) for key, value in OBJECTIVE.items()):
        raise ValueError('Zensar practice requires the complete standardized blueprint')
    return items
