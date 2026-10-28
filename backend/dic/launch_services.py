from django.db import connection
from .models import AcademicClass, AcademicAssignment


def assigned_class(participant_id, edition):
    if not {AcademicClass._meta.db_table, AcademicAssignment._meta.db_table}.issubset(connection.introspection.table_names()):
        return {'status':'pending_setup','name':None,'message':'Academic class setup is pending.'}
    assignment=AcademicAssignment.objects.select_related('academic_class').filter(
        participant_id=participant_id,edition=edition,academic_class__edition=edition,academic_class__active=True).first()
    if assignment:
        return {'status':'assigned','name':assignment.academic_class.name,'message':'Assigned by an authorized camp officer.'}
    return {'status':'unassigned','name':None,'message':'Your academic class has not yet been assigned.'}
