"""Shared required profile evidence; optional links do not lower completion."""


def profile_completion(profile):
    fields = [('full name', profile.full_name), ('college', profile.college),
              ('degree', profile.degree), ('branch', profile.branch),
              ('graduation year', profile.graduation_year), ('CGPA', profile.cgpa),
              ('phone', profile.phone), ('skills', profile.skills), ('resume', profile.resume)]
    missing = [name for name, value in fields if value is None or value == '' or value == []]
    return {'percent': round(100 * (len(fields)-len(missing))/len(fields)), 'missing': missing}
