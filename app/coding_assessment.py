from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import httpx

from app.config import get_settings

LOGGER = logging.getLogger("placeai.coding_assessment")

SUPPORTED_CODING_LANGUAGES = ("python", "java", "cpp", "javascript")
LANGUAGE_LABELS = {
    "python": "Python 3",
    "java": "Java",
    "cpp": "C++",
    "javascript": "JavaScript (Node.js)",
}
_LANGUAGE_PATTERNS = {
    "python": ("Python (3", "Python 3"),
    "java": ("Java (", "OpenJDK"),
    "cpp": ("C++",),
    "javascript": ("JavaScript", "Node.js"),
}
_LANGUAGE_FALLBACK_IDS = {
    "python": 71,
    "java": 62,
    "cpp": 54,
    "javascript": 63,
}
_LANGUAGE_CACHE: dict[str, int] = {}
_LANGUAGE_CACHE_AT = 0.0
_LANGUAGE_CACHE_TTL_SECONDS = 900


def _case(stdin: str, expected: str, *, hidden: bool) -> dict[str, Any]:
    return {"input": stdin, "expected_output": expected, "hidden": hidden}


CODING_CHALLENGE_BANK: tuple[dict[str, Any], ...] = (
    {
        "key": "pair_sum_exists",
        "title": "Pair Sum Exists",
        "question": (
            "Write a program that determines whether any two distinct elements in an integer array "
            "sum to a target value."
        ),
        "problem_statement": (
            "Given n integers and a target T, print YES if there are two values at different indices "
            "whose sum equals T. Otherwise print NO."
        ),
        "input_format": "Line 1: n target\nLine 2: n space-separated integers",
        "output_format": "Print YES or NO.",
        "constraints": ["1 <= n <= 100000", "-10^9 <= value, target <= 10^9"],
        "starter_code": {
            "python": """import sys

def has_pair(nums, target):
    # Write your solution here
    return False

def main():
    data = list(map(int, sys.stdin.read().split()))
    n, target = data[0], data[1]
    nums = data[2:2+n]
    print("YES" if has_pair(nums, target) else "NO")

if __name__ == "__main__":
    main()
""",
            "java": """import java.io.*;
import java.util.*;

public class Main {
    static boolean hasPair(int[] nums, int target) {
        // Write your solution here
        return false;
    }

    public static void main(String[] args) throws Exception {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int target = sc.nextInt();
        int[] nums = new int[n];
        for (int i = 0; i < n; i++) nums[i] = sc.nextInt();
        System.out.println(hasPair(nums, target) ? "YES" : "NO");
    }
}
""",
            "cpp": """#include <bits/stdc++.h>
using namespace std;

bool hasPair(const vector<long long>& nums, long long target) {
    // Write your solution here
    return false;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    long long target;
    cin >> n >> target;
    vector<long long> nums(n);
    for (auto &x : nums) cin >> x;
    cout << (hasPair(nums, target) ? "YES" : "NO") << '\n';
    return 0;
}
""",
            "javascript": """const fs = require('fs');

function hasPair(nums, target) {
  // Write your solution here
  return false;
}

const data = fs.readFileSync(0, 'utf8').trim().split(/\s+/).map(Number);
const n = data[0];
const target = data[1];
const nums = data.slice(2, 2 + n);
console.log(hasPair(nums, target) ? 'YES' : 'NO');
""",
        },
        "test_cases": [
            _case("5 9\n2 7 11 15 1\n", "YES\n", hidden=False),
            _case("4 8\n1 2 3 4\n", "NO\n", hidden=False),
            _case("2 10\n5 5\n", "YES\n", hidden=True),
            _case("1 5\n5\n", "NO\n", hidden=True),
            _case("6 0\n-3 1 2 3 -1 7\n", "YES\n", hidden=True),
            _case("5 -8\n-4 -4 2 6 10\n", "YES\n", hidden=True),
            _case("4 100\n20 30 40 50\n", "NO\n", hidden=True),
            _case("6 7\n1 6 2 5 3 4\n", "YES\n", hidden=True),
        ],
        "ideal_approach": (
            "Use a hash set. For each value x, check whether target - x has already been seen; "
            "then insert x. This runs in O(n) expected time and O(n) space."
        ),
    },
    {
        "key": "first_unique_character",
        "title": "First Unique Character",
        "question": (
            "Write a program that prints the first character in a string that appears exactly once."
        ),
        "problem_statement": (
            "Given one non-empty line of text, print the first character whose total frequency is one. "
            "If no such character exists, print -1. Treat characters as case-sensitive."
        ),
        "input_format": "One line containing the string.",
        "output_format": "Print the first unique character, or -1.",
        "constraints": ["1 <= length <= 100000"],
        "starter_code": {
            "python": """import sys

def first_unique(text):
    # Write your solution here
    return "-1"

text = sys.stdin.readline().rstrip("\n")
print(first_unique(text))
""",
            "java": """import java.io.*;
import java.util.*;

public class Main {
    static String firstUnique(String text) {
        // Write your solution here
        return "-1";
    }

    public static void main(String[] args) throws Exception {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        String text = br.readLine();
        System.out.println(firstUnique(text));
    }
}
""",
            "cpp": """#include <bits/stdc++.h>
using namespace std;

string firstUnique(const string& text) {
    // Write your solution here
    return "-1";
}

int main() {
    string text;
    getline(cin, text);
    cout << firstUnique(text) << '\n';
    return 0;
}
""",
            "javascript": """const fs = require('fs');

function firstUnique(text) {
  // Write your solution here
  return '-1';
}

const text = fs.readFileSync(0, 'utf8').replace(/\r?\n$/, '');
console.log(firstUnique(text));
""",
        },
        "test_cases": [
            _case("swiss\n", "w\n", hidden=False),
            _case("aabbc\n", "c\n", hidden=False),
            _case("aabb\n", "-1\n", hidden=True),
            _case("z\n", "z\n", hidden=True),
            _case("programming\n", "p\n", hidden=True),
            _case("level\n", "v\n", hidden=True),
            _case("aabccdbe\n", "d\n", hidden=True),
            _case("1122334\n", "4\n", hidden=True),
        ],
        "ideal_approach": (
            "Count each character in one pass, then scan the original string from left to right and "
            "return the first character with frequency one. O(n) time and O(k) space."
        ),
    },
    {
        "key": "balanced_brackets",
        "title": "Balanced Brackets",
        "question": (
            "Write a program that checks whether a bracket sequence containing (), [] and {} is balanced."
        ),
        "problem_statement": (
            "A sequence is balanced when every opening bracket is closed by the same type in the correct order. "
            "Print YES for balanced input and NO otherwise."
        ),
        "input_format": "One line containing only bracket characters: ()[]{}",
        "output_format": "Print YES or NO.",
        "constraints": ["1 <= length <= 200000"],
        "starter_code": {
            "python": """import sys

def is_balanced(text):
    # Write your solution here
    return False

text = sys.stdin.readline().strip()
print("YES" if is_balanced(text) else "NO")
""",
            "java": """import java.io.*;
import java.util.*;

public class Main {
    static boolean isBalanced(String text) {
        // Write your solution here
        return false;
    }

    public static void main(String[] args) throws Exception {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        String text = br.readLine().trim();
        System.out.println(isBalanced(text) ? "YES" : "NO");
    }
}
""",
            "cpp": """#include <bits/stdc++.h>
using namespace std;

bool isBalanced(const string& text) {
    // Write your solution here
    return false;
}

int main() {
    string text;
    cin >> text;
    cout << (isBalanced(text) ? "YES" : "NO") << '\n';
    return 0;
}
""",
            "javascript": """const fs = require('fs');

function isBalanced(text) {
  // Write your solution here
  return false;
}

const text = fs.readFileSync(0, 'utf8').trim();
console.log(isBalanced(text) ? 'YES' : 'NO');
""",
        },
        "test_cases": [
            _case("([]{})\n", "YES\n", hidden=False),
            _case("([)]\n", "NO\n", hidden=False),
            _case("()[]{}\n", "YES\n", hidden=True),
            _case("(((())))\n", "YES\n", hidden=True),
            _case("{[()]}\n", "YES\n", hidden=True),
            _case("((\n", "NO\n", hidden=True),
            _case("]\n", "NO\n", hidden=True),
            _case("({[]})[]{}\n", "YES\n", hidden=True),
        ],
        "ideal_approach": (
            "Use a stack. Push opening brackets; for every closing bracket, require the matching opener "
            "at the stack top. The stack must be empty at the end. O(n) time and O(n) space."
        ),
    },
    {
        "key": "longest_consecutive",
        "title": "Longest Consecutive Sequence",
        "question": (
            "Write a program that returns the length of the longest sequence of consecutive integer values."
        ),
        "problem_statement": (
            "Given an unsorted array, find the longest run of values that can be arranged as x, x+1, x+2, ... . "
            "Duplicates do not extend the run."
        ),
        "input_format": "Line 1: n\nLine 2: n space-separated integers",
        "output_format": "Print one integer: the longest consecutive-sequence length.",
        "constraints": ["1 <= n <= 100000", "-10^9 <= value <= 10^9"],
        "starter_code": {
            "python": """import sys

def longest_consecutive(nums):
    # Write your solution here
    return 0

data = list(map(int, sys.stdin.read().split()))
n = data[0]
nums = data[1:1+n]
print(longest_consecutive(nums))
""",
            "java": """import java.io.*;
import java.util.*;

public class Main {
    static int longestConsecutive(int[] nums) {
        // Write your solution here
        return 0;
    }

    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        int[] nums = new int[n];
        for (int i = 0; i < n; i++) nums[i] = sc.nextInt();
        System.out.println(longestConsecutive(nums));
    }
}
""",
            "cpp": """#include <bits/stdc++.h>
using namespace std;

int longestConsecutive(const vector<long long>& nums) {
    // Write your solution here
    return 0;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    vector<long long> nums(n);
    for (auto &x : nums) cin >> x;
    cout << longestConsecutive(nums) << '\n';
    return 0;
}
""",
            "javascript": """const fs = require('fs');

function longestConsecutive(nums) {
  // Write your solution here
  return 0;
}

const data = fs.readFileSync(0, 'utf8').trim().split(/\s+/).map(Number);
const n = data[0];
const nums = data.slice(1, 1 + n);
console.log(longestConsecutive(nums));
""",
        },
        "test_cases": [
            _case("6\n100 4 200 1 3 2\n", "4\n", hidden=False),
            _case("6\n0 3 7 2 5 8\n", "2\n", hidden=False),
            _case("9\n0 3 7 2 5 8 4 6 1\n", "9\n", hidden=True),
            _case("5\n1 2 0 1 3\n", "4\n", hidden=True),
            _case("1\n10\n", "1\n", hidden=True),
            _case("5\n5 5 5 5 5\n", "1\n", hidden=True),
            _case("6\n-2 -1 0 2 3 4\n", "3\n", hidden=True),
            _case("8\n10 11 12 20 21 22 23 24\n", "5\n", hidden=True),
        ],
        "ideal_approach": (
            "Store values in a set. Start a run only from values whose predecessor is absent, then count forward. "
            "This is O(n) expected time and O(n) space."
        ),
    },
)


def choose_coding_challenges(*, seed_value: str, previous_questions: list[str], count: int = 2) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    digest = hashlib.sha256((seed_value or "placeai").encode("utf-8")).digest()
    offset = int.from_bytes(digest[:4], "big") % len(CODING_CHALLENGE_BANK)
    ordered = [
        CODING_CHALLENGE_BANK[(offset + index) % len(CODING_CHALLENGE_BANK)]
        for index in range(len(CODING_CHALLENGE_BANK))
    ]
    previous_norm = {" ".join(str(q).casefold().split()) for q in previous_questions}
    fresh = [
        item for item in ordered
        if " ".join(item["question"].casefold().split()) not in previous_norm
    ]
    selected = (fresh + [item for item in ordered if item not in fresh])[:count]
    return [dict(item) for item in selected]


def public_coding_spec(spec: dict[str, Any]) -> dict[str, Any]:
    tests = spec.get("test_cases") or []
    visible = [
        {
            "index": index + 1,
            "input": str(case.get("input", "")),
            "expected_output": str(case.get("expected_output", "")),
        }
        for index, case in enumerate(tests)
        if not bool(case.get("hidden"))
    ]
    hidden_count = sum(1 for case in tests if bool(case.get("hidden")))
    return {
        "key": spec.get("key"),
        "title": spec.get("title"),
        "problem_statement": spec.get("problem_statement"),
        "input_format": spec.get("input_format"),
        "output_format": spec.get("output_format"),
        "constraints": list(spec.get("constraints") or []),
        "allowed_languages": [
            {"key": key, "label": LANGUAGE_LABELS[key]}
            for key in SUPPORTED_CODING_LANGUAGES
        ],
        "starter_code": {
            key: str((spec.get("starter_code") or {}).get(key, ""))
            for key in SUPPORTED_CODING_LANGUAGES
        },
        "sample_tests": visible,
        "hidden_test_count": hidden_count,
    }


def _headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    token = getattr(settings, "judge0_auth_token", "")
    if token:
        headers["X-Auth-Token"] = token
    return headers


def _judge0_base_url() -> str:
    settings = get_settings()
    return str(getattr(settings, "judge0_base_url", "https://ce.judge0.com")).rstrip("/")


def _language_id(language: str) -> int:
    global _LANGUAGE_CACHE_AT
    language = (language or "").strip().lower()
    if language not in SUPPORTED_CODING_LANGUAGES:
        raise ValueError("Unsupported coding language")

    now = time.time()
    if _LANGUAGE_CACHE and now - _LANGUAGE_CACHE_AT < _LANGUAGE_CACHE_TTL_SECONDS:
        return _LANGUAGE_CACHE[language]

    try:
        response = httpx.get(f"{_judge0_base_url()}/languages", headers=_headers(), timeout=6.0)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            resolved: dict[str, int] = {}
            for key, patterns in _LANGUAGE_PATTERNS.items():
                candidates = [
                    item for item in payload
                    if isinstance(item, dict)
                    and any(pattern.casefold() in str(item.get("name", "")).casefold() for pattern in patterns)
                ]
                if key == "python":
                    candidates = [
                        item for item in candidates
                        if "python (2" not in str(item.get("name", "")).casefold()
                    ]
                if candidates:
                    resolved[key] = max(candidates, key=lambda item: int(item.get("id", 0))).get("id")
            if all(key in resolved for key in SUPPORTED_CODING_LANGUAGES):
                _LANGUAGE_CACHE.clear()
                _LANGUAGE_CACHE.update({key: int(value) for key, value in resolved.items()})
                _LANGUAGE_CACHE_AT = now
                return _LANGUAGE_CACHE[language]
    except Exception as exc:
        LOGGER.warning("Judge0 language discovery failed; using stable fallback IDs error_type=%s", type(exc).__name__)

    _LANGUAGE_CACHE.clear()
    _LANGUAGE_CACHE.update(_LANGUAGE_FALLBACK_IDS)
    _LANGUAGE_CACHE_AT = now
    return _LANGUAGE_CACHE[language]


def _normalize_output(value: str | None) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.strip().split("\n"))


def execute_test_suite(
    *,
    source_code: str,
    language: str,
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = get_settings()
    if not getattr(settings, "coding_execution_enabled", True):
        raise RuntimeError("Coding execution is disabled")
    if not source_code.strip():
        raise ValueError("Source code is required")
    if len(source_code) > 20000:
        raise ValueError("Source code exceeds the 20,000 character limit")
    if not test_cases:
        raise ValueError("No test cases are configured")

    language_id = _language_id(language)
    submissions = [
        {
            "language_id": language_id,
            "source_code": source_code,
            "stdin": str(case.get("input", "")),
            "cpu_time_limit": 2.0,
            "wall_time_limit": 5.0,
            "memory_limit": 128000,
            "max_processes_and_or_threads": 30,
        }
        for case in test_cases
    ]
    started = time.perf_counter()
    response = httpx.post(
        f"{_judge0_base_url()}/submissions/batch?base64_encoded=false",
        headers=_headers(),
        json={"submissions": submissions},
        timeout=10.0,
    )
    response.raise_for_status()
    token_payload = response.json()
    if not isinstance(token_payload, list) or len(token_payload) != len(test_cases):
        raise RuntimeError("Coding execution service returned an invalid submission batch")
    tokens = [str(item.get("token", "")) for item in token_payload if isinstance(item, dict)]
    if len(tokens) != len(test_cases) or any(not token for token in tokens):
        raise RuntimeError("Coding execution service did not return all submission tokens")

    results_payload: list[dict[str, Any]] | None = None
    fields = "token,stdout,stderr,compile_output,message,status,time,memory"
    for _ in range(24):
        time.sleep(0.22)
        poll = httpx.get(
            f"{_judge0_base_url()}/submissions/batch",
            headers=_headers(),
            params={
                "tokens": ",".join(tokens),
                "base64_encoded": "false",
                "fields": fields,
            },
            timeout=8.0,
        )
        poll.raise_for_status()
        body = poll.json()
        rows = body.get("submissions") if isinstance(body, dict) else None
        if not isinstance(rows, list) or len(rows) != len(tokens):
            continue
        pending = False
        for row in rows:
            status = row.get("status") if isinstance(row, dict) else None
            status_id = int((status or {}).get("id", 0) or 0)
            if status_id in {1, 2}:
                pending = True
                break
        if not pending:
            results_payload = rows
            break

    if results_payload is None:
        raise RuntimeError("Coding execution timed out while waiting for the sandbox")

    public_results: list[dict[str, Any]] = []
    passed = 0
    compile_success = True
    first_compile_output = ""
    for index, (case, row) in enumerate(zip(test_cases, results_payload), start=1):
        status = row.get("status") if isinstance(row, dict) else {}
        status_id = int((status or {}).get("id", 0) or 0)
        status_text = str((status or {}).get("description", "Unknown"))
        compile_output = str(row.get("compile_output") or "")[:4000]
        stderr = str(row.get("stderr") or "")[:4000]
        stdout = str(row.get("stdout") or "")[:6000]
        if compile_output and not first_compile_output:
            first_compile_output = compile_output
        if status_id == 6 or "compilation" in status_text.casefold():
            compile_success = False
        case_passed = (
            status_id == 3
            and _normalize_output(stdout) == _normalize_output(str(case.get("expected_output", "")))
        )
        if case_passed:
            passed += 1
        public_results.append({
            "index": index,
            "hidden": bool(case.get("hidden")),
            "passed": case_passed,
            "status": status_text,
            "stdout": stdout,
            "stderr": stderr,
            "compile_output": compile_output,
            "time": row.get("time"),
            "memory": row.get("memory"),
        })

    return {
        "language": language,
        "language_label": LANGUAGE_LABELS[language],
        "compile_success": compile_success,
        "passed": passed,
        "total": len(test_cases),
        "pass_rate": round(100 * passed / len(test_cases)),
        "compile_output": first_compile_output,
        "execution_ms": int((time.perf_counter() - started) * 1000),
        "test_results": public_results,
    }
