"""One database-free policy/regression cycle. All connection attempts are blocked."""
from validate_dic_phase5_policy import main
from validate_dic_phase6_policy import check_graph as check_phase6_graph


def check_graph(loader, actual):
    check_phase6_graph(loader, actual)
    target = ('dic', '0032_phase4_timetables')
    plan = loader.graph.forwards_plan(target)
    if ('dic', '0031_phase5_feedback_welfare') not in plan:
        raise RuntimeError('Phase 4 must follow the existing Phase 5 leaf.')
    prepared = loader.project_state(target)
    if actual.models['dic', 'timetableentry'] != prepared.models['dic', 'timetableentry']:
        raise RuntimeError('Timetable model/migration mismatch.')
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.state import ProjectState
    changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(__import__('django.apps', fromlist=['apps']).apps)).changes(graph=loader.graph)
    if changes:
        raise RuntimeError('Uncommitted migration model changes: ' + ', '.join(changes))


if __name__ == '__main__':
    main(extra_tests=[
        'dic.test_timetables.TimetablePolicyTests',
        'dic.test_release_readiness.ReleaseReadinessTests', 'dic.test_reporting.ReportingPolicyTests',
        'dic_finance.tests.FinancePolicyTests', 'dic_movement.tests.MovementPolicyTests',
        'dic.test_checkin.CampCheckInTests', 'dic.test_house_configuration.FinalHouseConfigurationTests',
        'dic.tests.PaystackClientTests', 'dic.test_registration_privacy.RegistrationPrivacyPolicyTests',
        'dic.test_tutor_registration.TutorPolicyTests'], phase_label='Phase 4', graph_check=check_graph)
