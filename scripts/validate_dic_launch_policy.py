"""Focused launch checks; existing helper blocks all database connections."""
from validate_dic_phase5_policy import main


def graph_check(loader,actual):
    target=('dic','0033_launch_completion')
    prepared=loader.project_state(target)
    for name in ('academicclass','academicassignment','campannouncement','contactenquiry','foundationdonation'):
        if actual.models['dic',name]!=prepared.models['dic',name]:
            raise RuntimeError('Launch model/migration mismatch: '+name)
    if ('dic','0032_phase4_timetables') not in loader.graph.forwards_plan(target):
        raise RuntimeError('Launch migration ordering rejected.')
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.state import ProjectState
    if MigrationAutodetector(loader.project_state(),actual).changes(graph=loader.graph):
        raise RuntimeError('Model/migration drift requires review.')


if __name__=='__main__':
    main(extra_tests=['dic.test_launch_completion.LaunchCompletionPolicyTests',
        'dic.test_timetables.TimetablePolicyTests','dic.test_checkin.CampCheckInTests',
        'dic_movement.tests.MovementPolicyTests','dic.tests.PaystackClientTests'],
        phase_label='Launch completion (no database)',graph_check=graph_check)
