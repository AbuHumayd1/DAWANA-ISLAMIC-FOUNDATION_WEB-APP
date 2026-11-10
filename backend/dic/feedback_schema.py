"""Small, age-friendly questions; no participant identifiers in anonymous data."""
QUESTIONS = {
    'daily': {'ratings': {'learning':'Learning about Islam today', 'activities':'Activities today',
        'comfort':'Your room and comfort', 'meals':'Meals and care', 'organisation':'How the day was organised', 'overall':'Your day overall'},
        'comments': {'suggestions':'Anything we could do better? (optional)'}},
    'final': {'ratings': {'overall':'Your camp overall', 'knowledge':'What you learned'},
        'comments': {'beneficial':'What helped you most?', 'improvements':'What could be better?', 'suggestions':'Ideas for the next camp'}, 'recommend':True},
    'staff': {'ratings': {'effectiveness':'Operational effectiveness','coordination':'Scheduling and coordination',
        'participation':'Attendance and participation','facilities':'Facilities and logistics'},
        'comments': {'challenges':'Challenges encountered','recommendations':'Recommendations'}},
    'lecturer': {'ratings': {'organisation':'Session organisation','facilities':'Teaching facilities',
        'engagement':'Participant engagement','time':'Time management','support':'Support from organisers'},
        'comments': {'recommendations':'Recommendations'}},
}
LEGACY_QUESTIONS = QUESTIONS
LEGACY_RATINGS = [(1,'Needs improvement'),(2,'Okay'),(3,'Good')]
QUESTIONS = {**LEGACY_QUESTIONS,
    'daily': {'ratings': {'learning': "Today's classes and learning activities",
        'meals': "Today's meals", 'comfort': 'Accommodation and comfort',
        'organisation': "Today's activities and general organization"},
        'comments': {'suggestions': 'Comments and suggestions (optional)'}},
    'final': {'ratings': {'overall': 'Overall camp experience', 'knowledge': 'Academic classes and lectures',
        'meals': 'Feeding', 'comfort': 'Accommodation and comfort',
        'organisation': 'Camp organization', 'welfare': 'Welfare and care', 'activities': 'Camp activities'},
        'comments': {'suggestions': 'Suggestions for future editions (optional)'}, 'recommend': True}}
RATINGS = [(1,'Very Poor'),(2,'Poor'),(3,'Fair'),(4,'Very Good'),(5,'Excellent')]
CAMP_TIMEZONE = 'Africa/Lagos'


DAILY_V3 = {
    'ratings': {'overall': 'Overall daily experience', 'learning': 'Classes and learning',
        'meals': 'Food and meals', 'comfort': 'Accommodation and facilities',
        'activities': 'Activities and programmes', 'welfare': 'Welfare and camp organisation'},
    'comments': {'suggestions': 'Comments and suggestions (optional)'},
}
DAILY_V3_RATINGS = [(1, 'Poor'), (2, 'Fair'), (3, 'Good'), (4, 'Very Good'), (5, 'Excellent')]


def current_version(channel):
    return 3 if channel == 'daily' else 2


def rating_scale(version):
    if version not in (1, 2, 3):
        raise ValueError('Unknown questionnaire version.')
    return LEGACY_RATINGS if version == 1 else DAILY_V3_RATINGS if version == 3 else RATINGS


def questionnaire(channel, tutor=False, version=2):
    if version not in (1, 2, 3) or (version == 3 and channel != 'daily'):
        raise ValueError('Unknown questionnaire/channel version.')
    source = LEGACY_QUESTIONS if version == 1 else {**QUESTIONS, 'daily': DAILY_V3} if version == 3 else QUESTIONS
    result = {**source[channel], 'ratings': dict(source[channel]['ratings'])}
    if version in (2, 3) and channel in ('daily','final'):
        result['optional_ratings'] = ['comfort']
    if tutor and version in (2, 3):
        result['ratings'].pop('comfort', None)
        result['optional_ratings'] = []
    return result


def participant_questionnaire(channel, tutor=False):
    version = current_version(channel)
    return {**questionnaire(channel, tutor=tutor, version=version),
        'version': version, 'scale': rating_scale(version)}
CATEGORIES = {'health':'Health concern','accommodation':'Accommodation problem','safety':'Safety concern',
    'bullying':'Bullying or mistreatment','assistance':'Request for assistance','other':'Other welfare matter'}
STATUSES = {'new':'Submitted','review':'Under Review','resolved':'Resolved','closed':'Closed'}
PRIVACY_NOTICE = ('Camper answers are stored without identity or a response link in the duplicate ledger. '
    'Do not include names, contacts or identifying details in comments. Server access logs, timing, '
    'database operators or identifying comments may still reveal who submitted. Absolute anonymity is not guaranteed.')
URGENT_NOTICE = 'For urgent health or safety help, contact an available camp welfare officer immediately. This web form is not monitored for instant emergency assistance.'
