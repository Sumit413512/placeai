"""Private, lease-fenced execution receipts; answers and grading stay immutable."""
import json

from app import assessment_queue
from app.models import MockInterview


class CodeExecutionCheckpoint:
    def __init__(self, sessions, identity):
        self.sessions, self.identity = sessions, identity

    def get(self, key):
        with self.sessions() as db:
            db.info['assessment_lease'] = self.identity
            assessment_queue.assert_lease(db)
            row = db.get(MockInterview, self.identity[0])
            data = json.loads(row.evaluation_json or '{}')
            return data.get('_code_execution', {}).get(key, {})

    def put(self, key, value):
        with self.sessions() as db:
            db.info['assessment_lease'] = self.identity
            assessment_queue.assert_lease(db)
            row = db.query(MockInterview).filter_by(id=self.identity[0]).with_for_update().one()
            if row.overall_score is not None:
                return
            data = json.loads(row.evaluation_json or '{}')
            receipts = data.setdefault('_code_execution', {})
            if key not in receipts and len(receipts) >= 64:
                raise RuntimeError('Execution checkpoint capacity exceeded')
            receipts[key] = value
            row.evaluation_json = json.dumps(data)
            db.commit()
