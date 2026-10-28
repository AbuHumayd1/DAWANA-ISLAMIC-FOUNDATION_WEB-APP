"""All safe release regression checks. No database inspection/application."""
from validate_dic_phase5_policy import main as run_policy
from validate_dic_phase6_policy import check_graph


if __name__=='__main__':
    run_policy(extra_tests=[
        'dic.test_release_readiness.ReleaseReadinessTests','dic.test_reporting.ReportingPolicyTests',
        'dic_finance.tests.FinancePolicyTests','dic_movement.tests.MovementPolicyTests',
        'dic.test_checkin.CampCheckInTests','dic.test_house_configuration.FinalHouseConfigurationTests',
        'dic.tests.PaystackClientTests','dic.test_registration_privacy.RegistrationPrivacyPolicyTests',
        'dic.test_tutor_registration.TutorPolicyTests'],phase_label='Phase 7',graph_check=check_graph)
