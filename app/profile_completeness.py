"""Shared required profile evidence; optional links do not lower completion."""


def profile_completion(profile):
    fields = [('full name', profile.full_name), ('college', profile.college),
              ('degree', profile.degree), ('branch', profile.branch),
              ('graduation year', profile.graduation_year), ('CGPA', profile.cgpa),
              ('phone', profile.phone), ('skills', profile.skills), ('resume', profile.resume)]
    missing = [
        name for name, value in fields
        if value is None or (isinstance(value, str) and not value.strip())
        or (isinstance(value, list) and not any(str(item or '').strip() for item in value))
    ]
    complete_count = len(fields) - len(missing)
    return {
        'percent': round(100 * complete_count / len(fields)),
        'missing': missing,
        'complete_count': complete_count,
        'required_count': len(fields),
    }
