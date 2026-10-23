"""Publication checks apply to both legacy and current lesson media."""


def checks_passed(content):
    return all(content.get(name, {}).get('passed') is True
               for name in ('content_review', 'media_review', 'audiovisual_review'))
