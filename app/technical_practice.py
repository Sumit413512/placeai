"""Versioned technical practice: local answer keys, private attempts, server clock."""
import json
import secrets
from datetime import timedelta

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint

from app.database import Base
from app.models import generate_uuid, utcnow

VERSION = 'technical-foundations-1'
DURATION_SECONDS = 24 * 60
# Section, prompt, four alternatives, correct index, explanation.
BANK = (
    ('Data & SQL', 'Which clause filters groups after aggregation?', ('WHERE', 'HAVING', 'ORDER BY', 'DISTINCT'), 1, 'WHERE filters input rows; HAVING filters groups after GROUP BY and aggregation.'),
    ('Data & SQL', 'A LEFT JOIN has no matching right-hand row. What happens to the left row?', ('It is removed', 'It remains with NULL right-hand columns', 'The query fails', 'The right table is copied'), 1, 'A LEFT JOIN preserves every left row and supplies NULL values for unmatched right-hand columns.'),
    ('Data & SQL', 'Which property makes a set of database changes all succeed or all fail?', ('Atomicity', 'Sorting', 'Indexing', 'Denormalisation'), 0, 'Atomicity treats a transaction as one unit: commit every change or roll the transaction back.'),
    ('Data & SQL', 'What is a common trade-off of adding a database index?', ('All writes become free', 'Faster matching reads, with extra storage and write maintenance', 'Queries no longer need validation', 'Transactions stop working'), 1, 'An index can speed matching lookups, but consumes storage and must be maintained during writes.'),
    ('Programming & debugging', 'Binary search on a sorted array has which worst-case time complexity?', ('O(1)', 'O(log n)', 'O(n)', 'O(n²)'), 1, 'Each comparison halves the remaining search space, giving logarithmic worst-case time.'),
    ('Programming & debugging', 'A recursive function needs what to terminate reliably?', ('A print statement', 'A reachable base case and progress toward it', 'A global variable', 'Two loops'), 1, 'The base case stops recursion, and every recursive step must move toward that case.'),
    ('Programming & debugging', 'A function accepts non-negative quantities. Which set best tests its lower boundary?', ('100, 200, 300', '-1, 0, 1', 'Only 0', 'Only very large values'), 1, 'Testing just below, at and above the boundary checks rejection, the boundary itself and the first valid positive value.'),
    ('Programming & debugging', 'A service begins returning errors after a release. What is the strongest first investigation?', ('Rewrite every module', 'Correlate error traces and changed code, then reproduce a failing request', 'Disable all validation', 'Increase every timeout'), 1, 'Correlating the failure with changes and reproducing it narrows the cause before a verified fix or rollback.'),
    ('APIs & security', 'How should user-provided SQL values be sent to a database?', ('String concatenation', 'Parameterised queries', 'Removing spaces', 'Client-side escaping only'), 1, 'Bound parameters keep values separate from SQL syntax and prevent values from becoming executable query text.'),
    ('APIs & security', 'Where must access to another user’s private document be checked?', ('Only in the navigation menu', 'On the server for each request', 'Only when signing up', 'In a CSS rule'), 1, 'Every server request must verify the authenticated user and their permission for the requested resource.'),
    ('APIs & security', 'What does idempotency mean for a request?', ('It cannot fail', 'Repeating the same operation has the same intended effect as doing it once', 'It always returns HTTP 200', 'It needs no authentication'), 1, 'An idempotent operation avoids additional intended effects when repeated; response codes can still differ.'),
    ('APIs & security', 'Where should a private AI provider API key be used?', ('In public JavaScript', 'In a server environment secret', 'In an image URL', 'In a public Git file'), 1, 'Server secrets avoid exposing credentials in browser assets, public URLs and source repositories.'),
    ('Systems & delivery', 'How should a web app handle a slow video-generation job?', ('Keep an unbounded web request open', 'Persist a job and process it asynchronously with bounded retries', 'Regenerate on every refresh', 'Discard all errors'), 1, 'A persisted background job survives request timeouts; bounded retries and idempotency prevent duplicate work.'),
    ('Systems & delivery', 'When can a cached response safely contain private student data?', ('When the URL is short', 'When its key and access controls isolate the authorised user', 'Whenever a CDN is available', 'Whenever the response is JSON'), 1, 'Private caches must isolate users and still enforce access rules; a shared public cache can leak data.'),
    ('Systems & delivery', 'A production release passes unit tests. What else best checks the user journey?', ('Only checking the homepage title', 'Testing browser actions through API, persistence and returned UI', 'Removing error handling', 'Skipping permission checks'), 1, 'End-to-end verification checks the boundaries a real user depends on, including saved data and permission failures.'),
    ('Systems & delivery', 'What demonstrates that a backup is useful for recovery?', ('Its filename contains backup', 'A restore has been tested and the restored data verified', 'Its size is non-zero', 'It is stored beside the only database'), 1, 'A verified restore tests whether the backup is readable, complete and usable in the recovery procedure.'),
)


class TechnicalPracticeAttempt(Base):
    __tablename__ = 'technical_practice_attempts'
    __table_args__ = (Index('ix_technical_practice_owner', 'user_id', 'created_at'),
                     UniqueConstraint('user_id', 'request_id', name='uq_technical_practice_request'))
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    request_id = Column(String(36), nullable=False)
    version = Column(String(40), nullable=False, default=VERSION)
    questions_json = Column(Text, nullable=False)
    answers_json = Column(Text, nullable=False, default='{}')
    result_json = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    deadline_at = Column(DateTime, nullable=False, default=lambda: utcnow() + timedelta(seconds=DURATION_SECONDS))


def questions():
    output = []
    for index, (section, prompt, options, correct, explanation) in enumerate(BANK, 1):
        choices = list(options)
        secrets.SystemRandom().shuffle(choices)
        output.append(dict(id=index, section=section, question=prompt, options=choices,
                           correct=choices.index(options[correct]), explanation=explanation))
    return output


def finish(row):
    if row.result_json:
        return json.loads(row.result_json)
    issued, answers = json.loads(row.questions_json), json.loads(row.answers_json)
    reviews = [{**q, 'selected': answers.get(str(q['id'])),
                'earned': int(answers.get(str(q['id'])) == q['correct'])} for q in issued]
    sections = []
    for name in dict.fromkeys(q['section'] for q in issued):
        subset = [q for q in reviews if q['section'] == name]
        sections.append(dict(name=name, correct=sum(q['earned'] for q in subset), total=len(subset)))
    result = dict(version=row.version, correct=sum(q['earned'] for q in reviews), total=len(reviews),
                  score=round(100 * sum(q['earned'] for q in reviews) / len(reviews)),
                  sections=sections, questions=reviews,
                  note='Equal-weight answer-key scoring. No negative marking. This practice score does not change interview readiness or academic eligibility.')
    row.result_json = json.dumps(result)
    return result
